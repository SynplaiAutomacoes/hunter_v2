import unicodedata

from django.db import models
from djmoney.models.fields import MoneyField

from apps.core.models import TimeStampedModel
from apps.workshops.models.workshops import Workshop


class PaymentMethod(TimeStampedModel):
    class PaymentType(models.TextChoices):
        CREDIT = "CREDIT", "Crédito"
        DEBIT = "DEBIT", "Débito"
        BOTH = "BOTH", "Ambos"

    workshop = models.ForeignKey(Workshop, on_delete=models.CASCADE, related_name="payment_methods")
    description = models.CharField(verbose_name="Descrição", max_length=100)
    payment_type = models.CharField(verbose_name="Tipo", max_length=10, choices=PaymentType.choices, default=PaymentType.BOTH)
    installments_count = models.PositiveIntegerField(verbose_name="Número de Parcelas", default=1)
    tax_percentage = models.DecimalField(verbose_name="Taxa (%)", max_digits=5, decimal_places=2, null=True, blank=True)
    tax_value = MoneyField(verbose_name="Taxa (R$)", max_digits=14, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(verbose_name="Ativo", default=True)

    class Meta(TimeStampedModel.Meta):  # pyright: ignore[reportIncompatibleVariableOverride]
        verbose_name = "Forma de Pagamento"
        verbose_name_plural = "Formas de Pagamento"
        constraints = [models.UniqueConstraint(fields=("workshop", "description"), name="unique_payment_method_per_workshop")]

    def __str__(self) -> str:
        return self.description

    @classmethod
    def infer_payment_type(cls, description: object) -> str:
        normalized_description = unicodedata.normalize("NFKD", str(description or "").strip()).encode("ascii", "ignore").decode("ascii").upper()

        if "CREDITO" in normalized_description:
            return cls.PaymentType.CREDIT
        if "DEBITO" in normalized_description:
            return cls.PaymentType.DEBIT
        return cls.PaymentType.BOTH
