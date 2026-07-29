from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import Any

import requests
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.http import HttpRequest

from apps.finance.models.finance import (
    FiscalDocument,
    FiscalDocumentLink,
    FiscalDocumentLinkRole,
    FiscalDocumentOrigin,
    FiscalDocumentPurpose,
    FiscalDocumentStatus,
    FiscalDocumentType,
    FiscalEmissionAttemptStatus,
    FiscalEmissionDocumentKind,
    FiscalEmissionOperationType,
    WebmaniaCompany,
)
from apps.core.infrastructure.services.webmania.emission import build_webmania_webhook_url
from apps.finance.services.fiscal_attempts import FiscalEmissionAttemptBlocked, begin_emission_attempt, build_fiscal_document_operation_idempotency_key, build_payload_hash, mark_attempt_failed, mark_attempt_sent, mark_attempt_succeeded, mark_attempt_uncertain, sanitize_fiscal_payload
from apps.core.infrastructure.services.webmania.webmania_auth import WebmaniaAuthError, build_webmania_headers, sanitize_webmania_setting, should_use_global_webmania_auth
from apps.core.infrastructure.services.webmania.webmania_errors import build_webmania_request_exception_message, extract_webmania_error_message


logger = logging.getLogger(__name__)

ALLOWED_ADJUSTMENT_REGIMES = {"lucro_real", "lucro_normal", "lucro_presumido"}
BLOCKED_ADJUSTMENT_REGIMES = {"simples_nacional", "simples_nacional_sublimite", "mei"}
FORBIDDEN_ADJUSTMENT_PAYLOAD_KEYS = {
    "adicao",
    "adicoes",
    "agropecuario",
    "cbs",
    "cod_evento",
    "dfe_referenciado",
    "evento",
    "evento_ibs_cbs",
    "finalidade",
    "ibs",
    "ibs_cbs",
    "importacao",
    "impostos",
    "pedido",
    "produtos",
    "tipo_credito",
    "tipo_debito",
}


class NfeAdjustmentError(Exception):
    pass


def _build_headers(*, workshop=None) -> dict[str, str]:
    try:
        if should_use_global_webmania_auth():
            return build_webmania_headers()
        return build_webmania_headers(workshop=workshop)
    except WebmaniaAuthError as exc:
        raise NfeAdjustmentError(str(exc)) from exc


def _build_adjustment_url() -> str:
    custom_endpoint = sanitize_webmania_setting(getattr(settings, "WEBMANIA_NFE_ADJUSTMENT_ENDPOINT", ""))
    if custom_endpoint:
        return f"{custom_endpoint.rstrip('/')}/"
    base_url = sanitize_webmania_setting(getattr(settings, "WEBMANIA_TAX_CLASS_BASE_URL", "https://webmania.com.br/api")).rstrip("/")
    return f"{base_url}/1/nfe/ajuste/"


def _build_consulta_url() -> str:
    custom_endpoint = sanitize_webmania_setting(getattr(settings, "WEBMANIA_NFE_CONSULTA_ENDPOINT", ""))
    if custom_endpoint:
        return f"{custom_endpoint.rstrip('/')}/"
    base_url = sanitize_webmania_setting(getattr(settings, "WEBMANIA_TAX_CLASS_BASE_URL", "https://webmania.com.br/api")).rstrip("/")
    return f"{base_url}/1/nfe/consulta/"


def _decimal(value: Any, *, field_name: str, required_positive: bool = False) -> Decimal:
    raw_value = str(value if value is not None else "").strip()
    if not raw_value:
        raise NfeAdjustmentError(f"Informe valor valido para {field_name}.")
    try:
        decimal_value = Decimal(raw_value.replace(",", "."))
    except InvalidOperation as exc:
        raise NfeAdjustmentError(f"Informe valor valido para {field_name}.") from exc
    if required_positive and decimal_value <= 0:
        raise NfeAdjustmentError(f"{field_name} deve ser maior que zero.")
    if decimal_value < 0:
        raise NfeAdjustmentError(f"{field_name} nao pode ser negativo.")
    return decimal_value


