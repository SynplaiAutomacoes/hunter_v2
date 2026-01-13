from __future__ import annotations

from django.db import models


class CatalogGroup(models.Model):
    workshop = models.ForeignKey(
        "workshops.Workshop",
        on_delete=models.CASCADE,
        related_name="catalog_groups",
    )
    name = models.CharField(verbose_name="Nome", max_length=255)

    class Meta:
        verbose_name = "Grupo"
        verbose_name_plural = "Grupos"
        constraints = [
            models.UniqueConstraint(
                fields=("workshop", "name"),
                name="unique_group_name_per_workshop",
            ),
        ]

    def __str__(self) -> str:
        return self.name
