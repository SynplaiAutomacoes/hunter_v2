from __future__ import annotations

import base64
import logging
import mimetypes
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from tempfile import NamedTemporaryFile
from typing import Iterator, Literal

from bson import ObjectId
from bson.errors import InvalidId
from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.utils import timezone
from gridfs import GridFSBucket
from gridfs.errors import NoFile
from pymongo import MongoClient

from apps.finance.models.finance import WebmaniaCompany
from apps.finance.services.webmania_b2b import update_webmania_company
from apps.finance.services.webmania_secrets import decrypt_secret, encrypt_secret
from apps.workshops.models.workshops import Workshop


logger = logging.getLogger(__name__)

StoredFileKind = Literal["certificate", "logo"]


class WorkshopFileStorageError(Exception):
    pass


class WorkshopFileSyncError(Exception):
    pass


@dataclass(frozen=True)
class StoredWorkshopFile:
    file_id: str
    filename: str
    content_type: str
    content: bytes
    uploaded_at: datetime | None


@dataclass(frozen=True)
class _BufferedUpload:
    filename: str
    content_type: str
    content: bytes


class WorkshopMongoFileService:
    def __init__(
        self,
        *,
        mongo_uri: str,
        database_name: str,
        certificate_bucket: str,
        logo_bucket: str,
    ) -> None:
        normalized_uri = str(mongo_uri or "").strip()
        if not normalized_uri:
            raise WorkshopFileStorageError("Configure MONGODB_URI para salvar arquivos da oficina no MongoDB.")

        self.client = MongoClient(normalized_uri)
        self.database = self.client[database_name]
        self.bucket_names = {
            "certificate": certificate_bucket,
            "logo": logo_bucket,
        }

    def _get_bucket(self, *, kind: StoredFileKind) -> GridFSBucket:
        return GridFSBucket(self.database, bucket_name=self.bucket_names[kind])

    def save_file(
        self,
        *,
        kind: StoredFileKind,
        content: bytes,
        filename: str,
        content_type: str,
        workshop_id: int,
    ) -> StoredWorkshopFile:
        uploaded_at = timezone.now()
        metadata = {
            "workshop_id": workshop_id,
            "content_type": content_type,
            "uploaded_at": uploaded_at.isoformat(),
            "kind": kind,
        }
        file_id = self._get_bucket(kind=kind).upload_from_stream(filename, content, metadata=metadata)
        return StoredWorkshopFile(
            file_id=str(file_id),
            filename=filename,
            content_type=content_type,
            content=content,
            uploaded_at=uploaded_at,
        )

    def read_file(self, *, kind: StoredFileKind, file_id: str) -> StoredWorkshopFile:
        bucket = self._get_bucket(kind=kind)
        try:
            object_id = ObjectId(str(file_id or "").strip())
        except (InvalidId, TypeError) as exc:
            raise WorkshopFileStorageError("Identificador invalido do arquivo salvo no MongoDB.") from exc

        try:
            download_stream = bucket.open_download_stream(object_id)
        except NoFile as exc:
            raise WorkshopFileStorageError("Arquivo nao encontrado no MongoDB. Envie o arquivo novamente na gestao da oficina.") from exc

        metadata = download_stream.metadata or {}
        uploaded_at = _parse_datetime(metadata.get("uploaded_at"))
        filename = str(download_stream.filename or "arquivo.bin")
        content_type = _normalize_content_type(
            filename=filename,
            content_type=metadata.get("content_type"),
            default_content_type=_default_content_type(kind=kind, filename=filename),
        )

        return StoredWorkshopFile(
            file_id=str(object_id),
            filename=filename,
            content_type=content_type,
            content=download_stream.read(),
            uploaded_at=uploaded_at,
        )

    def delete_file(self, *, kind: StoredFileKind, file_id: str) -> None:
        normalized_file_id = str(file_id or "").strip()
        if not normalized_file_id:
            return

        try:
            self._get_bucket(kind=kind).delete(ObjectId(normalized_file_id))
        except (InvalidId, NoFile):
            return


def _parse_datetime(value: object) -> datetime | None:
    raw_value = str(value or "").strip()
    if not raw_value:
        return None

    try:
        return datetime.fromisoformat(raw_value)
    except ValueError:
        return None


def _default_content_type(*, kind: StoredFileKind, filename: str) -> str:
    guessed_type = mimetypes.guess_type(filename)[0]
    if guessed_type:
        return guessed_type
    if kind == "certificate":
        return "application/x-pkcs12"
    return "application/octet-stream"


def _normalize_content_type(*, filename: str, content_type: object, default_content_type: str) -> str:
    normalized_content_type = str(content_type or "").strip()
    if normalized_content_type:
        return normalized_content_type
    guessed_type = mimetypes.guess_type(filename)[0]
    if guessed_type:
        return guessed_type
    return default_content_type