def _decimal_to_payload(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), "f")


def _normalize_operation(value: Any) -> int:
    raw_value = str(value if value is not None else "").strip()
    if raw_value not in {"0", "1"}:
        raise NfeAdjustmentError("Operacao da Nota Fiscal de Ajuste deve ser 0 para entrada ou 1 para saida.")
    return int(raw_value)


def _normalize_required_text(value: Any, *, field_name: str, max_length: int) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise NfeAdjustmentError(f"{field_name} e obrigatorio.")
    if len(normalized) > max_length:
        raise NfeAdjustmentError(f"{field_name} excede {max_length} caracteres.")
    return normalized


def _normalize_optional_text(value: Any, *, field_name: str, max_length: int) -> str:
    normalized = str(value or "").strip()
    if len(normalized) > max_length:
        raise NfeAdjustmentError(f"{field_name} excede {max_length} caracteres.")
    return normalized


def _company_for_workshop(*, workshop: Any) -> WebmaniaCompany | None:
    return WebmaniaCompany.objects.filter(workshop=workshop).first()


def validate_adjustment_tax_regime(*, workshop: Any) -> str:
    company = _company_for_workshop(workshop=workshop)
    regime = str(getattr(company, "regime_tributario", "") or "").strip().lower()
    if regime in ALLOWED_ADJUSTMENT_REGIMES:
        return regime
    if regime in BLOCKED_ADJUSTMENT_REGIMES:
        raise NfeAdjustmentError("Nota Fiscal de Ajuste permitida somente para Lucro Real/Normal ou Lucro Presumido.")
    raise NfeAdjustmentError("Configure o regime tributario da empresa Webmania antes de emitir Nota Fiscal de Ajuste.")


def _assert_adjustment_scope(payload: dict[str, Any], *, source: str = "payload") -> None:
    forbidden_keys = sorted(str(key) for key in payload if str(key) in FORBIDDEN_ADJUSTMENT_PAYLOAD_KEYS)
    if forbidden_keys:
        if "finalidade" in forbidden_keys and str(payload.get("finalidade") or "").strip() in {"5", "6"}:
            raise NfeAdjustmentError("Nota Fiscal de Ajuste nao pode ser usada para Nota Fiscal de Credito ou Debito. Use a fase propria de IBS/CBS quando aprovada.")
        if any(key in forbidden_keys for key in ("evento", "evento_ibs_cbs", "cod_evento")):
            raise NfeAdjustmentError("Nota Fiscal de Ajuste nao pode registrar eventos IBS/CBS. Use o fluxo proprio de eventos quando aprovado.")
        if "produtos" in forbidden_keys:
            raise NfeAdjustmentError("Nota Fiscal de Ajuste nao pode conter produtos. Estorno deve usar o fluxo de devolucao/estorno.")
        if any(key in forbidden_keys for key in ("ibs", "cbs", "ibs_cbs", "impostos")):
            raise NfeAdjustmentError("Nota Fiscal de Ajuste nao aceita IBS/CBS ou impostos de produto sem contrato oficial.")
        if any(key in forbidden_keys for key in ("tipo_credito", "tipo_debito", "dfe_referenciado")):
            raise NfeAdjustmentError("Nota Fiscal de Ajuste nao pode ser usada para credito/debito fiscal.")
        raise NfeAdjustmentError(f"Campo fora do contrato de ajuste em {source}: {', '.join(forbidden_keys)}.")


