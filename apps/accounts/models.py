from __future__ import annotations

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q
from localflavor.br.models import BRCPFField

from apps.core.models import TimeStampedModel
from apps.workshops.models import Workshop


# TODO: Checar se Account preisa ser null e blank
class Account(TimeStampedModel):
    name = models.CharField(verbose_name="Conta", max_length=255)
    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="owned_account",
        null=True,
        blank=True,
    )

    def __str__(self) -> str:
        return self.name


# TODO: Checar se realmente preciso de is_account_owner
class User(AbstractUser):
    account = models.ForeignKey(
        "accounts.Account",
        on_delete=models.PROTECT,
        related_name="users",
        null=True,
        blank=True,
    )
    is_account_owner = models.BooleanField(default=False)
    cpf = BRCPFField(unique=False, null=False, blank=False)
    workshops = models.ManyToManyField(
        Workshop,
        through="workshops.WorkshopMember",
        related_name="users",
        blank=True,
    )

    class Meta(AbstractUser.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=("cpf",),
                condition=Q(is_account_owner=True),
                name="unique_owner_cpf",
            ),
        ]
