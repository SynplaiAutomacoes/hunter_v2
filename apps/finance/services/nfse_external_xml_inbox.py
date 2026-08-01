from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePath
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.finance.models.finance import NfseExternalXmlInbox, NfseExternalXmlInboxItem, NfseReceivedDocument, NfseReceivedImportBatch, NfseReceivedImportBatchItem, WebmaniaCompany
from apps.finance.services.nfse_received import NfseReceivedImportError, build_received_xml_hash, normalize_received_xml_for_hash, parse_nfse_received_xml, resolve_nfse_received_role, validate_nfse_received_import
from apps.finance.services.nfse_received_batch import MAX_NFSE_RECEIVED_BATCH_FILE_SIZE, MAX_NFSE_RECEIVED_BATCH_FILES, MAX_NFSE_RECEIVED_BATCH_TOTAL_SIZE, NfseReceivedBatchFile, import_nfse_received_xml_batch


ACTIVE_INBOX_STATUSES = {
    NfseExternalXmlInboxItem.Status.PENDING,
    NfseExternalXmlInboxItem.Status.APPROVED,
    NfseExternalXmlInboxItem.Status.PROCESSED,
}


@dataclass(frozen=True, slots=True)
class NfseExternalXmlInboxUploadFile:
    filename: str
    content: bytes
    content_type: str = ""


@dataclass(frozen=True, slots=True)
class NfseExternalXmlInboxBulkItemResult:
    item_id: int
    filename: str
    status: str
    success: bool
    message: str


@dataclass(frozen=True, slots=True)
class NfseExternalXmlInboxBulkResult:
    action: str
    results: list[NfseExternalXmlInboxBulkItemResult]

    @property
    def success_count(self) -> int:
        return sum(1 for result in self.results if result.success)

    @property
    def error_count(self) -> int:
        return sum(1 for result in self.results if not result.success)


class NfseExternalXmlInboxError(ValidationError):
    pass


def create_nfse_external_xml_inbox(
    *,
    workshop,
    company: WebmaniaCompany,
    files: list[NfseExternalXmlInboxUploadFile],
    source_label: str = "",
    created_by: Any | None = None,
) -> NfseExternalXmlInbox:
    if company.workshop_id != workshop.pk:
        raise NfseExternalXmlInboxError("A empresa emissora pertence a outra oficina.")
    if not company.nfse_external_xml_inbox_enabled:
        raise NfseExternalXmlInboxError("Inbox externa de XML NFS-e não esta habilitada para esta empresa.")
    if not files:
        raise NfseExternalXmlInboxError("Envie ao menos um XML candidato.")
    if len(files) > MAX_NFSE_RECEIVED_BATCH_FILES:
        raise NfseExternalXmlInboxError(f"A inbox deve receber no maximo {MAX_NFSE_RECEIVED_BATCH_FILES} arquivos por envio.")
    total_size = sum(len(file.content) for file in files)
    if total_size > MAX_NFSE_RECEIVED_BATCH_TOTAL_SIZE:
        raise NfseExternalXmlInboxError("O tamanho total do envio excede o limite permitido.")

    with transaction.atomic():
        inbox = NfseExternalXmlInbox.objects.create(
            workshop=workshop,
            company=company,
            source_type=NfseExternalXmlInbox.SourceType.MANUAL_UPLOAD,
            source_label=(source_label or "Upload manual").strip()[:120],
            created_by=created_by if getattr(created_by, "is_authenticated", False) else None,
        )
        seen_hashes: set[str] = set()
        seen_uuids: set[str] = set()
        seen_identifiers: set[str] = set()
        for upload_file in files:
            _create_candidate_item(inbox=inbox, upload_file=upload_file, seen_hashes=seen_hashes, seen_uuids=seen_uuids, seen_identifiers=seen_identifiers)
        refresh_nfse_external_xml_inbox_totals(inbox)
        return inbox