def _build_adjustment_payload(
    *,
    workshop: Any,
    operacao: Any,
    natureza_operacao: str,
    codigo_cfop: str,
    valor_icms: Any,
    situacao_tributaria: str,
    cliente: dict[str, Any],
    valor_icms_st: Any | None = None,
    informacoes_fisco: str = "",
    informacoes_complementares: str = "",
    extra_payload: dict[str, Any] | None = None,
    request: HttpRequest | None = None,
) -> dict[str, Any]:
    if not isinstance(cliente, dict) or not cliente:
        raise NfeAdjustmentError("Cliente e obrigatorio para Nota Fiscal de Ajuste.")
    if extra_payload is not None:
        if not isinstance(extra_payload, dict):
            raise NfeAdjustmentError("Campos adicionais da Nota Fiscal de Ajuste devem ser informados como objeto.")
        _assert_adjustment_scope(extra_payload, source="campos adicionais")
    payload: dict[str, Any] = {
        "operacao": _normalize_operation(operacao),
        "natureza_operacao": _normalize_required_text(natureza_operacao, field_name="Natureza da operacao", max_length=60),
        "codigo_cfop": _normalize_required_text(codigo_cfop, field_name="CFOP de ajuste", max_length=10),
        "valor_icms": _decimal_to_payload(_decimal(valor_icms, field_name="valor_icms", required_positive=True)),
        "ambiente": int(str(getattr(settings, "WEBMANIA_AMBIENT", "2") or "2")),
        "cliente": sanitize_fiscal_payload(cliente),
        "situacao_tributaria": _normalize_required_text(situacao_tributaria, field_name="Situacao tributaria", max_length=4),
    }
    if valor_icms_st not in (None, ""):
        payload["valor_icms_st"] = _decimal_to_payload(_decimal(valor_icms_st, field_name="valor_icms_st"))
    fiscal_info = _normalize_optional_text(informacoes_fisco, field_name="Informacoes ao fisco", max_length=2000)
    if fiscal_info:
        payload["informacoes_fisco"] = fiscal_info
    complementary_info = _normalize_optional_text(informacoes_complementares, field_name="Informacoes complementares", max_length=5000)
    if complementary_info:
        payload["informacoes_complementares"] = complementary_info
    notification_url = build_webmania_webhook_url(request=request)
    if notification_url:
        payload["url_notificacao"] = notification_url
    _assert_adjustment_scope(payload)
    return payload


def create_nfe_adjustment_draft(
    *,
    workshop: Any,
    requested_by: Any | None = None,
    operacao: Any,
    natureza_operacao: str,
    codigo_cfop: str,
    valor_icms: Any,
    situacao_tributaria: str,
    cliente: dict[str, Any],
    valor_icms_st: Any | None = None,
    informacoes_fisco: str = "",
    informacoes_complementares: str = "",
    extra_payload: dict[str, Any] | None = None,
    related_document: FiscalDocument | None = None,
    legal_confirmation: bool = False,
    estorno_sc_es_confirmation: bool = False,
    request: HttpRequest | None = None,
) -> FiscalDocument:
    if not legal_confirmation:
        raise NfeAdjustmentError("Confirme explicitamente a emissao da Nota Fiscal de Ajuste.")
    if not estorno_sc_es_confirmation:
        raise NfeAdjustmentError("Confirme que este caso nao e estorno SC/ES que deve usar devolucao/estorno.")
    tax_regime = validate_adjustment_tax_regime(workshop=workshop)
    payload = _build_adjustment_payload(
        workshop=workshop,
        operacao=operacao,
        natureza_operacao=natureza_operacao,
        codigo_cfop=codigo_cfop,
        valor_icms=valor_icms,
        valor_icms_st=valor_icms_st,
        situacao_tributaria=situacao_tributaria,
        cliente=cliente,
        informacoes_fisco=informacoes_fisco,
        informacoes_complementares=informacoes_complementares,
        extra_payload=extra_payload,
        request=request,
    )
    _assert_adjustment_scope(payload)
    with transaction.atomic():
        locked_related: FiscalDocument | None = None
        if related_document is not None:
            locked_related = FiscalDocument.objects.select_for_update().get(pk=related_document.pk, workshop=workshop)
        document = FiscalDocument.objects.create(
            workshop=workshop,
            account=getattr(workshop, "account", None),
            document_type=FiscalDocumentType.NFE,
            origin=FiscalDocumentOrigin.MANUAL,
            purpose=FiscalDocumentPurpose.ADJUSTMENT,
            environment=str(payload["ambiente"]),
            status=FiscalDocumentStatus.PROCESSING,
            remote_status=FiscalEmissionAttemptStatus.STARTED,
            request_payload=sanitize_fiscal_payload({**payload, "tax_regime": tax_regime}),
            requested_by=requested_by if getattr(requested_by, "is_authenticated", False) else None,
        )
        if locked_related is not None:
            FiscalDocumentLink.objects.create(document=document, related_document=locked_related, role=FiscalDocumentLinkRole.ADJUSTS, metadata=sanitize_fiscal_payload({"purpose": FiscalDocumentPurpose.ADJUSTMENT}))
        return document


