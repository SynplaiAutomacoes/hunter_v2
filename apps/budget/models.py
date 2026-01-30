from datetime import timedelta

from django.db import models, transaction
from django.core.validators import MinValueValidator, MaxValueValidator
from django.conf import settings
from django.db.models import Sum, F, DurationField
from djmoney.money import Money

from apps.catalog.models.kits import Kit
from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.core.models import TimeStampedModel
from djmoney.models.fields import MoneyField

from apps.workorder.models import WorkOrder

from apps.workshops.models.monthly_costs import MonthlyCost
from apps.workshops.models.workshop_costs import WorkshopCost, WorkshopCostItem
from django.utils import timezone
from django.shortcuts import get_object_or_404
from decimal import Decimal

def metodo_hunter(budget, workshop):
    custos_oficina = get_object_or_404(WorkshopCost, workshop=workshop, month=timezone.now().month, year=timezone.now().year)
    custos_mensais = get_object_or_404(MonthlyCost, workshop=workshop, name__iexact="Salários mecânicos produtivos")
    salario_mecanicos = get_object_or_404(WorkshopCostItem, workshop_cost=custos_oficina, monthly_cost=custos_mensais).amount

    # Índices
    mlr = custos_oficina.profitability_multiplier
    duracao_total = Decimal(budget.total_duration.total_seconds()) / Decimal(3600)

    # Custos
    custo_pecas = budget.total_costs_products_value
    custo_frete_pecas = Money(0, "BRL")
    custo_servico_terceiro = budget.total_third_party_services_cost
    custo_hora_mecanico = salario_mecanicos / custos_oficina.working_hours_month
    custo_total_mao_obra = duracao_total * custo_hora_mecanico

    # Valores de Venda
    venda_servico_terceiro = budget.total_third_party_services_selling
    venda_pecas = budget.total_products_value
    venda_mao_obra = budget.total_services_value - venda_servico_terceiro

    # Finais
    valor_orcamento = venda_pecas + custo_frete_pecas + venda_mao_obra + venda_servico_terceiro
    mlo = valor_orcamento.amount / (custo_pecas + custo_frete_pecas + custo_servico_terceiro + custo_total_mao_obra).amount
    lucro_operacional = valor_orcamento - custo_pecas - custo_frete_pecas - custo_total_mao_obra - custo_servico_terceiro
    rentabilidade = lucro_operacional.amount / valor_orcamento.amount


def metodo_tradicional(budget, workshop):
    custos_oficina = get_object_or_404(WorkshopCost, workshop=workshop, month=timezone.now().month, year=timezone.now().year)
    custos_mensais = get_object_or_404(MonthlyCost, workshop=workshop, name__iexact="Salários mecânicos produtivos")
    salario_mecanicos = get_object_or_404(WorkshopCostItem, workshop_cost=custos_oficina, monthly_cost=custos_mensais).amount

    # Índices
    duracao_total = Decimal(budget.total_duration.total_seconds()) / Decimal(3600)

    # Custos
    custo_pecas = budget.total_costs_products_value
    custo_frete_pecas = Money(0, "BRL")
    custo_hora_mecanico = salario_mecanicos / custos_oficina.working_hours_month
    custo_total_mao_obra = duracao_total * custo_hora_mecanico
    custo_servico_terceiro = budget.total_third_party_services_cost

    # Valores de Venda
    venda_pecas = budget.total_products_value
    valor_hora_vendida = custos_oficina.hourly_rate
    venda_mao_obra = valor_hora_vendida * duracao_total
    venda_servico_terceiro = budget.total_third_party_services_selling

    # Finais
    valor_orcamento = venda_pecas + custo_frete_pecas + venda_mao_obra + venda_servico_terceiro
    lucro_operacional = valor_orcamento - custo_pecas - custo_frete_pecas - custo_total_mao_obra - custo_servico_terceiro
    rentabilidade = lucro_operacional.amount / valor_orcamento.amount


class BudgetStatus(models.TextChoices):
    DRAFT = "draft", "Em Aberto"
    APPROVED = "approved", "Aprovado"
    REJECTED = "rejected", "Rejeitado"
    CANCELLED = "cancelled", "Cancelado"


