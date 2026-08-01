from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePath
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.finance.models.finance import NfseReceivedImportBatch, NfseReceivedImportBatchItem, WebmaniaCompany
from apps.finance.services.nfse_received import NfseReceivedImportError, import_nfse_received_xml, parse_nfse_received_xml


MAX_NFSE_RECEIVED_BATCH_FILES = 20
MAX_NFSE_RECEIVED_BATCH_FILE_SIZE = 2 * 1024 * 1024
MAX_NFSE_RECEIVED_BATCH_TOTAL_SIZE = 20 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class NfseReceivedBatchFile:
    filename: str
    content: bytes


class NfseReceivedBatchImportError(ValidationError):
    pass


def import_nfse_received_xml_batch(*, workshop, company: WebmaniaCompany, files: list[NfseReceivedBatchFile], created_by) -> NfseReceivedImportBatch:
    if company.workshop_id != workshop.pk:
        raise NfseReceivedBatchImportError("A empresa emissora pertence a outra oficina.")
    if not company.nfse_received_import_enabled:
        raise NfseReceivedBatchImportError("Importacao de NFS-e recebida não esta habilitada para esta empresa.")
    if not files:
        raise NfseReceivedBatchImportError("Envie ao menos um XML.")
    if len(files) > MAX_NFSE_RECEIVED_BATCH_FILES:
        raise NfseReceivedBatchImportError(f"O lote deve ter no maximo {MAX_NFSE_RECEIVED_BATCH_FILES} arquivos.")
    total_size = sum(len(item.content) for item in files)
    if total_size > MAX_NFSE_RECEIVED_BATCH_TOTAL_SIZE:
        raise NfseReceivedBatchImportError("O tamanho total do lote excede o limite permitido.")

    batch = NfseReceivedImportBatch.objects.create(
        workshop=workshop,
        company=company,
        total_files=len(files),
        created_by=created_by if getattr(created_by, "is_authenticated", False) else None,
    )
    seen_hashes: set[str] = set()
    seen_uuids: set[str] = set()
    seen_identifiers: set[str] = set()

    for batch_file in files:
        _process_batch_file(batch=batch, batch_file=batch_file, seen_hashes=seen_hashes, seen_uuids=seen_uuids, seen_identifiers=seen_identifiers, created_by=created_by)

    _refresh_batch_totals(batch)
    return batch


def _process_batch_file(*, batch: NfseReceivedImportBatch, batch_file: NfseReceivedBatchFile, seen_hashes: set[str], seen_uuids: set[str], seen_identifiers: set[str], created_by) -> None:
    filename = _safe_filename(batch_file.filename)
    content = batch_file.content
    structural_error = _validate_file_structure(filename=filename, content=content)
    if structural_error:
        _create_item(batch=batch, filename=filename, status=structural_error[0], error_code=structural_error[1], error_message=structural_error[2], validation_errors=[structural_error[2]])
        return

    try:
        parsed = parse_nfse_received_xml(content)
    except NfseReceivedImportError as exc:
        message = _error_message(exc)
        _create_item(batch=batch, filename=filename, status=NfseReceivedImportBatchItem.Status.INVALID_XML, error_code="invalid_xml", error_message=message, validation_errors=[message])
        return

    raw_summary = _summary_from_parsed(parsed)
    duplicate_error = _find_duplicate_in_batch(parsed=parsed, seen_hashes=seen_hashes, seen_uuids=seen_uuids, seen_identifiers=seen_identifiers)
    _remember_seen(parsed=parsed, seen_hashes=seen_hashes, seen_uuids=seen_uuids, seen_identifiers=seen_identifiers)
    if duplicate_error:
        _create_item(batch=batch, filename=filename, xml_hash=parsed.xml_hash, status=NfseReceivedImportBatchItem.Status.DUPLICATE, error_code="duplicate_in_batch", error_message=duplicate_error, validation_errors=[duplicate_error], raw_summary=raw_summary)
        return

    try:
        with transaction.atomic():
            document = import_nfse_received_xml(workshop=batch.workshop, company=batch.company, xml_bytes=content, created_by=created_by)
    except (NfseReceivedImportError, ValidationError) as exc:
        message = _error_message(exc)
        status, error_code = _classify_import_error(message)
        _create_item(batch=batch, filename=filename, xml_hash=parsed.xml_hash, status=status, error_code=error_code, error_message=message, validation_errors=getattr(exc, "messages", [message]), raw_summary=raw_summary)
        return

    _create_item(batch=batch, filename=filename, xml_hash=parsed.xml_hash, status=NfseReceivedImportBatchItem.Status.IMPORTED, received_document=document, raw_summary=raw_summary)


