from __future__ import annotations

import json
import re
from decimal import Decimal
from typing import Any

from apps.core.domain.value_objects import State
from apps.customer.cpf_cnpj_validator import is_valid_cnpj, is_valid_cpf


TRANSPORT_FORM_FIELD_NAMES: tuple[str, ...] = (
    "freight_mode",
    "transport_person_type",
    "transport_document",
    "transport_name",
    "transport_state_registration",
    "transport_address",
    "transport_state",
    "transport_city",
    "transport_postal_code",
    "transport_vehicle_plate",
    "transport_vehicle_state",
    "transport_rntc",
    "transport_volume_quantity",
    "transport_volume_species",
    "transport_gross_weight",
    "transport_net_weight",
    "transport_volume_brand",
    "transport_volume_numbering",
    "transport_seals",
    "nfe_transport_trailers_json",
)

FREIGHT_MODE_CHOICES: tuple[tuple[str, str], ...] = (
    ("9", "9 - Sem transporte"),
    ("0", "0 - Por conta do emitente (CIF)"),
    ("1", "1 - Por conta do destinatario (FOB)"),
    ("2", "2 - Por conta de terceiros"),
    ("3", "3 - Transporte proprio do emitente"),
    ("4", "4 - Transporte proprio do destinatario"),
)

TRANSPORT_PERSON_TYPE_CHOICES: tuple[tuple[str, str], ...] = (
    ("", "Não informar transportador"),
    ("pj", "Pessoa juridica"),
    ("pf", "Pessoa fisica"),
)

BRAZILIAN_STATE_CHOICES: tuple[tuple[str, str], ...] = (("", "Selecione"), *((state.value, state.value) for state in State), ("EX", "EX"))

_ALLOWED_FREIGHT_MODES = {0, 1, 2, 3, 4, 9}
_ALLOWED_TRANSPORT_STATES = {state.value for state in State} | {"EX"}
_WEBMANIA_VEHICLE_PLATE_RE = re.compile(r"^(?:[A-Z]{3}\d[A-Z0-9]\d{2}|[A-Z]{3}\d{3}|[A-Z]{2}\d{4}|[A-Z]{4}\d{3})$")
_CARRIER_KEYS = {
    "tipo_pessoa",
    "cnpj",
    "cpf",
    "razao_social",
    "nome_completo",
    "ie",
    "endereco",
    "uf",
    "cidade",
    "cep",
    "placa",
    "uf_veiculo",
    "rntc",
}
_VOLUME_KEYS = {
    "volume",
    "especie",
    "peso_bruto",
    "peso_liquido",
    "marca",
    "numeracao",
    "lacres",
}
_TRAILER_KEYS = {
    "placa",
    "uf_veiculo",
    "rntc",
    "vagao",
    "balsa",
}


class NfeTransportValidationError(ValueError):
    pass


def _digits(value: object) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _text(value: object) -> str:
    return str(value or "").strip()


def _decimal_text(value: object) -> str:
    if value in (None, ""):
        return ""
    return format(Decimal(str(value)), "f")


def _freight_mode(value: object) -> int:
    normalized_value = str(value).strip()
    try:
        mode = int(normalized_value)
    except (TypeError, ValueError) as exc:
        raise NfeTransportValidationError("Selecione uma modalidade de frete válida.") from exc
    if mode not in _ALLOWED_FREIGHT_MODES:
        raise NfeTransportValidationError("Selecione uma modalidade de frete válida.")
    return mode


def _has_transport_details(values: dict[str, Any]) -> bool:
    for field_name in TRANSPORT_FORM_FIELD_NAMES:
        if field_name == "freight_mode":
            continue
        value = values.get(field_name)
        if field_name == "nfe_transport_trailers_json" and _text(value) in {"", "[]"}:
            continue
        if value not in (None, ""):
            return True
    return False


