from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import re
from typing import Any
from xml.etree import ElementTree

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from apps.finance.models.finance import FiscalEmissionAttempt, FiscalEmissionOperationType, NfseItem, NfseReceivedDocument, WebmaniaCompany


TAX_ID_RE = re.compile(r"\D+")
CANCELED_STATUS_MARKERS = {"cancelada", "cancelado", "substituida", "substituido", "anulada", "anulado"}


@dataclass(frozen=True, slots=True)
class NfseReceivedParsedXml:
    xml_snapshot: str
    xml_hash: str
    uuid: str
    access_key_or_identifier: str
    verification_code: str
    provider_tax_id: str
    taker_tax_id: str
    intermediary_tax_id: str
    municipality_code: str
    environment: str
    issue_date: datetime | None
    service_amount: Decimal | None
    remote_status: str
    raw_payload: dict[str, Any]


class NfseReceivedImportError(ValidationError):
    pass


def normalize_tax_id(value: str | None) -> str:
    return TAX_ID_RE.sub("", value or "")


def normalize_received_xml_for_hash(xml_bytes: bytes) -> bytes:
    return xml_bytes.replace(b"\r\n", b"\n").replace(b"\r", b"\n").strip()


def build_received_xml_hash(xml_bytes: bytes) -> str:
    return hashlib.sha256(normalize_received_xml_for_hash(xml_bytes)).hexdigest()


def parse_nfse_received_xml(xml_bytes: bytes) -> NfseReceivedParsedXml:
    try:
        xml_snapshot = normalize_received_xml_for_hash(xml_bytes).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise NfseReceivedImportError("XML de NFS-e recebida invalido ou ilegivel.") from exc
    if _contains_unsafe_xml_declaration(xml_snapshot):
        raise NfseReceivedImportError("XML com DTD ou entidade externa nao e aceito nesta importacao.")
    try:
        root = ElementTree.fromstring(xml_snapshot)
    except ElementTree.ParseError as exc:
        raise NfseReceivedImportError("XML de NFS-e recebida invalido ou ilegivel.") from exc

    fields = {
        "uuid": _first_text(root, {"Uuid", "UUID", "IdNfse", "IdentificacaoNfse"}, prefer_attribute=("Id",)),
        "access_key_or_identifier": _first_text(root, {"ChaveAcesso", "ChaveNfse", "ChaveNFe", "NumeroNfse", "Numero", "InfNfse"}, prefer_attribute=("Id",)),
        "verification_code": _first_text(root, {"CodigoVerificacao", "CodigoAutenticidade", "Hash", "CodigoVerificador"}),
        "provider_tax_id": _first_tax_id_under(root, {"Prestador", "Fornecedor", "Emitente"}),
        "taker_tax_id": _first_tax_id_under(root, {"Tomador", "Destinatario", "ServicoTomado"}),
        "intermediary_tax_id": _first_tax_id_under(root, {"Intermediario", "IntermediarioServico"}),
        "municipality_code": _first_text(root, {"CodigoMunicipio", "CodigoMunicipioIncidencia", "MunicipioIncidencia", "CodigoMunicipioPrestacao"}),
        "environment": _normalize_environment(_first_text(root, {"Ambiente", "TpAmb", "tpAmb"})),
        "remote_status": _first_text(root, {"Status", "Situacao", "SituacaoNfse", "DescricaoStatus"}),
    }
    issue_date = _parse_issue_date(_first_text(root, {"DataEmissao", "DhEmi", "dhEmi", "dataEmissao"}))
    service_amount = _parse_decimal_amount(_first_text(root, {"ValorServicos", "ValorServico", "ValorTotalServicos", "ValorLiquidoNfse"}))

    raw_payload = {
        **fields,
        "issue_date": issue_date.isoformat() if issue_date else "",
        "service_amount": str(service_amount) if service_amount is not None else "",
        "root_tag": _local_name(root.tag),
    }
    return NfseReceivedParsedXml(xml_snapshot=xml_snapshot, xml_hash=build_received_xml_hash(xml_bytes), issue_date=issue_date, service_amount=service_amount, raw_payload=raw_payload, **fields)