def _normalize_filename(raw_name: object, *, fallback_name: str) -> str:
    normalized_name = str(raw_name or "").replace("\\", "/").split("/")[-1].strip()
    return normalized_name or fallback_name


def _read_uploaded_file(uploaded_file: UploadedFile, *, kind: StoredFileKind) -> _BufferedUpload:
    filename = _normalize_filename(
        getattr(uploaded_file, "name", ""),
        fallback_name="certificado.pfx" if kind == "certificate" else "arquivo.bin",
    )
    content = uploaded_file.read()
    if not content:
        raise WorkshopFileStorageError("O arquivo enviado esta vazio.")

    content_type = _normalize_content_type(
        filename=filename,
        content_type=getattr(uploaded_file, "content_type", ""),
        default_content_type=_default_content_type(kind=kind, filename=filename),
    )
    return _BufferedUpload(filename=filename, content_type=content_type, content=content)


@lru_cache(maxsize=8)
def _build_workshop_file_service(
    mongo_uri: str,
    database_name: str,
    certificate_bucket: str,
    logo_bucket: str,
) -> WorkshopMongoFileService:
    return WorkshopMongoFileService(
        mongo_uri=mongo_uri,
        database_name=database_name,
        certificate_bucket=certificate_bucket,
        logo_bucket=logo_bucket,
    )


def get_workshop_file_service() -> WorkshopMongoFileService:
    return _build_workshop_file_service(
        str(getattr(settings, "MONGODB_URI", "") or ""),
        str(getattr(settings, "MONGODB_DB_NAME", "hunter") or "hunter"),
        str(getattr(settings, "MONGODB_CERT_BUCKET", "certificado") or "certificado"),
        str(getattr(settings, "MONGODB_LOGO_BUCKET", "logo") or "logo"),
    )


def workshop_has_certificate(workshop: Workshop) -> bool:
    return bool(getattr(workshop, "certificate_mongo_file_id", "") or getattr(workshop, "pfx_certificate", None))


def workshop_has_logo(workshop: Workshop) -> bool:
    return bool(getattr(workshop, "logo_mongo_file_id", "") or getattr(workshop, "logo", None))


def get_workshop_certificate_file(workshop: Workshop) -> StoredWorkshopFile | None:
    mongo_file_id = str(getattr(workshop, "certificate_mongo_file_id", "") or "").strip()
    if mongo_file_id:
        return get_workshop_file_service().read_file(kind="certificate", file_id=mongo_file_id)

    field_file = getattr(workshop, "pfx_certificate", None)
    if not field_file:
        return None

    filename = _normalize_filename(getattr(field_file, "name", ""), fallback_name="certificado.pfx")
    try:
        field_file.open("rb")
        try:
            content = field_file.read()
        finally:
            field_file.close()
    except OSError as exc:
        raise WorkshopFileStorageError("O certificado da oficina nao esta disponivel. Envie novamente o arquivo na gestao da oficina.") from exc

    if not content:
        raise WorkshopFileStorageError("O certificado da oficina esta vazio. Envie novamente o arquivo na gestao da oficina.")

    return StoredWorkshopFile(
        file_id="",
        filename=filename,
        content_type=_default_content_type(kind="certificate", filename=filename),
        content=content,
        uploaded_at=None,
    )


def get_workshop_logo_file(workshop: Workshop) -> StoredWorkshopFile | None:
    mongo_file_id = str(getattr(workshop, "logo_mongo_file_id", "") or "").strip()
    if mongo_file_id:
        return get_workshop_file_service().read_file(kind="logo", file_id=mongo_file_id)

    field_file = getattr(workshop, "logo", None)
    if not field_file:
        return None

    filename = _normalize_filename(getattr(field_file, "name", ""), fallback_name="logo.png")
    try:
        field_file.open("rb")
        try:
            content = field_file.read()
        finally:
            field_file.close()
    except OSError:
        return None

    if not content:
        return None

    return StoredWorkshopFile(
        file_id="",
        filename=filename,
        content_type=_default_content_type(kind="logo", filename=filename),
        content=content,
        uploaded_at=None,
    )


def encode_workshop_certificate(workshop: Workshop) -> str:
    stored_file = get_workshop_certificate_file(workshop)
    if stored_file is None:
        return ""
    return base64.b64encode(stored_file.content).decode("ascii")


@contextmanager
def workshop_certificate_temp_path(workshop: Workshop) -> Iterator[str]:
    stored_file = get_workshop_certificate_file(workshop)
    if stored_file is None:
        raise WorkshopFileStorageError("Configure certificado e senha da oficina antes de consultar a SEFAZ.")

    suffix = ".pfx"
    if "." in stored_file.filename:
        suffix = f".{stored_file.filename.rsplit('.', 1)[-1]}"

    with NamedTemporaryFile(suffix=suffix, delete=False) as temporary_file:
        temporary_file.write(stored_file.content)
        temporary_path = temporary_file.name

    try:
        yield temporary_path
    finally:
        _safe_delete_temporary_file(temporary_path)


