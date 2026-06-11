from __future__ import annotations

import base64
import io
import logging
import mimetypes
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from tempfile import NamedTemporaryFile
from typing import Iterator, Literal
from urllib.parse import urlparse

from PIL import Image, UnidentifiedImageError
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.text import get_valid_filename

from apps.core.infrastructure.services import build_absolute_app_url
from apps.core.infrastructure.services.storage import StorageConfigurationError, StorageServiceError, get_storage_service
from apps.finance.models.finance import WebmaniaCompany
from apps.core.infrastructure.services.webmania.webmania_b2b import update_webmania_company
from apps.core.infrastructure.services.webmania.webmania_secrets import encrypt_secret
from apps.workshops.models.workshops import Workshop


logger = logging.getLogger(__name__)

StoredFileKind = Literal["certificate", "logo"]
MAX_LOGO_WIDTH_PX = 120
MAX_LOGO_HEIGHT_PX = 65
STORAGE_LOGO_READINESS_ATTEMPTS = 3


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


class WorkshopS3FileService:
    def save_file(
        self,
        *,
        kind: StoredFileKind,
        content: bytes,
        filename: str,
        content_type: str,
        workshop_id: int,
    ) -> StoredWorkshopFile:
        if workshop_id <= 0:
            raise WorkshopFileStorageError("Oficina invalida para salvar arquivo no bucket.")

        uploaded_at = timezone.now()
        file_id = _build_storage_key(kind=kind, workshop_id=workshop_id, filename=filename)

        try:
            get_storage_service().upload_file(
                content,
                file_id,
                content_type=content_type,
                metadata={
                    "filename": filename,
                    "uploaded_at": uploaded_at.isoformat(),
                    "kind": kind,
                },
            )
        except (StorageConfigurationError, StorageServiceError) as exc:
            raise WorkshopFileStorageError(str(exc)) from exc

        return StoredWorkshopFile(
            file_id=file_id,
            filename=filename,
            content_type=content_type,
            content=content,
            uploaded_at=uploaded_at,
        )

    def read_file(self, *, kind: StoredFileKind, file_id: str) -> StoredWorkshopFile:
        normalized_file_id = str(file_id or "").strip()
        if not normalized_file_id:
            raise WorkshopFileStorageError("Identificador invalido do arquivo salvo no bucket.")

        try:
            stored_object = get_storage_service().read_file(normalized_file_id)
        except (StorageConfigurationError, StorageServiceError) as exc:
            raise WorkshopFileStorageError("Arquivo nao encontrado no bucket configurado. Envie o arquivo novamente na gestao da oficina.") from exc

        metadata = stored_object.metadata
        filename = _normalize_filename(metadata.get("filename"), fallback_name=_fallback_filename(kind=kind))
        uploaded_at = _parse_datetime(metadata.get("uploaded_at"))
        content_type = _normalize_content_type(
            filename=filename,
            content_type=stored_object.content_type,
            default_content_type=_default_content_type(kind=kind, filename=filename),
        )

        return StoredWorkshopFile(
            file_id=normalized_file_id,
            filename=filename,
            content_type=content_type,
            content=stored_object.content,
            uploaded_at=uploaded_at,
        )

    def delete_file(self, *, kind: StoredFileKind, file_id: str) -> None:
        normalized_file_id = str(file_id or "").strip()
        if not normalized_file_id:
            return

        try:
            get_storage_service().delete_file(normalized_file_id)
        except (StorageConfigurationError, StorageServiceError) as exc:
            raise WorkshopFileStorageError(str(exc)) from exc

    def generate_presigned_url(self, *, file_id: str, expires_in: int = 3600) -> str:
        normalized_file_id = str(file_id or "").strip()
        if not normalized_file_id:
            raise WorkshopFileStorageError("Identificador invalido do arquivo salvo no bucket.")

        try:
            return get_storage_service().generate_presigned_url(normalized_file_id, expires_in=expires_in)
        except (StorageConfigurationError, StorageServiceError) as exc:
            raise WorkshopFileStorageError(str(exc)) from exc


