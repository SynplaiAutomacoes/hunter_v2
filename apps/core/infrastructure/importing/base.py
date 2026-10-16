from __future__ import annotations

from typing import Any, Protocol

from django.contrib.auth.models import AbstractBaseUser

from apps.core.infrastructure.importing.schema import ImportBatchResult, ImportEntitySchema, ImportRowError, ImportRowResult
from apps.workshops.models.workshops import Workshop


class ImportAdapter(Protocol):
    entity_key: str
    label: str
    permission_app_label: str
    permission_model: str
    permission_codename: str

    def get_schema(self, workshop: Workshop, *, options: dict[str, Any] | None = None) -> ImportEntitySchema: ...

    def import_rows(
        self,
        workshop: Workshop,
        mapped_rows: list[tuple[int, dict[str, Any]]],
        *,
        user: AbstractBaseUser | None = None,
        options: dict[str, Any] | None = None,
    ) -> ImportBatchResult: ...


class BaseRowImportAdapter:
    """Default adapter: one create_row call per mapped row inside its own transaction."""

    entity_key: str
    label: str
    permission_app_label: str
    permission_model: str
    permission_codename: str

    def get_schema(self, workshop: Workshop, *, options: dict[str, Any] | None = None) -> ImportEntitySchema:
        raise NotImplementedError

    def create_row(
        self,
        workshop: Workshop,
        mapped: dict[str, Any],
        *,
        user: AbstractBaseUser | None = None,
        options: dict[str, Any] | None = None,
    ) -> int | None:
        raise NotImplementedError

    def import_rows(
        self,
        workshop: Workshop,
        mapped_rows: list[tuple[int, dict[str, Any]]],
        *,
        user: AbstractBaseUser | None = None,
        options: dict[str, Any] | None = None,
    ) -> ImportBatchResult:
        from django.db import IntegrityError, transaction

        batch = ImportBatchResult()
        for row_number, mapped in mapped_rows:
            try:
                with transaction.atomic():
                    created_id = self.create_row(workshop, mapped, user=user, options=options)
                batch.add(
                    ImportRowResult(
                        row_number=row_number,
                        success=True,
                        message="Criado com sucesso.",
                        created_id=created_id,
                    )
                )
            except ImportRowError as exc:
                batch.add(ImportRowResult(row_number=row_number, success=False, message=exc.message))
            except IntegrityError:
                batch.add(
                    ImportRowResult(
                        row_number=row_number,
                        success=False,
                        message="Registro duplicado ou conflito de unicidade nesta oficina.",
                    )
                )
            except Exception as exc:  # noqa: BLE001 - surface per-row failure without aborting batch
                batch.add(ImportRowResult(row_number=row_number, success=False, message=str(exc) or "Erro inesperado."))
        return batch
