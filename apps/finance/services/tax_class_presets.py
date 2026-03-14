from __future__ import annotations

from copy import deepcopy
from typing import Any


DEFAULT_TAX_CLASS_PRESETS: dict[str, list[dict[str, Any]]] = {
    "nfe": [
        {
            "name": "Simples Nacional - Revenda padrão",
            "description": "Saída dentro/fora do estado para pessoa física e jurídica com CST 102.",
            "payload": {
                "descricao": "Classe de impostos para Saída de produtos de revenda",
                "icms": [
                    {"tipo_tributacao": "simples_nacional", "cenario": "saida_dentro_estado", "tipo_pessoa": "fisica", "codigo_cfop": "5102", "situacao_tributaria": "102"},
                    {"tipo_tributacao": "simples_nacional", "cenario": "saida_fora_estado", "tipo_pessoa": "fisica", "codigo_cfop": "6102", "situacao_tributaria": "102"},
                    {"tipo_tributacao": "simples_nacional", "cenario": "saida_dentro_estado", "tipo_pessoa": "juridica", "codigo_cfop": "5102", "situacao_tributaria": "102"},
                    {"tipo_tributacao": "simples_nacional", "cenario": "saida_fora_estado", "tipo_pessoa": "juridica", "codigo_cfop": "6102", "situacao_tributaria": "102"},
                ],
                "ipi": [
                    {"cenario": "padrao", "tipo_pessoa": "fisica", "situacao_tributaria": "99", "codigo_enquadramento": "999", "aliquota": "0.00"},
                    {"cenario": "padrao", "tipo_pessoa": "juridica", "situacao_tributaria": "99", "codigo_enquadramento": "999", "aliquota": "0.00"},
                ],
                "pis": [
                    {"cenario": "padrao", "tipo_pessoa": "fisica", "situacao_tributaria": "99", "aliquota": "0.00"},
                    {"cenario": "padrao", "tipo_pessoa": "juridica", "situacao_tributaria": "99", "aliquota": "0.00"},
                ],
                "cofins": [
                    {"cenario": "padrao", "tipo_pessoa": "fisica", "situacao_tributaria": "99", "aliquota": "0.00"},
                    {"cenario": "padrao", "tipo_pessoa": "juridica", "situacao_tributaria": "99", "aliquota": "0.00"},
                ],
            },
        },
        {
            "name": "Simples Nacional - Com crédito",
            "description": "Configuração com CST 101 e alíquota de crédito para destinatário jurídico.",
            "payload": {
                "descricao": "Classe de impostos SN com crédito de ICMS",
                "icms": [
                    {"tipo_tributacao": "simples_nacional", "cenario": "saida_dentro_estado", "tipo_pessoa": "juridica", "codigo_cfop": "5102", "situacao_tributaria": "101", "aliquota_credito": "2.00"},
                    {"tipo_tributacao": "simples_nacional", "cenario": "saida_fora_estado", "tipo_pessoa": "juridica", "codigo_cfop": "6102", "situacao_tributaria": "101", "aliquota_credito": "2.00"},
                ],
                "ipi": [{"cenario": "padrao", "tipo_pessoa": "juridica", "situacao_tributaria": "99", "codigo_enquadramento": "999", "aliquota": "0.00"}],
                "pis": [{"cenario": "padrao", "tipo_pessoa": "juridica", "situacao_tributaria": "99", "aliquota": "0.00"}],
                "cofins": [{"cenario": "padrao", "tipo_pessoa": "juridica", "situacao_tributaria": "99", "aliquota": "0.00"}],
            },
        },
    ],
    "nfse": [
        {
            "name": "NFS-e ABRASF - Serviço padrão",
            "description": "Preset básico com código de serviço no formato XX.XX ou XXXXX.",
            "payload": {
                "descricao": "Classe de impostos para prestação de serviço",
                "tipo": "nfse",
                "codigo_servico": "01.05",
                "natureza_operacao": "1",
                "exigibilidade_iss": "1",
                "iss_retido": "2",
            },
        },
        {
            "name": "NFS-e ABRASF - ISS retido",
            "description": "Preset com retenção de ISS pelo tomador.",
            "payload": {
                "descricao": "Classe de impostos para serviço com ISS retido",
                "tipo": "nfse",
                "codigo_servico": "01.05",
                "natureza_operacao": "1",
                "exigibilidade_iss": "1",
                "iss_retido": "1",
                "responsavel_retencao": "1",
            },
        },
    ],
}


def normalize_tax_class_preset_payload(*, payload: dict[str, Any], kind: str) -> dict[str, Any]:
    normalized_payload = deepcopy(payload)
    for key in ("referencia", "status", "data", "updated_date", "message", "msg", "error"):
        normalized_payload.pop(key, None)

    normalized_kind = str(kind or "").strip().lower()
    if normalized_kind == "nfse":
        normalized_payload["tipo"] = "nfse"
        normalized_payload["type"] = "nfse"
    else:
        normalized_payload.pop("tipo", None)
        normalized_payload.pop("type", None)

    return normalized_payload


def get_default_tax_class_presets() -> dict[str, list[dict[str, Any]]]:
    defaults = deepcopy(DEFAULT_TAX_CLASS_PRESETS)
    for kind, items in defaults.items():
        for item in items:
            payload = item.get("payload")
            if isinstance(payload, dict):
                item["payload"] = normalize_tax_class_preset_payload(payload=payload, kind=kind)
    return defaults
