from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Any, Iterable

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.db.models import PositiveIntegerField
from django.utils import timezone
from djmoney.models.fields import MoneyField
from djmoney.money import Money

from apps.budget.pricing import PricingSnapshot, build_pricing_snapshot, money_from_decimal
from apps.catalog.models.kits import Kit
from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.catalog.price_tracking import record_product_last_used_price
from apps.catalog.product_issues import ProductIssueSummary, annotate_product_issues
from apps.core.infrastructure.kit_prefetch import budget_kit_overrides_prefetch, workorder_kit_overrides_prefetch
from apps.core.infrastructure.models import TimeStampedModel
from apps.finance.models.payment_method import PaymentMethod

if TYPE_CHECKING:
    from apps.workshops.models.review_plans import ReviewPlan

logger = logging.getLogger(__name__)


class WorkOrderItemBenefitType(models.TextChoices):
    NORMAL = "normal", "Normal"
    WARRANTY = "warranty", "Garantia"
    COURTESY = "courtesy", "Cortesia"


class WorkOrderError(Exception):
    pass


class WorkOrderStatus(models.TextChoices):
    DRAFT = "draft", "Aprovado"
    WAITING_COLLABORATOR = "waiting_collaborator", "Aguardando Colaborador"
    WAITING_DELIVERY = "waiting_delivery", "Aguardando Entrega"
    APPROVED = "approved", "Veículo Entregue"
    REJECTED = "rejected", "Reprovado"
    CANCELLED = "cancelled", "Cancelado"


WORKORDER_REOPENABLE_STATUSES = frozenset(
    {
        WorkOrderStatus.APPROVED,
        WorkOrderStatus.REJECTED,
        WorkOrderStatus.CANCELLED,
    }
)

# Work in progress: the O.S. was approved but the vehicle has not been delivered yet.
WORKORDER_OPEN_STATUSES = frozenset(
    {
        WorkOrderStatus.DRAFT,
        WorkOrderStatus.WAITING_COLLABORATOR,
        WorkOrderStatus.WAITING_DELIVERY,
    }
)

# Statuses that already count as revenue for dashboards and DRE.
WORKORDER_REVENUE_STATUSES = frozenset(WORKORDER_OPEN_STATUSES | {WorkOrderStatus.APPROVED})


class WorkOrderSignatureStatus(models.TextChoices):
    NOT_SENT = "not_sent", "Não Enviado"
    SENDING = "sending", "Enviando"
    SENT = "sent", "Enviado"
    FAILED = "failed", "Falha no Envio"
    APPROVED = "approved", "Aprovado"


class WorkOrderDiscountType(models.TextChoices):
    PRODUCTS = "products", "Apenas Produtos"
    SERVICES = "services", "Apenas Serviços"
    BOTH = "both", "Produtos e Serviços"


class WorkOrderWarrantyPlan(models.TextChoices):
    DAYS_30 = "days_30", "30 dias"
    DAYS_90 = "days_90", "90 dias"
    DAYS_180 = "days_180", "180 dias"
    DAYS_365 = "days_365", "365 dias"
    NONE = "none", "Serviço sem garantia"


WARRANTY_PLAN_DAYS: dict[str, int | None] = {
    WorkOrderWarrantyPlan.DAYS_30: 30,
    WorkOrderWarrantyPlan.DAYS_90: 90,
    WorkOrderWarrantyPlan.DAYS_180: 180,
    WorkOrderWarrantyPlan.DAYS_365: 365,
    WorkOrderWarrantyPlan.NONE: None,
}