@transaction.atomic
def import_nfse_received_xml(*, workshop, company: WebmaniaCompany, xml_bytes: bytes, created_by) -> NfseReceivedDocument:
    if company.workshop_id != workshop.pk:
        raise NfseReceivedImportError("A empresa Webmania pertence a outra oficina.")
    if not company.nfse_received_import_enabled:
        raise NfseReceivedImportError("Importacao de NFS-e recebida nao esta habilitada para esta empresa.")

    parsed = parse_nfse_received_xml(xml_bytes)
    role = resolve_nfse_received_role(company=company, parsed=parsed)
    validation_errors = validate_nfse_received_import(workshop=workshop, parsed=parsed, role=role)
    if validation_errors:
        raise NfseReceivedImportError(validation_errors)

    document = NfseReceivedDocument(
        workshop=workshop,
        company=company,
        source=NfseReceivedDocument.Source.XML_UPLOAD,
        xml_snapshot=parsed.xml_snapshot,
        xml_hash=parsed.xml_hash,
        uuid=parsed.uuid,
        access_key_or_identifier=parsed.access_key_or_identifier,
        verification_code=parsed.verification_code,
        provider_tax_id=parsed.provider_tax_id,
        taker_tax_id=parsed.taker_tax_id,
        intermediary_tax_id=parsed.intermediary_tax_id,
        municipality_code=parsed.municipality_code,
        environment=parsed.environment,
        issue_date=parsed.issue_date,
        service_amount=parsed.service_amount,
        status="received",
        remote_status=parsed.remote_status,
        role=role,
        validation_status=NfseReceivedDocument.ValidationStatus.VALIDATED,
        validation_errors=[],
        raw_payload=parsed.raw_payload,
        created_by=created_by,
    )
    document.save()
    return document


def resolve_nfse_received_role(*, company: WebmaniaCompany, parsed: NfseReceivedParsedXml) -> str:
    company_tax_ids = {normalize_tax_id(company.cnpj), normalize_tax_id(company.cpf)}
    company_tax_ids.discard("")
    if not company_tax_ids:
        return NfseReceivedDocument.Role.UNKNOWN

    matched_roles: set[str] = set()
    if parsed.provider_tax_id in company_tax_ids:
        matched_roles.add(NfseReceivedDocument.Role.PROVIDER)
    if parsed.taker_tax_id in company_tax_ids:
        matched_roles.add(NfseReceivedDocument.Role.TAKER)
    if parsed.intermediary_tax_id in company_tax_ids:
        matched_roles.add(NfseReceivedDocument.Role.INTERMEDIARY)
    if len(matched_roles) > 1:
        return NfseReceivedDocument.Role.MULTIPLE
    return next(iter(matched_roles), NfseReceivedDocument.Role.UNKNOWN)


def validate_nfse_received_import(*, workshop, parsed: NfseReceivedParsedXml, role: str) -> list[str]:
    errors: list[str] = []
    if not (parsed.uuid or parsed.access_key_or_identifier or parsed.verification_code):
        errors.append("XML sem UUID, chave/identificador ou codigo de verificacao.")
    if not (parsed.provider_tax_id or parsed.taker_tax_id or parsed.intermediary_tax_id):
        errors.append("XML sem CPF/CNPJ de prestador, tomador ou intermediario.")
    if role in {NfseReceivedDocument.Role.UNKNOWN, NfseReceivedDocument.Role.MULTIPLE}:
        errors.append("XML nao identifica de forma segura o papel fiscal da oficina.")
    if _status_is_blocked(parsed.remote_status):
        errors.append("XML indica NFS-e cancelada, substituida ou anulada; esta fase nao importa esse estado.")
    errors.extend(_find_local_duplicates(workshop=workshop, parsed=parsed))
    errors.extend(_find_issued_document_collisions(workshop=workshop, parsed=parsed))
    return errors


