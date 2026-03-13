from django.db import models
from phonenumber_field.modelfields import PhoneNumberField
from apps.core.models import TimeStampedModel
from localflavor.br.models import BRCNPJField

class Source(TimeStampedModel):
    workshop = models.ForeignKey("workshops.Workshop", on_delete=models.CASCADE, related_name="sources")
    cnpj = BRCNPJField(verbose_name="CNPJ", default="", null=True, blank=True)
    name = models.CharField(verbose_name="Razão Social", max_length=255)
    phone = PhoneNumberField(region="BR", verbose_name="Telefone", max_length=20, default="", null=True, blank=True)
    email = models.EmailField(verbose_name="Email", default="", null=True, blank=True)

    class Meta:
        verbose_name = "Origem"
        verbose_name_plural = "Origens"
        constraints = [
            models.UniqueConstraint(
                fields=("workshop", "name"),
                name="unique_source_name_per_workshop",
            ),
        ]

    def __str__(self) -> str:
        return self.name