from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from djmoney.models.fields import MoneyField

from apps.core.infrastructure.models import TimeStampedModel


class FinancialTransfer(TimeStampedModel):
    """Internal transfer between two bank accounts of the same workshop."""

    workshop = models.ForeignKey("workshops.Workshop", on_delete=models.CASCADE, related_name="financial_transfers")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    source_account = models.ForeignKey("finance.BankAccount", on_delete=models.PROTECT, related_name="outgoing_transfers")
    destination_account = models.ForeignKey("finance.BankAccount", on_delete=models.PROTECT, related_name="incoming_transfers")
    reversal_of = models.OneToOneField("self", on_delete=models.PROTECT, null=True, blank=True, related_name="reversal_entry")
    transfer_date = models.DateField(verbose_name="Data da transferência", default=timezone.localdate)
    amount = MoneyField(verbose_name="Valor", max_digits=14, decimal_places=2)
    description = models.TextField(verbose_name="Observação", blank=True)

    class Meta(TimeStampedModel.Meta):
        verbose_name = "Transferência entre contas"
        verbose_name_plural = "Transferências entre contas"
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(source_account=models.F("destination_account")),
                name="financial_transfer_distinct_accounts",
            ),
        ]
        indexes = [models.Index(fields=["workshop", "transfer_date"])]

    def clean(self) -> None:
        super().clean()
        if self.source_account_id and self.destination_account_id and self.source_account_id == self.destination_account_id:
            raise ValidationError("A conta de origem deve ser diferente da conta de destino.")
        for field_name in ("source_account", "destination_account"):
            account = getattr(self, field_name, None)
            if account is not None and self.workshop_id and account.workshop_id != self.workshop_id:
                raise ValidationError({field_name: "Selecione uma conta cadastrada nesta oficina."})

    def __str__(self) -> str:
        return f"{self.source_account} → {self.destination_account}"