def _is_failed_response(payload: dict[str, Any]) -> bool:
    status = str(payload.get("status") or "").strip().lower()
    return status in {"erro", "error", "falha", "failed", "reprovado", "rejeitado"}


def _status_from_payload(payload: dict[str, Any]) -> str:
    status = str(payload.get("status") or "").strip().lower()
    if status in {FiscalDocumentStatus.APPROVED, FiscalDocumentStatus.REPROVED, FiscalDocumentStatus.CANCELED, FiscalDocumentStatus.DENIED, FiscalDocumentStatus.CONTINGENCY, FiscalDocumentStatus.PROCESSING}:
        return status
    if _is_failed_response(payload):
        return FiscalDocumentStatus.REPROVED
    return FiscalDocumentStatus.APPROVED if str(payload.get("uuid") or payload.get("chave") or "").strip() else FiscalDocumentStatus.PROCESSING


def apply_nfe_adjustment_document_payload(*, document: FiscalDocument, response_payload: dict[str, Any]) -> FiscalDocument:
    document.response_payload = sanitize_fiscal_payload(response_payload)
    document.status = _status_from_payload(response_payload)
    document.remote_status = str(response_payload.get("status") or document.remote_status or "").strip()
    document.remote_uuid = str(response_payload.get("uuid") or document.remote_uuid or "").strip()
    document.access_key = str(response_payload.get("chave") or document.access_key or "").strip()
    document.number = str(response_payload.get("nfe") or response_payload.get("numero") or document.number or "").strip()
    document.series = str(response_payload.get("serie") or document.series or "").strip()
    document.receipt = str(response_payload.get("recibo") or document.receipt or "").strip()
    document.xml_url = str(response_payload.get("xml") or document.xml_url or "").strip()
    document.danfe_url = str(response_payload.get("danfe") or document.danfe_url or "").strip()
    document.save(update_fields=["response_payload", "status", "remote_status", "remote_uuid", "access_key", "number", "series", "receipt", "xml_url", "danfe_url", "atualizado_em"])
    return document


def _mark_document_uncertain(*, document: FiscalDocument, error_message: str) -> None:
    document.status = FiscalDocumentStatus.UNCERTAIN
    document.response_payload = sanitize_fiscal_payload({"error": error_message})
    document.remote_status = FiscalDocumentStatus.UNCERTAIN
    document.save(update_fields=["status", "response_payload", "remote_status", "atualizado_em"])


