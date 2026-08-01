from typing import Any, cast

import re

from django.conf import settings
from django.utils import timezone

from apps.finance.models import WebmaniaCompany
from apps.workshops.services.files import WorkshopFileStorageError, encode_workshop_certificate as encode_workshop_certificate_from_store
from apps.workshops.util.workshops import has_workshop_perm


def is_webmania_homolog_environment() -> bool:
    raw_value = getattr(settings, "WEBMANIA_AMBIENT", "2")
    try:
        return int(str(raw_value).strip()) == 2
    except (TypeError, ValueError):
        return False


def to_public_integration_message(raw_message: object) -> str:
    normalized_message = str(raw_message or "").strip()
    if not normalized_message:
        return "Nao foi possivel concluir a operacao."

    for token in ("WEBMANIA", "Webmania", "webmania", "integração", "integraçao", "integracao"):
        normalized_message = normalized_message.replace(token, "")

    normalized_message = re.sub(r"\s{2,}", " ", normalized_message).strip(" ,.;:-")
    if not normalized_message:
        return "Nao foi possivel concluir a operacao."
    return normalized_message


def latest_sync_error(companies: list[WebmaniaCompany]) -> str:
    candidates = [company for company in companies if str(company.last_sync_error or "").strip()]
    if not candidates:
        return ""

    latest = max(
        candidates,
        key=lambda company: company.last_sync_at or company.atualizado_em or company.criado_em,
    )
    return str(latest.last_sync_error or "").strip()


def get_webmania_context_meta(user_account_id):
    """Retorna metadados consolidados para o contexto de listas/dashboards."""
    if not user_account_id:
        return {
            "webmania_company_count": 0,
            "webmania_last_sync_at": None,
            "webmania_last_sync_error": "",
        }

    acc_cos = list(WebmaniaCompany.objects.filter(workshop__account_id=user_account_id).exclude(webmania_company_id="").select_related("workshop"))

    syncs = [c.last_sync_at for c in acc_cos if c.last_sync_at]
    err = latest_sync_error(acc_cos)  # Assumindo que esta função já existe globalmente

    return {
        "webmania_company_count": len(acc_cos),
        "webmania_last_sync_at": max(syncs) if syncs else None,
        "webmania_last_sync_error": to_public_integration_message(err) if err else "",
    }


def has_webmania_change_perm(user, workshop, request=None) -> bool:
    """Verifica de forma centralizada se o usuário pode alterar dados da Webmania."""
    u = cast(Any, user)
    # Donos de conta costumam ter permissão total
    u_acc = getattr(u, "account", None)
    if u_acc and getattr(u_acc, "owner_id", None) == u.id:
        return True

    if not workshop:
        return False

    return has_workshop_perm(user=u, workshop=workshop, app_label=WebmaniaCompany._meta.app_label, model=str(WebmaniaCompany._meta.model_name), codename="change_webmaniacompany", request=request)


def save_company_sync_metadata(company: WebmaniaCompany, error: str = "") -> None:
    """Atualiza os campos de controle de sincronização da empresa."""
    normalized_error = to_public_integration_message(error) if str(error or "").strip() else ""
    company.last_sync_error = normalized_error

    update_fields = ["last_sync_error"]
    if not error:
        company.last_sync_at = timezone.now()
        update_fields.append("last_sync_at")

    company.save(update_fields=update_fields)


def encode_workshop_certificate(workshop) -> str:
    """Extrai e codifica o certificado PFX da oficina para Base64."""
    try:
        return encode_workshop_certificate_from_store(workshop)
    except WorkshopFileStorageError:
        return ""


def sync_workshop_from_company(workshop, company, sync_name=False, sync_address=False):
    """Sincroniza dados da WebmaniaCompany de volta para o modelo Workshop."""
    update_fields = []
    if sync_name:
        name = str(company.razao_social or company.nome_completo or "").strip()
        if name and workshop.name != name:
            workshop.name = name
            update_fields.append("name")

    if sync_address:
        parts = [str(company.endereco or "").strip(), str(company.numero or "").strip()]
        normalized_addr = ", ".join(p for p in parts if p)
        if normalized_addr and workshop.address != normalized_addr:
            workshop.address = normalized_addr
            update_fields.append("address")

        uf = str(company.uf or "").strip().upper()
        if len(uf) == 2 and workshop.uf != uf:
            workshop.uf = uf
            update_fields.append("uf")

    if update_fields:
        workshop.save(update_fields=update_fields)
