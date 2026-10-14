from __future__ import annotations

from typing import Any

from django.contrib.auth.models import AbstractBaseUser

from apps.core.infrastructure.importing.schema import ImportBatchResult
from apps.core.infrastructure.models.data_import import DataImportBatch, DataImportBatchItem
from apps.workshops.models.workshops import Workshop


def persist_import_batch(
    *,
    workshop: Workshop,
    entity_key: str,
    filename: str,
    mapping: dict[str, str],
    options: dict[str, Any] | None,
    user: AbstractBaseUser | None,
    batch_result: ImportBatchResult,
) -> DataImportBatch:
    """Persist import results as a rollbackable batch.

    Successful rows with the same object_id are deduplicated (kits emit the same
    id on multiple rows); the lowest row_number is kept as the canonical item.
    Failed rows are always stored.
    """
    batch = DataImportBatch.objects.create(
        workshop=workshop,
        entity_key=entity_key,
        filename=filename or "",
        options=options or {},
        mapping=mapping or {},
        user=user if user is not None and getattr(user, "is_authenticated", False) else None,
        status=DataImportBatch.Status.COMPLETED,
        success_count=batch_result.success_count,
        error_count=batch_result.error_count,
    )

    items_to_create: list[DataImportBatchItem] = []
    seen_object_ids: set[int] = set()

    # Prefer earliest successful row per object_id.
    successful = sorted(
        [r for r in batch_result.results if r.success and r.created_id is not None],
        key=lambda r: r.row_number,
    )
    for result in successful:
        object_id = int(result.created_id)  # type: ignore[arg-type]
        if object_id in seen_object_ids:
            continue
        seen_object_ids.add(object_id)
        items_to_create.append(
            DataImportBatchItem(
                batch=batch,
                row_number=result.row_number,
                object_id=object_id,
                success=True,
                message=result.message,
                rollback_status=DataImportBatchItem.RollbackStatus.ACTIVE,
            )
        )

    for result in batch_result.results:
        if result.success:
            continue
        items_to_create.append(
            DataImportBatchItem(
                batch=batch,
                row_number=result.row_number,
                object_id=None,
                success=False,
                message=result.message,
                rollback_status=DataImportBatchItem.RollbackStatus.ACTIVE,
            )
        )

    if items_to_create:
        DataImportBatchItem.objects.bulk_create(items_to_create)

    return batch