def _build_carrier_snapshot(values: dict[str, Any]) -> dict[str, Any]:
    person_type = _text(values.get("transport_person_type")).lower()
    document = _digits(values.get("transport_document"))
    name = _text(values.get("transport_name"))
    state_registration = _text(values.get("transport_state_registration"))

    carrier: dict[str, Any] = {}
    if person_type:
        if person_type not in {"pf", "pj"}:
            raise NfeTransportValidationError("Selecione um tipo de transportador válido.")
        if not document or not name:
            raise NfeTransportValidationError("Informe documento e nome do transportador.")
        if len(name) < 2 or len(name) > 60:
            raise NfeTransportValidationError("O nome do transportador deve possuir entre 2 e 60 caracteres.")
        carrier["tipo_pessoa"] = person_type
        if person_type == "pj":
            if not is_valid_cnpj(document):
                raise NfeTransportValidationError("Informe um CNPJ válido para a transportadora.")
            carrier["cnpj"] = document
            carrier["razao_social"] = name
            if state_registration:
                if state_registration != "0" and (len(state_registration) < 2 or len(state_registration) > 14):
                    raise NfeTransportValidationError("A inscricao estadual deve possuir entre 2 e 14 caracteres.")
                carrier["ie"] = state_registration
        else:
            if not is_valid_cpf(document):
                raise NfeTransportValidationError("Informe um CPF válido para o transportador.")
            if state_registration:
                raise NfeTransportValidationError("Inscricao estadual somente pode ser informada para transportadora pessoa juridica.")
            carrier["cpf"] = document
            carrier["nome_completo"] = name
    elif document or name or state_registration:
        raise NfeTransportValidationError("Selecione o tipo de transportador antes de informar seus dados.")

    text_fields = {
        "endereco": "transport_address",
        "uf": "transport_state",
        "cidade": "transport_city",
        "cep": "transport_postal_code",
        "rntc": "transport_rntc",
    }
    for snapshot_key, field_name in text_fields.items():
        value = _text(values.get(field_name))
        if snapshot_key == "cep":
            value = _digits(value)
            if value and len(value) != 8:
                raise NfeTransportValidationError("Informe um CEP válido para o transportador.")
        if snapshot_key == "uf" and value and value not in _ALLOWED_TRANSPORT_STATES:
            raise NfeTransportValidationError("Informe uma UF válida para o transportador.")
        if snapshot_key in {"endereco", "cidade"} and len(value) > 60:
            raise NfeTransportValidationError("Endereco e cidade do transportador devem possuir no maximo 60 caracteres.")
        if snapshot_key == "rntc" and len(value) > 20:
            raise NfeTransportValidationError("O RNTRC/ANTT deve possuir no maximo 20 caracteres.")
        if value:
            carrier[snapshot_key] = value

    if not person_type and any(key in carrier for key in {"endereco", "uf", "cidade", "cep"}):
        raise NfeTransportValidationError("Selecione o tipo de transportador antes de informar seu endereco.")
    if state_registration and not carrier.get("uf"):
        raise NfeTransportValidationError("Informe a UF da transportadora quando houver inscricao estadual.")

    plate = _text(values.get("transport_vehicle_plate")).upper()
    vehicle_state = _text(values.get("transport_vehicle_state")).upper()
    if plate:
        if not _WEBMANIA_VEHICLE_PLATE_RE.match(plate):
            raise NfeTransportValidationError("Informe uma placa de veiculo válida.")
        carrier["placa"] = plate
    if vehicle_state:
        if vehicle_state not in _ALLOWED_TRANSPORT_STATES:
            raise NfeTransportValidationError("Informe uma UF válida para o veiculo.")
        if not plate:
            raise NfeTransportValidationError("Informe a placa antes da UF do veiculo.")
        carrier["uf_veiculo"] = vehicle_state

    return carrier


