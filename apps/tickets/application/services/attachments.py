from __future__ import annotations

import mimetypes
import uuid
from dataclasses import dataclass

from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.utils import timezone
from django.utils.text import get_valid_filename

from apps.core.infrastructure.services.storage import StorageConfigurationError, StorageServiceError, get_storage_service
from apps.tickets.constants import MAX_ATTACHMENT_BYTES
from apps.tickets.models import Ticket, TicketAttachment, TicketAttachmentSource


class TicketAttachmentError(Exception):
    pass


@dataclass(frozen=True)
class PreparedAttachment:
    content: bytes
    original_name: str
    content_type: str
    size_bytes: int
    source: str


def prepare_uploaded_file(*, uploaded: UploadedFile, source: str = TicketAttachmentSource.UPLOAD) -> PreparedAttachment:
    content = uploaded.read()
    size_bytes = len(content)
    if size_bytes <= 0:
        raise TicketAttachmentError("Arquivo vazio.")
    if size_bytes > MAX_ATTACHMENT_BYTES:
        raise TicketAttachmentError("Arquivo excede o limite de 300 MB.")

    original_name = get_valid_filename(getattr(uploaded, "name", None) or "anexo.bin")
    content_type = str(getattr(uploaded, "content_type", None) or mimetypes.guess_type(original_name)[0] or "application/octet-stream")
    return PreparedAttachment(
        content=content,
        original_name=original_name,
        content_type=content_type,
        size_bytes=size_bytes,
        source=source,
    )


def _build_storage_key(*, workshop_id: int, ticket_id: int, filename: str) -> str:
    stamp = timezone.now().strftime("%Y%m%d%H%M%S")
    unique = uuid.uuid4().hex[:12]
    safe_name = get_valid_filename(filename) or "anexo.bin"
    return f"tickets/{workshop_id}/{ticket_id}/{stamp}_{unique}_{safe_name}"


def save_attachments(
    *,
    ticket: Ticket,
    uploaded_by,
    prepared: list[PreparedAttachment],
) -> list[TicketAttachment]:
    if not prepared:
        return []

    created: list[TicketAttachment] = []
    with transaction.atomic():
        for item in prepared:
            key = _build_storage_key(
                workshop_id=int(ticket.workshop_id),
                ticket_id=int(ticket.pk),
                filename=item.original_name,
            )
            try:
                get_storage_service().upload_file(
                    item.content,
                    key,
                    content_type=item.content_type,
                    metadata={
                        "filename": item.original_name,
                        "ticket_id": str(ticket.pk),
                        "source": item.source,
                    },
                )
            except (StorageConfigurationError, StorageServiceError) as exc:
                raise TicketAttachmentError(str(exc)) from exc

            created.append(
                TicketAttachment.objects.create(
                    ticket=ticket,
                    uploaded_by=uploaded_by,
                    file_key=key,
                    content_type=item.content_type,
                    original_name=item.original_name,
                    size_bytes=item.size_bytes,
                    source=item.source,
                )
            )
    return created


def attachment_download_url(*, attachment: TicketAttachment, expires_in: int = 3600) -> str | None:
    try:
        return get_storage_service().generate_presigned_url(attachment.file_key, expires_in=expires_in)
    except (StorageConfigurationError, StorageServiceError):
        return None