def _parse_datetime(value: object) -> datetime | None:
    raw_value = str(value or "").strip()
    if not raw_value:
        return None

    try:
        return datetime.fromisoformat(raw_value)
    except ValueError:
        return None


def _fallback_filename(*, kind: StoredFileKind) -> str:
    if kind == "certificate":
        return "certificado.pfx"
    return "logo.png"


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
    candidate_name = normalized_name or fallback_name
    valid_name = get_valid_filename(candidate_name)
    return valid_name or fallback_name


def _build_storage_key(*, kind: StoredFileKind, workshop_id: int, filename: str) -> str:
    folder = "logos" if kind == "logo" else "certificates"
    return f"workshops/{workshop_id}/{folder}/{uuid.uuid4().hex}/{filename}"


def _read_uploaded_file(uploaded_file: UploadedFile, *, kind: StoredFileKind) -> _BufferedUpload:
    filename = _normalize_filename(
        getattr(uploaded_file, "name", ""),
        fallback_name=_fallback_filename(kind=kind),
    )
    content = uploaded_file.read()
    if not content:
        raise WorkshopFileStorageError("O arquivo enviado esta vazio.")

    content_type = _normalize_content_type(
        filename=filename,
        content_type=getattr(uploaded_file, "content_type", ""),
        default_content_type=_default_content_type(kind=kind, filename=filename),
    )

    if kind == "logo":
        content, filename, content_type = _normalize_logo_upload(content=content, filename=filename, content_type=content_type)

    return _BufferedUpload(filename=filename, content_type=content_type, content=content)


def _normalize_logo_upload(*, content: bytes, filename: str, content_type: str) -> tuple[bytes, str, str]:
    rasterized_content = content
    normalized_content_type = str(content_type or "").strip().lower()
    if normalized_content_type == "image/svg+xml" or filename.lower().endswith(".svg"):
        rasterized_content = _rasterize_svg_to_png(content)

    try:
        with Image.open(io.BytesIO(rasterized_content)) as image:
            normalized_image = image.convert("RGBA")
            normalized_image.thumbnail((MAX_LOGO_WIDTH_PX, MAX_LOGO_HEIGHT_PX), Image.Resampling.LANCZOS)

            background = Image.new("RGB", normalized_image.size, (255, 255, 255))
            background.paste(normalized_image, mask=normalized_image.getchannel("A"))

            output = io.BytesIO()
            background.save(output, format="JPEG", quality=85, optimize=True)
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise WorkshopFileStorageError("Nao foi possivel processar a logomarca enviada. Use um arquivo de imagem valido.") from exc

    normalized_name = f"{filename.rsplit('.', 1)[0] if '.' in filename else filename}.jpg"
    safe_name = _normalize_filename(normalized_name, fallback_name="logo.jpg")
    return output.getvalue(), safe_name, "image/jpeg"


def _rasterize_svg_to_png(content: bytes) -> bytes:
    try:
        import cairosvg  # type: ignore[import-untyped]

        png_bytes = cairosvg.svg2png(bytestring=content)
        if png_bytes is None:
            raise WorkshopFileStorageError("Nao foi possivel converter a logomarca SVG para PNG.")
        return bytes(png_bytes)
    except OSError as exc:
        raise WorkshopFileStorageError("Nao foi possivel converter a logomarca SVG para PNG porque a biblioteca nativa do Cairo nao esta instalada neste ambiente. Use PNG, JPEG ou WEBP, ou instale o runtime do Cairo.") from exc
    except Exception as exc:
        raise WorkshopFileStorageError("Nao foi possivel converter a logomarca SVG para PNG.") from exc


@lru_cache(maxsize=1)
def get_workshop_file_service() -> WorkshopS3FileService:
    try:
        get_storage_service()
    except StorageConfigurationError as exc:
        raise WorkshopFileStorageError(str(exc)) from exc
    return WorkshopS3FileService()


def workshop_has_certificate(workshop: Workshop) -> bool:
    return bool(getattr(workshop, "certificate_file_key", ""))


def workshop_has_logo(workshop: Workshop) -> bool:
    return bool(getattr(workshop, "logo_file_key", ""))