@transaction.atomic
def approve_nfse_external_xml_inbox_item(*, item: NfseExternalXmlInboxItem, approved_by: Any | None = None) -> NfseExternalXmlInboxItem:
    locked = NfseExternalXmlInboxItem.objects.select_for_update().select_related("inbox", "inbox__company").get(pk=item.pk)
    if locked.status != NfseExternalXmlInboxItem.Status.PENDING:
        raise NfseExternalXmlInboxError("Somente item pendente pode ser aprovado.")
    if not locked.xml_snapshot.strip() or not locked.xml_hash:
        raise NfseExternalXmlInboxError("Item sem XML válido não pode ser aprovado.")
    if _active_duplicate_exists(item=locked):
        locked.status = NfseExternalXmlInboxItem.Status.DUPLICATE
        locked.validation_errors = ["XML duplicado em item ativo da inbox."]
        locked.save(update_fields=["status", "validation_errors", "atualizado_em"])
        refresh_nfse_external_xml_inbox_totals(locked.inbox)
        raise NfseExternalXmlInboxError("XML duplicado em item ativo da inbox.")
    locked.status = NfseExternalXmlInboxItem.Status.APPROVED
    locked.approved_by = approved_by if getattr(approved_by, "is_authenticated", False) else None
    locked.approved_at = timezone.now()
    locked.save(update_fields=["status", "approved_by", "approved_at", "atualizado_em"])
    refresh_nfse_external_xml_inbox_totals(locked.inbox)
    return locked


@transaction.atomic
def discard_nfse_external_xml_inbox_item(*, item: NfseExternalXmlInboxItem, reason: str, discarded_by: Any | None = None) -> NfseExternalXmlInboxItem:
    locked = NfseExternalXmlInboxItem.objects.select_for_update().select_related("inbox").get(pk=item.pk)
    if locked.status == NfseExternalXmlInboxItem.Status.PROCESSED:
        raise NfseExternalXmlInboxError("Item processado não pode ser descartado.")
    reason = reason.strip()
    if not reason:
        raise NfseExternalXmlInboxError("Informe o motivo do descarte.")
    locked.status = NfseExternalXmlInboxItem.Status.DISCARDED
    locked.discard_reason = reason[:1000]
    locked.discarded_by = discarded_by if getattr(discarded_by, "is_authenticated", False) else None
    locked.discarded_at = timezone.now()
    locked.save(update_fields=["status", "discard_reason", "discarded_by", "discarded_at", "atualizado_em"])
    refresh_nfse_external_xml_inbox_totals(locked.inbox)
    return locked


@transaction.atomic
def process_nfse_external_xml_inbox(*, inbox: NfseExternalXmlInbox, processed_by: Any | None = None, item_ids: list[int] | None = None) -> NfseReceivedImportBatch:
    locked_inbox = NfseExternalXmlInbox.objects.select_related("company").get(pk=inbox.pk, workshop=inbox.workshop)
    approved_queryset = locked_inbox.items.select_for_update().filter(status=NfseExternalXmlInboxItem.Status.APPROVED, linked_batch__isnull=True)
    if item_ids is not None:
        approved_queryset = approved_queryset.filter(pk__in=item_ids)
    approved_items = list(approved_queryset.order_by("pk"))
    if not approved_items:
        raise NfseExternalXmlInboxError("Não ha itens aprovados para processar.")
    files = [NfseReceivedBatchFile(filename=item.safe_filename, content=item.xml_snapshot.encode("utf-8")) for item in approved_items]
    batch = import_nfse_received_xml_batch(workshop=locked_inbox.workshop, company=locked_inbox.company, files=files, created_by=processed_by)

    batch_items = _batch_items_by_hash(batch)
    now = timezone.now()
    for item in approved_items:
        linked_batch_item = batch_items.get(item.xml_hash)
        item.linked_batch = batch
        item.linked_batch_item = linked_batch_item
        item.linked_received_document = linked_batch_item.received_document if linked_batch_item and linked_batch_item.received_document_id else None
        item.processed_by = processed_by if getattr(processed_by, "is_authenticated", False) else None
        item.processed_at = now
        if linked_batch_item and linked_batch_item.status == NfseReceivedImportBatchItem.Status.IMPORTED:
            item.status = NfseExternalXmlInboxItem.Status.PROCESSED
            item.validation_errors = []
        else:
            item.status = NfseExternalXmlInboxItem.Status.ERROR
            item.validation_errors = linked_batch_item.validation_errors if linked_batch_item else ["Item não localizado no lote processado."]
        item.save(
            update_fields=[
                "status",
                "validation_errors",
                "processed_by",
                "processed_at",
                "linked_batch",
                "linked_batch_item",
                "linked_received_document",
                "atualizado_em",
            ]
        )
    locked_inbox.processed_by = processed_by if getattr(processed_by, "is_authenticated", False) else None
    locked_inbox.processed_at = now
    locked_inbox.save(update_fields=["processed_by", "processed_at", "atualizado_em"])
    refresh_nfse_external_xml_inbox_totals(locked_inbox)
    return batch