def save_workshop_logo(*, workshop: Workshop, uploaded_file: UploadedFile) -> None:
    buffered_file = _read_uploaded_file(uploaded_file, kind="logo")
    stored_file = get_workshop_file_service().save_file(
        kind="logo",
        content=buffered_file.content,
        filename=buffered_file.filename,
        content_type=buffered_file.content_type,
        workshop_id=workshop.pk,
    )

    previous_mongo_file_id = str(getattr(workshop, "logo_mongo_file_id", "") or "").strip()
    previous_local_name = str(getattr(workshop.logo, "name", "") or "")

    update_fields = [
        "logo_mongo_file_id",
        "logo_file_name",
        "logo_content_type",
        "logo_uploaded_at",
    ]

    workshop.logo_mongo_file_id = stored_file.file_id
    workshop.logo_file_name = stored_file.filename
    workshop.logo_content_type = stored_file.content_type
    workshop.logo_uploaded_at = stored_file.uploaded_at
    if workshop.logo:
        workshop.logo = None
        update_fields.append("logo")

    with transaction.atomic():
        workshop.save(update_fields=update_fields)
        transaction.on_commit(lambda: _cleanup_replaced_file(kind="logo", previous_mongo_file_id=previous_mongo_file_id, previous_local_name=previous_local_name, field_name="logo", new_mongo_file_id=stored_file.file_id))


def clear_workshop_logo(*, workshop: Workshop) -> None:
    previous_mongo_file_id = str(getattr(workshop, "logo_mongo_file_id", "") or "").strip()
    previous_local_name = str(getattr(workshop.logo, "name", "") or "")

    update_fields = [
        "logo_mongo_file_id",
        "logo_file_name",
        "logo_content_type",
        "logo_uploaded_at",
    ]
    workshop.logo_mongo_file_id = ""
    workshop.logo_file_name = ""
    workshop.logo_content_type = ""
    workshop.logo_uploaded_at = None
    if workshop.logo:
        workshop.logo = None
        update_fields.append("logo")

    with transaction.atomic():
        workshop.save(update_fields=update_fields)
        transaction.on_commit(lambda: _cleanup_replaced_file(kind="logo", previous_mongo_file_id=previous_mongo_file_id, previous_local_name=previous_local_name, field_name="logo", new_mongo_file_id=""))


def save_workshop_certificate_atomic(
    *,
    workshop: Workshop,
    company: WebmaniaCompany,
    uploaded_file: UploadedFile | None,
    certificate_password: str,
) -> None:
    current_password = str(workshop.certificate_password or "").strip()
    resolved_password = str(certificate_password or "").strip() or current_password
    password_changed = resolved_password != current_password

    previous_company_certificate = decrypt_secret(company.certificado)
    previous_company_password = decrypt_secret(company.certificado_senha)
    previous_mongo_file_id = str(getattr(workshop, "certificate_mongo_file_id", "") or "").strip()
    previous_local_name = str(getattr(workshop.pfx_certificate, "name", "") or "")

    staged_file: StoredWorkshopFile | None = None
    encoded_certificate: str | None = None
    payload: dict[str, str] = {}

    if uploaded_file is not None:
        buffered_file = _read_uploaded_file(uploaded_file, kind="certificate")
        staged_file = get_workshop_file_service().save_file(
            kind="certificate",
            content=buffered_file.content,
            filename=buffered_file.filename,
            content_type=buffered_file.content_type,
            workshop_id=workshop.pk,
        )
        encoded_certificate = base64.b64encode(buffered_file.content).decode("ascii")
        payload["certificado"] = encoded_certificate
        payload["certificado_senha"] = resolved_password
    elif password_changed:
        payload["certificado_senha"] = resolved_password

    try:
        if payload:
            update_webmania_company(company=company, payload=payload)
    except Exception:
        if staged_file is not None:
            _safe_delete_mongo_file(kind="certificate", file_id=staged_file.file_id)
        raise

    try:
        with transaction.atomic():
            workshop_update_fields = ["certificate_password"]
            workshop.certificate_password = resolved_password

            if staged_file is not None:
                workshop.certificate_mongo_file_id = staged_file.file_id
                workshop.certificate_file_name = staged_file.filename
                workshop.certificate_content_type = staged_file.content_type
                workshop.certificate_uploaded_at = staged_file.uploaded_at
                workshop_update_fields.extend(
                    [
                        "certificate_mongo_file_id",
                        "certificate_file_name",
                        "certificate_content_type",
                        "certificate_uploaded_at",
                    ]
                )
                if workshop.pfx_certificate:
                    workshop.pfx_certificate = None
                    workshop_update_fields.append("pfx_certificate")

            workshop.save(update_fields=workshop_update_fields)
            update_company_certificate_snapshot(
                company,
                encoded_certificate=encoded_certificate,
                certificate_password=resolved_password if payload else None,
            )
            if staged_file is not None:
                transaction.on_commit(
                    lambda: _cleanup_replaced_file(
                        kind="certificate",
                        previous_mongo_file_id=previous_mongo_file_id,
                        previous_local_name=previous_local_name,
                        field_name="pfx_certificate",
                        new_mongo_file_id=staged_file.file_id,
                    )
                )
    except Exception as exc:
        if staged_file is not None:
            _safe_delete_mongo_file(kind="certificate", file_id=staged_file.file_id)

        restore_payload: dict[str, str] = {}
        if staged_file is not None:
            restore_payload["certificado"] = previous_company_certificate
            restore_payload["certificado_senha"] = previous_company_password
        elif password_changed:
            restore_payload["certificado_senha"] = previous_company_password

        if restore_payload:
            try:
                update_webmania_company(company=company, payload=restore_payload)
            except Exception as restore_exc:
                raise WorkshopFileSyncError("Falha ao salvar o certificado localmente e ao restaurar o certificado anterior na Webmania.") from restore_exc

        raise WorkshopFileSyncError("Falha ao concluir o salvamento atomico do certificado. Nenhuma alteracao foi mantida.") from exc