class Defect(models.Model):
    workshop = models.ForeignKey("workshops.Workshop", on_delete=models.CASCADE, related_name="defects")
    budget = models.ForeignKey("budget.Budget", on_delete=models.CASCADE, related_name="defects")
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Defeito"
        verbose_name_plural = "Defeitos"
        constraints = [
            models.UniqueConstraint(
                fields=("budget", "name"), name="unique_budget_name_per_defetct"
            )
        ]

    def __str__(self):
        return self.name


class Budget(TimeStampedModel):
    workshop = models.ForeignKey("workshops.Workshop", verbose_name="Oficina", on_delete=models.CASCADE, related_name="budgets")
    customer = models.ForeignKey("customer.Customer", verbose_name="Cliente", on_delete=models.SET_NULL, related_name="budgets", null=True)
    vehicle = models.ForeignKey("customer.Vehicle", verbose_name="Veículo", on_delete=models.SET_NULL, related_name="budgets", null=True)
    cost_estimator = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="Orçamentista", on_delete=models.SET_NULL, related_name="budgets", null=True)
    collaborator = models.ForeignKey("collaborators.WorkshopCollaborator", verbose_name="Colaborador", on_delete=models.SET_NULL, related_name="budgets", null=True)

    # Datas e Prazos
    expiration_date = models.DateField(verbose_name="Data de Validade", null=True, blank=True)
    entry_date = models.DateField(verbose_name="Data de Entrada")

    # Informações Técnicas
    problem_description = models.TextField(verbose_name="Relato principal do cliente", blank=True, null=True)
    technical_diagnosis = models.TextField(verbose_name="Observações Técnicas", blank=True, null=True)
    notes = models.TextField(verbose_name="Observações Complementares", blank=True, null=True)
    current_km = models.PositiveIntegerField(verbose_name="KM Atual", default=0)
    fuel_level = models.PositiveIntegerField(verbose_name="Nível do Tanque", default=0)
    defect = models.ForeignKey(Defect, on_delete=models.SET_NULL, related_name="budgets", null=True)

    # Financeiro
    discount_value = MoneyField(verbose_name="Aplicar Desconto (R$)", max_digits=14, decimal_places=2, default=0.00)

    # Margens e Ajustes
    profit_margin_parts = models.DecimalField(verbose_name="Percentual Lucro de Peças", max_digits=5, decimal_places=2, default=0.00)
    profit_margin_labor = models.DecimalField(verbose_name="Percentual Lucro de Mão de Obra", max_digits=5, decimal_places=2, default=0.00)
    slider = models.SmallIntegerField(verbose_name="Slider", default=0, validators=[MinValueValidator(-100), MaxValueValidator(100)], help_text="Negativo: Peça | Positivo: Mão de Obra")

    # Status e Controle
    status = models.CharField(verbose_name="Status", max_length=20, choices=BudgetStatus.choices, default=BudgetStatus.DRAFT)
    cancellation_reason = models.CharField(verbose_name="Motivo do Cancelamento", max_length=255, blank=True, null=True)
    current_step = models.PositiveSmallIntegerField(verbose_name="Etapa Atual", default=1)

    def save(self, *args, **kwargs):
        is_new = self.pk is None

        old_status = None
        if not is_new:
            old_status = Budget.objects.filter(pk=self.pk).values_list("status", flat=True).first()

        with transaction.atomic():
            super().save(*args, **kwargs)

            if old_status != BudgetStatus.APPROVED and self.status == BudgetStatus.APPROVED:
                WorkOrder.objects.get_or_create(
                    budget=self,
                    defaults={"workshop": self.workshop},
                )

        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Orçamento"
        verbose_name_plural = "Orçamentos"

    @property
    def expiration_date_display(self):
        return self.expiration_date or ""

    @property
    def budget_status(self):
        return BudgetStatus(self.status).label

    @property
    def collaborator_name(self):
        return self.collaborator.name if self.collaborator else "Sistema"

    @property
    def total_third_party_services_cost(self) -> Money:
        total = self.items.filter(service__is_third_party=True).aggregate(total=Sum(F("quantity") * F("service_cost_price")))["total"] or 0
        return Money(total, "BRL")

    @property
    def total_third_party_services_selling(self) -> Money:
        total = self.items.filter(service__is_third_party=True).aggregate(total=Sum(F("quantity") * F("service_selling_price")))["total"] or 0
        return Money(total, "BRL")

    @property
    def total_costs_products_value(self) -> Money:
        total = self.items.aggregate(total=Sum(F("quantity") * F("product_cost_price")))["total"] or 0
        return Money(total, 'BRL')

    @property
    def total_products_value(self) -> Money:
        total = self.items.aggregate(total=Sum(F("quantity") * F("product_selling_price")))["total"] or 0
        return Money(total, 'BRL')

    @property
    def total_costs_services_value(self) -> Money:
        total = self.items.aggregate(total=Sum(F("quantity") * F("service_cost_price")))["total"] or 0
        return Money(total, "BRL")

    @property
    def total_services_value(self) -> Money:
        total = self.items.aggregate(total=Sum(F("quantity") * F("service_selling_price")))["total"] or 0
        return Money(total, "BRL")

    @property
    def total_base_value(self) -> Money:
        return self.total_products_value + self.total_services_value

    @property
    def total_budget_value(self) -> Money:
        return self.total_base_value - self.discount_value

    @property
    def total_duration(self) -> timedelta:
        total = self.items.aggregate(total=Sum(F("quantity") * F("duration"), output_field=DurationField()))["total"]
        return total or timedelta()

    @property
    def total_duration_display(self) -> str:
        total_td = self.total_duration
        if not total_td: return "00h 00m"

        ts = int(total_td.total_seconds())
        return f"{ts // 3600:02d}h {(ts % 3600) // 60:02d}m"

    def __str__(self):
        return f"Budget #{self.id} - {self.customer}"