def _contains_unsafe_xml_declaration(xml_snapshot: str) -> bool:
    upper = xml_snapshot.upper()
    return "<!DOCTYPE" in upper or "<!ENTITY" in upper


def _status_is_blocked(value: str) -> bool:
    normalized = _normalize_text(value)
    return any(marker in normalized for marker in CANCELED_STATUS_MARKERS)


def _find_local_duplicates(*, workshop, parsed: NfseReceivedParsedXml) -> list[str]:
    errors: list[str] = []
    if NfseReceivedDocument.objects.filter(workshop=workshop, xml_hash=parsed.xml_hash).exists():
        errors.append("XML ja importado para esta oficina.")
    if parsed.uuid and NfseReceivedDocument.objects.filter(workshop=workshop, uuid=parsed.uuid).exists():
        errors.append("UUID de NFS-e recebida ja importado para esta oficina.")
    if parsed.access_key_or_identifier and NfseReceivedDocument.objects.filter(workshop=workshop, access_key_or_identifier=parsed.access_key_or_identifier).exists():
        errors.append("Identificador de NFS-e recebida ja importado para esta oficina.")
    return errors


def _find_issued_document_collisions(*, workshop, parsed: NfseReceivedParsedXml) -> list[str]:
    if parsed.uuid and NfseItem.objects.filter(workshop=workshop, uuid=parsed.uuid).exists():
        return ["XML recebido corresponde a NFS-e ja emitida localmente."]
    if parsed.uuid and FiscalEmissionAttempt.objects.filter(workshop=workshop, operation_type=FiscalEmissionOperationType.NFSE_MANUAL_EMISSION, remote_uuid=parsed.uuid).exists():
        return ["XML recebido corresponde a tentativa de emissao NFS-e local."]
    return []


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].split(":", 1)[-1]


def _first_text(root: ElementTree.Element, names: set[str], *, prefer_attribute: tuple[str, ...] = ()) -> str:
    normalized_names = {_normalize_text(name) for name in names}
    for element in root.iter():
        if _normalize_text(_local_name(element.tag)) not in normalized_names:
            continue
        for attr_name in prefer_attribute:
            attr_value = element.attrib.get(attr_name)
            if attr_value:
                return attr_value.strip()
        if element.text and element.text.strip():
            return element.text.strip()
    return ""


def _first_tax_id_under(root: ElementTree.Element, parent_names: set[str]) -> str:
    normalized_parent_names = {_normalize_text(name) for name in parent_names}
    for element in root.iter():
        if _normalize_text(_local_name(element.tag)) not in normalized_parent_names:
            continue
        tax_id = _first_text(element, {"Cnpj", "CNPJ", "Cpf", "CPF", "CpfCnpj", "CPFCNPJ"})
        normalized = normalize_tax_id(tax_id)
        if normalized:
            return normalized
    return ""


def _normalize_environment(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"1", "producao", "produção"}:
        return "1"
    if normalized in {"2", "homologacao", "homologação"}:
        return "2"
    return ""


def _parse_issue_date(value: str) -> datetime | None:
    if not value:
        return None
    parsed_datetime = parse_datetime(value)
    if parsed_datetime is not None:
        if timezone.is_naive(parsed_datetime):
            return timezone.make_aware(parsed_datetime)
        return parsed_datetime
    parsed_date = parse_date(value)
    if parsed_date is None:
        return None
    return timezone.make_aware(datetime.combine(parsed_date, datetime.min.time()))


def _parse_decimal_amount(value: str) -> Decimal | None:
    if not value:
        return None
    normalized = value.strip().replace(".", "").replace(",", ".") if "," in value else value.strip()
    try:
        return Decimal(normalized).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def _normalize_text(value: str) -> str:
    return value.strip().lower()