def bulk_approve_nfse_external_xml_inbox_items(*, inbox: NfseExternalXmlInbox, item_ids: list[int], approved_by: Any | None = None) -> NfseExternalXmlInboxBulkResult:
    items = _bulk_items(inbox=inbox, item_ids=item_ids)
    results: list[NfseExternalXmlInboxBulkItemResult] = []
    for item in items:
        try:
            approved = approve_nfse_external_xml_inbox_item(item=item, approved_by=approved_by)
        except NfseExternalXmlInboxError as exc:
            results.append(_bulk_result(item=item, success=False, message="; ".join(_messages(exc))))
        else:
            results.append(_bulk_result(item=approved, success=True, message="Item aprovado."))
    return NfseExternalXmlInboxBulkResult(action="approve", results=results)


def bulk_discard_nfse_external_xml_inbox_items(*, inbox: NfseExternalXmlInbox, item_ids: list[int], reason: str, discarded_by: Any | None = None) -> NfseExternalXmlInboxBulkResult:
    reason = reason.strip()
    if not reason:
        raise NfseExternalXmlInboxError("Informe o motivo do descarte.")
    items = _bulk_items(inbox=inbox, item_ids=item_ids)
    results: list[NfseExternalXmlInboxBulkItemResult] = []
    for item in items:
        try:
            discarded = discard_nfse_external_xml_inbox_item(item=item, reason=reason, discarded_by=discarded_by)
        except NfseExternalXmlInboxError as exc:
            results.append(_bulk_result(item=item, success=False, message="; ".join(_messages(exc))))
        else:
            results.append(_bulk_result(item=discarded, success=True, message="Item descartado."))
    return NfseExternalXmlInboxBulkResult(action="discard", results=results)


def bulk_process_nfse_external_xml_inbox_items(*, inbox: NfseExternalXmlInbox, item_ids: list[int], processed_by: Any | None = None) -> NfseExternalXmlInboxBulkResult:
    items = _bulk_items(inbox=inbox, item_ids=item_ids)
    results: list[NfseExternalXmlInboxBulkItemResult] = []
    eligible_ids: list[int] = []
    for item in items:
        if item.status != NfseExternalXmlInboxItem.Status.APPROVED:
            results.append(_bulk_result(item=item, success=False, message="Somente item aprovado pode ser processado."))
            continue
        if item.linked_batch_id or item.linked_received_document_id:
            results.append(_bulk_result(item=item, success=False, message="Item já possui vinculo de processamento."))
            continue
        if not item.xml_snapshot.strip() or not item.xml_hash:
            results.append(_bulk_result(item=item, success=False, message="Item sem XML válido não pode ser processado."))
            continue
        eligible_ids.append(item.pk)

    if eligible_ids:
        try:
            process_nfse_external_xml_inbox(inbox=inbox, processed_by=processed_by, item_ids=eligible_ids)
        except (NfseExternalXmlInboxError, ValidationError) as exc:
            message = "; ".join(_messages(exc))
            for item in items:
                if item.pk in eligible_ids:
                    results.append(_bulk_result(item=item, success=False, message=message))
        else:
            refreshed_items = {item.pk: item for item in NfseExternalXmlInboxItem.objects.filter(pk__in=eligible_ids)}
            for item_id in eligible_ids:
                refreshed = refreshed_items[item_id]
                if refreshed.status == NfseExternalXmlInboxItem.Status.PROCESSED:
                    results.append(_bulk_result(item=refreshed, success=True, message="Item processado pelo lote XML."))
                else:
                    results.append(_bulk_result(item=refreshed, success=False, message="; ".join(refreshed.validation_errors or ["Item processado com erro."])))
    return NfseExternalXmlInboxBulkResult(action="process", results=results)


def refresh_nfse_external_xml_inbox_totals(inbox: NfseExternalXmlInbox) -> None:
    items = list(inbox.items.all())
    total_items = len(items)
    pending_count = sum(1 for item in items if item.status == NfseExternalXmlInboxItem.Status.PENDING)
    approved_count = sum(1 for item in items if item.status == NfseExternalXmlInboxItem.Status.APPROVED)
    discarded_count = sum(1 for item in items if item.status == NfseExternalXmlInboxItem.Status.DISCARDED)
    processed_count = sum(1 for item in items if item.status == NfseExternalXmlInboxItem.Status.PROCESSED)
    error_count = sum(1 for item in items if item.status in {NfseExternalXmlInboxItem.Status.INVALID, NfseExternalXmlInboxItem.Status.DUPLICATE, NfseExternalXmlInboxItem.Status.ERROR})
    if processed_count and processed_count + discarded_count + error_count == total_items:
        status = NfseExternalXmlInbox.Status.PROCESSED
    elif processed_count or error_count and approved_count:
        status = NfseExternalXmlInbox.Status.PARTIALLY_PROCESSED
    elif total_items and error_count == total_items:
        status = NfseExternalXmlInbox.Status.FAILED
    else:
        status = NfseExternalXmlInbox.Status.OPEN
    NfseExternalXmlInbox.objects.filter(pk=inbox.pk).update(
        total_items=total_items,
        pending_count=pending_count,
        approved_count=approved_count,
        discarded_count=discarded_count,
        processed_count=processed_count,
        error_count=error_count,
        status=status,
        atualizado_em=timezone.now(),
    )
    inbox.total_items = total_items
    inbox.pending_count = pending_count
    inbox.approved_count = approved_count
    inbox.discarded_count = discarded_count
    inbox.processed_count = processed_count
    inbox.error_count = error_count
    inbox.status = status


