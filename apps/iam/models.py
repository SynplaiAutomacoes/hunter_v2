from __future__ import annotations

from django.contrib.auth.models import Permission
from django.db import models

from apps.accounts.models import Account
from apps.core.models import TimeStampedModel


class WorkshopRole(TimeStampedModel):
    """Grupo de permissões reutilizável dentro de uma `Account` (tenant)."""

    account = models.ForeignKey(
        Account,
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
        verbose_name = "Cargo da Oficina"
        verbose_name_plural = "Cargos da Oficina"
        constraints = [
            models.UniqueConstraint(
                fields=("account", "name"),
                name="unique_workshop_role_per_account",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.account})"