def _build_volume_snapshot(values: dict[str, Any]) -> dict[str, Any]:
    volumes: dict[str, Any] = {}
    quantity = values.get("transport_volume_quantity")
    if quantity not in (None, ""):
        normalized_quantity = int(quantity)
        if normalized_quantity < 1 or len(str(normalized_quantity)) > 15:
            raise NfeTransportValidationError("A quantidade de volumes deve possuir entre 1 e 15 digitos.")
        volumes["volume"] = normalized_quantity

    for snapshot_key, field_name in {
        "especie": "transport_volume_species",
        "marca": "transport_volume_brand",
        "numeracao": "transport_volume_numbering",
        "lacres": "transport_seals",
    }.items():
        value = _text(values.get(field_name))
        if len(value) > 60:
            raise NfeTransportValidationError("Especie, marca, numeração e lacres devem possuir no maximo 60 caracteres.")
        if value:
            volumes[snapshot_key] = value

    for snapshot_key, field_name in {
        "peso_bruto": "transport_gross_weight",
        "peso_liquido": "transport_net_weight",
    }.items():
        value = _decimal_text(values.get(field_name))
        if value:
            if Decimal(value) < 0:
                raise NfeTransportValidationError("Os pesos dos volumes não podem ser negativos.")
            volumes[snapshot_key] = value

    return volumes


def _build_trailers_snapshot(values: dict[str, Any]) -> list[dict[str, Any]]:
    raw_trailers = values.get("nfe_transport_trailers_json")
    if raw_trailers in (None, "", []):
        return []
    if isinstance(raw_trailers, str):
        try:
            raw_trailers = json.loads(raw_trailers)
        except ValueError as exc:
            raise NfeTransportValidationError("Informe os reboques em JSON válido.") from exc
    if not isinstance(raw_trailers, list):
        raise NfeTransportValidationError("Reboques devem ser informados como uma lista JSON.")

    trailers: list[dict[str, Any]] = []
    for raw_trailer in raw_trailers:
        if not isinstance(raw_trailer, dict) or not raw_trailer:
            raise NfeTransportValidationError("Cada reboque deve ser um objeto JSON preenchido.")
        if set(raw_trailer) - _TRAILER_KEYS:
            raise NfeTransportValidationError("Reboque possui campos não permitidos.")

        trailer: dict[str, Any] = {}
        plate = _text(raw_trailer.get("placa")).upper()
        vehicle_state = _text(raw_trailer.get("uf_veiculo")).upper()
        rntc = _text(raw_trailer.get("rntc"))
        wagon = _text(raw_trailer.get("vagao"))
        ferry = _text(raw_trailer.get("balsa"))

        if plate:
            if not _WEBMANIA_VEHICLE_PLATE_RE.match(plate):
                raise NfeTransportValidationError("Informe uma placa de reboque válida.")
            trailer["placa"] = plate
        if vehicle_state:
            if vehicle_state not in _ALLOWED_TRANSPORT_STATES:
                raise NfeTransportValidationError("Informe uma UF válida para o reboque.")
            if not plate:
                raise NfeTransportValidationError("Informe a placa antes da UF do reboque.")
            trailer["uf_veiculo"] = vehicle_state
        if rntc:
            if len(rntc) > 20:
                raise NfeTransportValidationError("O RNTRC/ANTT do reboque deve possuir no maximo 20 caracteres.")
            trailer["rntc"] = rntc
        if wagon:
            if not wagon.isdigit() or len(wagon) > 20:
                raise NfeTransportValidationError("O vagao do reboque deve ser numerico e possuir no maximo 20 digitos.")
            trailer["vagao"] = int(wagon)
        if ferry:
            if len(ferry) > 20:
                raise NfeTransportValidationError("A identificacao da balsa deve possuir no maximo 20 caracteres.")
            trailer["balsa"] = ferry
        if not trailer:
            raise NfeTransportValidationError("Informe ao menos um dado para cada reboque.")
        trailers.append(trailer)
    return trailers