def _create_candidate_item(*, inbox: NfseExternalXmlInbox, upload_file: NfseExternalXmlInboxUploadFile, seen_hashes: set[str], seen_uuids: set[str], seen_identifiers: set[str]) -> NfseExternalXmlInboxItem:
    original_filename = upload_file.filename or "arquivo.xml"
    safe_filename = _safe_filename(original_filename)
    content = upload_file.content
    structural_error = _validate_file_structure(filename=safe_filename, content=content)
    if structural_error:
        return _create_item(inbox=inbox, original_filename=original_filename, safe_filename=safe_filename, content_type=upload_file.content_type, size_bytes=len(content), status=NfseExternalXmlInboxItem.Status.INVALID, validation_errors=[structural_error])
    xml_hash = build_received_xml_hash(content)
    xml_snapshot = normalize_received_xml_for_hash(content).decode("utf-8", errors="replace")
    try:
        parsed = parse_nfse_received_xml(content)
    except NfseReceivedImportError as exc:
        return _create_item(
            inbox=inbox,
            original_filename=original_filename,
            safe_filename=safe_filename,
            content_type=upload_file.content_type,
            size_bytes=len(content),
            xml_snapshot=xml_snapshot,
            xml_hash=xml_hash,
            status=NfseExternalXmlInboxItem.Status.INVALID,
            validation_errors=_messages(exc),
        )

    role = resolve_nfse_received_role(company=inbox.company, parsed=parsed)
    validation_errors = validate_nfse_received_import(workshop=inbox.workshop, parsed=parsed, role=role)
    duplicate_errors = _find_inbox_duplicate_errors(inbox=inbox, parsed=parsed, seen_hashes=seen_hashes, seen_uuids=seen_uuids, seen_identifiers=seen_identifiers)
    _remember_seen(parsed=parsed, seen_hashes=seen_hashes, seen_uuids=seen_uuids, seen_identifiers=seen_identifiers)
    summary = _summary_from_parsed(parsed=parsed, role=role)
    if duplicate_errors:
        return _create_item(
            inbox=inbox,
            original_filename=original_filename,
            safe_filename=safe_filename,
            content_type=upload_file.content_type,
            size_bytes=len(content),
            xml_snapshot=parsed.xml_snapshot,
            xml_hash=parsed.xml_hash,
            status=NfseExternalXmlInboxItem.Status.DUPLICATE,
            validation_errors=duplicate_errors,
            parsed_summary=summary,
        )
    if validation_errors:
        status = NfseExternalXmlInboxItem.Status.DUPLICATE if any("já importado" in error.lower() or "duplic" in error.lower() for error in validation_errors) else NfseExternalXmlInboxItem.Status.INVALID
        return _create_item(
            inbox=inbox,
            original_filename=original_filename,
            safe_filename=safe_filename,
            content_type=upload_file.content_type,
            size_bytes=len(content),
            xml_snapshot=parsed.xml_snapshot,
            xml_hash=parsed.xml_hash,
            status=status,
            validation_errors=validation_errors,
            parsed_summary=summary,
        )
    return _create_item(
        inbox=inbox,
        original_filename=original_filename,
        safe_filename=safe_filename,
        content_type=upload_file.content_type,
        size_bytes=len(content),
        xml_snapshot=parsed.xml_snapshot,
        xml_hash=parsed.xml_hash,
        status=NfseExternalXmlInboxItem.Status.PENDING,
        parsed_summary=summary,
    )


def _validate_file_structure(*, filename: str, content: bytes) -> str:
    if not filename.lower().endswith(".xml"):
        return "Arquivo deve ter extensão .xml."
    if not content:
        return "Arquivo XML vazio."
    if len(content) > MAX_NFSE_RECEIVED_BATCH_FILE_SIZE:
        return "Arquivo XML excede o limite de 2 MB."
    if not content.lstrip().startswith(b"<"):
        return "Arquivo não contem XML."
    return ""


