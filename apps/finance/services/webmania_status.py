from __future__ import annotations


def _normalize_status(value: object) -> str:
    return str(value or "").strip().lower()


def normalize_nfe_status(value: object) -> str:
    normalized = _normalize_status(value)
    mapping = {
        "processamento": "processando",
        "processando": "processando",
        "aprovado": "aprovado",
        "reprovado": "reprovado",
        "cancelado": "cancelado",
        "denegado": "denegado",
        "contingencia": "contingencia",
    }
    return mapping.get(normalized, normalized)


def normalize_nfse_item_status(value: object) -> str:
    normalized = _normalize_status(value)
    mapping = {
        "processamento": "processando",
        "processando": "processando",
        "processado": "aprovado",
        "aprovado": "aprovado",
        "reprovado": "reprovado",
        "agendado": "agendado",
        "cancelado": "cancelado",
        "contingencia": "contingencia",
    }
    return mapping.get(normalized, normalized)


def normalize_nfse_batch_status(value: object) -> str:
    normalized = _normalize_status(value)
    mapping = {
        "processamento": "processando",
        "processando": "processando",
        "processado": "processado",
        "agendado": "agendado",
        "reprovado": "reprovado",
        "cancelado": "cancelado",
        "contingencia": "contingencia",
    }
    return mapping.get(normalized, normalized)


def normalize_nfe_request_status(value: object) -> str:
    normalized = _normalize_status(value)
    mapping = {
        "processamento": "processing",
        "processando": "processing",
        "aprovado": "approved",
        "reprovado": "reproved",
        "cancelado": "canceled",
        "denegado": "denied",
        "contingencia": "contingency",
    }
    return mapping.get(normalized, normalized)


def normalize_nfse_request_status(value: object) -> str:
    normalized = _normalize_status(value)
    mapping = {
        "processamento": "processing",
        "processando": "processing",
        "processado": "approved",
        "aprovado": "approved",
        "reprovado": "reproved",
        "agendado": "scheduled",
        "cancelado": "canceled",
        "contingencia": "contingency",
    }
    return mapping.get(normalized, normalized)