def build_workshop_logo_public_url(*, workshop: Workshop, request=None) -> str:
    path = reverse("workshops:logo_public", kwargs={"token": workshop.logo_public_token})
    public_url = build_absolute_app_url(path=path, request=None)
    if not _is_public_url(public_url):
        raise WorkshopFileStorageError("Configure APP_BASE_URL com uma URL publica para sincronizar a logomarca com a Webmania.")
    return public_url


def ensure_logo_is_readable_from_storage(*, file_id: str, attempts: int = STORAGE_LOGO_READINESS_ATTEMPTS) -> None:
    last_error = ""
    for attempt in range(1, attempts + 1):
        try:
            stored_logo = get_workshop_file_service().read_file(kind="logo", file_id=file_id)
        except WorkshopFileStorageError as exc:
            last_error = str(exc)
            logger.warning("workshop_logo_storage_read_retry file_id=%s attempt=%s error=%s", file_id, attempt, last_error)
            continue

        if stored_logo.content:
            logger.info("workshop_logo_storage_ready file_id=%s attempt=%s content_type=%s", file_id, attempt, stored_logo.content_type)
            return

        last_error = "empty logo content"
        logger.warning("workshop_logo_storage_read_empty file_id=%s attempt=%s", file_id, attempt)

    raise WorkshopFileSyncError("A logomarca salva ainda nao ficou disponivel no bucket. Tente novamente em instantes.")


def _is_public_url(url: str) -> bool:
    parsed = urlparse(str(url or "").strip())
    hostname = str(parsed.hostname or "").strip().lower()
    if not hostname:
        return False
    if hostname in {"localhost", "127.0.0.1", "0.0.0.0"}:
        return False
    if hostname.endswith(".local"):
        return False
    return True


def get_workshop_certificate_file(workshop: Workshop) -> StoredWorkshopFile | None:
    file_id = str(getattr(workshop, "certificate_file_key", "") or "").strip()
    if not file_id:
        return None

    return get_workshop_file_service().read_file(kind="certificate", file_id=file_id)


def get_workshop_logo_file(workshop: Workshop) -> StoredWorkshopFile | None:
    file_id = str(getattr(workshop, "logo_file_key", "") or "").strip()
    if not file_id:
        return None

    return get_workshop_file_service().read_file(kind="logo", file_id=file_id)


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


