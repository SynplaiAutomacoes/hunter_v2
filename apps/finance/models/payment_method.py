from django.db import models

from apps.core.models import TimeStampedModel
from apps.workshops.models.workshops import Workshop


class PaymentMethod(TimeStampedModel):
    workshop = models.ForeignKey(Workshop, on_delete=models.CASCADE, related_name="payment_methods")
    description = models.CharField(verbose_name="Descrição", max_length=100)
    is_active = models.BooleanField(verbose_name="Ativo", default=True)

    class Meta:
        verbose_name = "Forma de Pagamento"
        verbose_name_plural = "Formas de Pagamento"
        constraints = [
            models.UniqueConstraint(fields=("workshop", "description"), name="unique_payment_method_per_workshop")
        ]

    def __str__(self):
        return self.description