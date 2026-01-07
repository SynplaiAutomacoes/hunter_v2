from django.conf import settings
from django.db import models
from django.db.models import CharField, BooleanField
from localflavor.br.models import BRCNPJField

from apps.core.models import TimeStampedModel


class Workshop(TimeStampedModel):
    account = models.ForeignKey(
        "accounts.Account",
        on_delete=models.PROTECT,
        related_name="workshops",
        null=True,
        blank=True,
    )
    name = CharField(verbose_name="Nome", max_length=255, null=False, blank=False)
    cnpj = BRCNPJField(verbose_name="CNPJ", null=True, blank=True, unique=True)
    is_active = BooleanField(verbose_name="Ativa", default=True)

    def __str__(self):
        return self.name


class WorkshopMember(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="workshop_members",
    )
    workshop = models.ForeignKey(
        Workshop,
        on_delete=models.CASCADE,
        related_name="members",
    )
    role = models.ForeignKey(
        "iam.WorkshopRole",
        on_delete=models.PROTECT,
        related_name="workshop_members",
        null=True,
        blank=True,
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("user", "workshop"),
                name="unique_user_workshop_member",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user} @ {self.workshop} ({self.role})"