def save_workshop_logo_atomic(
    *,
    workshop: Workshop,
    company: WebmaniaCompany,
    uploaded_file: UploadedFile,
    request=None,
) -> str:
    buffered_file = _read_uploaded_file(uploaded_file, kind="logo")
    staged_file = get_workshop_file_service().save_file(
        kind="logo",
        content=buffered_file.content,
        filename=buffered_file.filename,
        content_type=buffered_file.content_type,
        workshop_id=workshop.pk,
    )

    previous_file_id = str(getattr(workshop, "logo_file_key", "") or "").strip()
    previous_file_name = str(getattr(workshop, "logo_file_name", "") or "").strip()
    previous_content_type = str(getattr(workshop, "logo_content_type", "") or "").strip()
    previous_uploaded_at = getattr(workshop, "logo_uploaded_at", None)
    previous_company_logo_url = str(company.logomarca or "").strip()
    public_logo_url = build_workshop_logo_public_url(workshop=workshop, request=request)

    try:
        with transaction.atomic():
            workshop.logo_file_key = staged_file.file_id
            workshop.logo_file_name = staged_file.filename
            workshop.logo_content_type = staged_file.content_type
            workshop.logo_uploaded_at = staged_file.uploaded_at
            workshop.save(update_fields=["logo_file_key", "logo_file_name", "logo_content_type", "logo_uploaded_at"])
    except Exception as exc:
        _safe_delete_file(kind="logo", file_id=staged_file.file_id)
        raise WorkshopFileSyncError("Falha ao concluir o salvamento da logo. Nenhuma alteracao foi mantida.") from exc

    try:
        ensure_logo_is_readable_from_storage(file_id=staged_file.file_id)
    except Exception:
        _rollback_logo_upload(
            workshop=workshop,
            company=company,
            previous_file_id=previous_file_id,
            previous_file_name=previous_file_name,
            previous_content_type=previous_content_type,
            previous_uploaded_at=previous_uploaded_at,
            previous_company_logo_url=previous_company_logo_url,
        )
        _safe_delete_file(kind="logo", file_id=staged_file.file_id)
        raise

    try:
        update_webmania_company(company=company, payload={"logomarca": public_logo_url})
    except Exception:
        _rollback_logo_upload(
            workshop=workshop,
            company=company,
            previous_file_id=previous_file_id,
            previous_file_name=previous_file_name,
            previous_content_type=previous_content_type,
            previous_uploaded_at=previous_uploaded_at,
            previous_company_logo_url=previous_company_logo_url,
        )
        _safe_delete_file(kind="logo", file_id=staged_file.file_id)
        raise

    try:
        with transaction.atomic():
            if company.logomarca != public_logo_url:
                company.logomarca = public_logo_url
                company.save(update_fields=["logomarca"])

            transaction.on_commit(lambda: _cleanup_replaced_file(kind="logo", previous_file_id=previous_file_id, new_file_id=staged_file.file_id))
    except Exception as exc:
        _rollback_logo_upload(
            workshop=workshop,
            company=company,
            previous_file_id=previous_file_id,
            previous_file_name=previous_file_name,
            previous_content_type=previous_content_type,
            previous_uploaded_at=previous_uploaded_at,
            previous_company_logo_url=previous_company_logo_url,
        )
        if previous_company_logo_url != public_logo_url:
            try:
                update_webmania_company(company=company, payload={"logomarca": previous_company_logo_url})
            except Exception as restore_exc:
                raise WorkshopFileSyncError("Falha ao salvar a logo localmente e ao restaurar a logo anterior na Webmania.") from restore_exc
        _safe_delete_file(kind="logo", file_id=staged_file.file_id)
        raise WorkshopFileSyncError("Falha ao concluir o salvamento da logo. Nenhuma alteracao foi mantida.") from exc

    return public_logo_url


def clear_workshop_logo_atomic(*, workshop: Workshop, company: WebmaniaCompany, request=None) -> None:
    previous_file_id = str(getattr(workshop, "logo_file_key", "") or "").strip()
    previous_company_logo_url = str(company.logomarca or "").strip()
    previous_public_url = build_workshop_logo_public_url(workshop=workshop, request=request)

    try:
        update_webmania_company(company=company, payload={"logomarca": ""})
    except Exception:
        raise

    try:
        with transaction.atomic():
            workshop.logo_file_key = ""
            workshop.logo_file_name = ""
            workshop.logo_content_type = ""
            workshop.logo_uploaded_at = None
            workshop.save(update_fields=["logo_file_key", "logo_file_name", "logo_content_type", "logo_uploaded_at"])

            if company.logomarca:
                company.logomarca = ""
                company.save(update_fields=["logomarca"])

            transaction.on_commit(lambda: _safe_delete_file(kind="logo", file_id=previous_file_id))
    except Exception as exc:
        restore_url = previous_company_logo_url or previous_public_url
        if restore_url:
            try:
                update_webmania_company(company=company, payload={"logomarca": restore_url})
            except Exception as restore_exc:
                raise WorkshopFileSyncError("Falha ao remover a logo localmente e ao restaurar a URL anterior na Webmania.") from restore_exc
        raise WorkshopFileSyncError("Falha ao concluir a remocao da logo. Nenhuma alteracao foi mantida.") from exc


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

    previous_file_id = str(getattr(workshop, "certificate_file_key", "") or "").strip()
    previous_remote_password = current_password
    try:
        previous_remote_certificate = encode_workshop_certificate(workshop) if previous_file_id else ""
    except WorkshopFileStorageError:
        previous_remote_certificate = ""

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
            _safe_delete_file(kind="certificate", file_id=staged_file.file_id)
        raise

    try:
        with transaction.atomic():
            workshop_update_fields = ["certificate_password"]
            workshop.certificate_password = resolved_password

            if staged_file is not None:
                workshop.certificate_file_key = staged_file.file_id
                workshop.certificate_file_name = staged_file.filename
                workshop.certificate_content_type = staged_file.content_type
                workshop.certificate_uploaded_at = staged_file.uploaded_at
                workshop_update_fields.extend(
                    [
                        "certificate_file_key",
                        "certificate_file_name",
                        "certificate_content_type",
                        "certificate_uploaded_at",
                    ]
                )

            workshop.save(update_fields=workshop_update_fields)
            update_company_certificate_snapshot(company, certificate_password=resolved_password if payload else None)
            if staged_file is not None:
                transaction.on_commit(lambda: _cleanup_replaced_file(kind="certificate", previous_file_id=previous_file_id, new_file_id=staged_file.file_id))
    except Exception as exc:
        if staged_file is not None:
            _safe_delete_file(kind="certificate", file_id=staged_file.file_id)

        restore_payload: dict[str, str] = {}
        if staged_file is not None:
            restore_payload["certificado"] = previous_remote_certificate
            restore_payload["certificado_senha"] = previous_remote_password
        elif password_changed:
            restore_payload["certificado_senha"] = previous_remote_password

        if restore_payload:
            try:
                update_webmania_company(company=company, payload=restore_payload)
            except Exception as restore_exc:
                raise WorkshopFileSyncError("Falha ao salvar o certificado localmente e ao restaurar o certificado anterior na Webmania.") from restore_exc

        raise WorkshopFileSyncError("Falha ao concluir o salvamento atomico do certificado. Nenhuma alteracao foi mantida.") from exc


