from datetime import timedelta
from types import SimpleNamespace
from typing import Any, Iterable

from django.db import models, transaction
from django.core.validators import MinValueValidator, MaxValueValidator
from django.conf import settings
from djmoney.money import Money

from apps.catalog.models.kits import Kit
from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.catalog.price_tracking import record_product_last_used_price
from apps.catalog.product_issues import ProductIssueSummary, annotate_product_issues
from apps.catalog.util import calculate_catalog_service_prices
from apps.core.models import TimeStampedModel
from djmoney.models.fields import MoneyField

from apps.budget.pricing import PricingSnapshot, build_pricing_snapshot, resolve_discount_fields
from apps.workorder.models import WorkOrder

from apps.workshops.models.workshop_costs import WorkshopCost, WorkshopCostItem
from apps.workshops.util.monthly_costs import get_mechanic_salary_monthly_cost
from django.utils import timezone
from decimal import Decimal, ROUND_HALF_UP


class BudgetStatus(models.TextChoices):
    DRAFT = "draft", "Em Aberto"
    WAITING_CLIENT = "waiting_client", "Aguardando Relato do Cliente"
    WAITING_DIAGNOSIS = "waiting_diagnosis", "Aguardando Diagnóstico"
    WAITING_ITEMS = "waiting_items", "Aguardando Itens"
    WAITING_PRICING = "waiting_pricing", "Aguardando Precificação"
    WAITING_REVIEW = "waiting_review", "Aguardando Revisão"
    WAITING_APPROVAL = "waiting_approval", "Aguardando Aprovação"
    APPROVED = "approved", "Aprovado"
    REJECTED = "rejected", "Rejeitado"
    CANCELLED = "cancelled", "Cancelado"


class SignatureStatus(models.TextChoices):
    NOT_SENT = "not_sent", "Não Enviado"
    SENDING = "sending", "Enviando"
    SENT = "sent", "Enviado"
    FAILED = "failed", "Falha no Envio"
    APPROVED = "approved", "Aprovado"


class BudgetType(models.TextChoices):
    SALE = "sale", "Venda"
    WARRANTY = "warranty", "Garantia"
    COURTESY = "courtesy", "Cortesia"


class FuelLevel(models.IntegerChoices):
    FULL = 8, "Cheio"
    SEVEN_EIGHTHS = 7, "7/8"
    THREE_QUARTERS = 6, "3/4"
    ONE_HALF = 5, "1/2"
    ONE_QUARTER = 4, "1/4"
    ONE_EIGHTH = 3, "1/8"
    RESERVE = 2, "Reserva"
    EMPTY = 1, "Vazio"


class Defect(models.Model):
    workshop = models.ForeignKey("workshops.Workshop", on_delete=models.CASCADE, related_name="defects")
    budget = models.ForeignKey("budget.Budget", on_delete=models.CASCADE, related_name="defects")
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Defeito"
        verbose_name_plural = "Defeitos"
        constraints = [models.UniqueConstraint(fields=("budget", "name"), name="unique_budget_name_per_defetct")]

    def __str__(self):
        return self.name