def build_nfe_transport_snapshot(values: dict[str, Any]) -> dict[str, Any]:
    mode = _freight_mode(values.get("freight_mode", 9))
    if mode == 9:
        if _has_transport_details(values):
            raise NfeTransportValidationError("Selecione uma modalidade com transporte ou remova os dados de transportador e volumes.")
        return {}

    snapshot = {
        "modalidade": mode,
        "transportador": _build_carrier_snapshot(values),
        "volumes": _build_volume_snapshot(values),
    }
    trailers = _build_trailers_snapshot(values)
    if trailers:
        snapshot["reboques"] = trailers
    return snapshot


def build_nfe_transport_form_initial(snapshot: object) -> dict[str, Any]:
    if not isinstance(snapshot, dict):
        return {}

    carrier = snapshot.get("transportador")
    volumes = snapshot.get("volumes")
    trailers = snapshot.get("reboques")
    carrier = carrier if isinstance(carrier, dict) else {}
    volumes = volumes if isinstance(volumes, dict) else {}
    trailers = trailers if isinstance(trailers, list) else []

    person_type = _text(carrier.get("tipo_pessoa"))
    document = carrier.get("cnpj") if person_type == "pj" else carrier.get("cpf")
    name = carrier.get("razao_social") if person_type == "pj" else carrier.get("nome_completo")

    return {
        "freight_mode": str(snapshot.get("modalidade", 9)),
        "transport_person_type": person_type,
        "transport_document": _text(document),
        "transport_name": _text(name),
        "transport_state_registration": _text(carrier.get("ie")),
        "transport_address": _text(carrier.get("endereco")),
        "transport_state": _text(carrier.get("uf")),
        "transport_city": _text(carrier.get("cidade")),
        "transport_postal_code": _text(carrier.get("cep")),
        "transport_vehicle_plate": _text(carrier.get("placa")),
        "transport_vehicle_state": _text(carrier.get("uf_veiculo")),
        "transport_rntc": _text(carrier.get("rntc")),
        "transport_volume_quantity": volumes.get("volume"),
        "transport_volume_species": _text(volumes.get("especie")),
        "transport_gross_weight": _text(volumes.get("peso_bruto")),
        "transport_net_weight": _text(volumes.get("peso_liquido")),
        "transport_volume_brand": _text(volumes.get("marca")),
        "transport_volume_numbering": _text(volumes.get("numeracao")),
        "transport_seals": _text(volumes.get("lacres")),
        "nfe_transport_trailers_json": json.dumps(trailers, ensure_ascii=False) if trailers else "",
    }


def build_webmania_transport_payload(*, freight_mode: object, snapshot: object) -> tuple[int, dict[str, Any]]:
    mode = _freight_mode(freight_mode)
    if mode == 9:
        return mode, {}
    if not isinstance(snapshot, dict):
        raise NfeTransportValidationError("Snapshot de transporte inválido.")

    snapshot_mode = _freight_mode(snapshot.get("modalidade"))
    if snapshot_mode != mode:
        raise NfeTransportValidationError("Modalidade de frete divergente do snapshot de transporte.")

    carrier = snapshot.get("transportador")
    volumes = snapshot.get("volumes")
    trailers = snapshot.get("reboques", [])
    if not isinstance(carrier, dict) or not isinstance(volumes, dict):
        raise NfeTransportValidationError("Snapshot de transporte incompleto.")
    if not isinstance(trailers, list):
        raise NfeTransportValidationError("Snapshot de reboques inválido.")
    if set(carrier) - _CARRIER_KEYS or set(volumes) - _VOLUME_KEYS:
        raise NfeTransportValidationError("Snapshot de transporte possui campos não permitidos.")

    normalized_snapshot = build_nfe_transport_snapshot(build_nfe_transport_form_initial(snapshot))
    if normalized_snapshot != snapshot:
        raise NfeTransportValidationError("Snapshot de transporte não esta normalizado.")

    transport_payload = {key: value for key, value in carrier.items() if key != "tipo_pessoa" and value not in (None, "")}
    transport_payload.update({key: value for key, value in volumes.items() if value not in (None, "")})
    if trailers:
        transport_payload["reboque"] = trailers
    return mode, transport_payload