def update_company_certificate_snapshot(
    company: WebmaniaCompany,
    *,
    encoded_certificate: str | None,
    certificate_password: str | None,
) -> None:
    update_fields: list[str] = []

    if encoded_certificate is not None:
        new_certificate_value = encrypt_secret(encoded_certificate) if encoded_certificate else ""
        if company.certificado != new_certificate_value:
            company.certificado = new_certificate_value
            update_fields.append("certificado")

    if certificate_password is not None:
        new_password_value = encrypt_secret(certificate_password) if certificate_password else ""
        if company.certificado_senha != new_password_value:
            company.certificado_senha = new_password_value
            update_fields.append("certificado_senha")

    if update_fields:
        company.save(update_fields=update_fields)


def schedule_workshop_files_cleanup(workshop: Workshop) -> None:
    certificate_mongo_file_id = str(getattr(workshop, "certificate_mongo_file_id", "") or "").strip()
    certificate_local_name = str(getattr(workshop.pfx_certificate, "name", "") or "")
    logo_mongo_file_id = str(getattr(workshop, "logo_mongo_file_id", "") or "").strip()
    logo_local_name = str(getattr(workshop.logo, "name", "") or "")

    def _cleanup() -> None:
        _safe_delete_mongo_file(kind="certificate", file_id=certificate_mongo_file_id)
        _safe_delete_mongo_file(kind="logo", file_id=logo_mongo_file_id)
        _safe_delete_legacy_file(Workshop, field_name="pfx_certificate", file_name=certificate_local_name)
        _safe_delete_legacy_file(Workshop, field_name="logo", file_name=logo_local_name)

    transaction.on_commit(_cleanup)


def _cleanup_replaced_file(
    *,
    kind: StoredFileKind,
    previous_mongo_file_id: str,
    previous_local_name: str,
    field_name: str,
    new_mongo_file_id: str,
) -> None:
    if previous_mongo_file_id and previous_mongo_file_id != new_mongo_file_id:
        _safe_delete_mongo_file(kind=kind, file_id=previous_mongo_file_id)
    if previous_local_name:
        _safe_delete_legacy_file(Workshop, field_name=field_name, file_name=previous_local_name)


def _safe_delete_mongo_file(*, kind: StoredFileKind, file_id: str) -> None:
    if not str(file_id or "").strip():
        return

    try:
        get_workshop_file_service().delete_file(kind=kind, file_id=file_id)
    except WorkshopFileStorageError:
        logger.warning("workshop_mongo_file_cleanup_failed kind=%s file_id=%s", kind, file_id)


def _safe_delete_legacy_file(model_class: type[Workshop], *, field_name: str, file_name: str) -> None:
    normalized_name = str(file_name or "").strip()
    if not normalized_name:
        return

    try:
        field = model_class._meta.get_field(field_name)
        storage = getattr(field, "storage", None)
        if storage is None:
            return
        storage.delete(normalized_name)
    except OSError:
        logger.warning("workshop_legacy_file_cleanup_failed field=%s file=%s", field_name, normalized_name)


def _safe_delete_temporary_file(file_path: str) -> None:
    try:
        import os

        os.remove(file_path)
    except OSError:
        logger.warning("workshop_temp_certificate_cleanup_failed file=%s", file_path)