class BudgetImage(TimeStampedModel):
    workshop = models.ForeignKey("workshops.Workshop", on_delete=models.CASCADE, related_name="budget_image")
    budget = models.ForeignKey(Budget, on_delete=models.CASCADE, related_name="budget_image")
    content = models.BinaryField(null=True, blank=True)
    content_name = models.CharField(max_length=100, null=True, blank=True)
    content_type = models.CharField(max_length=100, null=True, blank=True)

    class Meta:
        verbose_name = "Imagem do Orçamento"
        verbose_name_plural = "Imagens do Orçamento"

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
    quantity = models.PositiveIntegerField(verbose_name="Quantidade", default=1)
    service_cost_price = MoneyField(verbose_name="Valor de Custo (Serviço)", max_digits=14, decimal_places=2, default=0)
    product_cost_price = MoneyField(verbose_name="Valor de Custo (Produto)", max_digits=14, decimal_places=2, default=0)
    service_selling_price = MoneyField(verbose_name="Valor de Venda (Serviço)", max_digits=14, decimal_places=2, default=0)
    product_selling_price = MoneyField(verbose_name="Valor de Venda (Produto)", max_digits=14, decimal_places=2, default=0)
    duration = models.DurationField(verbose_name="Duração", null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.pk:
            if self.product:
                self.product_cost_price = self.product.cost_price
                self.product_selling_price = self.product.selling_price

            elif self.service:
                self.service_cost_price = self.service.suggested_cost or Money(0, 'BRL')
                self.service_selling_price = self.service.selling_price
                self.duration = self.service.duration

            elif self.kit:
                self.product_selling_price = sum((kp.product.selling_price * kp.quantity for kp in self.kit.kit_products.all()), Money(0, "BRL"))
                self.service_selling_price = sum((ks.service.selling_price * ks.quantity for ks in self.kit.kit_services.all()), Money(0, "BRL"))

                self.product_cost_price = sum((kp.product.cost_price * kp.quantity for kp in self.kit.kit_products.all()), Money(0, "BRL"))
                self.service_cost_price = sum((ks.service.suggested_cost * ks.quantity for ks in self.kit.kit_services.all() if ks.service.suggested_cost), Money(0, "BRL"))

                self.duration = sum((ks.service.duration for ks in self.kit.kit_services.all()), timedelta())

        super().save(*args, **kwargs)

    @property
    def total_price(self):
        return (self.product_selling_price + self.service_selling_price) * self.quantity


    class Meta:
        verbose_name = "Item do Orçamento"