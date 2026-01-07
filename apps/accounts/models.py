from __future__ import annotations

from django.conf import settings
from django.contrib.auth.models import AbstractUser, Permission
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


class WorkshopRole(TimeStampedModel):
    account = models.ForeignKey(
        "accounts.Account",
        on_delete=models.CASCADE,
        related_name="workshop_roles",
    )
    name = models.CharField(verbose_name="Nome", max_length=255)
    permissions = models.ManyToManyField(
        Permission,
        blank=True,
        related_name="workshop_roles",
        verbose_name="Permissões",
    )
    is_system = models.BooleanField(default=False)
    is_editable = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("account", "name"),
                name="unique_workshop_role_per_account",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.account})"


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
        "accounts.WorkshopRole",
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

    def __str__(self):
        return f"{self.user} @ {self.workshop} ({self.role})"


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
        through="WorkshopMember",
        related_name="users",
        blank=True,
    )
