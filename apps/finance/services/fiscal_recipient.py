from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from apps.customer.cpf_cnpj_validator import is_valid_cnpj, is_valid_cpf


@dataclass(slots=True)
class FiscalRecipient:
    customer_type: str
    name: str
    cpf_or_cnpj: str
    phone: str
    email: str
    logradouro: str
    numero: int | str
    complemento: str
    bairro: str
    cidade: str
    estado: str
    cep: str
    state_registration: str
    municipal_registration: str

    @property
    def cpf_or_cnpj_formatted(self) -> str:
        document = _digits_only(self.cpf_or_cnpj)
        if len(document) == 11:
            return f"{document[:3]}.{document[3:6]}.{document[6:9]}-{document[9:]}"
        if len(document) == 14:
            return f"{document[:2]}.{document[2:5]}.{document[5:8]}/{document[8:12]}-{document[12:]}"
        return self.cpf_or_cnpj

    @property
    def full_address(self) -> str:
        parts = [
            self.logradouro,
            str(self.numero or ""),
            self.complemento,
            self.bairro,
            self.cidade,
            self.estado,
            self.cep,
        ]
        return ", ".join(part.strip() for part in parts if str(part or "").strip())


def _digits_only(value: object) -> str:
    return "".join(char for char in str(value or "") if char.isdigit())


def recipient_snapshot_from_form_data(data: dict[str, Any]) -> dict[str, str | int]:
    customer_type = str(data.get("customer_type") or "PF").upper()
    if customer_type not in {"PF", "PJ"}:
        customer_type = "PF"

    numero_raw = data.get("numero")
    try:
        numero = int(numero_raw) if numero_raw not in (None, "") else 1
    except (TypeError, ValueError):
        numero = 1

    return {
        "customer_type": customer_type,
        "name": str(data.get("name") or "").strip(),
        "cpf_or_cnpj": _digits_only(data.get("cpf_or_cnpj")),
        "phone": str(data.get("phone") or "").strip(),
        "email": str(data.get("email") or "").strip(),
        "logradouro": str(data.get("logradouro") or "").strip(),
        "numero": numero,
        "complemento": str(data.get("complemento") or "").strip(),
        "bairro": str(data.get("bairro") or "").strip(),
        "cidade": str(data.get("cidade") or "").strip(),
        "estado": str(data.get("estado") or "").strip(),
        "cep": _digits_only(data.get("cep")),
        "state_registration": str(data.get("state_registration") or "").strip(),
        "municipal_registration": str(data.get("municipal_registration") or "").strip(),
    }


def fiscal_recipient_from_snapshot(snapshot: dict[str, Any] | None) -> FiscalRecipient | None:
    if not isinstance(snapshot, dict) or not snapshot:
        return None

    name = str(snapshot.get("name") or "").strip()
    document = _digits_only(snapshot.get("cpf_or_cnpj"))
    if not name or not document:
        return None

    return FiscalRecipient(
        customer_type=str(snapshot.get("customer_type") or "PF").upper(),
        name=name,
        cpf_or_cnpj=document,
        phone=str(snapshot.get("phone") or "").strip(),
        email=str(snapshot.get("email") or "").strip(),
        logradouro=str(snapshot.get("logradouro") or "").strip(),
        numero=snapshot.get("numero") or 1,
        complemento=str(snapshot.get("complemento") or "").strip(),
        bairro=str(snapshot.get("bairro") or "").strip(),
        cidade=str(snapshot.get("cidade") or "").strip(),
        estado=str(snapshot.get("estado") or "").strip(),
        cep=_digits_only(snapshot.get("cep")),
        state_registration=str(snapshot.get("state_registration") or "").strip(),
        municipal_registration=str(snapshot.get("municipal_registration") or "").strip(),
    )


def recipient_name_from_snapshot(snapshot: dict[str, Any]) -> str:
    return str(snapshot.get("name") or "").strip()


def validate_recipient_snapshot(snapshot: dict[str, Any]) -> dict[str, list[str]]:
    errors: dict[str, list[str]] = {}
    customer_type = str(snapshot.get("customer_type") or "PF").upper()
    document = _digits_only(snapshot.get("cpf_or_cnpj"))

    if not str(snapshot.get("name") or "").strip():
        errors.setdefault("name", []).append("Informe o nome do destinatário.")

    if customer_type == "PF":
        if not document:
            errors.setdefault("cpf_or_cnpj", []).append("CPF é obrigatório para pessoa física.")
        elif not is_valid_cpf(document):
            errors.setdefault("cpf_or_cnpj", []).append("Informe um CPF válido.")
    elif customer_type == "PJ":
        if not document:
            errors.setdefault("cpf_or_cnpj", []).append("CNPJ é obrigatório para pessoa jurídica.")
        elif not is_valid_cnpj(document):
            errors.setdefault("cpf_or_cnpj", []).append("Informe um CNPJ válido.")
    else:
        errors.setdefault("customer_type", []).append("Tipo de pessoa inválido.")

    required_address_fields = {
        "logradouro": "logradouro",
        "numero": "número",
        "bairro": "bairro",
        "cidade": "cidade",
        "estado": "UF",
        "cep": "CEP",
    }
    for field_name, label in required_address_fields.items():
        value = snapshot.get(field_name)
        if field_name == "numero":
            if value in (None, ""):
                errors.setdefault(field_name, []).append(f"Informe o {label}.")
            continue
        if not str(value or "").strip():
            errors.setdefault(field_name, []).append(f"Informe o {label}.")

    cep_digits = _digits_only(snapshot.get("cep"))
    if cep_digits and len(cep_digits) != 8:
        errors.setdefault("cep", []).append("Informe um CEP válido com 8 dígitos.")

    return errors


def resolve_fiscal_recipient_for_nfe_request(nfe_request: Any) -> FiscalRecipient | None:
    snapshot_recipient = fiscal_recipient_from_snapshot(getattr(nfe_request, "recipient_snapshot", None))
    if snapshot_recipient is not None:
        return snapshot_recipient

    workorder = getattr(nfe_request, "workorder", None)
    if workorder is None:
        return None

    customer = getattr(getattr(workorder, "budget", None), "customer", None)
    if customer is None:
        return None

    return FiscalRecipient(
        customer_type=str(getattr(customer, "customer_type", "PF") or "PF"),
        name=str(customer.name or ""),
        cpf_or_cnpj=str(customer.cpf_or_cnpj or ""),
        phone=str(customer.phone or ""),
        email=str(customer.email or ""),
        logradouro=str(customer.logradouro or ""),
        numero=getattr(customer, "numero", 1) or 1,
        complemento=str(getattr(customer, "complemento", "") or ""),
        bairro=str(customer.bairro or ""),
        cidade=str(customer.cidade or ""),
        estado=str(customer.estado or ""),
        cep=str(customer.cep or ""),
        state_registration=str(getattr(customer, "state_registration", "") or ""),
        municipal_registration=str(getattr(customer, "municipal_registration", "") or ""),
    )


def resolve_fiscal_recipient_for_nfse_request(nfse_request: Any) -> FiscalRecipient | None:
    return resolve_fiscal_recipient_for_nfe_request(nfse_request)
