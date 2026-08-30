from django.db import models
from django.conf import settings
from apps.core.infrastructure.models import TimeStampedModel
from decimal import Decimal, ROUND_HALF_UP
from djmoney.models.fields import MoneyField
from djmoney.money import Money


class MovementGroup(TimeStampedModel):
    workshop = models.ForeignKey("workshops.Workshop", on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    name = models.CharField(verbose_name="Nome", max_length=255)
    description = models.TextField(verbose_name="Descrição", blank=True, null=True)
    due_date = models.DateField(verbose_name="Data de Vencimento")
    gross_amount = MoneyField(verbose_name="Valor Bruto", max_digits=14, decimal_places=2, default=0)
    discount_mode = models.CharField(
        verbose_name="Tipo de Desconto",
        max_length=12,
        choices=[("NONE", "Sem desconto"), ("AMOUNT", "Desconto em reais (R$)"), ("PERCENTAGE", "Desconto em percentual (%)")],
        default="NONE",
    )
    discount_value = MoneyField(verbose_name="Desconto (R$)", max_digits=14, decimal_places=2, default=0)
    discount_percentage = models.DecimalField(verbose_name="Desconto (%)", max_digits=7, decimal_places=4, default=Decimal("0.00"))
    net_amount = MoneyField(verbose_name="Valor Líquido", max_digits=14, decimal_places=2, default=0)
    
    supplier = models.ForeignKey("suppliers.Supplier", on_delete=models.SET_NULL, null=True, blank=True, related_name="movement_groups")
    collaborator = models.ForeignKey("collaborators.WorkshopCollaborator", on_delete=models.SET_NULL, null=True, blank=True, related_name="movement_groups")

    def __str__(self):
        return self.name

    def sync_net_amount(self) -> None:
        gross_value = Decimal(str(self.gross_amount.amount or 0))
        discount_amount = Decimal("0.00")
        if self.discount_mode == "AMOUNT":
            discount_amount = Decimal(str(self.discount_value.amount or 0))
        elif self.discount_mode == "PERCENTAGE":
            discount_amount = gross_value * Decimal(str(self.discount_percentage or 0)) / Decimal("100")

        discount_amount = min(max(discount_amount, Decimal("0.00")), gross_value)
        self.net_amount = Money(
            (gross_value - discount_amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            self.gross_amount.currency,
        )