class WorkOrder(TimeStampedModel):
    workshop = models.ForeignKey("workshops.Workshop", on_delete=models.CASCADE, related_name="workorders")
    budget = models.ForeignKey("budget.Budget", on_delete=models.CASCADE, related_name="workorders", help_text="Orçamento Aprovado vinculado à esta O.S.")
    collaborators = models.ManyToManyField("collaborators.WorkshopCollaborator", verbose_name="Colaboradores", related_name="workorders", blank=True)
    status = models.CharField(verbose_name="Status", max_length=32, choices=WorkOrderStatus.choices, default=WorkOrderStatus.DRAFT)
    current_step = models.PositiveSmallIntegerField(verbose_name="Etapa atual", default=1)
    discount_value = MoneyField(verbose_name="Desconto da O.S. (R$)", max_digits=14, decimal_places=2, default=0.00)
    discount_percentage = models.DecimalField(verbose_name="Desconto da O.S. (%)", max_digits=7, decimal_places=6, default=Decimal("0.00"), validators=[MinValueValidator(0), MaxValueValidator(1)])
    discount_type = models.CharField(verbose_name="Tipo de Desconto", max_length=10, choices=WorkOrderDiscountType.choices, default=WorkOrderDiscountType.BOTH)
    signature_token_version = models.PositiveIntegerField(verbose_name="ID do PDF da Ordem de Serviço", default=1)
    signature_token_active = models.BooleanField(verbose_name="Token de Assinatura Ativo", default=True)
    signature_request_status = models.CharField(max_length=30, choices=WorkOrderSignatureStatus.choices, default=WorkOrderSignatureStatus.NOT_SENT)
    signature_external_id = models.CharField(max_length=255, blank=True, null=True)
    signature_document_id = models.CharField(max_length=255, blank=True, null=True)
    signature_sent_at = models.DateTimeField(blank=True, null=True)
    signature_decline_pending = models.BooleanField(verbose_name="Recusa de assinatura pendente", default=False)
    delivered_at = models.DateTimeField(verbose_name="Data da Entrega", blank=True, null=True)
    warranty_plan = models.CharField(
        verbose_name="Plano de garantia",
        max_length=20,
        choices=WorkOrderWarrantyPlan.choices,
        null=True,
        blank=True,
    )
    unsigned_delivery_reason = models.TextField(verbose_name="Justificativa da entrega sem assinatura", blank=True)
    cancellation_reason = models.TextField(verbose_name="Justificativa do cancelamento", blank=True)
    rejection_reason = models.TextField(verbose_name="Justificativa da rejeicao", blank=True)
    reopen_reason = models.TextField(verbose_name="Justificativa da reabertura", blank=True)
    km_final = models.PositiveIntegerField(verbose_name="KM Final", null=True, blank=True)
    last_oil_change_date = models.DateField(verbose_name="Data da última troca de óleo", null=True, blank=True)
    last_oil_change_km = models.PositiveIntegerField(verbose_name="KM da última troca de óleo", null=True, blank=True)
    review_plan = models.ForeignKey(
        "workshops.ReviewPlan",
        verbose_name="Plano de revisão",
        on_delete=models.SET_NULL,
        related_name="workorders",
        null=True,
        blank=True,
    )
    budget_type = models.CharField(verbose_name="Tipo", max_length=50, choices=[("sale", "Venda"), ("warranty", "Garantia"), ("courtesy", "Cortesia")], default="sale")
    pricing_method = models.CharField(verbose_name="Método de Precificação", max_length=20, choices=[("hunter", "Hunter"), ("traditional", "Tradicional")], null=True, blank=True)
    stored_total_amount = MoneyField(
        verbose_name="Total armazenado da O.S.",
        max_digits=14,
        decimal_places=2,
        default=0.00,
        help_text="Total denormalizado para agregações (dashboard). Atualizado no write path.",
    )
    stored_paid_amount = MoneyField(
        verbose_name="Total pago armazenado da O.S.",
        max_digits=14,
        decimal_places=2,
        default=0.00,
        help_text="Soma denormalizada dos planos de pagamento. Atualizado no write path.",
    )

    def save(self, *args, **kwargs):
        if self.budget_id:
            self.budget_type = self.budget.budget_type
            if not self.pricing_method and self.budget.pricing_method:
                self.pricing_method = self.budget.pricing_method

        is_new = self.pk is None
        if not is_new:
            old = type(self).objects.filter(pk=self.pk).values("status").first()
            old_status = old["status"] if old else None
        else:
            old_status = None

        super().save(*args, **kwargs)

        if not is_new and self.status == WorkOrderStatus.APPROVED and old_status != WorkOrderStatus.APPROVED:
            if not getattr(self, "_skip_stock_consumption_guard", False):
                self._ensure_stock_consumed_on_approve(user=getattr(self, "_consumption_user", None))

    @property
    def public_number(self) -> int:
        return self.get_id

    @property
    def workorder_status_badge(self):
        status_color = {
            WorkOrderStatus.DRAFT: "badge-soft badge-ghost min-w-sm",
            WorkOrderStatus.WAITING_COLLABORATOR: "badge-info min-w-sm",
            WorkOrderStatus.WAITING_DELIVERY: "badge-warning min-w-sm",
            WorkOrderStatus.APPROVED: "badge-success min-w-sm",
            WorkOrderStatus.REJECTED: "badge-error min-w-sm",
            WorkOrderStatus.CANCELLED: "badge-warning min-w-sm",
        }

        status_value = self.status

        try:
            status_enum = WorkOrderStatus(status_value)
            label = str(status_enum.label)
        except ValueError:
            label = str(self.status).replace("_", " ").title()

        return {"text": label, "class": status_color.get(status_value, "badge-ghost")}

    @property
    def type_badge(self):
        if self.budget_type == "warranty":
            return {"text": "Garantia", "class": "badge-error"}
        if self.budget_type == "courtesy":
            return {"text": "Cortesia", "class": "badge-info"}
        return {"text": "Venda", "class": "badge-success"}

    def sync_items_benefit_type_to_budget_type(self) -> int:
        benefit_type = WorkOrderItemBenefitType.NORMAL
        if self.budget_type == "warranty":
            benefit_type = WorkOrderItemBenefitType.WARRANTY
        elif self.budget_type == "courtesy":
            benefit_type = WorkOrderItemBenefitType.COURTESY
        return self.items.exclude(item_benefit_type=benefit_type).update(item_benefit_type=benefit_type)

    def _iter_items(self) -> Iterable["WorkOrderItem"]:
        if not self.pk:
            return ()

        prefetched_items = getattr(self, "_prefetched_objects_cache", {}).get("items")
        if prefetched_items is not None:
            return prefetched_items

        return (
            self.items.select_related("product", "service", "kit")
            .prefetch_related(
                workorder_kit_overrides_prefetch(),
                "kit__kit_products__product",
                "kit__kit_services__service",
            )
            .all()
        )

    def iter_payments(self) -> Iterable["WorkOrderPaymentMethod"]:
        if not self.pk:
            return ()

        prefetched_payments = getattr(self, "_prefetched_objects_cache", {}).get("payments")
        if prefetched_payments is not None:
            return prefetched_payments

        return self.payments.all()

    def _raw_labor_duration(self) -> timedelta:
        total = timedelta(0)
        for item in self._iter_items():
            if item.service and item.duration:
                total += item.duration * item.quantity
                continue

            if not item.kit_id:
                continue

            for override in item._iter_frozen_kit_service_overrides():
                if override.quantity > 0 and override.duration:
                    total += override.duration * override.quantity * item.quantity
        return total

    @property
    def mechanic_hour_cost_value(self) -> Money:
        pricing_context = self.budget.get_frozen_pricing_context()
        salario_mecanicos = pricing_context.productive_salary_total
        horas_uteis_mes = pricing_context.working_hours_per_month
        if not horas_uteis_mes or horas_uteis_mes == 0:
            return Money(0, "BRL")

        return salario_mecanicos / horas_uteis_mes

    @property
    def get_id(self) -> int:
        return self.budget.public_number

    @property
    def total_labor_cost_value(self) -> Money:
        # Dashboard/list total-only paths: with slider==0, labor cost does not change total_budget_value.
        if getattr(self, "_skip_mechanic_labor_cost", False):
            return Money(0, "BRL")
        duracao_em_horas = Decimal(self._raw_labor_duration().total_seconds()) / Decimal(3600)
        return self.mechanic_hour_cost_value * duracao_em_horas

    def _build_pricing_snapshot(self, labor_selling_value_override: Money | None = None) -> PricingSnapshot:
        return build_pricing_snapshot(
            items=list(self._iter_items()),
            slider=int(getattr(self.budget, "slider", 0) or 0),
            discount_value=self.discount_value,
            discount_percentage=self.discount_percentage,
            labor_cost_value=self.total_labor_cost_value,
            labor_selling_value_override=labor_selling_value_override,
        )

    def build_cost_snapshot(self) -> PricingSnapshot:
        """Snapshot including warranty/courtesy items, used to measure real costs."""
        return build_pricing_snapshot(
            items=list(self._iter_items()),
            slider=int(getattr(self.budget, "slider", 0) or 0),
            discount_value=self.discount_value,
            discount_percentage=self.discount_percentage,
            labor_cost_value=self.total_labor_cost_value,
            include_benefit_items=True,
        )

    @property
    def pricing_snapshot(self) -> PricingSnapshot:
        cached_snapshot = getattr(self, "_pricing_snapshot_cache", None)
        if cached_snapshot is None:
            cached_snapshot = self._build_pricing_snapshot()
            setattr(self, "_pricing_snapshot_cache", cached_snapshot)
        return cached_snapshot

    def invalidate_pricing_snapshot_cache(self) -> None:
        if hasattr(self, "_pricing_snapshot_cache"):
            delattr(self, "_pricing_snapshot_cache")
        if hasattr(self, "_product_issue_summary_cache"):
            delattr(self, "_product_issue_summary_cache")

    def refresh_stored_total_amount(self) -> None:
        if self.pk is None:
            return
        if getattr(self, "_skip_stored_total_refresh", False):
            return
        total = self.stored_total_source_value
        type(self).objects.filter(pk=self.pk).update(stored_total_amount=total)
        self.stored_total_amount = total

    def refresh_stored_paid_amount(self) -> None:
        if self.pk is None:
            return
        paid = self.paid_value
        type(self).objects.filter(pk=self.pk).update(stored_paid_amount=paid)
        self.stored_paid_amount = paid

    def refresh_stored_amounts(self) -> None:
        if self.pk is None:
            return
        total = self.stored_total_source_value
        paid = self.paid_value
        type(self).objects.filter(pk=self.pk).update(stored_total_amount=total, stored_paid_amount=paid)
        self.stored_total_amount = total
        self.stored_paid_amount = paid

    @property
    def product_issue_summary(self) -> ProductIssueSummary:
        cached_summary = getattr(self, "_product_issue_summary_cache", None)
        if cached_summary is None:
            # After delivery/cancel/reject, stock was already consumed or will not be used —
            # comparing against current stock would show misleading shortage warnings.
            cached_summary = annotate_product_issues(
                workshop=self.workshop,
                items=self.pricing_snapshot.product_lines,
                check_stock=not self.is_status_locked,
            )
            setattr(self, "_product_issue_summary_cache", cached_summary)
        return cached_summary

    @property
    def has_stock_issues(self) -> bool:
        return self.product_issue_summary.has_stock_issues

    @property
    def has_invalid_ncm_items(self) -> bool:
        return self.product_issue_summary.has_invalid_ncm_issues

    @property
    def paid_value(self) -> Money:
        paid_amount = sum((payment.total_paid.amount for payment in self.iter_payments()), start=Decimal("0.00"))
        return money_from_decimal(paid_amount)

    @property
    def pending_payment_value(self) -> Money:
        total_amount = money_from_decimal(self.total_budget_value.amount).amount
        pending_amount = max(Decimal("0.00"), total_amount - self.paid_value.amount)
        return money_from_decimal(pending_amount)

    @property
    def is_fully_paid(self) -> bool:
        return self.pending_payment_value.amount <= Decimal("0.00")

    @property
    def payment_block_reason(self) -> str | None:
        if self.budget_type in ("warranty", "courtesy"):
            return None
        if self.is_fully_paid:
            return None
        return "Receba o pagamento integral da ordem de serviço antes de enviar para assinatura ou entregar o veículo."

    @property
    def signature_blockers(self) -> list[str]:
        blockers: list[str] = []
        if self.km_final is None:
            blockers.append("É necessário inserir o Km Final para desbloquear o botão.")
        else:
            km_initial = int(getattr(self.budget, "current_km", 0) or 0)
            if self.km_final < km_initial:
                blockers.append(
                    f"O KM final não pode ser menor que o KM inicial ({km_initial:,})."
                    .replace(",", ".")
                )
        payment_reason = self.payment_block_reason
        if payment_reason:
            blockers.append(payment_reason)
        stock_reason = self.product_issue_summary.stock_block_reason()
        if stock_reason:
            blockers.append(stock_reason)
        return blockers

    @property
    def has_signature_blockers(self) -> bool:
        return bool(self.signature_blockers)

    @property
    def is_customer_signature_approved(self) -> bool:
        return self.signature_request_status == WorkOrderSignatureStatus.APPROVED

    @property
    def can_reopen(self) -> bool:
        return self.status in WORKORDER_REOPENABLE_STATUSES

    @property
    def is_status_locked(self) -> bool:
        return self.status in WORKORDER_REOPENABLE_STATUSES

    @property
    def can_change_delivery_status(self) -> bool:
        return self.status == WorkOrderStatus.WAITING_DELIVERY

    @property
    def signature_blockers_display(self) -> str:
        return " ".join(self.signature_blockers)

    @property
    def completion_blockers(self) -> list[str]:
        blockers = list(self.signature_blockers)
        invalid_ncm_reason = self.product_issue_summary.invalid_ncm_block_reason()
        if invalid_ncm_reason:
            blockers.append(invalid_ncm_reason)
        return blockers

    @property
    def has_completion_blockers(self) -> bool:
        return bool(self.completion_blockers)

    @property
    def completion_blockers_display(self) -> str:
        return " ".join(self.completion_blockers)

    def mark_signature_sending(self) -> None:
        self.signature_request_status = WorkOrderSignatureStatus.SENDING
        self.save(update_fields=["signature_request_status"])

    def mark_signature_sent(self, external_id: str, *, document_id: str | None = None) -> None:
        self.signature_request_status = WorkOrderSignatureStatus.SENT
        self.signature_external_id = external_id
        self.signature_document_id = document_id
        self.signature_sent_at = timezone.now()
        self.save(update_fields=["signature_request_status", "signature_external_id", "signature_document_id", "signature_sent_at"])

    def mark_signature_failed(self) -> None:
        self.signature_request_status = WorkOrderSignatureStatus.FAILED
        self.save(update_fields=["signature_request_status"])

    def revoke_signature_token(self) -> None:
        self.signature_token_active = False
        self.save(update_fields=["signature_token_active"])

    def regenerate_signature_token(self) -> None:
        self.signature_token_version += 1
        self.signature_token_active = True
        self.save(update_fields=["signature_token_version", "signature_token_active"])

    def mark_signature_approved(self) -> None:
        if self.signature_request_status == WorkOrderSignatureStatus.APPROVED:
            return
        self.signature_request_status = WorkOrderSignatureStatus.APPROVED
        self.save(update_fields=["signature_request_status"])

    def approve(self) -> None:
        if self.status == WorkOrderStatus.APPROVED:
            return
        self.status = WorkOrderStatus.APPROVED
        self.current_step = max(int(self.current_step or 1), 4)
        if self.pk and not getattr(self, "_skip_stock_consumption_guard", False):
            self._ensure_stock_consumed_on_approve()
        update_fields = ["status", "current_step"]
        if self.delivered_at is None:
            self.delivered_at = timezone.now()
            update_fields.append("delivered_at")
        self.save(update_fields=update_fields)

    def _ensure_stock_consumed_on_approve(self, user: object | None = None) -> None:
        from apps.stock.services.workorder_stock import has_unreversed_exit_movements
        from apps.workorder.approval import approve_workorder_with_stock

        if has_unreversed_exit_movements(workorder=self):
            return

        try:
            approve_workorder_with_stock(workorder=self, user=user)
        except Exception as exc:
            logger.exception(
                "workorder_stock_defensive_guard_failed",
                extra={
                    "workorder_id": self.pk,
                    "error": str(exc),
                },
            )

    def _ensure_no_payments(self, action: str) -> None:
        if self.payments.exists():
            raise WorkOrderError(f"Exclua os planos de pagamento antes de {action} a O.S.")

    def cancel(self, *, reason: str) -> None:
        from apps.stock.services.workorder_stock import return_workorder_stock_to_inventory

        if self.is_status_locked:
            raise WorkOrderError("Reabra a O.S. antes de alterar o status.")

        self._ensure_no_payments("cancelar")
        with transaction.atomic():
            locked_workorder = WorkOrder.objects.select_for_update().get(pk=self.pk)

            locked_workorder.status = WorkOrderStatus.CANCELLED
            locked_workorder.cancellation_reason = reason
            locked_workorder.rejection_reason = ""

            locked_workorder.save(update_fields=["status", "cancellation_reason", "rejection_reason"])

            return_workorder_stock_to_inventory(
                workorder=locked_workorder,
                user=getattr(self, "_consumption_user", None),
                reason="Estoque devolvido por cancelamento da O.S.",
            )

        self.status = WorkOrderStatus.CANCELLED
        self.cancellation_reason = reason
        self.rejection_reason = ""

    def reject(self, *, reason: str) -> None:
        from apps.stock.services.workorder_stock import return_workorder_stock_to_inventory

        if self.is_status_locked:
            raise WorkOrderError("Reabra a O.S. antes de alterar o status.")

        self._ensure_no_payments("reprovar")
        with transaction.atomic():
            locked_workorder = WorkOrder.objects.select_for_update().get(pk=self.pk)

            locked_workorder.status = WorkOrderStatus.REJECTED
            locked_workorder.rejection_reason = reason
            locked_workorder.cancellation_reason = ""

            locked_workorder.save(update_fields=["status", "rejection_reason", "cancellation_reason"])

            return_workorder_stock_to_inventory(
                workorder=locked_workorder,
                user=getattr(self, "_consumption_user", None),
                reason="Estoque devolvido por reprovação da O.S.",
            )

        self.status = WorkOrderStatus.REJECTED
        self.rejection_reason = reason
        self.cancellation_reason = ""

    def reopen(self, *, reason: str) -> None:
        if not self.can_reopen:
            raise WorkOrderError("Somente ordens de serviço entregues, canceladas ou rejeitadas podem ser reabertas.")

        self.status = WorkOrderStatus.WAITING_DELIVERY
        self.current_step = 4
        self.delivered_at = None
        self.reopen_reason = reason

        self.save(update_fields=["status", "current_step", "delivered_at", "reopen_reason"])

    def apply_discount(self, value: Money, percentage: Decimal, discount_type: str | None = None) -> None:
        self.discount_value = value
        self.discount_percentage = percentage
        update_fields = ["discount_value", "discount_percentage"]
        if discount_type is not None:
            self.discount_type = discount_type
            update_fields.append("discount_type")

        self.save(update_fields=update_fields)
        self.invalidate_pricing_snapshot_cache()
        self.refresh_stored_total_amount()

    def set_km_final(self, km_final: int) -> None:
        self.km_final = km_final
        self.save(update_fields=["km_final"])
        self._sync_vehicle_km_from_exit()

    def save_delivery_draft(self, *, cleaned_data: dict[str, Any], posted_fields: set[str]) -> None:
        update_fields: list[str] = []
        sync_km = False

        if "km_final" in posted_fields:
            km_final = cleaned_data.get("km_final")
            self.km_final = int(km_final) if km_final is not None else None
            update_fields.append("km_final")
            sync_km = self.km_final is not None

        if "unsigned_delivery_reason" in posted_fields:
            self.unsigned_delivery_reason = str(cleaned_data.get("unsigned_delivery_reason") or "")
            update_fields.append("unsigned_delivery_reason")

        if "warranty_plan" in posted_fields:
            self.warranty_plan = cleaned_data.get("warranty_plan") or None
            update_fields.append("warranty_plan")

        if "last_oil_change_date" in posted_fields:
            self.last_oil_change_date = cleaned_data.get("last_oil_change_date")
            update_fields.append("last_oil_change_date")

        if "last_oil_change_km" in posted_fields:
            self.last_oil_change_km = cleaned_data.get("last_oil_change_km")
            update_fields.append("last_oil_change_km")

        if "review_plan" in posted_fields:
            self.review_plan = cleaned_data.get("review_plan")
            update_fields.append("review_plan")

        if not update_fields:
            return

        self.save(update_fields=update_fields)
        if sync_km:
            self._sync_vehicle_km_from_exit()

    def set_unsigned_delivery_reason(self, reason: str) -> None:
        self.unsigned_delivery_reason = reason
        self.save(update_fields=["unsigned_delivery_reason"])

    @property
    def warranty_days(self) -> int | None:
        if not self.warranty_plan:
            return None
        return WARRANTY_PLAN_DAYS.get(self.warranty_plan)

    @property
    def warranty_expires_at(self) -> date | None:
        days = self.warranty_days
        if days is None or self.delivered_at is None:
            return None
        delivery_date = timezone.localtime(self.delivered_at).date()
        return delivery_date + timedelta(days=days)

    @property
    def warranty_status_label(self) -> str | None:
        if not self.warranty_plan:
            return None
        if self.warranty_plan == WorkOrderWarrantyPlan.NONE:
            return "Sem garantia"
        if self.delivered_at is None:
            return None
        expires_at = self.warranty_expires_at
        if expires_at is None:
            return None
        if timezone.localdate() <= expires_at:
            return "Em garantia"
        return "Garantia vencida"

    @property
    def warranty_plan_display(self) -> str:
        if not self.warranty_plan:
            return ""
        return WorkOrderWarrantyPlan(self.warranty_plan).label

    def complete_delivery(
        self,
        *,
        km_final: int,
        unsigned_delivery_reason: str = "",
        last_oil_change_date: date | None = None,
        last_oil_change_km: int | None = None,
        review_plan: "ReviewPlan | None" = None,
        warranty_plan: str | None = None,
    ) -> None:
        self.km_final = km_final
        self.unsigned_delivery_reason = unsigned_delivery_reason
        update_fields = ["km_final", "unsigned_delivery_reason"]
        if warranty_plan is not None:
            self.warranty_plan = warranty_plan
            update_fields.append("warranty_plan")
        if last_oil_change_date is not None:
            self.last_oil_change_date = last_oil_change_date
            update_fields.append("last_oil_change_date")
        if last_oil_change_km is not None:
            self.last_oil_change_km = last_oil_change_km
            update_fields.append("last_oil_change_km")
        if review_plan is not None:
            self.review_plan = review_plan
            update_fields.append("review_plan")
        self.save(update_fields=update_fields)
        self._sync_vehicle_km_from_exit()

    def _sync_vehicle_km_from_exit(self) -> None:
        from apps.customer.services.vehicle_km import sync_vehicle_km_from_exit

        budget = getattr(self, "budget", None)
        vehicle = getattr(budget, "vehicle", None) if budget is not None else None
        if vehicle is None:
            return
        sync_vehicle_km_from_exit(vehicle=vehicle, km_final=self.km_final)

    @property
    def total_products_shipping(self) -> Money:
        return self.pricing_snapshot.total_products_shipping

    @property
    def total_services_shipping(self) -> Money:
        return self.pricing_snapshot.total_services_shipping

    @property
    def resolved_discount_percentage(self) -> Decimal:
        return (Decimal(self.discount_percentage or 0) * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @property
    def discount_percentage_display(self) -> str:
        return f"{self.resolved_discount_percentage:.2f}%".replace(".", ",")

    @property
    def total_costs_products_value(self) -> Money:
        return self.pricing_snapshot.total_costs_products_value

    @property
    def total_products_value(self) -> Money:
        return self.pricing_snapshot.total_products_value

    @property
    def total_duration(self) -> timedelta:
        return self.pricing_snapshot.total_duration

    @property
    def total_third_party_services_cost(self) -> Money:
        return self.pricing_snapshot.total_third_party_services_cost

    @property
    def total_third_party_services_selling(self) -> Money:
        return self.pricing_snapshot.total_third_party_services_selling

    @property
    def total_costs_services_value(self) -> Money:
        return self.pricing_snapshot.total_costs_services_value

    @property
    def total_services_value(self) -> Money:
        return self.pricing_snapshot.total_services_value

    @property
    def get_total_products_by_slider(self) -> Money:
        return self.pricing_snapshot.total_products_by_slider

    @property
    def get_total_services_by_slider(self) -> Money:
        return self.pricing_snapshot.total_services_by_slider

    @property
    def get_total_labor_by_slider(self) -> Money:
        return self.pricing_snapshot.total_labor_by_slider

    @property
    def total_duration_display(self) -> str:
        return self._format_duration_display(self.total_duration)

    def _extract_snapshot_values(self, snapshot: PricingSnapshot | None = None) -> dict[str, Any]:
        if snapshot is not None:
            return {
                "total_duration": snapshot.total_duration,
                "total_duration_display": snapshot.total_duration,
                "total_costs_products_value": snapshot.total_costs_products_value,
                "total_products_shipping": snapshot.total_products_shipping,
                "total_third_party_services_cost": snapshot.total_third_party_services_cost,
                "total_products_value": snapshot.total_products_value,
                "total_third_party_services_selling": snapshot.total_third_party_services_selling,
                "total_services_value": snapshot.total_services_value,
            }
        return {
            "total_duration": self.total_duration,
            "total_duration_display": self.total_duration,
            "total_costs_products_value": self.total_costs_products_value,
            "total_products_shipping": self.total_products_shipping,
            "total_third_party_services_cost": self.total_third_party_services_cost,
            "total_products_value": self.total_products_value,
            "total_third_party_services_selling": self.total_third_party_services_selling,
            "total_services_value": self.total_services_value,
        }

    def calculate_pricing_methods(self, snapshot: PricingSnapshot | None = None):
        v = self._extract_snapshot_values(snapshot)
        duracao_total_td = v["total_duration"]
        duracao_total = Decimal(duracao_total_td.total_seconds()) / Decimal(3600)
        duracao_display = self._format_duration_display(duracao_total_td)

        pricing_context = self.budget.get_frozen_pricing_context()
        salario_mecanicos = pricing_context.productive_salary_total
        horas_uteis_mes = pricing_context.working_hours_per_month

        if not horas_uteis_mes or horas_uteis_mes == 0:
            return self._fallback_pricing_data(v, duracao_display)

        custo_pecas = v["total_costs_products_value"]
        custo_frete_pecas = v["total_products_shipping"]
        custo_servico_terceiro = v["total_third_party_services_cost"]
        custo_hora_mecanico = salario_mecanicos / horas_uteis_mes
        custo_total_mao_obra = duracao_total * custo_hora_mecanico

        venda_pecas = v["total_products_value"] - custo_frete_pecas
        venda_servico_terceiro = v["total_third_party_services_selling"]

        divisor_mlo = (custo_pecas + custo_frete_pecas + custo_servico_terceiro + custo_total_mao_obra).amount
        soma_base_orcamento = venda_pecas + custo_frete_pecas + venda_servico_terceiro
        subtracao_base_lucro = custo_pecas + custo_frete_pecas + custo_total_mao_obra + custo_servico_terceiro

        trad_data = self._build_tradicional_method_data(
            pricing_context=pricing_context,
            duracao_total=duracao_total,
            duracao_display=duracao_display,
            custo_pecas=custo_pecas,
            custo_frete_pecas=custo_frete_pecas,
            custo_servico_terceiro=custo_servico_terceiro,
            custo_hora_mecanico=custo_hora_mecanico,
            custo_total_mao_obra=custo_total_mao_obra,
            venda_pecas=venda_pecas,
            venda_servico_terceiro=venda_servico_terceiro,
            soma_base_orcamento=soma_base_orcamento,
            subtracao_base_lucro=subtracao_base_lucro,
            divisor_mlo=divisor_mlo,
        )

        hun_data = self._build_hunter_method_data(
            duracao_display=duracao_display,
            custo_pecas=custo_pecas,
            custo_frete_pecas=custo_frete_pecas,
            custo_servico_terceiro=custo_servico_terceiro,
            custo_hora_mecanico=custo_hora_mecanico,
            custo_total_mao_obra=custo_total_mao_obra,
            venda_pecas=venda_pecas,
            venda_servico_terceiro=venda_servico_terceiro,
            venda_mao_obra_hun=v["total_services_value"] - venda_servico_terceiro,
            soma_base_orcamento=soma_base_orcamento,
            subtracao_base_lucro=subtracao_base_lucro,
            divisor_mlo=divisor_mlo,
        )

        return trad_data if trad_data["rentabilidade"] > hun_data["rentabilidade"] else hun_data

    def _build_tradicional_method_data(
        self,
        *,
        pricing_context,
        duracao_total,
        duracao_display,
        custo_pecas,
        custo_frete_pecas,
        custo_servico_terceiro,
        custo_hora_mecanico,
        custo_total_mao_obra,
        venda_pecas,
        venda_servico_terceiro,
        soma_base_orcamento,
        subtracao_base_lucro,
        divisor_mlo,
    ) -> dict[str, Any]:
        valor_hora_vendida = pricing_context.hourly_cost_value
        venda_mao_obra = valor_hora_vendida * duracao_total
        valor_orcamento = soma_base_orcamento + venda_mao_obra
        lucro_operacional = valor_orcamento - subtracao_base_lucro
        rentabilidade = self._calc_rentabilidade(valor_orcamento, lucro_operacional)
        mlo = self._calc_mlo(divisor_mlo, valor_orcamento)
        return {
            "method_name": "Tradicional",
            "custo_pecas": custo_pecas,
            "custo_frete_pecas": custo_frete_pecas,
            "custo_servico_terceiro": custo_servico_terceiro,
            "custo_hora_mecanico": custo_hora_mecanico,
            "custo_total_mao_obra": custo_total_mao_obra,
            "duracao_total": duracao_display,
            "lucro_operacional": lucro_operacional,
            "mlr": pricing_context.profitability_multiplier,
            "mlo": mlo,
            "venda_pecas": venda_pecas,
            "venda_servico_terceiro": venda_servico_terceiro,
            "venda_mao_obra": venda_mao_obra,
            "rentabilidade": rentabilidade,
            "valor_orcamento": valor_orcamento,
        }

    def _build_hunter_method_data(
        self,
        *,
        duracao_display,
        custo_pecas,
        custo_frete_pecas,
        custo_servico_terceiro,
        custo_hora_mecanico,
        custo_total_mao_obra,
        venda_pecas,
        venda_servico_terceiro,
        venda_mao_obra_hun,
        soma_base_orcamento,
        subtracao_base_lucro,
        divisor_mlo,
    ) -> dict[str, Any]:
        valor_orcamento = soma_base_orcamento + venda_mao_obra_hun
        lucro_operacional = valor_orcamento - subtracao_base_lucro
        rentabilidade = self._calc_rentabilidade(valor_orcamento, lucro_operacional)
        mlo = self._calc_mlo(divisor_mlo, valor_orcamento)
        return {
            "method_name": "Hunter",
            "custo_pecas": custo_pecas,
            "custo_frete_pecas": custo_frete_pecas,
            "custo_servico_terceiro": custo_servico_terceiro,
            "custo_hora_mecanico": custo_hora_mecanico,
            "custo_total_mao_obra": custo_total_mao_obra,
            "duracao_total": duracao_display,
            "lucro_operacional": lucro_operacional,
            "mlr": Decimal("0.00"),
            "venda_pecas": venda_pecas,
            "venda_servico_terceiro": venda_servico_terceiro,
            "venda_mao_obra": venda_mao_obra_hun,
            "rentabilidade": rentabilidade,
            "mlo": mlo,
            "valor_orcamento": valor_orcamento,
        }

    def _calc_rentabilidade(self, valor_orcamento: Money, lucro_operacional: Money) -> Decimal:
        if valor_orcamento.amount > 0:
            return ((lucro_operacional.amount / valor_orcamento.amount) * 100).quantize(Decimal("0.01"), ROUND_HALF_UP)
        return Decimal("0.00")

    def _calc_mlo(self, divisor_mlo: Decimal, valor_orcamento: Money) -> Decimal:
        if divisor_mlo > 0:
            return (valor_orcamento.amount / divisor_mlo).quantize(Decimal("0.01"), ROUND_HALF_UP)
        return Decimal("0.00")

    def _fallback_pricing_data(self, v: dict[str, Any], duracao_display: str) -> dict[str, Any]:
        custo_pecas = v["total_costs_products_value"]
        custo_frete_pecas = v["total_products_shipping"]
        custo_servico_terceiro = v["total_third_party_services_cost"]
        venda_pecas = v["total_products_value"] - custo_frete_pecas
        venda_servico_terceiro = v["total_third_party_services_selling"]
        venda_mao_obra = v["total_services_value"] - venda_servico_terceiro
        valor_orcamento = v["total_products_value"] + v["total_services_value"]
        lucro_operacional = valor_orcamento - (custo_pecas + custo_frete_pecas + custo_servico_terceiro)
        rentabilidade = self._calc_rentabilidade(valor_orcamento, lucro_operacional)
        return {
            "method_name": "Base",
            "custo_pecas": custo_pecas,
            "custo_frete_pecas": custo_frete_pecas,
            "custo_servico_terceiro": custo_servico_terceiro,
            "custo_hora_mecanico": Money(0, "BRL"),
            "custo_total_mao_obra": Money(0, "BRL"),
            "duracao_total": duracao_display,
            "lucro_operacional": lucro_operacional,
            "mlr": Decimal("0.00"),
            "venda_pecas": venda_pecas,
            "venda_servico_terceiro": venda_servico_terceiro,
            "venda_mao_obra": venda_mao_obra,
            "rentabilidade": rentabilidade,
            "mlo": Decimal("0.00"),
            "valor_orcamento": valor_orcamento,
        }

    @staticmethod
    def _format_duration_display(duration: timedelta) -> str:
        if not duration:
            return "00h 00m"
        ts = int(duration.total_seconds())
        return f"{ts // 3600:02d}h {(ts % 3600) // 60:02d}m"

    @property
    def total_base_value(self) -> Money:
        return self.pricing_snapshot.total_base_value

    @property
    def total_budget_value(self) -> Money:
        return self.pricing_snapshot.total_budget_value

    @property
    def is_fixed_budget(self) -> bool:
        if self.budget_type == "sale" and self.budget_id:
            linked_budget_type = self.budget.budget_type
            if linked_budget_type in ("warranty", "courtesy"):
                return True
        return self.budget_type in ("warranty", "courtesy")

    @property
    def operational_total_value(self) -> Money:
        """Catalog face total including warranty/courtesy items (for listings)."""
        total = Money(0, "BRL")
        for item in self._iter_items():
            total += item.total_price
        return total

    @property
    def stored_total_source_value(self) -> Money:
        """Canonical value persisted into ``stored_total_amount``."""
        if self.is_fixed_budget:
            return self.operational_total_value
        return self.total_budget_value

    @property
    def display_total_budget_value(self) -> Money:
        if self.is_fixed_budget:
            return self.operational_total_value
        return self.total_budget_value

    @property
    def display_total_base_value(self) -> Money:
        if self.is_fixed_budget:
            return self.operational_total_value
        return self.total_base_value

    @property
    def resolved_discount_value(self) -> Money:
        return self.pricing_snapshot.resolved_discount_value

    def sync_from_budget(self) -> None:
        """Sync work order items from the linked budget, freezing all prices.

        Deletes all existing items and recreates them from budget items,
        copying frozen prices, descriptions, overrides, and quantities.
        After sync, all kit items are marked as kit_snapshot_frozen = True.
        """
        from apps.finance.services.workorder_financial_movements import sync_workorder_financial_movement

        budget_items = list(
            self.budget.items.select_related("product", "service", "kit")
            .prefetch_related(
                budget_kit_overrides_prefetch(),
                "kit__kit_products__product",
                "kit__kit_services__service",
            )
            .order_by("id")
        )

        with transaction.atomic():
            self.items.all().delete()

            workorder_items = WorkOrderItem.objects.bulk_create(
                [
                    WorkOrderItem(
                        workshop=self.workshop,
                        workorder=self,
                        product=budget_item.product,
                        service=budget_item.service,
                        kit=budget_item.kit,
                        description=budget_item.description,
                        quantity=budget_item.quantity,
                        is_customer_supplied=budget_item.is_customer_supplied,
                        shipping=budget_item.shipping,
                        product_cost_price=budget_item.product_cost_price,
                        product_selling_price=budget_item.product_selling_price,
                        service_cost_price=budget_item.service_cost_price,
                        service_selling_price=budget_item.service_selling_price,
                        service_shipping=budget_item.service_shipping,
                        duration=budget_item.duration,
                        item_benefit_type=budget_item.item_benefit_type,
                    )
                    for budget_item in budget_items
                ]
            )

            budget_to_workorder_item = {budget_item.id: workorder_item for budget_item, workorder_item in zip(budget_items, workorder_items, strict=False)}

            overrides_to_create: list[WorkOrderKitItemOverride] = []
            for budget_item in budget_items:
                mapped_item = budget_to_workorder_item.get(budget_item.id)
                if mapped_item is None:
                    continue

                for override in budget_item.kit_overrides.all():
                    overrides_to_create.append(
                        WorkOrderKitItemOverride(
                            workshop=self.workshop,
                            workorder_item=mapped_item,
                            product=override.product,
                            service=override.service,
                            quantity=override.quantity,
                            product_cost_price=override.product_cost_price,
                            product_selling_price=override.product_selling_price,
                            shipping=override.shipping,
                            service_cost_price=override.service_cost_price,
                            service_selling_price=override.service_selling_price,
                            duration=override.duration,
                        )
                    )

            if overrides_to_create:
                WorkOrderKitItemOverride.objects.bulk_create(overrides_to_create)

            kit_item_ids = [item.id for item in workorder_items if item.kit_id]
            if kit_item_ids:
                WorkOrderItem.objects.filter(id__in=kit_item_ids).update(kit_snapshot_frozen=True)

            self.discount_value = self.budget.resolved_discount_value
            self.discount_percentage = self.budget.resolved_discount_percentage
            self.discount_type = self.budget.discount_type
            self.budget_type = self.budget.budget_type
            self.save(update_fields=["discount_value", "discount_percentage", "discount_type", "budget_type"])

            collaborator_ids = list(self.budget.collaborators.values_list("id", flat=True))
            if not collaborator_ids and self.budget.collaborator_id:
                collaborator_ids = [self.budget.collaborator_id]
            self.collaborators.set(collaborator_ids)

            self.invalidate_pricing_snapshot_cache()
            self.refresh_stored_amounts()

            sync_workorder_financial_movement(workorder=self)

    class Meta:
        verbose_name = "Ordem de Serviço"
        verbose_name_plural = "Ordens de Serviço"
        permissions = [
            ("reopen_workorder", "Can Reopen Ordem de Serviço"),
        ]
        indexes = [
            models.Index(fields=["workshop", "status", "delivered_at"], name="workorder_ws_status_deliv_idx"),
            models.Index(fields=["workshop", "status", "criado_em"], name="workorder_ws_status_criado_idx"),
        ]

    def __str__(self):
        return f"OS #{self.get_id} | WorkOrder #{self.id}"


class WorkOrderPaymentMethod(TimeStampedModel):
    workorder = models.ForeignKey(WorkOrder, on_delete=models.CASCADE, related_name="payments")
    payment_method = models.ForeignKey(PaymentMethod, on_delete=models.PROTECT, verbose_name="Forma de Pagamento", null=True, blank=True)
    installments_count = PositiveIntegerField(verbose_name="Número de Parcelas", default=1)
    first_installment_amount = MoneyField(verbose_name="Valor da Primeira Parcela", max_digits=14, decimal_places=2, default=0.00)
    remaining_installments_amount = MoneyField(verbose_name="Valor das Parcelas Restantes", max_digits=14, decimal_places=2, default=0.00)
    due_date = models.DateField(verbose_name="Vencimento", default=timezone.localdate)
    movement_group = models.ForeignKey("finance.MovementGroup", on_delete=models.SET_NULL, null=True, blank=True, related_name="workorder_payments")

    class Meta:
        verbose_name = "Plano de Pagamento"
        verbose_name_plural = "Planos de Pagamento"
        indexes = [
            models.Index(fields=["due_date", "workorder"], name="wo_payment_due_wo_idx"),
        ]

    @property
    def total_paid(self) -> Money:
        return money_from_decimal(self.first_installment_amount.amount + ((self.installments_count - 1) * self.remaining_installments_amount.amount))

    def __str__(self):
        return f"Plano de Pagamento #{self.id} - {self.payment_method}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.workorder_id:
            self.workorder.refresh_stored_paid_amount()

    def delete(self, *args, **kwargs):
        workorder = self.workorder if self.workorder_id else None
        result = super().delete(*args, **kwargs)
        if workorder is not None:
            workorder.refresh_stored_paid_amount()
        return result


class WorkOrderAttachment(TimeStampedModel):
    workorder = models.ForeignKey(WorkOrder, on_delete=models.CASCADE, related_name="attachments")
    content = models.BinaryField(null=True, blank=True)
    content_name = models.CharField(max_length=100, null=True, blank=True)
    content_type = models.CharField(max_length=100, null=True, blank=True)

    class Meta:
        verbose_name = "Imagem da OS"
        verbose_name_plural = "Imagens da OS"

    def __str__(self):
        return f"Image #{self.id} from Work Order : {self.workorder}"


class WorkOrderItem(TimeStampedModel):
    """An item (product, service, or kit) within a WorkOrder.

    --- Freeze (congelamento) rule ---
    On creation, all relevant catalog data is COPIED (frozen) into this item:
    - Product: cost_price, selling_price, description
    - Service: cost_price, selling_price, duration, description
    - Kit: ensure_kit_snapshot() creates WorkOrderKitItemOverride records for
      EVERY kit component, freezing each product and service individually.

    After creation, changes to the catalog do NOT affect this item.
    The only ways to update frozen data are:
    1. Manual editing via WorkOrderKitEditView
    2. Re-sync from the linked budget via sync_from_budget()
    """

    workshop = models.ForeignKey("workshops.Workshop", on_delete=models.CASCADE, related_name="workorder_items")
    workorder = models.ForeignKey(WorkOrder, on_delete=models.CASCADE, related_name="items")

    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)
    service = models.ForeignKey(Service, on_delete=models.SET_NULL, null=True, blank=True)
    kit = models.ForeignKey(Kit, on_delete=models.SET_NULL, null=True, blank=True)

    description = models.CharField(verbose_name="Descrição", max_length=100, default="")
    quantity = models.PositiveIntegerField(verbose_name="Quantidade", default=1)
    is_customer_supplied = models.BooleanField(verbose_name="Peça fornecida pelo cliente", default=False)

    shipping = MoneyField(verbose_name="Frete", max_digits=14, decimal_places=2, default=0)
    product_cost_price = MoneyField(verbose_name="Custo", max_digits=14, decimal_places=2, default=0)
    product_selling_price = MoneyField(verbose_name="Valor de Venda", max_digits=14, decimal_places=2, default=0)

    service_cost_price = MoneyField(verbose_name="Custo", max_digits=14, decimal_places=2, default=0)
    service_selling_price = MoneyField(verbose_name="Valor de Venda", max_digits=14, decimal_places=2, default=0)
    service_shipping = MoneyField(verbose_name="Frete do Serviço", max_digits=14, decimal_places=2, default=0)
    duration = models.DurationField(verbose_name="Duração", null=True, blank=True)
    kit_snapshot_frozen = models.BooleanField(verbose_name="Kit snapshot frozen", default=False)
    item_benefit_type = models.CharField(
        verbose_name="Tipo de Benefício",
        max_length=20,
        choices=WorkOrderItemBenefitType.choices,
        default=WorkOrderItemBenefitType.NORMAL,
    )

    def _clear_kit_snapshot_caches(self) -> None:
        for cache_name in ("_kit_override_maps_cache", "_kit_unit_totals_cache"):
            if hasattr(self, cache_name):
                delattr(self, cache_name)

    def ensure_kit_snapshot(self) -> None:
        """Freeze all kit components by creating WorkOrderKitItemOverride records.

        Iterates every product and service in the kit and creates/updates
        an override record with the current catalog prices. Once created,
        the snapshot is marked as frozen so this method is idempotent.

        Called automatically on first save() and defensively from any method
        that reads kit overrides (_get_kit_override_maps, _iter_frozen_kit_*).
        """
        if not self.pk or not self.kit_id or self.kit_snapshot_frozen:
            return

        existing_overrides = list(self.kit_overrides.select_related("product", "service").all())
        product_overrides = {ov.product_id: ov for ov in existing_overrides if ov.product_id}
        service_overrides = {ov.service_id: ov for ov in existing_overrides if ov.service_id}

        with transaction.atomic():
            for kit_product in self.kit.kit_products.select_related("product").all():
                override = product_overrides.get(kit_product.product_id)
                WorkOrderKitItemOverride.objects.update_or_create(
                    workshop=self.workshop,
                    workorder_item=self,
                    product=kit_product.product,
                    defaults={
                        "quantity": override.quantity if override else kit_product.quantity,
                        "product_cost_price": override.product_cost_price if override else kit_product.product.cost_price,
                        "product_selling_price": override.product_selling_price if override else kit_product.product.selling_price,
                        "shipping": override.shipping if override else Money(0, "BRL"),
                    },
                )

            for kit_service in self.kit.kit_services.select_related("service").all():
                override = service_overrides.get(kit_service.service_id)
                default_cost = kit_service.resolved_cost_price
                default_sell = kit_service.resolved_selling_price
                WorkOrderKitItemOverride.objects.update_or_create(
                    workshop=self.workshop,
                    workorder_item=self,
                    service=kit_service.service,
                    defaults={
                        "quantity": override.quantity if override else kit_service.quantity,
                        "service_cost_price": override.service_cost_price if override else default_cost,
                        "service_selling_price": override.service_selling_price if override else default_sell,
                        "duration": override.duration if override else (kit_service.duration or timedelta()),
                    },
                )

            WorkOrderItem.objects.filter(pk=self.pk, kit_snapshot_frozen=False).update(kit_snapshot_frozen=True)

        self.kit_snapshot_frozen = True
        self._clear_kit_snapshot_caches()
        self.refresh_kit_snapshot_totals()

    def refresh_kit_snapshot_totals(self) -> None:
        """Recalculate aggregate price fields from current override records.

        Updates product_selling_price, product_cost_price, service_selling_price,
        service_cost_price, and duration on this item to match the sum of its
        frozen override records. Called after ensure_kit_snapshot().
        """
        if not self.pk or not self.kit_id:
            return

        self._clear_kit_snapshot_caches()

        product_cost_total = Money(0, "BRL")
        product_selling_total = Money(0, "BRL")
        service_cost_total = Money(0, "BRL")
        service_selling_total = Money(0, "BRL")
        total_duration = timedelta()

        for override in self._iter_frozen_kit_product_overrides():
            if override.quantity <= 0:
                continue
            product_cost_total += override.product_cost_price * override.quantity
            product_selling_total += override.product_selling_price * override.quantity

        for override in self._iter_frozen_kit_service_overrides():
            if override.quantity <= 0:
                continue
            service_cost_total += override.service_cost_price * override.quantity
            service_selling_total += override.service_selling_price * override.quantity
            if override.duration:
                total_duration += override.duration * override.quantity

        WorkOrderItem.objects.filter(pk=self.pk).update(
            product_cost_price=product_cost_total,
            product_selling_price=product_selling_total,
            service_cost_price=service_cost_total,
            service_selling_price=service_selling_total,
            duration=total_duration,
        )

        self.product_cost_price = product_cost_total
        self.product_selling_price = product_selling_total
        self.service_cost_price = service_cost_total
        self.service_selling_price = service_selling_total
        self.duration = total_duration

    def save(self, *args, **kwargs):
        if not self.pk:
            if self.product:
                self.product_cost_price = self.product.cost_price
                self.product_selling_price = self.product.selling_price
                self.description = self.product.name

            elif self.service:
                self.service_cost_price = self.service.suggested_cost or Money(0, "BRL")
                self.service_selling_price = self.service.selling_price
                self.service_shipping = self.service.shipping or Money(0, "BRL")
                self.duration = self.service.duration
                self.description = self.service.name

            elif self.kit:
                self.product_selling_price = sum((kp.product.selling_price * kp.quantity for kp in self.kit.kit_products.all()), Money(0, "BRL"))
                self.service_selling_price = sum((ks.resolved_selling_price * ks.quantity for ks in self.kit.kit_services.all()), Money(0, "BRL"))

                self.product_cost_price = sum((kp.product.cost_price * kp.quantity for kp in self.kit.kit_products.all()), Money(0, "BRL"))
                self.service_cost_price = sum((ks.service.suggested_cost * ks.quantity for ks in self.kit.kit_services.all() if ks.service.suggested_cost), Money(0, "BRL"))

                self.duration = sum((ks.service.duration for ks in self.kit.kit_services.all()), timedelta())
                self.description = self.kit.name

            budget_type = getattr(self.workorder, "budget_type", "sale") if self.workorder_id else "sale"
            if budget_type == "warranty":
                self.item_benefit_type = WorkOrderItemBenefitType.WARRANTY
            elif budget_type == "courtesy":
                self.item_benefit_type = WorkOrderItemBenefitType.COURTESY
            else:
                self.item_benefit_type = WorkOrderItemBenefitType.NORMAL

        super().save(*args, **kwargs)

        if self.kit_id and not self.kit_snapshot_frozen:
            self.ensure_kit_snapshot()

        self.workorder.invalidate_pricing_snapshot_cache()
        if not getattr(self.workorder, "_skip_stored_total_refresh", False):
            self.workorder.refresh_stored_total_amount()

        if self.product_id and not self.is_customer_supplied:
            record_product_last_used_price(product=self.product, price=self.product_selling_price)

    def delete(self, *args, **kwargs):
        workorder = self.workorder if self.workorder_id else None
        result = super().delete(*args, **kwargs)
        if workorder is not None and not getattr(workorder, "_skip_stored_total_refresh", False):
            workorder.invalidate_pricing_snapshot_cache()
            workorder.refresh_stored_total_amount()
        return result

    @property
    def item_type(self) -> str:
        if self.product_id:
            return "product"
        if self.service_id:
            return "service"
        if self.kit_id:
            return "kit"
        return "unknown"

    @property
    def duration_display(self):
        if not self.duration:
            return "00h 00m"

        total_seconds = int(self.duration.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60

        return f"{hours:02d}h {minutes:02d}m"

    def _cached_kit_overrides(self) -> list["WorkOrderKitItemOverride"]:
        """Return kit overrides using prefetch cache when available (no write-on-read)."""
        prefetched = getattr(self, "_prefetched_objects_cache", {}).get("kit_overrides")
        if prefetched is not None:
            return list(prefetched)

        cached = getattr(self, "_kit_overrides_list_cache", None)
        if cached is not None:
            return cached

        cached = list(self.kit_overrides.all())
        setattr(self, "_kit_overrides_list_cache", cached)
        return cached

    def _iter_frozen_kit_product_overrides(self):
        """Yield non-zero-quantity product overrides without ensure_kit_snapshot on read."""
        if not self.kit_id:
            return
        for override in self._cached_kit_overrides():
            if override.product_id and override.quantity > 0:
                yield override

    def _iter_frozen_kit_service_overrides(self):
        """Yield non-zero-quantity service overrides without ensure_kit_snapshot on read."""
        if not self.kit_id:
            return
        for override in self._cached_kit_overrides():
            if override.service_id and override.quantity > 0:
                yield override

    def _get_kit_override_maps(self) -> tuple[dict[int, "WorkOrderKitItemOverride"], dict[int, "WorkOrderKitItemOverride"]]:
        """Return (product_overrides, service_overrides) dicts keyed by component ID."""
        cache = getattr(self, "_kit_override_maps_cache", None)
        if cache is not None:
            return cache

        product_overrides: dict[int, "WorkOrderKitItemOverride"] = {}
        service_overrides: dict[int, "WorkOrderKitItemOverride"] = {}

        for override in self._cached_kit_overrides():
            if override.product_id:
                product_overrides[override.product_id] = override
            if override.service_id:
                service_overrides[override.service_id] = override

        cache = (product_overrides, service_overrides)
        setattr(self, "_kit_override_maps_cache", cache)
        return cache

    def _iter_kit_products(self):
        if not self.kit:
            return ()

        prefetched = getattr(self.kit, "_prefetched_objects_cache", {}).get("kit_products")
        if prefetched is not None:
            return prefetched

        return self.kit.kit_products.select_related("product").all()

    def _iter_kit_services(self):
        if not self.kit:
            return ()

        prefetched = getattr(self.kit, "_prefetched_objects_cache", {}).get("kit_services")
        if prefetched is not None:
            return prefetched

        return self.kit.kit_services.select_related("service").all()

    @property
    def effective_kit_products(self) -> list[dict[str, Any]]:
        if not self.kit:
            return []

        products: list[dict[str, Any]] = []

        for override in self._iter_frozen_kit_product_overrides():
            products.append({"id": override.product_id, "name": override.product.name, "quantity": override.quantity})

        return products

    @property
    def effective_kit_services(self) -> list[dict[str, Any]]:
        if not self.kit:
            return []

        services: list[dict[str, Any]] = []

        for override in self._iter_frozen_kit_service_overrides():
            services.append({"id": override.service_id, "name": override.service.name, "quantity": override.quantity})

        return services

    @property
    def effective_kit_products_count(self) -> int:
        return len(self.effective_kit_products)

    @property
    def effective_kit_services_count(self) -> int:
        return len(self.effective_kit_services)

    @property
    def total_price(self):
        if self.kit:
            return self.get_kit_total_with_overrides()
        shipping_total = self.shipping + self.service_shipping
        return ((self.product_selling_price + self.service_selling_price) * self.quantity) + shipping_total

    def get_kit_total_with_overrides(self):
        if not self.kit:
            return Money(0, "BRL")
        return (self.get_kit_products_total() + self.get_kit_services_total()) * self.quantity

    def get_kit_products_total(self):
        if not self.kit:
            return Money(0, "BRL")
        return sum((ov.product_selling_price * ov.quantity) + ov.shipping for ov in self._iter_frozen_kit_product_overrides()) * self.quantity

    def get_kit_services_total(self):
        if not self.kit:
            return Money(0, "BRL")
        return sum(ov.service_selling_price * ov.quantity for ov in self._iter_frozen_kit_service_overrides()) * self.quantity

    def get_kit_services_duration(self):
        if not self.kit:
            return timedelta(0)
        return sum((ov.duration * ov.quantity) for ov in self._iter_frozen_kit_service_overrides() if ov.duration) * self.quantity

    def get_kit_products_shipping_total(self):
        if not self.kit:
            return Money(0, "BRL")
        return sum(ov.shipping for ov in self._iter_frozen_kit_product_overrides() if ov.quantity > 0) * self.quantity

    def get_kit_products_cost_total(self):
        if not self.kit:
            return Money(0, "BRL")
        return sum(ov.product_cost_price * ov.quantity for ov in self._iter_frozen_kit_product_overrides()) * self.quantity

    def get_kit_services_cost_total(self):
        if not self.kit:
            return Money(0, "BRL")
        return sum(ov.service_cost_price * ov.quantity for ov in self._iter_frozen_kit_service_overrides()) * self.quantity

    def get_kit_third_party_services_cost_total(self):
        if not self.kit:
            return Money(0, "BRL")
        return sum(ov.service_cost_price * ov.quantity for ov in self._iter_frozen_kit_service_overrides() if ov.service and ov.service.is_third_party) * self.quantity

    def get_kit_third_party_services_selling_total(self):
        if not self.kit:
            return Money(0, "BRL")
        return sum(ov.service_selling_price * ov.quantity for ov in self._iter_frozen_kit_service_overrides() if ov.service and ov.service.is_third_party) * self.quantity

    class Meta:
        verbose_name = "Item da O.S."
        verbose_name_plural = "Itens da O.S."

    def __str__(self):
        return f"Item #{self.id} da O.S. #{self.workorder_id}"


class WorkOrderKitItemOverride(TimeStampedModel):
    workshop = models.ForeignKey("workshops.Workshop", on_delete=models.CASCADE, related_name="workorder_kit_overrides")
    workorder_item = models.ForeignKey(WorkOrderItem, on_delete=models.CASCADE, related_name="kit_overrides")

    product = models.ForeignKey(Product, null=True, blank=True, on_delete=models.CASCADE)
    service = models.ForeignKey(Service, null=True, blank=True, on_delete=models.CASCADE)

    quantity = models.IntegerField(verbose_name="Quantidade", default=1, validators=[MinValueValidator(0)])

    product_cost_price = MoneyField(verbose_name="Custo do Produto", max_digits=14, decimal_places=2, default=0, default_currency="BRL")
    product_selling_price = MoneyField(verbose_name="Preço de Venda do Produto", max_digits=14, decimal_places=2, default=0, default_currency="BRL")
    shipping = MoneyField(verbose_name="Frete", max_digits=14, decimal_places=2, default=0, default_currency="BRL")

    service_cost_price = MoneyField(verbose_name="Custo do Serviço", max_digits=14, decimal_places=2, default=0, default_currency="BRL")
    service_selling_price = MoneyField(verbose_name="Preço de Venda do Serviço", max_digits=14, decimal_places=2, default=0, default_currency="BRL")
    duration = models.DurationField(verbose_name="Duração", null=True, blank=True)

    class Meta:
        verbose_name = "Override de Item do Kit da O.S."
        verbose_name_plural = "Overrides de Itens do Kit da O.S."
        constraints = [
            models.UniqueConstraint(fields=["workorder_item", "product"], condition=models.Q(product__isnull=False), name="unique_workorder_kit_product"),
            models.UniqueConstraint(fields=["workorder_item", "service"], condition=models.Q(service__isnull=False), name="unique_workorder_kit_service"),
        ]

    def __str__(self):
        if self.product:
            return f"Override O.S.: {self.product.name} - WorkOrder #{self.workorder_item.workorder_id}"
        if self.service:
            return f"Override O.S.: {self.service.name} - WorkOrder #{self.workorder_item.workorder_id}"
        return f"Override O.S. #{self.id}"


class WorkOrderHistory(TimeStampedModel):
    class Action(models.TextChoices):
        REOPENED = "reopened", "O.S. reaberta"

    workorder = models.ForeignKey("workorder.WorkOrder", on_delete=models.CASCADE, related_name="history_entries")
    user = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, related_name="workorder_history_entries", null=True, blank=True)
    action = models.CharField(verbose_name="Ação", max_length=30, choices=Action.choices)
    reason = models.TextField(verbose_name="Justificativa", blank=True)

    class Meta:
        verbose_name = "Histórico da O.S."
        verbose_name_plural = "Histórico das O.S."
        ordering = ["-criado_em", "-pk"]

    def __str__(self) -> str:
        return f"{self.get_action_display()} - O.S. #{self.workorder.get_id}"
