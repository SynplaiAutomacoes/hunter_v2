from __future__ import annotations

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q
from localflavor.br.models import BRCPFField

from apps.core.models import TimeStampedModel


class Account(TimeStampedModel):
    name = models.CharField(verbose_name="Conta", max_length=255)
    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="owned_account",
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "Conta"
        verbose_name_plural = "Contas"

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
    is_account_owner = models.BooleanField(default=False)  # Util para constraint
    cpf = BRCPFField(unique=False, null=False, blank=False)
    workshops = models.ManyToManyField(
        "workshops.Workshop",
        through="collaborators.WorkshopMember",
        related_name="users",
        blank=True,
    )

    class Meta(AbstractUser.Meta):
        verbose_name = "Usuário"
        verbose_name_plural = "Usuários"
        constraints = [
            models.UniqueConstraint(
                fields=("cpf",),
                condition=Q(is_account_owner=True),
                name="unique_owner_cpf",
            ),
        ]