class Budget(TimeStampedModel):
    CUSTOMER_AGREED_DEPARTURE_REQUIRED_MESSAGE = "Informe a data de saída combinada com o cliente."
    SERVICE_EXPECTED_COMPLETION_REQUIRED_MESSAGE = "Informe a data prevista de término do serviço."
    STEP6_DATE_ORDER_ERROR_MESSAGE = "A data de saída combinada com o cliente não pode ser menor que a data prevista de término do serviço."

    workshop = models.ForeignKey("workshops.Workshop", verbose_name="Oficina", on_delete=models.CASCADE, related_name="budgets")
    customer = models.ForeignKey("customer.Customer", verbose_name="Cliente", on_delete=models.SET_NULL, related_name="budgets", null=True)
    vehicle = models.ForeignKey("customer.Vehicle", verbose_name="Veículo", on_delete=models.SET_NULL, related_name="budgets", null=True)
    cost_estimator = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="Orçamentista", on_delete=models.SET_NULL, related_name="budgets", null=True)
    collaborator = models.ForeignKey("collaborators.WorkshopCollaborator", verbose_name="Colaborador", on_delete=models.SET_NULL, related_name="budgets", null=True)
    collaborators = models.ManyToManyField("collaborators.WorkshopCollaborator", verbose_name="Colaboradores", related_name="collaborators_budgets", blank=True)
    checklist = models.ForeignKey("checklist.Checklist", verbose_name="Checklist", on_delete=models.SET_NULL, related_name="budgets", null=True, blank=True)
    reference_budget = models.ForeignKey("self", verbose_name="Orçamento de Referência", on_delete=models.SET_NULL, related_name="related_budgets", null=True, blank=True)

    # Datas e Prazos
    expiration_date = models.DateField(verbose_name="Data de Validade", null=True, blank=True)
    entry_date = models.DateField(verbose_name="Data de Entrada")
    customer_agreed_departure_at = models.DateTimeField(verbose_name="Data de saída combinada com o Cliente", null=True, blank=True)
    service_expected_completion_at = models.DateTimeField(verbose_name="Data prevista de término do serviço", null=True, blank=True)
    is_warranty_budget = models.BooleanField(verbose_name="Orçamento de Garantia", default=False)
    budget_type = models.CharField(verbose_name="Tipo de Orçamento", max_length=50, choices=BudgetType.choices, default=BudgetType.SALE)

    # Informações Técnicas
    problem_description = models.TextField(verbose_name="Relato principal do cliente", blank=True, null=True)
    technical_diagnosis = models.TextField(verbose_name="Observações Técnicas", blank=True, null=True)
    notes = models.TextField(verbose_name="Observações Complementares", blank=True, null=True)
    pdf_observation = models.CharField(verbose_name="Observação do PDF", max_length=250, blank=True, default="")
    current_km = models.PositiveIntegerField(verbose_name="KM Atual", default=0)
    fuel_level = models.PositiveIntegerField(verbose_name="Nível do Tanque", choices=FuelLevel.choices, null=True, blank=True)
    defect = models.ForeignKey(Defect, on_delete=models.SET_NULL, related_name="budgets", null=True)

    # Financeiro
    discount_value = MoneyField(verbose_name="Aplicar Desconto (R$)", max_digits=14, decimal_places=2, default=0.00)
    discount_percentage = models.DecimalField(verbose_name="Aplicar Desconto (%)", max_digits=7, decimal_places=6, default=0.00, validators=[MinValueValidator(0), MaxValueValidator(1)])

    # Margens e Ajustes
    profit_margin_parts = models.DecimalField(verbose_name="Percentual Lucro de Peças", max_digits=5, decimal_places=2, default=0.00)
    profit_margin_labor = models.DecimalField(verbose_name="Percentual Lucro de Mão de Obra", max_digits=5, decimal_places=2, default=0.00)
    slider = models.SmallIntegerField(verbose_name="Slider", default=0, validators=[MinValueValidator(-100), MaxValueValidator(100)], help_text="Negativo: Peça | Positivo: Mão de Obra")

    # Status e Controle
    status = models.CharField(verbose_name="Status", max_length=50, choices=BudgetStatus.choices, default=BudgetStatus.DRAFT)
    cancellation_reason = models.CharField(verbose_name="Motivo do Cancelamento", max_length=255, blank=True, null=True)
    current_step = models.PositiveSmallIntegerField(verbose_name="Etapa Atual", default=1)
    step5_calculation_viewed = models.BooleanField(verbose_name="Calculo da etapa 5 visualizado", default=False)

    pricing_reference_month = models.PositiveSmallIntegerField(verbose_name="Mês de referência da precificação", null=True, blank=True)
    pricing_reference_year = models.PositiveIntegerField(verbose_name="Ano de referência da precificação", null=True, blank=True)
    pricing_productive_salary_total = MoneyField(verbose_name="Total congelado de salários produtivos", max_digits=14, decimal_places=2, null=True, blank=True)
    pricing_working_hours_per_month = models.DecimalField(verbose_name="Horas úteis/mês congeladas", max_digits=10, decimal_places=2, null=True, blank=True)
    pricing_minimum_hourly_cost = MoneyField(verbose_name="Custo hora mínimo congelado", max_digits=14, decimal_places=2, null=True, blank=True)
    pricing_hourly_cost_value = MoneyField(verbose_name="Valor hora congelado", max_digits=14, decimal_places=2, null=True, blank=True)
    pricing_profitability_multiplier = models.DecimalField(verbose_name="Multiplicador congelado", max_digits=10, decimal_places=2, null=True, blank=True)

    # Token SuperSign
    signature_token_version = models.PositiveIntegerField(verbose_name="ID do PDF do Orçamento", default=1)
    signature_token_active = models.BooleanField(verbose_name="Token de Assinatura Ativo", default=True)
    signature_request_status = models.CharField(max_length=30, choices=SignatureStatus.choices, default=SignatureStatus.NOT_SENT)
    signature_external_id = models.CharField(max_length=255, blank=True, null=True)
    signature_document_id = models.CharField(max_length=255, blank=True, null=True)
    signature_sent_at = models.DateTimeField(blank=True, null=True)

    def save(self, *args, **kwargs):
        self.sync_discount_fields()

        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            update_fields_set = set(update_fields)
            update_fields_set.update({"discount_value", "discount_value_currency", "discount_percentage"})
            kwargs["update_fields"] = list(update_fields_set)

        is_new = self.pk is None

        old_status = None
        if not is_new:
            old_status = Budget.objects.filter(pk=self.pk).values_list("status", flat=True).first()

        with transaction.atomic():
            super().save(*args, **kwargs)

            if old_status != BudgetStatus.APPROVED and self.status == BudgetStatus.APPROVED:
                if self.vehicle_id and self.current_km is not None:
                    vehicle = self.vehicle
                    if vehicle and vehicle.km != self.current_km:
                        vehicle.km = self.current_km
                        vehicle.save(update_fields=["km"])

                workorder, _ = WorkOrder.objects.get_or_create(
                    budget=self,
                    defaults={"workshop": self.workshop},
                )
                workorder.sync_from_budget()

            if self.status == BudgetStatus.APPROVED or self.status == BudgetStatus.REJECTED or self.status == BudgetStatus.CANCELLED:
                self.signature_token_active = False
                super().save(update_fields=["signature_token_active"])

    class Meta:
        verbose_name = "Orçamento"
        verbose_name_plural = "Orçamentos"

    @property
    def has_frozen_pricing_snapshot(self) -> bool:
        return self.pricing_reference_month is not None and self.pricing_reference_year is not None

    def _get_pricing_reference_date(self):
        return self.criado_em if self.criado_em else timezone.now()

    def _get_reference_workshop_cost(self) -> WorkshopCost | None:
        reference_date = self._get_pricing_reference_date()
        workshop_cost = WorkshopCost.objects.filter(workshop=self.workshop, month=reference_date.month, year=reference_date.year).first()
        if workshop_cost is not None:
            return workshop_cost

        return WorkshopCost.objects.filter(workshop=self.workshop, month=timezone.now().month, year=timezone.now().year).first()

    def build_pricing_snapshot_data(self) -> dict[str, Any]:
        workshop_cost = self._get_reference_workshop_cost()
        productive_salary_total = Money(0, "BRL")
        working_hours_per_month = Decimal("0.00")
        minimum_hourly_cost = Money(0, "BRL")
        hourly_cost_value = Money(0, "BRL")
        profitability_multiplier = Decimal("0.00")

        reference_date = self._get_pricing_reference_date()
        reference_month = reference_date.month
        reference_year = reference_date.year

        if workshop_cost is not None:
            reference_month = workshop_cost.month
            reference_year = workshop_cost.year
            working_hours_per_month = workshop_cost.working_hours_per_month or Decimal("0.00")
            minimum_hourly_cost = workshop_cost.minimum_hourly_cost or Money(0, "BRL")
            hourly_cost_value = workshop_cost.hourly_cost_value or Money(0, "BRL")
            profitability_multiplier = workshop_cost.profitability_multiplier or Decimal("0.00")

            mechanic_salary_obj = get_mechanic_salary_monthly_cost(workshop=self.workshop)
            if mechanic_salary_obj is not None:
                salary_item = WorkshopCostItem.objects.filter(workshop_cost=workshop_cost, monthly_cost=mechanic_salary_obj).first()
                if salary_item is not None:
                    productive_salary_total = salary_item.amount

        return {
            "pricing_reference_month": reference_month,
            "pricing_reference_year": reference_year,
            "pricing_productive_salary_total": productive_salary_total,
            "pricing_working_hours_per_month": working_hours_per_month,
            "pricing_minimum_hourly_cost": minimum_hourly_cost,
            "pricing_hourly_cost_value": hourly_cost_value,
            "pricing_profitability_multiplier": profitability_multiplier,
        }

    def freeze_pricing_snapshot(self, *, force: bool = False) -> None:
        if self.pk is None:
            return

        if self.has_frozen_pricing_snapshot and not force:
            return

        snapshot_data = self.build_pricing_snapshot_data()
        type(self).objects.filter(pk=self.pk).update(**snapshot_data)
        for field_name, value in snapshot_data.items():
            setattr(self, field_name, value)

    def get_frozen_pricing_context(self):
        if not self.has_frozen_pricing_snapshot:
            self.freeze_pricing_snapshot()

        return SimpleNamespace(
            minimum_hourly_cost=self.pricing_minimum_hourly_cost or Money(0, "BRL"),
            hourly_cost_value=self.pricing_hourly_cost_value or Money(0, "BRL"),
            profitability_multiplier=self.pricing_profitability_multiplier or Decimal("0.00"),
            working_hours_per_month=self.pricing_working_hours_per_month or Decimal("0.00"),
            productive_salary_total=self.pricing_productive_salary_total or Money(0, "BRL"),
            month=self.pricing_reference_month,
            year=self.pricing_reference_year,
        )

    def _get_live_pricing_fallback_context(self) -> SimpleNamespace:
        workshop_cost = self._get_reference_workshop_cost()
        productive_salary_total = Money(0, "BRL")
        working_hours_per_month = Decimal("0.00")
        hourly_cost_value = Money(0, "BRL")
        profitability_multiplier = Decimal("1.00")

        if workshop_cost is not None:
            working_hours_per_month = workshop_cost.working_hours_per_month or Decimal("0.00")
            hourly_cost_value = workshop_cost.hourly_cost_value or Money(0, "BRL")
            profitability_multiplier = workshop_cost.profitability_multiplier or Decimal("1.00")

            mechanic_salary_obj = get_mechanic_salary_monthly_cost(workshop=self.workshop)
            if mechanic_salary_obj is not None:
                salary_item = WorkshopCostItem.objects.filter(workshop_cost=workshop_cost, monthly_cost=mechanic_salary_obj).first()
                if salary_item is not None:
                    productive_salary_total = salary_item.amount

        return SimpleNamespace(
            hourly_cost_value=hourly_cost_value,
            profitability_multiplier=profitability_multiplier,
            working_hours_per_month=working_hours_per_month,
            productive_salary_total=productive_salary_total,
        )

    @property
    def get_mlr(self):
        frozen_profitability_multiplier = self.get_frozen_pricing_context().profitability_multiplier
        if frozen_profitability_multiplier and frozen_profitability_multiplier > 0:
            return frozen_profitability_multiplier

        return self._get_live_pricing_fallback_context().profitability_multiplier

    @property
    def get_mlo(self):
        pricing_context = self.get_frozen_pricing_context()
        salario_mecanicos = pricing_context.productive_salary_total
        horas_uteis_mes = pricing_context.working_hours_per_month

        if not horas_uteis_mes or horas_uteis_mes == 0:
            pricing_context = self._get_live_pricing_fallback_context()
            salario_mecanicos = pricing_context.productive_salary_total
            horas_uteis_mes = pricing_context.working_hours_per_month
            if not horas_uteis_mes or horas_uteis_mes == 0:
                return Decimal("1.00")

        duracao_total = Decimal(self.total_duration.total_seconds()) / Decimal(3600)

        # Custos
        custo_pecas = self.total_costs_products_value
        custo_servico_terceiro = self.total_third_party_services_cost
        custo_hora_mecanico = salario_mecanicos / horas_uteis_mes
        custo_total_mao_obra = duracao_total * custo_hora_mecanico
        custo_frete_pecas = self.total_products_shipping

        # Venda
        venda_servico_terceiro = self.total_third_party_services_selling
        venda_mao_obra_hun = self.total_services_value - venda_servico_terceiro
        venda_pecas = self.total_products_value - custo_frete_pecas

        #
        soma_base_orcamento = venda_pecas + custo_frete_pecas + venda_servico_terceiro
        valor_orcamento_hun = soma_base_orcamento + venda_mao_obra_hun
        divisor_mlo = (custo_pecas + custo_frete_pecas + custo_servico_terceiro + custo_total_mao_obra).amount

        return (valor_orcamento_hun.amount / divisor_mlo) if divisor_mlo > 0 else Decimal("1.00")

    def calculate_pricing_methods(self):
        fallback_data = self._build_pricing_fallback_data()
        pricing_context = self.get_frozen_pricing_context()
        salario_mecanicos = pricing_context.productive_salary_total

        # Índices
        duracao_total = Decimal(self.total_duration.total_seconds()) / Decimal(3600)
        horas_uteis_mes = pricing_context.working_hours_per_month

        if not horas_uteis_mes or horas_uteis_mes == 0:
            return fallback_data

        # Custos
        custo_pecas = self.total_costs_products_value
        custo_frete_pecas = self.total_products_shipping
        custo_servico_terceiro = self.total_third_party_services_cost
        custo_hora_mecanico = salario_mecanicos / horas_uteis_mes
        custo_total_mao_obra = duracao_total * custo_hora_mecanico

        # Valores de Venda
        venda_pecas = self.total_products_value - custo_frete_pecas
        venda_servico_terceiro = self.total_third_party_services_selling

        soma_base_orcamento = venda_pecas + custo_frete_pecas + venda_servico_terceiro
        subtracao_base_lucro = custo_pecas + custo_frete_pecas + custo_total_mao_obra + custo_servico_terceiro

        # MÉTOD0 TRADICIONAL
        valor_hora_vendida_trad = pricing_context.hourly_cost_value
        venda_mao_obra_trad = valor_hora_vendida_trad * duracao_total
        valor_orcamento_trad = soma_base_orcamento + venda_mao_obra_trad
        lucro_operacional_trad = valor_orcamento_trad - subtracao_base_lucro
        if valor_orcamento_trad.amount > 0:
            rentabilidade_trad = ((lucro_operacional_trad.amount / valor_orcamento_trad.amount) * 100).quantize(Decimal("0.01"), ROUND_HALF_UP)
        else:
            rentabilidade_trad = Decimal("0.00")

        # MÉTOD0 HUNTER
        venda_mao_obra_hun = self.total_services_value - venda_servico_terceiro
        valor_orcamento_hun = soma_base_orcamento + venda_mao_obra_hun
        lucro_operacional_hun = valor_orcamento_hun - subtracao_base_lucro
        if valor_orcamento_hun.amount > 0:
            rentabilidade_hun = ((lucro_operacional_hun.amount / valor_orcamento_hun.amount) * 100).quantize(Decimal("0.01"), ROUND_HALF_UP)
        else:
            rentabilidade_hun = Decimal("0.00")

        # Organização dos dados
        data_trad = {
            "method_name": "Tradicional",
            "custo_pecas": custo_pecas,
            "custo_frete_pecas": custo_frete_pecas,
            "custo_servico_terceiro": custo_servico_terceiro,
            "custo_hora_mecanico": custo_hora_mecanico,
            "custo_total_mao_obra": custo_total_mao_obra,
            "duracao_total": self.total_duration_display,
            "lucro_operacional": lucro_operacional_trad,
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
            "mlr": self.get_mlr,
            "venda_pecas": venda_pecas,
            "venda_servico_terceiro": venda_servico_terceiro,
            "venda_mao_obra": venda_mao_obra_hun,
            "rentabilidade": rentabilidade_hun,
            "mlo": self.get_mlo,
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

    def revoke_signature_token(self) -> None:
        self.signature_token_active = False
        self.save(update_fields=["signature_token_active"])

    def regenerate_signature_token(self) -> None:
        self.signature_token_version += 1
        self.signature_token_active = True
        self.save(update_fields=["signature_token_version", "signature_token_active"])

    def mark_signature_sending(self) -> None:
        self.signature_request_status = SignatureStatus.SENDING
        self.save(update_fields=["signature_request_status"])

    def mark_signature_sent(self, external_id: str, *, document_id: str | None = None) -> None:
        self.signature_request_status = SignatureStatus.SENT
        self.signature_external_id = external_id
        self.signature_document_id = document_id
        self.signature_sent_at = timezone.now()
        self.save(update_fields=["signature_request_status", "signature_external_id", "signature_document_id", "signature_sent_at"])

    def mark_signature_failed(self) -> None:
        self.signature_request_status = SignatureStatus.FAILED
        self.save(update_fields=["signature_request_status"])

    def mark_signature_approved(self) -> None:
        self.signature_request_status = SignatureStatus.APPROVED
        self.save(update_fields=["signature_request_status"])

    @property
    def total_duration_display(self) -> str:
        total_td = self.total_duration
        if not total_td:
            return "00h 00m"

        ts = int(total_td.total_seconds())
        return f"{ts // 3600:02d}h {(ts % 3600) // 60:02d}m"

    @property
    def budget_status(self):
        return BudgetStatus(self.status).label

    @property
    def collaborator_name(self):
        collabs = self.collaborators.all()
        if collabs.exists():
            return ", ".join([c.name for c in collabs])
        return "Sistema"

    @property
    def rentability(self) -> Money:
        data = self.calculate_pricing_methods()
        return data["rentabilidade"]

    def _is_local_product_item(self, item: "BudgetItem") -> bool:
        return bool(item.is_local and ((item.product_cost_price and item.product_cost_price.amount > 0) or (item.product_selling_price and item.product_selling_price.amount > 0) or (item.shipping and item.shipping.amount > 0)))

    def _is_local_service_item(self, item: "BudgetItem") -> bool:
        return bool(item.is_local and ((item.service_cost_price and item.service_cost_price.amount > 0) or (item.service_selling_price and item.service_selling_price.amount > 0) or item.duration))

    def _iter_items(self) -> Iterable["BudgetItem"]:
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

    def _raw_labor_duration(self) -> timedelta:
        total = timedelta(0)
        for item in self._iter_items():
            if (item.service or self._is_local_service_item(item)) and item.duration:
                if item.service and item.service.is_third_party:
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
                elif kit_service.quantity > 0 and kit_service.duration:
                    total += kit_service.duration * kit_service.quantity * item.quantity
        return total

    @property
    def mechanic_hour_cost_value(self) -> Money:
        pricing_context = self.get_frozen_pricing_context()
        salario_mecanicos = pricing_context.productive_salary_total
        horas_uteis_mes = pricing_context.working_hours_per_month
        if not horas_uteis_mes or horas_uteis_mes == 0:
            return Money(0, "BRL")

        return salario_mecanicos / horas_uteis_mes

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
                slider=int(self.slider or 0),
                discount_value=self.discount_value,
                discount_percentage=self.discount_percentage,
                labor_cost_value=self.total_labor_cost_value,
                is_local_product_item=self._is_local_product_item,
                is_local_service_item=self._is_local_service_item,
            )
            setattr(self, "_pricing_snapshot_cache", cached_snapshot)

            pricing_method_data = self.calculate_pricing_methods()
            labor_selling_value_override = pricing_method_data.get("venda_mao_obra") if pricing_method_data.get("method_name") == "Tradicional" else None
            if isinstance(labor_selling_value_override, Money):
                cached_snapshot = build_pricing_snapshot(
                    items=list(self._iter_items()),
                    slider=int(self.slider or 0),
                    discount_value=self.discount_value,
                    discount_percentage=self.discount_percentage,
                    labor_cost_value=self.total_labor_cost_value,
                    labor_selling_value_override=labor_selling_value_override,
                    is_local_product_item=self._is_local_product_item,
                    is_local_service_item=self._is_local_service_item,
                )
            setattr(self, "_pricing_snapshot_cache", cached_snapshot)
        return cached_snapshot

    def invalidate_pricing_snapshot_cache(self) -> None:
        if hasattr(self, "_pricing_snapshot_cache"):
            delattr(self, "_pricing_snapshot_cache")
        if hasattr(self, "_product_issue_summary_cache"):
            delattr(self, "_product_issue_summary_cache")

    def sync_discount_fields(self) -> None:
        self.invalidate_pricing_snapshot_cache()
        resolved_discount_value, resolved_discount_percentage = resolve_discount_fields(
            total_base_value=self.display_total_base_value if self.is_warranty_budget else self.total_base_value,
            discount_value=self.discount_value,
            discount_percentage=self.discount_percentage,
        )
        self.discount_value = resolved_discount_value
        self.discount_percentage = resolved_discount_percentage
        self.invalidate_pricing_snapshot_cache()

    ## Products
    @property
    def total_products_shipping(self) -> Money:
        return self.pricing_snapshot.total_products_shipping

    @property
    def total_costs_products_value(self) -> Money:
        return self.pricing_snapshot.total_costs_products_value

    @property
    def total_products_value(self) -> Money:
        return self.pricing_snapshot.total_products_value

    ## Services
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
    def budget_status_badge(self):
        status_color = {
            BudgetStatus.DRAFT: "badge-neutral",
            BudgetStatus.WAITING_CLIENT: "badge-warning",
            BudgetStatus.WAITING_DIAGNOSIS: "badge-warning",
            BudgetStatus.WAITING_ITEMS: "badge-warning",
            BudgetStatus.WAITING_PRICING: "badge-info",
            BudgetStatus.WAITING_REVIEW: "badge-info",
            BudgetStatus.APPROVED: "badge-success",
            BudgetStatus.REJECTED: "badge-error",
            BudgetStatus.CANCELLED: "badge-error",
        }

        return {"text": BudgetStatus(self.status).label, "class": status_color.get(self.status, "badge-neutral")}

    @property
    def type_budget_badge(self):
        if self.is_warranty_budget:
            return {"text": "Garantia", "class": "badge-error"}

        if self.budget_type == "courtesy":
            return {"text": "Cortesia", "class": "badge-info"}

        return {"text": "Venda", "class": "badge-success"}

    ## Total
    @property
    def total_base_value(self) -> Money:
        return self.pricing_snapshot.total_base_value

    @property
    def warranty_total_products_value(self) -> Money:
        return self.total_costs_products_value + self.total_products_shipping

    @property
    def warranty_total_products_value_without_shipping(self) -> Money:
        return self.total_costs_products_value

    @property
    def warranty_total_services_value(self) -> Money:
        return self.total_costs_services_value

    @property
    def warranty_total_base_value(self) -> Money:
        return self.warranty_total_products_value + self.warranty_total_services_value

    @property
    def display_total_products_by_slider(self) -> Money:
        if self.is_warranty_budget:
            return self.warranty_total_products_value
        return self.get_total_products_by_slider

    @property
    def display_total_products_by_slider_without_shipping(self) -> Money:
        if self.is_warranty_budget:
            return self.warranty_total_products_value_without_shipping
        return self.get_total_products_by_slider_without_shipping

    @property
    def display_total_services_by_slider(self) -> Money:
        if self.is_warranty_budget:
            return self.warranty_total_services_value
        return self.get_total_services_by_slider

    @property
    def display_total_base_value(self) -> Money:
        if self.is_warranty_budget:
            return self.warranty_total_base_value
        return self.total_base_value

    @property
    def total_budget_value(self) -> Money:
        return self.pricing_snapshot.total_budget_value

    @property
    def resolved_discount_value(self) -> Money:
        return self.pricing_snapshot.resolved_discount_value

    @property
    def resolved_discount_percentage(self) -> Decimal:
        return self.pricing_snapshot.resolved_discount_percentage

    @property
    def display_resolved_discount_value(self) -> Money:
        if not self.is_warranty_budget:
            return self.resolved_discount_value

        resolved_discount_value, _ = resolve_discount_fields(
            total_base_value=self.display_total_base_value,
            discount_value=self.discount_value,
            discount_percentage=self.discount_percentage,
        )
        return resolved_discount_value

    @property
    def display_total_budget_value(self) -> Money:
        if self.is_warranty_budget:
            return self.display_total_base_value - self.display_resolved_discount_value
        return self.total_budget_value

    @property
    def display_resolved_discount_percentage(self) -> Decimal:
        if not self.is_warranty_budget:
            return self.resolved_discount_percentage

        _, resolved_discount_percentage = resolve_discount_fields(
            total_base_value=self.display_total_base_value,
            discount_value=self.discount_value,
            discount_percentage=self.discount_percentage,
        )
        return resolved_discount_percentage

    @property
    def has_local_items(self):
        return self.items.filter(is_local=True).exists()

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
    def step6_action_blockers(self) -> list[str]:
        blockers: list[str] = []
        if not self.customer_agreed_departure_at:
            blockers.append(self.CUSTOMER_AGREED_DEPARTURE_REQUIRED_MESSAGE)

        if not self.service_expected_completion_at:
            blockers.append(self.SERVICE_EXPECTED_COMPLETION_REQUIRED_MESSAGE)

        if self.customer_agreed_departure_at and self.service_expected_completion_at and self.customer_agreed_departure_at < self.service_expected_completion_at:
            blockers.append(self.STEP6_DATE_ORDER_ERROR_MESSAGE)

        return blockers

    @property
    def approval_blockers(self) -> list[str]:
        blockers = list(self.step6_action_blockers)

        if self.has_local_items:
            blockers.append("Existem itens nao cadastrados no sistema.")

        return blockers

    @property
    def has_approval_blockers(self) -> bool:
        return bool(self.approval_blockers)

    @property
    def approval_blockers_display(self) -> str:
        return " ".join(self.approval_blockers)

    @property
    def signature_blockers(self) -> list[str]:
        return list(self.approval_blockers)

    @property
    def has_signature_blockers(self) -> bool:
        return bool(self.signature_blockers)

    @property
    def signature_blockers_display(self) -> str:
        return " ".join(self.signature_blockers)

    @property
    def ordered_images(self):
        """Returns budget images ordered by upload date (oldest first)"""
        return self.budget_image.all()

    @property
    def get_total_products_by_slider(self):
        return self.pricing_snapshot.total_products_by_slider

    @property
    def get_total_products_by_slider_without_shipping(self):
        return self.get_total_products_by_slider - self.total_products_shipping

    @property
    def get_total_services_by_slider(self):
        return self.pricing_snapshot.total_services_by_slider

    @property
    def get_total_labor_by_slider(self):
        return self.pricing_snapshot.total_labor_by_slider

    def __str__(self):
        return f"Budget #{self.id} - {self.customer}"


