from __future__ import annotations

from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Iterable

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.db.models import PositiveIntegerField
from django.utils import timezone
from djmoney.models.fields import MoneyField
from djmoney.money import Money

from apps.budget.pricing import PricingSnapshot, build_pricing_snapshot
from apps.catalog.models.kits import Kit
from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.catalog.price_tracking import record_product_last_used_price
from apps.catalog.product_issues import ProductIssueSummary, annotate_product_issues
from apps.core.models import TimeStampedModel
from apps.finance.models.payment_method import PaymentMethod


class WorkOrderStatus(models.TextChoices):
    DRAFT = "draft", "Aprovado"
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


class WorkOrderSignatureStatus(models.TextChoices):
    NOT_SENT = "not_sent", "Não Enviado"
    SENDING = "sending", "Enviando"
    SENT = "sent", "Enviado"
    FAILED = "failed", "Falha no Envio"
    APPROVED = "approved", "Aprovado"


class WorkOrder(TimeStampedModel):
    workshop = models.ForeignKey("workshops.Workshop", on_delete=models.CASCADE, related_name="workorders")
    budget = models.ForeignKey("budget.Budget", on_delete=models.CASCADE, related_name="workorders", help_text="Orçamento Aprovado vinculado à esta O.S.")
    collaborators = models.ManyToManyField("collaborators.WorkshopCollaborator", verbose_name="Colaboradores", related_name="workorders", blank=True)
    status = models.CharField(verbose_name="Status", max_length=20, choices=WorkOrderStatus.choices, default=WorkOrderStatus.DRAFT)
    discount_value = MoneyField(verbose_name="Desconto da O.S. (R$)", max_digits=14, decimal_places=2, default=0.00)
    discount_percentage = models.DecimalField(verbose_name="Desconto da O.S. (%)", max_digits=7, decimal_places=6, default=Decimal("0.00"), validators=[MinValueValidator(0), MaxValueValidator(1)])
    signature_token_version = models.PositiveIntegerField(verbose_name="ID do PDF da Ordem de Serviço", default=1)
    signature_token_active = models.BooleanField(verbose_name="Token de Assinatura Ativo", default=True)
    signature_request_status = models.CharField(max_length=30, choices=WorkOrderSignatureStatus.choices, default=WorkOrderSignatureStatus.NOT_SENT)
    signature_external_id = models.CharField(max_length=255, blank=True, null=True)
    signature_document_id = models.CharField(max_length=255, blank=True, null=True)
    signature_sent_at = models.DateTimeField(blank=True, null=True)
    delivered_at = models.DateTimeField(verbose_name="Data da Entrega", blank=True, null=True)
    unsigned_delivery_reason = models.TextField(verbose_name="Justificativa da entrega sem assinatura", blank=True)
    cancellation_reason = models.TextField(verbose_name="Justificativa do cancelamento", blank=True)
    rejection_reason = models.TextField(verbose_name="Justificativa da rejeicao", blank=True)
    reopen_reason = models.TextField(verbose_name="Justificativa da reabertura", blank=True)
    km_final = models.PositiveIntegerField(verbose_name="KM Final", null=True, blank=True)
    budget_type = models.CharField(verbose_name="Tipo", max_length=50, choices=[("sale", "Venda"), ("warranty", "Garantia"), ("courtesy", "Cortesia")], default="sale")

    def save(self, *args, **kwargs):
        if self.budget_id and self.budget_id:
            self.budget_type = self.budget.budget_type
        super().save(*args, **kwargs)

    @property
    def public_number(self) -> int:
        return self.get_id

    @property
    def workorder_status_badge(self):
        status_color = {
            WorkOrderStatus.DRAFT: "badge-soft badge-ghost min-w-sm",
            WorkOrderStatus.APPROVED: "badge-success min-w-sm",
            WorkOrderStatus.REJECTED: "badge-error min-w-sm",
            WorkOrderStatus.CANCELLED: "badge-warning min-w-sm",
        }

        return {"text": WorkOrderStatus(self.status).label, "class": status_color.get(self.status, "badge-ghost")}

    @property
    def type_badge(self):
        if self.budget_type == "warranty":
            return {"text": "Garantia", "class": "badge-error"}
        if self.budget_type == "courtesy":
            return {"text": "Cortesia", "class": "badge-info"}
        return {"text": "Venda", "class": "badge-success"}

    def _iter_items(self) -> Iterable["WorkOrderItem"]:
        if not self.pk:
            return ()

        prefetched_items = getattr(self, "_prefetched_objects_cache", {}).get("items")
        if prefetched_items is not None:
            return prefetched_items

        return (
            self.items.select_related("product", "service", "kit")
            .prefetch_related(
                "kit_overrides",
                "kit__kit_products__product",
                "kit__kit_services__service",
            )
            .all()
        )

    def _iter_payments(self) -> Iterable["WorkOrderPaymentMethod"]:
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
                if item.service.is_third_party:
                    continue
                total += item.duration * item.quantity
                continue

            if not item.kit:
                continue

            _, service_overrides = item._get_kit_override_maps()
            for kit_service in item._iter_kit_services():
                if kit_service.service.is_third_party:
                    continue

                override = service_overrides.get(kit_service.service_id)
                if override:
                    if override.quantity > 0 and override.duration:
                        total += override.duration * override.quantity * item.quantity
                elif kit_service.quantity > 0 and kit_service.service.duration:
                    total += kit_service.service.duration * kit_service.quantity * item.quantity
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
        return self.budget.pk

    @property
    def total_labor_cost_value(self) -> Money:
        duracao_em_horas = Decimal(self._raw_labor_duration().total_seconds()) / Decimal(3600)
        return self.mechanic_hour_cost_value * duracao_em_horas

    @property
    def pricing_snapshot(self) -> PricingSnapshot:
        cached_snapshot = getattr(self, "_pricing_snapshot_cache", None)
        if cached_snapshot is None:
            cached_snapshot = build_pricing_snapshot(
                items=list(self._iter_items()),
                slider=int(getattr(self.budget, "slider", 0) or 0),
                discount_value=self.discount_value,
                labor_cost_value=self.total_labor_cost_value,
            )
            setattr(self, "_pricing_snapshot_cache", cached_snapshot)

            pricing_method_data = self.calculate_pricing_methods()
            labor_selling_value_override = pricing_method_data.get("venda_mao_obra") if pricing_method_data.get("method_name") == "Tradicional" else None
            if isinstance(labor_selling_value_override, Money):
                cached_snapshot = build_pricing_snapshot(
                    items=list(self._iter_items()),
                    slider=int(getattr(self.budget, "slider", 0) or 0),
                    discount_value=self.discount_value,
                    labor_cost_value=self.total_labor_cost_value,
                    labor_selling_value_override=labor_selling_value_override,
                )
            setattr(self, "_pricing_snapshot_cache", cached_snapshot)
        return cached_snapshot

    def invalidate_pricing_snapshot_cache(self) -> None:
        if hasattr(self, "_pricing_snapshot_cache"):
            delattr(self, "_pricing_snapshot_cache")
        if hasattr(self, "_product_issue_summary_cache"):
            delattr(self, "_product_issue_summary_cache")

    @property
    def product_issue_summary(self) -> ProductIssueSummary:
        cached_summary = getattr(self, "_product_issue_summary_cache", None)
        if cached_summary is None:
            cached_summary = annotate_product_issues(workshop=self.workshop, items=self.pricing_snapshot.product_lines)
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
        paid_amount = sum((payment.total_paid.amount for payment in self._iter_payments()), start=Decimal("0.00"))
        return Money(paid_amount, "BRL")

    @property
    def pending_payment_value(self) -> Money:
        pending_amount = max(Decimal("0.00"), self.total_budget_value.amount - self.paid_value.amount)
        return Money(pending_amount, "BRL")

    @property
    def is_fully_paid(self) -> bool:
        return self.pending_payment_value.amount <= Decimal("0.00")

    @property
    def payment_block_reason(self) -> str | None:
        if self.is_fully_paid:
            return None
        return "Receba o pagamento integral da ordem de serviço antes de enviar para assinatura ou entregar o veículo."

    @property
    def signature_blockers(self) -> list[str]:
        blockers: list[str] = []
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
        self.signature_request_status = WorkOrderSignatureStatus.APPROVED
        if not self.is_fully_paid:
            self.save(update_fields=["signature_request_status"])
            return
        self.status = WorkOrderStatus.APPROVED
        if self.delivered_at is None:
            self.delivered_at = timezone.now()
            self.save(update_fields=["status", "signature_request_status", "delivered_at"])
            return
        self.save(update_fields=["status", "signature_request_status"])

    @property
    def total_products_shipping(self) -> Money:
        return self.pricing_snapshot.total_products_shipping

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
        total_td = self.total_duration
        if not total_td:
            return "00h 00m"

        ts = int(total_td.total_seconds())
        return f"{ts // 3600:02d}h {(ts % 3600) // 60:02d}m"

    def calculate_pricing_methods(self):
        fallback_data = self._build_pricing_fallback_data()
        pricing_context = self.budget.get_frozen_pricing_context()
        salario_mecanicos = pricing_context.productive_salary_total
        mlr = pricing_context.profitability_multiplier
        duracao_total = Decimal(self.total_duration.total_seconds()) / Decimal(3600)
        horas_uteis_mes = pricing_context.working_hours_per_month

        if not horas_uteis_mes or horas_uteis_mes == 0:
            return fallback_data

        custo_pecas = self.total_costs_products_value
        custo_frete_pecas = self.total_products_shipping
        custo_servico_terceiro = self.total_third_party_services_cost
        custo_hora_mecanico = salario_mecanicos / horas_uteis_mes
        custo_total_mao_obra = duracao_total * custo_hora_mecanico

        venda_pecas = self.total_products_value - custo_frete_pecas
        venda_servico_terceiro = self.total_third_party_services_selling

        divisor_mlo = (custo_pecas + custo_frete_pecas + custo_servico_terceiro + custo_total_mao_obra).amount
        soma_base_orcamento = venda_pecas + custo_frete_pecas + venda_servico_terceiro
        subtracao_base_lucro = custo_pecas + custo_frete_pecas + custo_total_mao_obra + custo_servico_terceiro

        valor_hora_vendida_trad = pricing_context.hourly_cost_value
        venda_mao_obra_trad = valor_hora_vendida_trad * duracao_total
        valor_orcamento_trad = soma_base_orcamento + venda_mao_obra_trad
        lucro_operacional_trad = valor_orcamento_trad - subtracao_base_lucro
        if valor_orcamento_trad.amount > 0:
            rentabilidade_trad = ((lucro_operacional_trad.amount / valor_orcamento_trad.amount) * 100).quantize(Decimal("0.01"), ROUND_HALF_UP)
        else:
            rentabilidade_trad = Decimal("0.00")

        venda_mao_obra_hun = self.total_services_value - venda_servico_terceiro
        valor_orcamento_hun = soma_base_orcamento + venda_mao_obra_hun
        mlo = valor_orcamento_hun.amount / divisor_mlo if divisor_mlo > 0 else 0
        lucro_operacional_hun = valor_orcamento_hun - subtracao_base_lucro
        if valor_orcamento_hun.amount > 0:
            rentabilidade_hun = ((lucro_operacional_hun.amount / valor_orcamento_hun.amount) * 100).quantize(Decimal("0.01"), ROUND_HALF_UP)
        else:
            rentabilidade_hun = Decimal("0.00")

        data_trad = {
            "method_name": "Tradicional",
            "custo_pecas": custo_pecas,
            "custo_frete_pecas": custo_frete_pecas,
            "custo_servico_terceiro": custo_servico_terceiro,
            "custo_hora_mecanico": custo_hora_mecanico,
            "custo_total_mao_obra": custo_total_mao_obra,
            "duracao_total": self.total_duration_display,
            "lucro_operacional": lucro_operacional_trad,
            "mlr": mlr,
            "mlo": mlo,
            "venda_pecas": venda_pecas,
            "venda_servico_terceiro": venda_servico_terceiro,
            "venda_mao_obra": venda_mao_obra_trad,
            "rentabilidade": rentabilidade_trad,
            "valor_orcamento": valor_orcamento_trad,
        }

        data_hun = {
            "method_name": "Hunter",
            "custo_pecas": custo_pecas,
            "custo_frete_pecas": custo_frete_pecas,
            "custo_servico_terceiro": custo_servico_terceiro,
            "custo_hora_mecanico": custo_hora_mecanico,
            "custo_total_mao_obra": custo_total_mao_obra,
            "duracao_total": self.total_duration_display,
            "lucro_operacional": lucro_operacional_hun,
            "mlr": mlr,
            "venda_pecas": venda_pecas,
            "venda_servico_terceiro": venda_servico_terceiro,
            "venda_mao_obra": venda_mao_obra_hun,
            "rentabilidade": rentabilidade_hun,
            "mlo": mlo,
            "valor_orcamento": valor_orcamento_hun,
        }

        return data_trad if rentabilidade_trad > rentabilidade_hun else data_hun

    def _build_pricing_fallback_data(self) -> dict[str, Any]:
        custo_pecas = self.total_costs_products_value
        custo_frete_pecas = self.total_products_shipping
        custo_servico_terceiro = self.total_third_party_services_cost
        custo_hora_mecanico = Money(0, "BRL")
        custo_total_mao_obra = Money(0, "BRL")

        venda_pecas = self.total_products_value - custo_frete_pecas
        venda_servico_terceiro = self.total_third_party_services_selling
        venda_mao_obra = self.total_services_value - venda_servico_terceiro
        valor_orcamento = self.total_products_value + self.total_services_value
        lucro_operacional = valor_orcamento - (custo_pecas + custo_frete_pecas + custo_total_mao_obra + custo_servico_terceiro)

        if valor_orcamento.amount > 0:
            rentabilidade = ((lucro_operacional.amount / valor_orcamento.amount) * 100).quantize(Decimal("0.01"), ROUND_HALF_UP)
        else:
            rentabilidade = Decimal("0.00")

        return {
            "method_name": "Base",
            "custo_pecas": custo_pecas,
            "custo_frete_pecas": custo_frete_pecas,
            "custo_servico_terceiro": custo_servico_terceiro,
            "custo_hora_mecanico": custo_hora_mecanico,
            "custo_total_mao_obra": custo_total_mao_obra,
            "duracao_total": self.total_duration_display,
            "lucro_operacional": lucro_operacional,
            "mlr": Decimal("0.00"),
            "venda_pecas": venda_pecas,
            "venda_servico_terceiro": venda_servico_terceiro,
            "venda_mao_obra": venda_mao_obra,
            "rentabilidade": rentabilidade,
            "mlo": Decimal("0.00"),
            "valor_orcamento": valor_orcamento,
        }

    @property
    def total_base_value(self) -> Money:
        return self.pricing_snapshot.total_base_value

    @property
    def total_budget_value(self) -> Money:
        return self.pricing_snapshot.total_budget_value

    def sync_from_budget(self) -> None:
        from apps.finance.services.workorder_financial_movements import sync_workorder_financial_movement

        budget_items = list(
            self.budget.items.select_related("product", "service", "kit")
            .prefetch_related(
                "kit_overrides",
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
                        shipping=budget_item.shipping,
                        product_cost_price=budget_item.product_cost_price,
                        product_selling_price=budget_item.product_selling_price,
                        service_cost_price=budget_item.service_cost_price,
                        service_selling_price=budget_item.service_selling_price,
                        duration=budget_item.duration,
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

            self.discount_value = self.budget.resolved_discount_value
            self.discount_percentage = self.budget.resolved_discount_percentage
            self.save(update_fields=["discount_value", "discount_percentage"])

            collaborator_ids = list(self.budget.collaborators.values_list("id", flat=True))
            if not collaborator_ids and self.budget.collaborator_id:
                collaborator_ids = [self.budget.collaborator_id]
            self.collaborators.set(collaborator_ids)

            self.invalidate_pricing_snapshot_cache()

            sync_workorder_financial_movement(workorder=self)

    class Meta:
        verbose_name = "Ordem de Serviço"
        verbose_name_plural = "Ordens de Serviço"
        permissions = [
            ("reopen_workorder", "Can Reopen Ordem de Serviço"),
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

    @property
    def total_paid(self) -> Money:
        return Money(self.first_installment_amount.amount + ((self.installments_count - 1) * self.remaining_installments_amount.amount), "BRL")

    def __str__(self):
        return f"Plano de Pagamento #{self.id} - {self.payment_method}"


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
    workshop = models.ForeignKey("workshops.Workshop", on_delete=models.CASCADE, related_name="workorder_items")
    workorder = models.ForeignKey(WorkOrder, on_delete=models.CASCADE, related_name="items")

    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)
    service = models.ForeignKey(Service, on_delete=models.SET_NULL, null=True, blank=True)
    kit = models.ForeignKey(Kit, on_delete=models.SET_NULL, null=True, blank=True)

    description = models.CharField(verbose_name="Descrição", max_length=100, default="")
    quantity = models.PositiveIntegerField(verbose_name="Quantidade", default=1)

    shipping = MoneyField(verbose_name="Frete", max_digits=14, decimal_places=2, default=0)
    product_cost_price = MoneyField(verbose_name="Custo", max_digits=14, decimal_places=2, default=0)
    product_selling_price = MoneyField(verbose_name="Valor de Venda", max_digits=14, decimal_places=2, default=0)

    service_cost_price = MoneyField(verbose_name="Custo", max_digits=14, decimal_places=2, default=0)
    service_selling_price = MoneyField(verbose_name="Valor de Venda", max_digits=14, decimal_places=2, default=0)
    duration = models.DurationField(verbose_name="Duração", null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.pk:
            if self.product:
                self.product_cost_price = self.product.cost_price
                self.product_selling_price = self.product.selling_price
                self.description = self.product.name

            elif self.service:
                self.service_cost_price = self.service.suggested_cost or Money(0, "BRL")
                self.service_selling_price = self.service.selling_price
                self.duration = self.service.duration
                self.description = self.service.name

            elif self.kit:
                self.product_selling_price = sum((kp.product.selling_price * kp.quantity for kp in self.kit.kit_products.all()), Money(0, "BRL"))
                self.service_selling_price = sum((ks.resolved_selling_price * ks.quantity for ks in self.kit.kit_services.all()), Money(0, "BRL"))

                self.product_cost_price = sum((kp.product.cost_price * kp.quantity for kp in self.kit.kit_products.all()), Money(0, "BRL"))
                self.service_cost_price = sum((ks.service.suggested_cost * ks.quantity for ks in self.kit.kit_services.all() if ks.service.suggested_cost), Money(0, "BRL"))

                self.duration = sum((ks.service.duration for ks in self.kit.kit_services.all()), timedelta())
                self.description = self.kit.name

        super().save(*args, **kwargs)

        self.workorder.invalidate_pricing_snapshot_cache()

        if self.product_id:
            record_product_last_used_price(product=self.product, price=self.product_selling_price)

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

    def _get_kit_override_maps(self) -> tuple[dict[int, "WorkOrderKitItemOverride"], dict[int, "WorkOrderKitItemOverride"]]:
        cache = getattr(self, "_kit_override_maps_cache", None)
        if cache is not None:
            return cache

        product_overrides: dict[int, "WorkOrderKitItemOverride"] = {}
        service_overrides: dict[int, "WorkOrderKitItemOverride"] = {}

        for override in self.kit_overrides.all():
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

        product_overrides, _ = self._get_kit_override_maps()
        products: list[dict[str, Any]] = []

        for kit_product in self._iter_kit_products():
            override = product_overrides.get(kit_product.product_id)
            quantity = override.quantity if override else kit_product.quantity
            if quantity <= 0:
                continue

            products.append({"id": kit_product.product_id, "name": kit_product.product.name, "quantity": quantity})

        return products

    @property
    def effective_kit_services(self) -> list[dict[str, Any]]:
        if not self.kit:
            return []

        _, service_overrides = self._get_kit_override_maps()
        services: list[dict[str, Any]] = []

        for kit_service in self._iter_kit_services():
            override = service_overrides.get(kit_service.service_id)
            quantity = override.quantity if override else kit_service.quantity
            if quantity <= 0:
                continue

            services.append({"id": kit_service.service_id, "name": kit_service.service.name, "quantity": quantity})

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
        return ((self.product_selling_price + self.service_selling_price) * self.quantity) + self.shipping

    def get_kit_total_with_overrides(self):
        if not self.kit:
            return Money(0, "BRL")

        total_produtos = Money(0, "BRL")
        total_servicos = Money(0, "BRL")
        product_overrides, service_overrides = self._get_kit_override_maps()

        for kit_product in self._iter_kit_products():
            override = product_overrides.get(kit_product.product_id)
            if override:
                if override.quantity <= 0:
                    produto_subtotal = Money(0, "BRL")
                else:
                    produto_subtotal = (override.product_selling_price * override.quantity) + override.shipping
            elif kit_product.quantity > 0:
                produto_subtotal = (kit_product.product.selling_price * kit_product.quantity) + Money(0, "BRL")
            else:
                produto_subtotal = Money(0, "BRL")
            total_produtos += produto_subtotal

        for kit_service in self._iter_kit_services():
            override = service_overrides.get(kit_service.service_id)
            if override:
                if override.quantity <= 0:
                    servico_subtotal = Money(0, "BRL")
                else:
                    servico_subtotal = override.service_selling_price * override.quantity
            elif kit_service.quantity > 0:
                servico_subtotal = kit_service.resolved_selling_price * kit_service.quantity
            else:
                servico_subtotal = Money(0, "BRL")
            total_servicos += servico_subtotal

        total_kit = total_produtos + total_servicos

        return total_kit * self.quantity

    def get_kit_products_total(self):
        if not self.kit:
            return Money(0, "BRL")

        total_produtos = Money(0, "BRL")
        product_overrides, _ = self._get_kit_override_maps()
        for kit_product in self._iter_kit_products():
            override = product_overrides.get(kit_product.product_id)
            if override:
                if override.quantity <= 0:
                    produto_subtotal = Money(0, "BRL")
                else:
                    produto_subtotal = (override.product_selling_price * override.quantity) + override.shipping
            elif kit_product.quantity > 0:
                produto_subtotal = (kit_product.product.selling_price * kit_product.quantity) + Money(0, "BRL")
            else:
                produto_subtotal = Money(0, "BRL")
            total_produtos += produto_subtotal

        return total_produtos * self.quantity

    def get_kit_services_total(self):
        if not self.kit:
            return Money(0, "BRL")

        total_servicos = Money(0, "BRL")
        _, service_overrides = self._get_kit_override_maps()
        for kit_service in self._iter_kit_services():
            override = service_overrides.get(kit_service.service_id)
            if override:
                if override.quantity <= 0:
                    servico_subtotal = Money(0, "BRL")
                else:
                    servico_subtotal = override.service_selling_price * override.quantity
            elif kit_service.quantity > 0:
                servico_subtotal = kit_service.resolved_selling_price * kit_service.quantity
            else:
                servico_subtotal = Money(0, "BRL")
            total_servicos += servico_subtotal

        return total_servicos * self.quantity

    def get_kit_services_duration(self):
        if not self.kit:
            return timedelta(0)

        total_duration = timedelta(0)
        _, service_overrides = self._get_kit_override_maps()
        for kit_service in self._iter_kit_services():
            override = service_overrides.get(kit_service.service_id)
            if override:
                if override.quantity > 0 and override.duration:
                    total_duration += override.duration * override.quantity
            elif kit_service.quantity > 0 and kit_service.service.duration:
                total_duration += kit_service.service.duration * kit_service.quantity

        return total_duration * self.quantity

    def get_kit_products_shipping_total(self):
        if not self.kit:
            return Money(0, "BRL")

        total_shipping = Money(0, "BRL")
        product_overrides, _ = self._get_kit_override_maps()
        for kit_product in self._iter_kit_products():
            override = product_overrides.get(kit_product.product_id)
            if override and override.quantity > 0:
                total_shipping += override.shipping

        return total_shipping * self.quantity

    def get_kit_products_cost_total(self):
        if not self.kit:
            return Money(0, "BRL")

        total_cost = Money(0, "BRL")
        product_overrides, _ = self._get_kit_override_maps()
        for kit_product in self._iter_kit_products():
            override = product_overrides.get(kit_product.product_id)
            if override:
                if override.quantity <= 0:
                    continue
                total_cost += override.product_cost_price * override.quantity
            elif kit_product.quantity > 0:
                total_cost += kit_product.product.cost_price * kit_product.quantity

        return total_cost * self.quantity

    def get_kit_services_cost_total(self):
        if not self.kit:
            return Money(0, "BRL")

        total_cost = Money(0, "BRL")
        _, service_overrides = self._get_kit_override_maps()
        for kit_service in self._iter_kit_services():
            override = service_overrides.get(kit_service.service_id)
            if override:
                if override.quantity <= 0:
                    continue
                total_cost += override.service_cost_price * override.quantity
            elif kit_service.quantity > 0 and kit_service.service.suggested_cost:
                total_cost += kit_service.service.suggested_cost * kit_service.quantity

        return total_cost * self.quantity

    def get_kit_third_party_services_cost_total(self):
        if not self.kit:
            return Money(0, "BRL")

        total_cost = Money(0, "BRL")
        _, service_overrides = self._get_kit_override_maps()
        for kit_service in self._iter_kit_services():
            if not kit_service.service.is_third_party:
                continue

            override = service_overrides.get(kit_service.service_id)
            if override:
                if override.quantity <= 0:
                    continue
                total_cost += override.service_cost_price * override.quantity
            elif kit_service.quantity > 0 and kit_service.service.suggested_cost:
                total_cost += kit_service.service.suggested_cost * kit_service.quantity

        return total_cost * self.quantity

    def get_kit_third_party_services_selling_total(self):
        if not self.kit:
            return Money(0, "BRL")

        total_selling = Money(0, "BRL")
        _, service_overrides = self._get_kit_override_maps()
        for kit_service in self._iter_kit_services():
            if not kit_service.service.is_third_party:
                continue

            override = service_overrides.get(kit_service.service_id)
            if override:
                if override.quantity <= 0:
                    continue
                total_selling += override.service_selling_price * override.quantity
            elif kit_service.quantity > 0:
                total_selling += kit_service.resolved_selling_price * kit_service.quantity

        return total_selling * self.quantity

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
