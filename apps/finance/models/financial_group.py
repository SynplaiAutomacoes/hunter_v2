from __future__ import annotations

from typing import Any, cast

from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction

from apps.core.models import TimeStampedModel
from apps.workshops.models.workshops import Workshop


class FinancialGroup(TimeStampedModel):
    SORT_SEGMENT_WIDTH = 6
    MAX_HIERARCHY_RETRIES = 5

    workshop = models.ForeignKey(
        Workshop,
        verbose_name="Oficina",
        on_delete=models.CASCADE,
        related_name="financial_groups",
    )
    parent = models.ForeignKey(
        "self",
        verbose_name="Grupo pai",
        on_delete=models.PROTECT,
        related_name="children",
        null=True,
        blank=True,
    )
    name = models.CharField(verbose_name="Nome", max_length=255)
    code = models.CharField(verbose_name="Código", max_length=255, editable=False)
    sequence = models.PositiveIntegerField(verbose_name="Sequência", editable=False)
    level = models.PositiveIntegerField(verbose_name="Nível", editable=False)
    sort_key = models.CharField(verbose_name="Chave de ordenação", max_length=255, editable=False)
    is_active = models.BooleanField(verbose_name="Ativo", default=True)

    class Meta(TimeStampedModel.Meta):
        verbose_name = "Grupo Financeiro"
        verbose_name_plural = "Grupos Financeiros"
        ordering = ["sort_key", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=("workshop", "parent", "sequence"),
                name="unique_financial_group_sequence_per_parent",
            ),
            models.UniqueConstraint(
                fields=("workshop", "code"),
                name="unique_financial_group_code_per_workshop",
            ),
            models.UniqueConstraint(
                fields=("workshop", "sort_key"),
                name="unique_financial_group_sort_key_per_workshop",
            ),
        ]
        indexes = [
            models.Index(fields=["workshop", "parent"]),
            models.Index(fields=["workshop", "sort_key"]),
            models.Index(fields=["workshop", "is_active"]),
        ]

    def __str__(self) -> str:
        if self.code:
            return f"{self.code} {self.name}"
        return self.name

    @property
    def parent_display(self) -> str:
        if not getattr(self, "parent_id", None):
            return "-"
        return str(self.parent)

    def clean(self) -> None:
        super().clean()
        self._validate_parent_rules()

    def save(self, *args: Any, **kwargs: Any) -> None:
        self._validate_parent_rules()

        if not self._state.adding:
            super().save(*args, **kwargs)
            return

        last_error: IntegrityError | None = None
        for _ in range(self.MAX_HIERARCHY_RETRIES):
            try:
                with transaction.atomic():
                    parent = self._get_locked_parent()
                    next_sequence = self._get_next_sequence(parent=parent)

                    self.sequence = next_sequence
                    self.level = 1 if parent is None else parent.level + 1
                    self.code = self._build_code(parent=parent, sequence=next_sequence)
                    self.sort_key = self._build_sort_key(parent=parent, sequence=next_sequence)

                    super().save(*args, **kwargs)
                    return
            except IntegrityError as exc:
                last_error = exc
                self.sequence = 0
                self.level = 0
                self.code = ""
                self.sort_key = ""

        if last_error is not None:
            raise last_error

    def _validate_parent_rules(self) -> None:
        parent_id = getattr(self, "parent_id", None)
        workshop_id = getattr(self, "workshop_id", None)
        parent = self._get_parent_instance()

        if parent_id and parent is None:
            raise ValidationError({"parent": "Selecione um grupo pai válido."})

        if parent_id and self.pk and parent_id == self.pk:
            raise ValidationError({"parent": "O grupo pai não pode ser o próprio grupo."})

        if parent is not None and workshop_id and getattr(parent, "workshop_id", None) != workshop_id:
            raise ValidationError({"parent": "O grupo pai precisa pertencer à mesma oficina."})

        if not self.pk:
            return

        original = type(self).objects.filter(pk=self.pk).only("parent_id").first()
        if original is not None and getattr(original, "parent_id", None) != parent_id:
            raise ValidationError({"parent": "Alterar o grupo pai ainda não é suportado."})

    def _get_parent_instance(self) -> FinancialGroup | None:
        parent_id = getattr(self, "parent_id", None)
        if not parent_id:
            return None

        parent = getattr(self, "parent", None)
        if parent is not None and getattr(parent, "pk", None) == parent_id:
            return cast(FinancialGroup, parent)

        return cast(
            FinancialGroup | None,
            type(self).objects.filter(pk=parent_id).only("id", "workshop_id", "code", "sort_key", "level").first(),
        )

    def _get_locked_parent(self) -> FinancialGroup | None:
        parent_id = getattr(self, "parent_id", None)
        if not parent_id:
            return None

        parent = type(self).objects.select_for_update().only("id", "workshop_id", "code", "sort_key", "level").get(pk=parent_id)
        self.parent = parent
        return parent

    def _get_next_sequence(self, *, parent: FinancialGroup | None) -> int:
        max_sequence = type(self).objects.select_for_update().filter(workshop=self.workshop, parent=parent).aggregate(max_sequence=models.Max("sequence")).get("max_sequence") or 0
        return max_sequence + 1

    def _build_code(self, *, parent: FinancialGroup | None, sequence: int) -> str:
        if parent is None:
            return str(sequence)
        return f"{parent.code}.{sequence}"

    def _build_sort_key(self, *, parent: FinancialGroup | None, sequence: int) -> str:
        segment = f"{sequence:0{self.SORT_SEGMENT_WIDTH}d}"
        if parent is None:
            return segment
        return f"{parent.sort_key}.{segment}"