class BudgetImageType(models.TextChoices):
    PRINCIPAL = "principal", "Principal"
    FRONTAL = "frontal", "Frontal"
    TRASEIRA = "traseira", "Traseira"
    DIREITA = "direita", "Direita"
    ESQUERDA = "esquerda", "Esquerda"
    PAINEL = "painel", "Painel"
    CHASSI = "chassi", "Chassi"
    MOTOR = "motor", "Motor"
    ADDITIONAL = "additional", "Adicional"


class BudgetImage(TimeStampedModel):
    workshop = models.ForeignKey("workshops.Workshop", on_delete=models.CASCADE, related_name="budget_image")
    budget = models.ForeignKey(Budget, on_delete=models.CASCADE, related_name="budget_image")
    content = models.BinaryField(null=True, blank=True)
    content_name = models.CharField(max_length=100, null=True, blank=True)
    content_type = models.CharField(max_length=100, null=True, blank=True)
    image_type = models.CharField(max_length=20, choices=BudgetImageType.choices, default=BudgetImageType.ADDITIONAL, verbose_name="Tipo de Imagem")

    class Meta:
        verbose_name = "Imagem do Orçamento"
        verbose_name_plural = "Imagens do Orçamento"
        ordering = ["criado_em"]
        constraints = [models.UniqueConstraint(fields=["budget", "image_type"], condition=~models.Q(image_type=BudgetImageType.ADDITIONAL), name="unique_budget_image_type_non_additional")]

    def __str__(self):
        return f"Image #{self.id} from Budget: {self.budget}"