def _assert_transmittable(*, document: FiscalDocument) -> None:
    if document.origin != FiscalDocumentOrigin.MANUAL or document.purpose != FiscalDocumentPurpose.ADJUSTMENT:
        raise NfeAdjustmentError("Documento fiscal invalido para transmissao de ajuste.")
    existing_attempt = document.emission_attempts.filter(operation_type=FiscalEmissionOperationType.ADJUSTMENT).order_by("-pk").first()
    if existing_attempt is None:
        return
    if existing_attempt.status == FiscalEmissionAttemptStatus.UNCERTAIN:
        raise NfeAdjustmentError("Ja existe tentativa de ajuste em estado remoto incerto. Reconcilie antes de tentar novamente.")
    if existing_attempt.status in {FiscalEmissionAttemptStatus.SENT, FiscalEmissionAttemptStatus.SUCCEEDED}:
        raise NfeAdjustmentError("Esta intencao de ajuste ja possui envio remoto registrado.")
    raise NfeAdjustmentError("Esta intencao de ajuste ja possui tentativa fiscal registrada.")


def transmit_nfe_adjustment_document(*, document: FiscalDocument) -> FiscalDocument:
    with transaction.atomic():
        locked_document = FiscalDocument.objects.select_for_update().select_related("workshop").get(pk=document.pk)
        _assert_transmittable(document=locked_document)
        validate_adjustment_tax_regime(workshop=locked_document.workshop)
        payload = dict(locked_document.request_payload or {})
        payload.pop("tax_regime", None)
        _assert_adjustment_scope(payload)
        idempotency_key = build_fiscal_document_operation_idempotency_key(workshop_id=locked_document.workshop_id, derived_document_id=locked_document.pk, operation_type=FiscalEmissionOperationType.ADJUSTMENT, request_generation=1)
        try:
            attempt = begin_emission_attempt(
                workshop=locked_document.workshop,
                document_kind=FiscalEmissionDocumentKind.NFE,
                operation_type=FiscalEmissionOperationType.ADJUSTMENT,
                request_model=FiscalDocument.__name__,
                request_id=locked_document.pk,
                fiscal_document=locked_document,
                idempotency_key=idempotency_key,
                request_payload=payload,
                payload_hash=build_payload_hash(payload),
            )
        except FiscalEmissionAttemptBlocked as exc:
            raise NfeAdjustmentError(str(exc)) from exc

    headers = _build_headers(workshop=locked_document.workshop)
    mark_attempt_sent(attempt=attempt)
    try:
        response = requests.post(_build_adjustment_url(), json=payload, headers=headers, timeout=30)
        response.raise_for_status()
    except requests.Timeout as exc:
        message = "Timeout ao emitir Nota Fiscal de Ajuste; estado remoto incerto."
        logger.warning("nfe_adjustment_timeout", extra={"fiscal_document_id": locked_document.pk, "fiscal_attempt_id": attempt.pk})
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        _mark_document_uncertain(document=locked_document, error_message=message)
        raise NfeAdjustmentError(message) from exc
    except requests.RequestException as exc:
        message = build_webmania_request_exception_message(exc, default="Falha ao emitir Nota Fiscal de Ajuste", scope="nfe")
        mark_attempt_failed(attempt=attempt, error_message=message)
        locked_document.status = FiscalDocumentStatus.REPROVED
        locked_document.response_payload = sanitize_fiscal_payload({"error": message})
        locked_document.save(update_fields=["status", "response_payload", "atualizado_em"])
        raise NfeAdjustmentError(message) from exc

    try:
        response_payload = response.json()
    except ValueError as exc:
        message = "Resposta invalida da Webmania ao emitir Nota Fiscal de Ajuste; estado remoto incerto."
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        _mark_document_uncertain(document=locked_document, error_message=message)
        raise NfeAdjustmentError(message) from exc
    if not isinstance(response_payload, dict):
        message = "Resposta invalida da Webmania ao emitir Nota Fiscal de Ajuste; estado remoto incerto."
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        _mark_document_uncertain(document=locked_document, error_message=message)
        raise NfeAdjustmentError(message)

    locked_document = apply_nfe_adjustment_document_payload(document=locked_document, response_payload=response_payload)
    if _is_failed_response(response_payload):
        message = extract_webmania_error_message(response_payload, scope="nfe") or "Nota Fiscal de Ajuste rejeitada pela Webmania."
        mark_attempt_failed(attempt=attempt, error_message=message, response_payload=response_payload)
        raise NfeAdjustmentError(message)
    mark_attempt_succeeded(attempt=attempt, response_payload=response_payload)
    return locked_document