def update_company_certificate_snapshot(
    company: WebmaniaCompany,
    *,
    certificate_password: str | None,
) -> None:
    update_fields: list[str] = []

    if company.certificado:
        company.certificado = ""
        update_fields.append("certificado")

    if certificate_password is not None:
        new_password_value = encrypt_secret(certificate_password) if certificate_password else ""
        if company.certificado_senha != new_password_value:
            company.certificado_senha = new_password_value
            update_fields.append("certificado_senha")

    if update_fields:
        company.save(update_fields=update_fields)


def schedule_workshop_files_cleanup(workshop: Workshop) -> None:
    certificate_file_id = str(getattr(workshop, "certificate_file_key", "") or "").strip()
    logo_file_id = str(getattr(workshop, "logo_file_key", "") or "").strip()

    def _cleanup() -> None:
        _safe_delete_file(kind="certificate", file_id=certificate_file_id)
        _safe_delete_file(kind="logo", file_id=logo_file_id)

    transaction.on_commit(_cleanup)


def _cleanup_replaced_file(*, kind: StoredFileKind, previous_file_id: str, new_file_id: str) -> None:
    if previous_file_id and previous_file_id != new_file_id:
        _safe_delete_file(kind=kind, file_id=previous_file_id)


def _rollback_logo_upload(
    *,
    workshop: Workshop,
    company: WebmaniaCompany,
    previous_file_id: str,
    previous_file_name: str,
    previous_content_type: str,
    previous_uploaded_at: datetime | None,
    previous_company_logo_url: str,
) -> None:
    workshop.logo_file_key = previous_file_id
    workshop.logo_file_name = previous_file_name
    workshop.logo_content_type = previous_content_type
    workshop.logo_uploaded_at = previous_uploaded_at
    workshop.save(update_fields=["logo_file_key", "logo_file_name", "logo_content_type", "logo_uploaded_at"])

    if company.logomarca != previous_company_logo_url:
        company.logomarca = previous_company_logo_url
        company.save(update_fields=["logomarca"])


def _safe_delete_file(*, kind: StoredFileKind, file_id: str) -> None:
    if not str(file_id or "").strip():
        return

    try:
        get_workshop_file_service().delete_file(kind=kind, file_id=file_id)
    except WorkshopFileStorageError:
        logger.warning("workshop_file_cleanup_failed kind=%s file_id=%s", kind, file_id)


def _safe_delete_temporary_file(file_path: str) -> None:
    try:
        import os

        os.remove(file_path)
    except OSError:
        logger.warning("workshop_temp_certificate_cleanup_failed file=%s", file_path)