class BudgetItem(TimeStampedModel):
    workshop = models.ForeignKey("workshops.Workshop", on_delete=models.CASCADE, related_name="items")
    budget = models.ForeignKey(Budget, on_delete=models.CASCADE, related_name="items")

    # Referências
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)
    service = models.ForeignKey(Service, on_delete=models.SET_NULL, null=True, blank=True)
    kit = models.ForeignKey(Kit, on_delete=models.SET_NULL, null=True, blank=True)

    # Dados
    description = models.CharField(verbose_name="Descrição", max_length=100, default="")
    quantity = models.PositiveIntegerField(verbose_name="Quantidade", default=1)
    is_local = models.BooleanField(verbose_name="Item Local", default=False, help_text="Item criado apenas neste orçamento, não cadastrado no banco de dados")
    is_customer_supplied = models.BooleanField(verbose_name="Peça trazida pelo cliente", default=False)

    ## Produto
    shipping = MoneyField(verbose_name="Frete", max_digits=14, decimal_places=2, default=0)
    product_cost_price = MoneyField(verbose_name="Custo", max_digits=14, decimal_places=2, default=0)
    product_selling_price = MoneyField(verbose_name="Valor de Venda", max_digits=14, decimal_places=2, default=0)

    ## Serviço
    service_cost_price = MoneyField(verbose_name="Custo", max_digits=14, decimal_places=2, default=0)
    service_selling_price = MoneyField(verbose_name="Valor de Venda", max_digits=14, decimal_places=2, default=0)
    duration = models.DurationField(verbose_name="Duração", null=True, blank=True)
    kit_snapshot_frozen = models.BooleanField(verbose_name="Snapshot do kit congelado", default=False)

    def save(self, *args, **kwargs):
        is_new = not self.pk
        if is_new:
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
                self.product_cost_price = sum((kp.product.cost_price * kp.quantity for kp in self.kit.kit_products.all()), Money(0, "BRL"))

                workshop_cost = self._get_budget_reference_workshop_cost()
                service_selling_total = Money(0, "BRL")
                service_cost_total = Money(0, "BRL")
                total_duration = timedelta()
                for kit_service in self.kit.kit_services.select_related("service").all():
                    service_cost, service_selling = self.resolve_kit_service_base_prices(kit_service=kit_service, workshop_cost=workshop_cost)
                    service_selling_total += service_selling * kit_service.quantity
                    service_cost_total += service_cost * kit_service.quantity
                    total_duration += (kit_service.duration or timedelta()) * kit_service.quantity

                self.service_selling_price = service_selling_total
                self.service_cost_price = service_cost_total
                self.duration = total_duration
                self.description = self.kit.name

        super().save(*args, **kwargs)

        if self.kit_id and not self.kit_snapshot_frozen:
            self.ensure_kit_snapshot()

        if self.product_id:
            record_product_last_used_price(product=self.product, price=self.product_selling_price)

    def _clear_kit_snapshot_caches(self) -> None:
        for cache_name in ("_kit_override_maps_cache", "_kit_unit_totals_cache"):
            if hasattr(self, cache_name):
                delattr(self, cache_name)

    def ensure_kit_snapshot(self) -> None:
        if not self.pk or not self.kit_id or self.kit_snapshot_frozen:
            return

        workshop_cost = self._get_budget_reference_workshop_cost()
        existing_overrides = list(self.kit_overrides.select_related("product", "service").all())
        product_overrides = {override.product_id: override for override in existing_overrides if override.product_id}
        service_overrides = {override.service_id: override for override in existing_overrides if override.service_id}

        with transaction.atomic():
            for kit_product in self.kit.kit_products.select_related("product").all():
                override = product_overrides.get(kit_product.product_id)
                BudgetKitItemOverride.objects.update_or_create(
                    workshop=self.workshop,
                    budget_item=self,
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
                default_cost, default_sell = self.resolve_kit_service_base_prices(kit_service=kit_service, workshop_cost=workshop_cost)
                BudgetKitItemOverride.objects.update_or_create(
                    workshop=self.workshop,
                    budget_item=self,
                    service=kit_service.service,
                    defaults={
                        "quantity": override.quantity if override else kit_service.quantity,
                        "service_cost_price": override.service_cost_price if override else default_cost,
                        "service_selling_price": override.service_selling_price if override else default_sell,
                        "duration": override.duration if override else (kit_service.duration or timedelta()),
                    },
                )

            BudgetItem.objects.filter(pk=self.pk, kit_snapshot_frozen=False).update(kit_snapshot_frozen=True)

        self.kit_snapshot_frozen = True
        self._clear_kit_snapshot_caches()
        self.refresh_kit_snapshot_totals()

    def refresh_kit_snapshot_totals(self) -> None:
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

        BudgetItem.objects.filter(pk=self.pk).update(
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

    def _iter_frozen_kit_product_overrides(self):
        if not self.kit_id:
            return ()

        self.ensure_kit_snapshot()
        return self.kit_overrides.filter(product__isnull=False).select_related("product").all()

    def _iter_frozen_kit_service_overrides(self):
        if not self.kit_id:
            return ()

        self.ensure_kit_snapshot()
        return self.kit_overrides.filter(service__isnull=False).select_related("service").all()

    @property
    def duration_display(self):
        if not self.duration:
            return "00h 00m"

        total_seconds = int(self.duration.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60

        return f"{hours:02d}h {minutes:02d}m"

    def _get_kit_override_maps(self) -> tuple[dict[int, "BudgetKitItemOverride"], dict[int, "BudgetKitItemOverride"]]:
        cache = getattr(self, "_kit_override_maps_cache", None)
        if cache is not None:
            return cache

        if self.kit_id:
            self.ensure_kit_snapshot()

        product_overrides: dict[int, "BudgetKitItemOverride"] = {}
        service_overrides: dict[int, "BudgetKitItemOverride"] = {}

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

    def _get_budget_reference_workshop_cost(self) -> WorkshopCost | None:
        cache_set = getattr(self, "_budget_workshop_cost_cache_set", False)
        if cache_set:
            return getattr(self, "_budget_workshop_cost_cache", None)

        workshop_cost = self.budget.get_frozen_pricing_context() if self.budget_id and self.budget else None

        setattr(self, "_budget_workshop_cost_cache", workshop_cost)
        setattr(self, "_budget_workshop_cost_cache_set", True)
        return workshop_cost

    def resolve_kit_service_base_prices(self, *, kit_service: Any, workshop_cost: WorkshopCost | None = None) -> tuple[Money, Money]:
        duration = kit_service.duration or timedelta()
        manual_cost = getattr(kit_service, "cost_price", None)
        manual_duration_selling = getattr(kit_service, "duration_selling_price", None)
        inserted_selling = kit_service.resolved_selling_price
        resolved_workshop_cost = workshop_cost if workshop_cost is not None else self._get_budget_reference_workshop_cost()

        if resolved_workshop_cost is not None:
            duration_cost, duration_sell = calculate_catalog_service_prices(duration, resolved_workshop_cost)
            resolved_cost = manual_cost if manual_cost is not None else duration_cost
            resolved_duration_selling = manual_duration_selling if manual_duration_selling is not None else duration_sell
            if self.kit and self.kit.service_pricing_mode == Kit.ServicePricingMode.BY_DURATION:
                return resolved_cost, resolved_duration_selling
            return resolved_cost, inserted_selling

        fallback_cost = manual_cost if manual_cost is not None else (kit_service.service.suggested_cost or Money(0, "BRL"))
        fallback_duration_selling = manual_duration_selling if manual_duration_selling is not None else inserted_selling
        if self.kit and self.kit.service_pricing_mode == Kit.ServicePricingMode.BY_DURATION:
            return fallback_cost, fallback_duration_selling
        return fallback_cost, inserted_selling

    @property
    def effective_kit_products(self) -> list[dict[str, Any]]:
        if not self.kit:
            return []

        products: list[dict[str, Any]] = []

        for override in self._iter_frozen_kit_product_overrides():
            quantity = override.quantity
            if quantity <= 0:
                continue

            products.append({"id": override.product_id, "name": override.product.name, "quantity": quantity})

        return products

    @property
    def effective_kit_services(self) -> list[dict[str, Any]]:
        if not self.kit:
            return []

        services: list[dict[str, Any]] = []

        for override in self._iter_frozen_kit_service_overrides():
            quantity = override.quantity
            if quantity <= 0:
                continue

            services.append({"id": override.service_id, "name": override.service.name, "quantity": quantity})

        return services

    @property
    def effective_kit_products_count(self) -> int:
        return len(self.effective_kit_products)

    @property
    def effective_kit_services_count(self) -> int:
        return len(self.effective_kit_services)

    @property
    def total_price(self):
        # Se for kit, calcular com base nos overrides
        if self.kit:
            return self.get_kit_total_with_overrides()
        return ((self.product_selling_price + self.service_selling_price) * self.quantity) + self.shipping

    @property
    def display_product_selling_price(self) -> Money:
        if self.budget.is_warranty_budget:
            return Money(0, "BRL")
        return self.product_selling_price

    @property
    def display_service_selling_price(self) -> Money:
        if self.budget.is_warranty_budget:
            return Money(0, "BRL")
        return self.service_selling_price

    @property
    def display_total_price(self) -> Money:
        if not self.budget.is_warranty_budget:
            return self.total_price
        if self.kit:
            return self.get_kit_products_cost_total() + self.get_kit_products_shipping_total() + self.get_kit_services_cost_total()
        if self.product_id or self.is_local and ((self.product_cost_price and self.product_cost_price.amount > 0) or (self.shipping and self.shipping.amount > 0)):
            return (self.product_cost_price * self.quantity) + self.shipping
        return self.service_cost_price * self.quantity

    @property
    def display_unit_price(self) -> Money:
        if not self.budget.is_warranty_budget:
            return self.unit_price
        if self.quantity <= 0:
            return Money(0, "BRL")
        if self.kit:
            return self.kit_unit_cost
        if self.product_id or self.is_local and ((self.product_cost_price and self.product_cost_price.amount > 0) or (self.shipping and self.shipping.amount > 0)):
            return self.product_cost_price
        return self.service_cost_price

    @property
    def display_kit_unit_price(self) -> Money:
        if self.budget.is_warranty_budget:
            return Money(0, "BRL")
        return self.kit_unit_price

    def _get_kit_unit_cost_and_price(self) -> tuple[Money, Money]:
        cache = getattr(self, "_kit_unit_totals_cache", None)
        if cache is not None:
            return cache

        if not self.kit:
            cache = (Money(0, "BRL"), Money(0, "BRL"))
            setattr(self, "_kit_unit_totals_cache", cache)
            return cache

        unit_cost = Money(0, "BRL")
        unit_price = Money(0, "BRL")

        for override in self._iter_frozen_kit_product_overrides():
            quantity = override.quantity
            if quantity <= 0:
                continue

            unit_cost += override.product_cost_price * quantity
            unit_price += override.product_selling_price * quantity

        for override in self._iter_frozen_kit_service_overrides():
            quantity = override.quantity
            if quantity <= 0:
                continue

            unit_cost += override.service_cost_price * quantity
            unit_price += override.service_selling_price * quantity

        cache = (unit_cost, unit_price)
        setattr(self, "_kit_unit_totals_cache", cache)
        return cache

    @property
    def kit_unit_cost(self) -> Money:
        return self._get_kit_unit_cost_and_price()[0]

    @property
    def kit_unit_price(self) -> Money:
        return self._get_kit_unit_cost_and_price()[1]

    def get_kit_total_with_overrides(self):
        """Calcula o total do kit considerando os overrides

        Total = (Soma total de produtos) + (Soma total de serviços)
        Produto total = (preço * quantidade do produto) + frete
        Serviço total = preço * quantidade do serviço

        Depois multiplica pela quantidade de kits no orçamento
        """
        if not self.kit:
            return Money(0, "BRL")

        total_produtos = Money(0, "BRL")
        total_servicos = Money(0, "BRL")

        # Calcular total dos produtos: (preço * qtd) + frete para cada produto
        for override in self._iter_frozen_kit_product_overrides():
            if override.quantity <= 0:
                produto_subtotal = Money(0, "BRL")
            else:
                produto_subtotal = (override.product_selling_price * override.quantity) + override.shipping
            total_produtos += produto_subtotal

        # Calcular total dos serviços: preço * qtd para cada serviço
        for override in self._iter_frozen_kit_service_overrides():
            if override.quantity <= 0:
                servico_subtotal = Money(0, "BRL")
            else:
                servico_subtotal = override.service_selling_price * override.quantity
            total_servicos += servico_subtotal

        # Total do kit = soma de produtos + soma de serviços
        total_kit = total_produtos + total_servicos

        # Multiplicar pela quantidade de kits no orçamento
        return total_kit * self.quantity

    def get_kit_products_total(self):
        """Retorna apenas o total de produtos do kit (para resumo separado)"""
        if not self.kit:
            return Money(0, "BRL")

        total_produtos = Money(0, "BRL")
        for override in self._iter_frozen_kit_product_overrides():
            if override.quantity <= 0:
                produto_subtotal = Money(0, "BRL")
            else:
                produto_subtotal = (override.product_selling_price * override.quantity) + override.shipping
            total_produtos += produto_subtotal

        return total_produtos * self.quantity

    def get_kit_services_total(self):
        """Retorna apenas o total de serviços do kit (para resumo separado)"""
        if not self.kit:
            return Money(0, "BRL")

        total_servicos = Money(0, "BRL")
        for override in self._iter_frozen_kit_service_overrides():
            if override.quantity <= 0:
                servico_subtotal = Money(0, "BRL")
            else:
                servico_subtotal = override.service_selling_price * override.quantity
            total_servicos += servico_subtotal

        return total_servicos * self.quantity

    def get_kit_services_duration(self):
        """Retorna a duração total dos serviços do kit"""
        if not self.kit:
            return timedelta(0)

        total_duration = timedelta(0)
        for override in self._iter_frozen_kit_service_overrides():
            if override.quantity > 0 and override.duration:
                total_duration += override.duration * override.quantity

        return total_duration * self.quantity

    def get_kit_products_shipping_total(self):
        if not self.kit:
            return Money(0, "BRL")

        total_shipping = Money(0, "BRL")
        for override in self._iter_frozen_kit_product_overrides():
            if override.quantity > 0:
                total_shipping += override.shipping

        return total_shipping * self.quantity

    def get_kit_products_cost_total(self):
        if not self.kit:
            return Money(0, "BRL")

        total_cost = Money(0, "BRL")
        for override in self._iter_frozen_kit_product_overrides():
            if override.quantity <= 0:
                continue
            total_cost += override.product_cost_price * override.quantity

        return total_cost * self.quantity

    def get_kit_services_cost_total(self):
        if not self.kit:
            return Money(0, "BRL")

        total_cost = Money(0, "BRL")
        for override in self._iter_frozen_kit_service_overrides():
            if override.quantity <= 0:
                continue
            total_cost += override.service_cost_price * override.quantity

        return total_cost * self.quantity

    def get_kit_third_party_services_cost_total(self):
        if not self.kit:
            return Money(0, "BRL")

        total_cost = Money(0, "BRL")
        for override in self._iter_frozen_kit_service_overrides():
            if not override.service.is_third_party:
                continue

            if override.quantity <= 0:
                continue
            total_cost += override.service_cost_price * override.quantity

        return total_cost * self.quantity

    def get_kit_third_party_services_selling_total(self):
        if not self.kit:
            return Money(0, "BRL")

        total_selling = Money(0, "BRL")
        for override in self._iter_frozen_kit_service_overrides():
            if not override.service.is_third_party:
                continue

            if override.quantity <= 0:
                continue
            total_selling += override.service_selling_price * override.quantity

        return total_selling * self.quantity

    @property
    def unit_price(self):
        if self.kit:
            return self.kit_unit_price
        if self.quantity == 0:
            return Money(0, "BRL")
        return Money((self.product_selling_price + self.service_selling_price).amount / self.quantity, "BRL")

    @property
    def profit_value(self):
        if self.kit:
            return Money(self.kit_unit_price.amount - self.kit_unit_cost.amount, "BRL")
        return Money((self.product_selling_price.amount + self.service_selling_price.amount) - (self.product_cost_price.amount + self.service_cost_price.amount), "BRL")

    @property
    def adjusted_unit_price(self):
        """
        Retorna o valor unitário ajustado pelo slider.
        Se for Kit, retorna a soma dos componentes ajustados.
        """
        budget = self.budget
        slider = budget.slider

        # Se slider é 0, não perde tempo calculando
        if slider == 0:
            return self.unit_price

        # Se for um item de Kit, a lógica muda: precisamos processar os filhos
        if self.kit:
            # Calculamos a soma dos preços ajustados de cada componente do kit
            total_kit_ajustado = Money(0, "BRL")

            # Componentes de Produto no Kit
            for ovr in self._iter_frozen_kit_product_overrides():
                u_p = ovr.product_selling_price
                u_c = ovr.product_cost_price
                qty = ovr.quantity

                # Ajustamos o preço unitário deste componente específico
                ajustado = self.calculate_individual_adjustment(original_unit=u_p, unit_cost=u_c, is_product=True)
                total_kit_ajustado += ajustado * qty

            # Componentes de Serviço no Kit
            for ovr in self._iter_frozen_kit_service_overrides():
                u_p = ovr.service_selling_price
                u_c = ovr.service_cost_price
                qty = ovr.quantity

                ajustado = self.calculate_individual_adjustment(original_unit=u_p, unit_cost=u_c, is_product=False)
                total_kit_ajustado += ajustado * qty

            return total_kit_ajustado / self.quantity if self.quantity else Money(0, "BRL")

        # Se for item simples (Produto ou Serviço)
        is_p = bool(self.product)
        u_p = self.product_selling_price if is_p else self.service_selling_price
        u_c = self.product_cost_price if is_p else self.service_cost_price

        return self.calculate_individual_adjustment(u_p, u_c, is_p)

    def calculate_individual_adjustment(self, original_unit, unit_cost, is_product):
        """
        Métodc auxiliar para aplicar a fórmula do slider em um valor unitário isolado.
        """
        budget = self.budget
        slider = budget.slider

        # Define bases de cálculo de acordo com o tipo
        if is_product:
            total_group = budget.total_products_value
            total_opposite = budget.total_services_value
            cost_opposite = budget.total_costs_services_value
        else:
            total_group = budget.total_services_value
            total_opposite = budget.total_products_value
            cost_opposite = budget.total_costs_products_value

        if total_group.amount == 0:
            return original_unit

        # 1. Participação do item no grupo
        share = original_unit.amount / total_group.amount

        # 2. Quanto o slider quer transferir (intensidade)
        percentual_slider = Decimal(abs(slider)) / 100

        # 3. Valor disponível no grupo oposto para transferência
        margem_transferivel_oposta = max(total_opposite - cost_opposite, Money(0, "BRL"))
        valor_transferido_total = margem_transferivel_oposta * percentual_slider

        # 4. Verifica se este item ganha ou perde
        ganha_valor = (slider < 0 and is_product) or (slider > 0 and not is_product)

        if ganha_valor:
            # Aplica o share sobre o que veio do outro grupo
            return original_unit + (valor_transferido_total * share)
        else:
            # Perde valor: retira do próprio lucro do item proporcional ao slider
            margem_propria = max(original_unit - unit_cost, Money(0, "BRL"))
            return original_unit - (margem_propria * percentual_slider)

    class Meta:
        verbose_name = "Item do Orçamento"
        verbose_name_plural = "Itens do Orçamento"


class BudgetKitItemOverride(TimeStampedModel):
    """Armazena modificações de itens do kit específicas para este orçamento"""

    workshop = models.ForeignKey("workshops.Workshop", on_delete=models.CASCADE, related_name="kit_overrides")
    budget_item = models.ForeignKey(BudgetItem, on_delete=models.CASCADE, related_name="kit_overrides")

    # Referência ao item original do kit (um dos dois deve estar preenchido)
    product = models.ForeignKey(Product, null=True, blank=True, on_delete=models.CASCADE)
    service = models.ForeignKey(Service, null=True, blank=True, on_delete=models.CASCADE)

    # Campos editáveis
    quantity = models.IntegerField(verbose_name="Quantidade", default=1, validators=[MinValueValidator(0)])

    # Campos de Produto
    product_cost_price = MoneyField(verbose_name="Custo do Produto", max_digits=14, decimal_places=2, default=0, default_currency="BRL")
    product_selling_price = MoneyField(verbose_name="Preço de Venda do Produto", max_digits=14, decimal_places=2, default=0, default_currency="BRL")
    shipping = MoneyField(verbose_name="Frete", max_digits=14, decimal_places=2, default=0, default_currency="BRL")

    # Campos de Serviço
    service_cost_price = MoneyField(verbose_name="Custo do Serviço", max_digits=14, decimal_places=2, default=0, default_currency="BRL")
    service_selling_price = MoneyField(verbose_name="Preço de Venda do Serviço", max_digits=14, decimal_places=2, default=0, default_currency="BRL")
    duration = models.DurationField(verbose_name="Duração", null=True, blank=True)

    class Meta:
        verbose_name = "Override de Item do Kit"
        verbose_name_plural = "Overrides de Itens do Kit"
        # Garantir que não haja duplicatas
        constraints = [
            models.UniqueConstraint(fields=["budget_item", "product"], condition=models.Q(product__isnull=False), name="unique_budget_kit_product"),
            models.UniqueConstraint(fields=["budget_item", "service"], condition=models.Q(service__isnull=False), name="unique_budget_kit_service"),
        ]

    def __str__(self):
        if self.product:
            return f"Override: {self.product.name} - Budget #{self.budget_item.budget_id}"
        elif self.service:
            return f"Override: {self.service.name} - Budget #{self.budget_item.budget_id}"
        return f"Override #{self.id}"
