
def map_batch_payload(payload: dict) -> dict:
    try:
        rps_quantity = int(payload.get("quantidade_rps"))
    except (ValueError):
        print(f"Valor inválido para quantidade_rps: {payload.get('quantidade_rps')}")
        rps_quantity = 0

    log_payload = payload.get("log")

    if not isinstance(log_payload, dict):
        log_payload = {"error": "Log payload is not a dict", "raw": log_payload}

    return {
        "uuid": payload.get("uuid", None),
        "model": payload.get("modelo", "lote_rps"),
        "status": payload.get("status", ""),
        "reason": payload.get("motivo", ""),
        "batch_number": payload.get("numero_lote", ""),
        "batch_series": payload.get("serie_lote", ""),
        "rps_quantity": rps_quantity,
        "protocol": payload.get("protocolo", ""),
        "log_payload": log_payload,
    }

def map_item_payload(payload: dict) -> dict:
    log_payload = payload.get("log")

    if type(log_payload) is not dict:
        log_payload = {"raw": log_payload}

    return {
        "uuid": payload.get("uuid", None),
        "model": payload.get("modelo", "nfse"),
        "status": payload.get("status", ""),
        "reason": payload.get("motivo", ""),
        "number": payload.get("numero", ""),
        "verification_code": payload.get("codigo_verificacao", ""),
        "rps_series": payload.get("serie_rps", ""),
        "rps_number": payload.get("numero_rps", ""),
        "xml_url": payload.get("xml", ""),
        "pdf_nfse_url": payload.get("pdf_nfse", ""),
        "pdf_nfse_status": payload.get("pdf_nfse_status", ""),
        "pdf_rps_url": payload.get("pdf_rps", ""),
        "log_payload": log_payload,
    }

def extract_items_from_batch(payload: dict) -> list[dict]:
    items = payload.get("info_nfse", [])
    if not isinstance(items, list):
        return []
    return [map_item_payload(item) for item in items if isinstance(item, dict)]