def create_and_emit_nfe_adjustment(**kwargs: Any) -> FiscalDocument:
    document = create_nfe_adjustment_draft(**kwargs)
    return transmit_nfe_adjustment_document(document=document)


def consult_nfe_adjustment_document(*, document: FiscalDocument) -> dict[str, Any]:
    params: dict[str, str] = {}
    if str(document.remote_uuid or "").strip():
        params["uuid"] = str(document.remote_uuid).strip()
    elif str(document.access_key or "").strip():
        params["chave"] = str(document.access_key).strip()
    else:
        attempt = document.emission_attempts.exclude(remote_uuid="").order_by("-pk").first()
        if attempt is not None:
            params["uuid"] = str(attempt.remote_uuid).strip()
    if not params:
        raise NfeAdjustmentError("Nao foi possivel consultar a Nota Fiscal de Ajuste sem UUID ou chave de acesso.")
    try:
        response = requests.get(_build_consulta_url(), params=params, headers=_build_headers(workshop=document.workshop), timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        message = build_webmania_request_exception_message(exc, default="Falha ao consultar Nota Fiscal de Ajuste", scope="nfe")
        raise NfeAdjustmentError(message) from exc
    try:
        payload = response.json()
    except ValueError as exc:
        raise NfeAdjustmentError("Resposta invalida da API de consulta da Nota Fiscal de Ajuste.") from exc
    if not isinstance(payload, dict):
        raise NfeAdjustmentError("Resposta invalida da API de consulta da Nota Fiscal de Ajuste.")
    error_message = extract_webmania_error_message(payload.get("error") or payload.get("msg") or payload.get("message"), scope="nfe")
    if error_message:
        raise NfeAdjustmentError(error_message)
    return payload


def reconcile_nfe_adjustment_document(*, document: FiscalDocument) -> FiscalDocument:
    payload = consult_nfe_adjustment_document(document=document)
    document = apply_nfe_adjustment_document_payload(document=document, response_payload=payload)
    document.refresh_from_db()
    return document


def resolve_nfe_adjustment_document_for_webhook(*, payload: dict[str, Any]) -> FiscalDocument | None:
    event_uuid = str(payload.get("uuid") or "").strip()
    access_key = str(payload.get("chave") or "").strip()
    queryset = FiscalDocument.objects.filter(origin=FiscalDocumentOrigin.MANUAL, purpose=FiscalDocumentPurpose.ADJUSTMENT)
    filters = Q()
    if event_uuid:
        filters |= Q(remote_uuid=event_uuid) | Q(emission_attempts__remote_uuid=event_uuid)
    if access_key:
        filters |= Q(access_key=access_key) | Q(emission_attempts__remote_key=access_key)
    if not event_uuid and not access_key:
        return None
    matches = list(queryset.filter(filters).distinct().order_by("-pk")[:2])
    if len(matches) != 1:
        return None
    return matches[0]


def is_ambiguous_nfe_adjustment_webhook(*, payload: dict[str, Any]) -> bool:
    event_uuid = str(payload.get("uuid") or "").strip()
    access_key = str(payload.get("chave") or "").strip()
    if not event_uuid and not access_key:
        return False
    filters = Q()
    if event_uuid:
        filters |= Q(remote_uuid=event_uuid) | Q(emission_attempts__remote_uuid=event_uuid)
    if access_key:
        filters |= Q(access_key=access_key) | Q(emission_attempts__remote_key=access_key)
    return FiscalDocument.objects.filter(origin=FiscalDocumentOrigin.MANUAL, purpose=FiscalDocumentPurpose.ADJUSTMENT).filter(filters).distinct().values("pk")[:2].count() > 1
