from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from apps.core.models import TimeStampedModel
from djmoney.models.fields import MoneyField


class BudgetStatus(models.TextChoices):
    DRAFT = "draft", "Em Aberto"
    APPROVED = "approved", "Aprovado"
    REJECTED = "rejected", "Rejeitado"
    CANCELLED = "cancelled", "Cancelado"
    FINISHED = "finished", "Concluído"


class Budget(TimeStampedModel):
    workshop = models.ForeignKey("workshops.Workshop", verbose_name="Oficina", on_delete=models.CASCADE, related_name="budgets")
    customer = models.ForeignKey("customer.Customer", verbose_name="Cliente", on_delete=models.SET_NULL, related_name="budgets", null=True)
    vehicle = models.ForeignKey("customer.Vehicle", verbose_name="Veículo", on_delete=models.SET_NULL, related_name="budgets", null=True)
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
    # TODO add "sintomas_identificados" field

    # Financeiro
    base_value = MoneyField(verbose_name="Valor Subtotal", max_digits=14, decimal_places=2, default=0.00)
    discount_value = MoneyField(verbose_name="Valor de Desconto", max_digits=14, decimal_places=2, default=0.00)
    total_value = MoneyField(verbose_name="Valor Total", max_digits=14, decimal_places=2, default=0.00)

    # Margens e Ajustes
    profit_margin_parts = models.DecimalField(verbose_name="Percentual Lucro de Peças", max_digits=5, decimal_places=2, default=0.00)
    profit_margin_labor = models.DecimalField(verbose_name="Percentual Lucro de Mão de Obra", max_digits=5, decimal_places=2, default=0.00)
    slider = models.SmallIntegerField(verbose_name="Slider", default=0, validators=[MinValueValidator(-100), MaxValueValidator(100)], help_text="Negativo: Peça | Positivo: Mão de Obra")

    # Status e Controle
    status = models.CharField(verbose_name="Status", max_length=20, choices=BudgetStatus.choices, default=BudgetStatus.DRAFT)
    cancellation_reason = models.CharField(verbose_name="Motivo do Cancelamento", max_length=255, blank=True, null=True)
    current_step = models.PositiveSmallIntegerField(verbose_name="Etapa Atual", default=1)

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

    def __str__(self):
        return f"Budget #{self.id} - {self.customer}"