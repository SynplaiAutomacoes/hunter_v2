from django.db import models

from apps.core.models import TimeStampedModel
from apps.workshops.models.workshops import Workshop

class BankAccount(TimeStampedModel):
    class AccountType(models.TextChoices):
        CORRENTE = "CORRENTE", "Conta Corrente"
        POUPANCA = "POUPANCA", "Conta Poupança"
        PAGAMENTO = "PAGAMENTO", "Conta Pagamento"
        OUTRO = "OUTRO", "Outro"

    workshop = models.ForeignKey(Workshop, on_delete=models.CASCADE, related_name="bank_accounts")
    bank_code = models.CharField(verbose_name="Código do Banco", max_length=10)
    bank_name = models.CharField(verbose_name="Nome do Banco", max_length=255)
    account_type = models.CharField(verbose_name="Tipo de Conta", max_length=20, choices=AccountType.choices, default=AccountType.CORRENTE)
    agency = models.CharField(verbose_name="Agência", max_length=20)
    account_number = models.CharField(verbose_name="Conta Corrente", max_length=30)
    is_active = models.BooleanField(verbose_name="Ativo", default=True)

    class Meta:
        verbose_name = "Conta Bancária"
        verbose_name_plural = "Contas Bancárias"
        constraints = [
            models.UniqueConstraint(fields=("workshop", "bank_code", "account_number"), name="unique_account_per_workshop")
        ]

    def __str__(self):
        return f"{self.bank_name} - {self.account_number}"