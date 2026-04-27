from __future__ import annotations

import mimetypes
import uuid
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache

from django.core.files.uploadedfile import UploadedFile
from django.utils import timezone
from django.utils.text import get_valid_filename

from apps.core.services.storage_service import StorageConfigurationError, StorageServiceError, get_storage_service


class ChecklistFileStorageError(Exception):
    pass


@dataclass(frozen=True)
class StoredChecklistFile:
    file_id: str
    filename: str
    content_type: str
    content: bytes
    uploaded_at: datetime | None


class ChecklistS3FileService:
    def save_file(self, *, content: bytes, filename: str, content_type: str, workshop_id: int) -> StoredChecklistFile:
        if workshop_id <= 0:
            raise ChecklistFileStorageError("Oficina invalida para salvar arquivo no bucket.")

        normalized_filename = _normalize_filename(filename)
        normalized_content_type = _normalize_content_type(filename=normalized_filename, content_type=content_type)
        uploaded_at = timezone.now()
        key = _build_storage_key(workshop_id=workshop_id, filename=normalized_filename)

        try:
            get_storage_service().upload_file(
                content,
                key,
                content_type=normalized_content_type,
                metadata={
                    "filename": normalized_filename,
                    "uploaded_at": uploaded_at.isoformat(),
                    "kind": "checklist_pdf",
                },
            )
        except (StorageConfigurationError, StorageServiceError) as exc:
            raise ChecklistFileStorageError(str(exc)) from exc

        return StoredChecklistFile(
            file_id=key,
            filename=normalized_filename,
            content_type=normalized_content_type,
            content=content,
            uploaded_at=uploaded_at,
        )

    def read_file(self, *, file_id: str) -> StoredChecklistFile:
        normalized_file_id = str(file_id or "").strip()
        if not normalized_file_id:
            raise ChecklistFileStorageError("Identificador invalido do arquivo salvo no bucket.")

        try:
            stored_object = get_storage_service().read_file(normalized_file_id)
        except (StorageConfigurationError, StorageServiceError) as exc:
            raise ChecklistFileStorageError("Arquivo nao encontrado no bucket configurado. Envie o arquivo novamente.") from exc

        filename = _normalize_filename(stored_object.metadata.get("filename") or "checklist.pdf")
        content_type = _normalize_content_type(filename=filename, content_type=stored_object.content_type)
        uploaded_at = _parse_datetime(stored_object.metadata.get("uploaded_at"))

        return StoredChecklistFile(
            file_id=normalized_file_id,
            filename=filename,
            content_type=content_type,
            content=stored_object.content,
            uploaded_at=uploaded_at,
        )

    def delete_file(self, *, file_id: str) -> None:
        normalized_file_id = str(file_id or "").strip()
        if not normalized_file_id:
            return

        try:
            get_storage_service().delete_file(normalized_file_id)
        except (StorageConfigurationError, StorageServiceError) as exc:
            raise ChecklistFileStorageError(str(exc)) from exc


def _parse_datetime(value: object) -> datetime | None:
    normalized_value = str(value or "").strip()
    if not normalized_value:
        return None

    try:
        return datetime.fromisoformat(normalized_value)
    except ValueError:
        return None


def _normalize_filename(raw_name: object) -> str:
    normalized_name = str(raw_name or "").replace("\\", "/").split("/")[-1].strip()
    base_name = get_valid_filename(normalized_name or "checklist.pdf")
    if not base_name.lower().endswith(".pdf"):
        stem = base_name.rsplit(".", 1)[0] if "." in base_name else base_name
        base_name = f"{stem}.pdf"
    return base_name or "checklist.pdf"


def _normalize_content_type(*, filename: str, content_type: object) -> str:
    normalized_content_type = str(content_type or "").strip().lower()
    if normalized_content_type in {"application/pdf", "application/x-pdf"}:
        return "application/pdf"

    guessed_type = mimetypes.guess_type(filename)[0]
    if guessed_type:
        return guessed_type
    return "application/pdf"


def _build_storage_key(*, workshop_id: int, filename: str) -> str:
    return f"workshop/{workshop_id}/pdfs/{uuid.uuid4().hex}-{filename}"


def _read_uploaded_pdf(uploaded_file: UploadedFile) -> tuple[bytes, str, str]:
    filename = _normalize_filename(getattr(uploaded_file, "name", ""))
    content = uploaded_file.read()
    if not content:
        raise ChecklistFileStorageError("O arquivo enviado esta vazio.")

    content_type = _normalize_content_type(filename=filename, content_type=getattr(uploaded_file, "content_type", ""))
    if content_type != "application/pdf":
        raise ChecklistFileStorageError("Envie um arquivo PDF valido.")

    return content, filename, content_type


@lru_cache(maxsize=1)
def get_checklist_file_service() -> ChecklistS3FileService:
    try:
        get_storage_service()
    except StorageConfigurationError as exc:
        raise ChecklistFileStorageError(str(exc)) from exc
    return ChecklistS3FileService()


def save_checklist_pdf_file(*, workshop_id: int, uploaded_file: UploadedFile) -> StoredChecklistFile:
    content, filename, content_type = _read_uploaded_pdf(uploaded_file)
    return get_checklist_file_service().save_file(content=content, filename=filename, content_type=content_type, workshop_id=workshop_id)


def read_checklist_pdf_file(*, file_id: str) -> StoredChecklistFile:
    return get_checklist_file_service().read_file(file_id=file_id)


def delete_checklist_pdf_file(*, file_id: str) -> None:
    get_checklist_file_service().delete_file(file_id=file_id)