def _validate_file_structure(*, filename: str, content: bytes) -> tuple[str, str, str] | None:
    if not filename.lower().endswith(".xml"):
        return NfseReceivedImportBatchItem.Status.INVALID_XML, "invalid_extension", "Arquivo deve ter extensão .xml."
    if not content:
        return NfseReceivedImportBatchItem.Status.INVALID_XML, "empty_file", "Arquivo XML vazio."
    if len(content) > MAX_NFSE_RECEIVED_BATCH_FILE_SIZE:
        return NfseReceivedImportBatchItem.Status.REJECTED, "file_too_large", "Arquivo XML excede o limite de 2 MB."
    stripped = content.lstrip()
    if not stripped.startswith(b"<"):
        return NfseReceivedImportBatchItem.Status.INVALID_XML, "invalid_content", "Arquivo não contem XML."
    return None


def _find_duplicate_in_batch(*, parsed, seen_hashes: set[str], seen_uuids: set[str], seen_identifiers: set[str]) -> str:
    if parsed.xml_hash in seen_hashes:
        return "XML duplicado dentro do lote."
    if parsed.uuid and parsed.uuid in seen_uuids:
        return "UUID duplicado dentro do lote."
    if parsed.access_key_or_identifier and parsed.access_key_or_identifier in seen_identifiers:
        return "Identificador duplicado dentro do lote."
    return ""


def _remember_seen(*, parsed, seen_hashes: set[str], seen_uuids: set[str], seen_identifiers: set[str]) -> None:
    seen_hashes.add(parsed.xml_hash)
    if parsed.uuid:
        seen_uuids.add(parsed.uuid)
    if parsed.access_key_or_identifier:
        seen_identifiers.add(parsed.access_key_or_identifier)


def _summary_from_parsed(parsed) -> dict[str, Any]:
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
    }


def _classify_import_error(message: str) -> tuple[str, str]:
    normalized = message.lower()
    if "já importado" in normalized or "já importado" in normalized or "duplic" in normalized or "uuid de nfs-e recebida" in normalized or "identificador de nfs-e recebida" in normalized:
        return NfseReceivedImportBatchItem.Status.DUPLICATE, "duplicate_existing"
    if "papel fiscal" in normalized or "cpf/cnpj" in normalized or "outra oficina" in normalized or "empresa emissora" in normalized or "empresa webmania" in normalized or "emitida localmente" in normalized:
        return NfseReceivedImportBatchItem.Status.INVALID_TENANT, "invalid_tenant"
    if "xml" in normalized and ("invalido" in normalized or "ilegivel" in normalized or "dtd" in normalized or "entidade" in normalized):
        return NfseReceivedImportBatchItem.Status.INVALID_XML, "invalid_xml"
    return NfseReceivedImportBatchItem.Status.REJECTED, "validation_error"


def _create_item(
    *,
    batch: NfseReceivedImportBatch,
    filename: str,
    status: str,
    xml_hash: str = "",
    received_document=None,
    error_code: str = "",
    error_message: str = "",
    validation_errors: list[str] | None = None,
    raw_summary: dict[str, Any] | None = None,
) -> NfseReceivedImportBatchItem:
    return NfseReceivedImportBatchItem.objects.create(
        batch=batch,
        filename=filename,
        xml_hash=xml_hash,
        status=status,
        received_document=received_document,
        error_code=error_code,
        error_message=error_message,
        validation_errors=validation_errors or [],
        raw_summary=raw_summary or {},
    )


def _refresh_batch_totals(batch: NfseReceivedImportBatch) -> None:
    items = list(batch.items.all())
    success_count = sum(1 for item in items if item.status == NfseReceivedImportBatchItem.Status.IMPORTED)
    duplicate_count = sum(1 for item in items if item.status == NfseReceivedImportBatchItem.Status.DUPLICATE)
    error_count = len(items) - success_count
    if not items or success_count == 0 and error_count == len(items):
        status = NfseReceivedImportBatch.Status.FAILED
    elif error_count:
        status = NfseReceivedImportBatch.Status.COMPLETED_WITH_ERRORS
    else:
        status = NfseReceivedImportBatch.Status.COMPLETED
    batch.success_count = success_count
    batch.duplicate_count = duplicate_count
    batch.error_count = error_count
    batch.status = status
    batch.save(update_fields=["success_count", "duplicate_count", "error_count", "status", "atualizado_em"])


def _safe_filename(filename: str) -> str:
    name = PurePath(filename or "arquivo.xml").name.strip() or "arquivo.xml"
    return name[:255]


def _error_message(exc: ValidationError) -> str:
    return "; ".join(getattr(exc, "messages", [str(exc)]))
