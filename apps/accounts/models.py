from __future__ import annotations

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from localflavor.br.models import BRCPFField

from apps.core.models import TimeStampedModel
from apps.workshops.models import Workshop


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


class User(AbstractUser):
    account = models.ForeignKey(
        "accounts.Account",
        on_delete=models.PROTECT,
        related_name="users",
        null=True,
        blank=True,
    )
    cpf = BRCPFField(unique=True, null=False, blank=False)
    workshops = models.ManyToManyField(
        Workshop,
        through="workshops.WorkshopMember",
        related_name="users",
        blank=True,
    )
