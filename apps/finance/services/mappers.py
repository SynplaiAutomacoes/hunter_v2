import logging

from apps.finance.services.nfse_remote_updates import parse_nfse_remote_updated_at
from apps.finance.services.webmania_status import normalize_nfse_batch_status, normalize_nfse_item_status


logger = logging.getLogger(__name__)


def map_batch_payload(payload: dict) -> dict:
    raw_quantity = payload.get("quantidade_rps", 0)
    try:
        rps_quantity = int(raw_quantity)
    except (ValueError, TypeError):
        logger.warning("Valor invalido para quantidade_rps no payload de lote", extra={"quantidade_rps": raw_quantity})
        rps_quantity = 0

    log_payload = payload.get("log")

    if not isinstance(log_payload, dict):
        log_payload = {"error": "Log payload is not a dict", "raw": log_payload}

    return {
        "uuid": payload.get("uuid", None),
        "model": payload.get("modelo", "lote_rps"),
        "status": normalize_nfse_batch_status(payload.get("status") or "processando"),
        "reason": payload.get("motivo", ""),
        "batch_number": payload.get("numero_lote", ""),
        "batch_series": payload.get("serie_lote", ""),
        "rps_quantity": rps_quantity,
        "protocol": payload.get("protocolo", ""),
        "log_payload": log_payload,
        "remote_updated_at": parse_nfse_remote_updated_at(payload.get("atualizado_em") or payload.get("remote_updated_at")),
    }


def map_item_payload(payload: dict) -> dict:
    log_payload = payload.get("log")

    if not isinstance(log_payload, dict):
        log_payload = {"error": "Log payload is not a dict", "raw": log_payload}

    return {
        "uuid": payload.get("uuid", None),
        "model": payload.get("modelo", "nfse"),
        "status": normalize_nfse_item_status(payload.get("status") or "processando"),
        "reason": payload.get("motivo", ""),
        "number": payload.get("numero", ""),
        "verification_code": payload.get("codigo_verificacao", ""),
        "rps_series": payload.get("serie_rps", ""),
        "rps_number": payload.get("numero_rps", ""),
        "xml_url": payload.get("xml", ""),
        "pdf_nfse_url": payload.get("pdf_nfse", ""),
        "pdf_nfse_status": normalize_nfse_batch_status(payload.get("pdf_nfse_status") or "processando"),
        "pdf_rps_url": payload.get("pdf_rps", ""),
        "log_payload": log_payload,
        "remote_updated_at": parse_nfse_remote_updated_at(payload.get("atualizado_em") or payload.get("remote_updated_at")),
    }


def extract_items_from_batch(payload: dict) -> list[dict]:
    items = payload.get("info_nfse", [])
    if not isinstance(items, list):
        return []
    return [map_item_payload(item) for item in items if isinstance(item, dict)]
