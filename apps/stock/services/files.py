from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache

from django.utils import timezone

from apps.core.infrastructure.services.storage import StorageConfigurationError, StorageServiceError, get_storage_service


class StockImportFileStorageError(Exception):
    pass


@dataclass(frozen=True)
class StoredImportXmlFile:
    file_id: str
    filename: str
    content_type: str
    content: bytes
    workshop_id: int
    uploaded_at: datetime | None


class StockImportS3FileService:
    def save_file(self, *, content: bytes, filename: str, content_type: str, workshop_id: int, nf_key: str) -> StoredImportXmlFile:
        if workshop_id <= 0:
            raise StockImportFileStorageError("Oficina invalida para salvar arquivo no bucket.")

        if not nf_key:
            raise StockImportFileStorageError("Chave da NF-e é obrigatória para salvar o XML no bucket.")

        normalized_filename = _normalize_xml_filename(filename, nf_key)
        normalized_content_type = _normalize_content_type(content_type=content_type)
        uploaded_at = timezone.now()
        key = _build_storage_key(workshop_id=workshop_id, nf_key=nf_key, filename=normalized_filename)

        try:
            get_storage_service().upload_file(
                content,
                key,
                content_type=normalized_content_type,
                metadata={
                    "filename": normalized_filename,
                    "workshop_id": str(workshop_id),
                    "nf_key": nf_key,
                    "uploaded_at": uploaded_at.isoformat(),
                    "kind": "import_nfe_xml",
                },
            )
        except (StorageConfigurationError, StorageServiceError) as exc:
            raise StockImportFileStorageError(str(exc)) from exc

        return StoredImportXmlFile(
            file_id=key,
            filename=normalized_filename,
            content_type=normalized_content_type,
            content=content,
            workshop_id=workshop_id,
            uploaded_at=uploaded_at,
        )

    def read_file(self, *, file_id: str) -> StoredImportXmlFile:
        normalized_file_id = str(file_id or "").strip()
        if not normalized_file_id:
            raise StockImportFileStorageError("Identificador invalido do arquivo salvo no bucket.")

        try:
            stored_object = get_storage_service().read_file(normalized_file_id)
        except (StorageConfigurationError, StorageServiceError) as exc:
            raise StockImportFileStorageError("Arquivo nao encontrado no bucket configurado.") from exc

        filename = stored_object.metadata.get("filename") or "NF-e.xml"
        content_type = _normalize_content_type(content_type=stored_object.content_type)
        workshop_id = int(stored_object.metadata.get("workshop_id", 0))
        uploaded_at = _parse_datetime(stored_object.metadata.get("uploaded_at"))

        return StoredImportXmlFile(
            file_id=normalized_file_id,
            filename=filename,
            content_type=content_type,
            content=stored_object.content,
            workshop_id=workshop_id,
            uploaded_at=uploaded_at,
        )

    def delete_file(self, *, file_id: str) -> None:
        normalized_file_id = str(file_id or "").strip()
        if not normalized_file_id:
            return

        try:
            get_storage_service().delete_file(normalized_file_id)
        except (StorageConfigurationError, StorageServiceError):
            pass

    def generate_presigned_url(self, *, file_id: str, expires_in: int = 3600) -> str:
        normalized_file_id = str(file_id or "").strip()
        if not normalized_file_id:
            raise StockImportFileStorageError("Identificador invalido do arquivo salvo no bucket.")

        try:
            return get_storage_service().generate_presigned_url(normalized_file_id, expires_in=expires_in)
        except (StorageConfigurationError, StorageServiceError) as exc:
            raise StockImportFileStorageError(str(exc)) from exc


def _parse_datetime(value: object) -> datetime | None:
    normalized_value = str(value or "").strip()
    if not normalized_value:
        return None

    try:
        return datetime.fromisoformat(normalized_value)
    except ValueError:
        return None


def _normalize_xml_filename(original_name: str, nf_key: str) -> str:
    clean_key = "".join(c for c in nf_key if c.isdigit()) or "unknown"
    return f"NF-{clean_key}.xml"


def _normalize_content_type(*, content_type: object) -> str:
    normalized = str(content_type or "").strip().lower()
    if normalized in {"application/xml", "text/xml"}:
        return "application/xml"
    return "application/xml"


def _build_storage_key(*, workshop_id: int, nf_key: str, filename: str) -> str:
    return f"workshops/{workshop_id}/nfes/{nf_key}/{uuid.uuid4().hex}-{filename}"


@lru_cache(maxsize=1)
def get_stock_import_file_service() -> StockImportS3FileService:
    try:
        get_storage_service()
    except StorageConfigurationError as exc:
        raise StockImportFileStorageError(str(exc)) from exc
    return StockImportS3FileService()


def save_import_xml_file(*, content: bytes, filename: str, content_type: str, workshop_id: int, nf_key: str) -> StoredImportXmlFile:
    return get_stock_import_file_service().save_file(
        content=content,
        filename=filename,
        content_type=content_type,
        workshop_id=workshop_id,
        nf_key=nf_key,
    )


def read_import_xml_file(*, file_id: str) -> StoredImportXmlFile:
    return get_stock_import_file_service().read_file(file_id=file_id)


def delete_import_xml_file(*, file_id: str) -> None:
    get_stock_import_file_service().delete_file(file_id=file_id)
