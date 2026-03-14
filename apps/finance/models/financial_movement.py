from django.db import models

from apps.core.models import TimeStampedModel
from djmoney.models.fields import MoneyField

from django.conf import settings

from apps.finance.models import PaymentMethod, FinancialGroup
from apps.finance.models.bank_account import BankAccount


class FinancialMovement(TimeStampedModel):
    class MovementDirection(models.TextChoices):
        CREDIT = "CREDIT", "Crédito"
        DEBIT = "DEBIT", "Débito"

    workshop = models.ForeignKey(to="workshops.Workshop", on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    current_step = models.PositiveSmallIntegerField(default=1)

    # Origem
    source = models.ForeignKey(to="sources.Source", verbose_name="Origem", on_delete=models.PROTECT)

    # Itens
    description = models.CharField(verbose_name="Descrição dos Itens", max_length=255, blank=True, null=True)
    items_observation = models.TextField(verbose_name="Observações dos Itens", blank=True, null=True)

    # Financeiro
    direction = models.CharField(max_length=15, verbose_name="Tipo", choices=MovementDirection.choices, default=MovementDirection.DEBIT, blank=True, null=True)
    payment_method = models.ForeignKey(PaymentMethod, verbose_name="Forma de Pagamento", on_delete=models.PROTECT, blank=True, null=True)
    nf_number = models.CharField(max_length=50, verbose_name="Número da NF", blank=True, null=True)
    amount = MoneyField(verbose_name="Valor", max_digits=14, decimal_places=2, default=0, null=True)
    due_date = models.DateField(verbose_name="Data de Vencimento", blank=True, null=True)
    budget_plan = models.ForeignKey(FinancialGroup, on_delete=models.PROTECT, verbose_name="Plano Orçamentário", blank=True, null=True)
    bank_account = models.ForeignKey(BankAccount, on_delete=models.PROTECT, verbose_name="Conta Bancária", blank=True, null=True)
    attachment = models.FileField(upload_to="financial/attachments/", null=True, blank=True, verbose_name="Anexo")
    financial_observation = models.TextField(verbose_name="Observação Financeira", blank=True, null=True)