def _find_inbox_duplicate_errors(*, inbox: NfseExternalXmlInbox, parsed, seen_hashes: set[str], seen_uuids: set[str], seen_identifiers: set[str]) -> list[str]:
    errors: list[str] = []
    if parsed.xml_hash in seen_hashes:
        errors.append("XML duplicado dentro do envio.")
    if parsed.uuid and parsed.uuid in seen_uuids:
        errors.append("UUID duplicado dentro do envio.")
    if parsed.access_key_or_identifier and parsed.access_key_or_identifier in seen_identifiers:
        errors.append("Identificador duplicado dentro do envio.")
    active_items = NfseExternalXmlInboxItem.objects.filter(inbox__workshop=inbox.workshop, status__in=ACTIVE_INBOX_STATUSES)
    if active_items.filter(xml_hash=parsed.xml_hash).exists():
        errors.append("XML já existe em item ativo da inbox.")
    if parsed.xml_hash and NfseReceivedDocument.objects.filter(workshop=inbox.workshop, xml_hash=parsed.xml_hash).exists():
        errors.append("XML já importado como NFS-e recebida.")
    return errors


def _active_duplicate_exists(*, item: NfseExternalXmlInboxItem) -> bool:
    return NfseExternalXmlInboxItem.objects.filter(inbox__workshop=item.inbox.workshop, xml_hash=item.xml_hash, status__in=ACTIVE_INBOX_STATUSES).exclude(pk=item.pk).exists()


def _remember_seen(*, parsed, seen_hashes: set[str], seen_uuids: set[str], seen_identifiers: set[str]) -> None:
    seen_hashes.add(parsed.xml_hash)
    if parsed.uuid:
        seen_uuids.add(parsed.uuid)
    if parsed.access_key_or_identifier:
        seen_identifiers.add(parsed.access_key_or_identifier)


def _summary_from_parsed(*, parsed, role: str) -> dict[str, Any]:
    return {
        "uuid": parsed.uuid,
        "access_key_or_identifier": parsed.access_key_or_identifier,
        "provider_tax_id": parsed.provider_tax_id,
        "taker_tax_id": parsed.taker_tax_id,
        "intermediary_tax_id": parsed.intermediary_tax_id,
        "municipality_code": parsed.municipality_code,
        "environment": parsed.environment,
        "remote_status": parsed.remote_status,
        "service_amount": str(parsed.service_amount) if parsed.service_amount is not None else "",
        "role": role,
    }


def _batch_items_by_hash(batch: NfseReceivedImportBatch) -> dict[str, NfseReceivedImportBatchItem]:
    return {item.xml_hash: item for item in batch.items.all() if item.xml_hash}


def _bulk_items(*, inbox: NfseExternalXmlInbox, item_ids: list[int]) -> list[NfseExternalXmlInboxItem]:
    unique_ids = list(dict.fromkeys(item_ids))
    if not unique_ids:
        raise NfseExternalXmlInboxError("Selecione ao menos um item.")
    return list(NfseExternalXmlInboxItem.objects.filter(inbox=inbox, inbox__workshop=inbox.workshop, pk__in=unique_ids).select_related("inbox").order_by("pk"))


def _bulk_result(*, item: NfseExternalXmlInboxItem, success: bool, message: str) -> NfseExternalXmlInboxBulkItemResult:
    return NfseExternalXmlInboxBulkItemResult(item_id=item.pk, filename=item.safe_filename, status=item.status, success=success, message=message)


def _create_item(
    *,
    inbox: NfseExternalXmlInbox,
    original_filename: str,
    safe_filename: str,
    content_type: str,
    size_bytes: int,
    status: str,
    xml_snapshot: str = "",
    xml_hash: str = "",
    validation_errors: list[str] | None = None,
    parsed_summary: dict[str, Any] | None = None,
) -> NfseExternalXmlInboxItem:
    return NfseExternalXmlInboxItem.objects.create(
        inbox=inbox,
        original_filename=original_filename[:255],
        safe_filename=safe_filename,
        content_type=content_type[:120],
        xml_snapshot=xml_snapshot,
        xml_hash=xml_hash,
        size_bytes=size_bytes,
        source_metadata={"source_type": inbox.source_type, "source_label": inbox.source_label},
        status=status,
        validation_errors=validation_errors or [],
        parsed_summary=parsed_summary or {},
    )


def _safe_filename(filename: str) -> str:
    name = PurePath(filename or "arquivo.xml").name.strip() or "arquivo.xml"
    return name[:255]


def _messages(exc: ValidationError) -> list[str]:
    return list(getattr(exc, "messages", [str(exc)]))
