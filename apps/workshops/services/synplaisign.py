from __future__ import annotations

import logging
import re
import secrets
import string
from typing import Any

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.urls import reverse

from apps.core.infrastructure.gateways import synplaisign as gateway
from apps.core.infrastructure.services.signature import build_absolute_app_url
from apps.core.infrastructure.services.webmania.webmania_secrets import decrypt_secret, encrypt_secret
from apps.workshops.models.workshops import Workshop


logger = logging.getLogger(__name__)


class WorkshopSynplaiSignError(Exception):
    pass


def get_workshop_synplaisign_api_key(workshop: Workshop) -> str:
    api_key = decrypt_secret(getattr(workshop, "synplaisign_api_key", "") or "")
    if not api_key:
        raise WorkshopSynplaiSignError("Oficina sem API key SynplaiSign configurada. Recrie as credenciais da oficina.")
    return api_key


def get_workshop_synplaisign_webhook_secret(workshop: Workshop) -> str:
    return decrypt_secret(getattr(workshop, "synplaisign_webhook_secret", "") or "")


def get_workshop_synplaisign_owner_password(workshop: Workshop) -> str:
    return decrypt_secret(getattr(workshop, "synplaisign_owner_password", "") or "")


def _default_webhook_url() -> str:
    return build_absolute_app_url(path=reverse("budget:signature_webhook"))


def _organization_name_for_workshop(workshop: Workshop) -> str:
    """Nome fantasia da empresa fiscal; fallback razao social; depois nome da oficina."""
    try:
        company = workshop.webmania_company
    except ObjectDoesNotExist:
        company = None

    if company is not None:
        fantasy = str(getattr(company, "nome_fantasia", "") or "").strip()
        if fantasy:
            return fantasy
        razao = str(getattr(company, "razao_social", "") or getattr(company, "nome_completo", "") or "").strip()
        if razao:
            return razao

    return str(workshop.name or "").strip() or f"Oficina {workshop.pk}"


def _resolve_account_owner(workshop: Workshop) -> Any:
    account = getattr(workshop, "account", None)
    if account is None:
        raise WorkshopSynplaiSignError("Oficina sem conta vinculada para provisionar SynplaiSign.")

    owner = getattr(account, "owner", None)
    if owner is None:
        raise WorkshopSynplaiSignError("Conta da oficina sem Owner para provisionar SynplaiSign.")
    return owner


def _owner_display_name(owner: Any) -> str:
    full_name = ""
    get_full_name = getattr(owner, "get_full_name", None)
    if callable(get_full_name):
        full_name = str(get_full_name() or "").strip()
    if full_name:
        return full_name

    first = str(getattr(owner, "first_name", "") or "").strip()
    last = str(getattr(owner, "last_name", "") or "").strip()
    combined = f"{first} {last}".strip()
    if combined:
        return combined

    return str(getattr(owner, "username", "") or getattr(owner, "email", "") or "Owner").strip()


def _owner_email(owner: Any) -> str:
    email = str(getattr(owner, "email", "") or "").strip()
    if not email:
        raise WorkshopSynplaiSignError("Owner da conta sem email para provisionar SynplaiSign.")
    return email


def _slugify_workshop_name(raw_name: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", raw_name.strip().lower()).strip("_")
    return (normalized[:40] or "oficina")


def _build_api_key_name(workshop: Workshop) -> str:
    suffix = "".join(secrets.choice(string.digits) for _ in range(5))
    return f"{_slugify_workshop_name(str(workshop.name or ''))}-{suffix}"


def _generate_owner_password() -> str:
    # SynplaiSign account password (not the Hunter login password).
    return secrets.token_urlsafe(24)


EXPECTED_WEBHOOK_EVENTS: tuple[str, ...] = ("ENVELOPE_COMPLETED", "DOCUMENT_DECLINED")


def _delete_remote_webhooks(*, api_key: str, webhooks: list[dict[str, Any]]) -> None:
    for webhook in webhooks:
        webhook_id = str(webhook.get("id") or "").strip()
        if not webhook_id:
            continue
        try:
            gateway.delete_webhook(api_key=api_key, webhook_id=webhook_id)
        except gateway.SynplaiSignGatewayError:
            logger.exception(
                "synplaisign_webhook_delete_failed",
                extra={"webhook_id": webhook_id, "url": webhook.get("url")},
            )


def _ensure_workshop_webhook(*, workshop: Workshop, api_key: str, webhook_url: str) -> None:
    expected_events = list(EXPECTED_WEBHOOK_EVENTS)
    local_secret = decrypt_secret(getattr(workshop, "synplaisign_webhook_secret", "") or "")
    existing = gateway.list_webhooks(api_key=api_key)
    same_url = [webhook for webhook in existing if webhook.get("url") == webhook_url]

    matching: dict[str, Any] | None = None
    for webhook in same_url:
        webhook_events = webhook.get("events")
        if isinstance(webhook_events, list) and all(event in webhook_events for event in expected_events):
            matching = webhook
            break

    if matching is not None and local_secret:
        matching_id = str(matching.get("id") or "").strip()
        duplicates = [webhook for webhook in same_url if str(webhook.get("id") or "").strip() != matching_id]
        if duplicates:
            _delete_remote_webhooks(api_key=api_key, webhooks=duplicates)
        update_fields: list[str] = []
        if matching_id and workshop.synplaisign_webhook_id != matching_id:
            workshop.synplaisign_webhook_id = matching_id
            update_fields.append("synplaisign_webhook_id")
        if update_fields:
            workshop.save(update_fields=update_fields)
        # Existing remote webhook matches and local secret is present — never rotate secret.
        return

    if matching is not None and not local_secret:
        logger.warning(
            "synplaisign_webhook_secret_missing",
            extra={"workshop_id": workshop.pk, "webhook_id": matching.get("id"), "url": webhook_url},
        )

    # Recreate: remove every remote config for this URL first to avoid duplicate secrets.
    if same_url:
        _delete_remote_webhooks(api_key=api_key, webhooks=same_url)

    created = gateway.create_webhook(api_key=api_key, url=webhook_url, events=expected_events)
    webhook_id = str(created.get("id") or "").strip()
    secret = str(created.get("secret") or "").strip()
    update_fields = []
    if webhook_id:
        workshop.synplaisign_webhook_id = webhook_id
        update_fields.append("synplaisign_webhook_id")
    if secret:
        workshop.synplaisign_webhook_secret = encrypt_secret(secret)
        update_fields.append("synplaisign_webhook_secret")
    if update_fields:
        workshop.save(update_fields=update_fields)


_SYNPLAISIGN_CREDENTIAL_FIELDS: tuple[str, ...] = (
    "synplaisign_api_key_id",
    "synplaisign_api_key",
    "synplaisign_owner_password",
    "synplaisign_webhook_id",
    "synplaisign_webhook_secret",
)


def _find_synplaisign_credential_donor(*, workshop: Workshop, account_workshops: list[Workshop] | None = None) -> Workshop | None:
    """Return another workshop of the same account/owner that already has SynplaiSign credentials.

    SynplaiSign rejects duplicate OWNER emails, so sibling workshops must reuse the same API key.
    """
    candidates = account_workshops
    if candidates is None:
        account_id = getattr(workshop, "account_id", None)
        if not account_id:
            return None
        candidates = list(
            Workshop.objects.filter(account_id=account_id)
            .exclude(pk=workshop.pk)
            .exclude(synplaisign_api_key="")
            .order_by("pk")
        )
        return candidates[0] if candidates else None

    for candidate in candidates:
        if candidate.pk == workshop.pk:
            continue
        if str(getattr(candidate, "synplaisign_api_key", "") or "").strip():
            return candidate
    return None


def _copy_synplaisign_credentials(*, source: Workshop, target: Workshop) -> None:
    for field_name in _SYNPLAISIGN_CREDENTIAL_FIELDS:
        setattr(target, field_name, getattr(source, field_name) or "")
    target.save(update_fields=list(_SYNPLAISIGN_CREDENTIAL_FIELDS))


def _lock_workshop_for_synplaisign_provision(workshop_pk: int) -> tuple[Workshop, list[Workshop]]:
    """Lock the target workshop and siblings of the same account in pk order (deadlock-safe)."""
    account_id = Workshop.objects.filter(pk=workshop_pk).values_list("account_id", flat=True).first()
    if account_id:
        account_workshops = list(
            Workshop.objects.select_for_update(of=("self",))
            .select_related("account", "account__owner")
            .filter(account_id=account_id)
            .order_by("pk")
        )
        locked = next((item for item in account_workshops if item.pk == workshop_pk), None)
        if locked is None:
            raise Workshop.DoesNotExist(f"Workshop matching query does not exist: pk={workshop_pk}")
        return locked, account_workshops

    locked = (
        Workshop.objects.select_for_update(of=("self",))
        .select_related("account", "account__owner")
        .get(pk=workshop_pk)
    )
    return locked, [locked]


def provision_workshop_synplaisign(
    *,
    workshop: Workshop,
    webhook_url: str | None = None,
    force: bool = False,
) -> Workshop:
    """Ensure SynplaiSign credentials + webhook for a workshop.

    When another workshop of the same account/owner already has credentials, reuses that API key
    (SynplaiSign does not allow duplicate OWNER emails). Otherwise registers via
    ``POST /auth/register-with-api-key`` with ``SYNPLAISIGN_MASTER_KEY``.

    When ``force=True`` and no sibling donor exists, discards local credentials and registers again.
    When a sibling donor exists, ``force`` still reuses the donor (cannot create a second login).
    """
    master_key = str(getattr(settings, "SYNPLAISIGN_MASTER_KEY", "") or "").strip()
    if not master_key:
        raise WorkshopSynplaiSignError("SYNPLAISIGN_MASTER_KEY nao configurado")

    resolved_webhook_url = (webhook_url or _default_webhook_url()).strip()

    try:
        with transaction.atomic():
            locked, account_workshops = _lock_workshop_for_synplaisign_provision(workshop.pk)
            api_key = decrypt_secret(locked.synplaisign_api_key)
            should_create = force or not api_key

            if api_key and not force:
                logger.info(
                    "synplaisign_api_key_already_present",
                    extra={"workshop_id": locked.pk, "api_key_id": locked.synplaisign_api_key_id},
                )
            elif should_create:
                donor = _find_synplaisign_credential_donor(workshop=locked, account_workshops=account_workshops)
                if donor is not None:
                    _copy_synplaisign_credentials(source=donor, target=locked)
                    api_key = decrypt_secret(locked.synplaisign_api_key)
                    if not api_key:
                        raise WorkshopSynplaiSignError(
                            f"Oficina donor={donor.pk} sem API key SynplaiSign valida para reutilizar."
                        )
                    logger.info(
                        "synplaisign_api_key_reused_from_owner_workshop",
                        extra={
                            "workshop_id": locked.pk,
                            "donor_workshop_id": donor.pk,
                            "api_key_id": locked.synplaisign_api_key_id,
                            "forced": force,
                        },
                    )
                else:
                    if force and api_key:
                        logger.warning(
                            "synplaisign_api_key_force_recreate",
                            extra={"workshop_id": locked.pk, "previous_api_key_id": locked.synplaisign_api_key_id},
                        )
                        for field_name in _SYNPLAISIGN_CREDENTIAL_FIELDS:
                            setattr(locked, field_name, "")
                        locked.save(update_fields=list(_SYNPLAISIGN_CREDENTIAL_FIELDS))

                    owner = _resolve_account_owner(locked)
                    password = _generate_owner_password()
                    api_key_name = _build_api_key_name(locked)
                    registered = gateway.register_with_api_key(
                        master_key=master_key,
                        organization_name=_organization_name_for_workshop(locked),
                        name=_owner_display_name(owner),
                        email=_owner_email(owner),
                        password=password,
                        api_key_name=api_key_name,
                    )
                    api_key_payload = registered.get("apiKey") if isinstance(registered.get("apiKey"), dict) else {}
                    key_id = str(api_key_payload.get("id") or "").strip()
                    raw_key = str(api_key_payload.get("key") or "").strip()
                    if not raw_key:
                        raise WorkshopSynplaiSignError("SynplaiSign nao retornou a API key no registro")

                    locked.synplaisign_api_key_id = key_id
                    locked.synplaisign_api_key = encrypt_secret(raw_key)
                    locked.synplaisign_owner_password = encrypt_secret(password)
                    locked.save(
                        update_fields=[
                            "synplaisign_api_key_id",
                            "synplaisign_api_key",
                            "synplaisign_owner_password",
                        ]
                    )
                    api_key = raw_key
                    logger.info(
                        "synplaisign_api_key_provisioned",
                        extra={
                            "workshop_id": locked.pk,
                            "api_key_id": key_id,
                            "api_key_name": api_key_name,
                            "forced": force,
                        },
                    )

            # Never rotates an existing API key unless force; only ensures webhook for the current key.
            _ensure_workshop_webhook(workshop=locked, api_key=api_key, webhook_url=resolved_webhook_url)

            locked.refresh_from_db()
            workshop.synplaisign_api_key_id = locked.synplaisign_api_key_id
            workshop.synplaisign_api_key = locked.synplaisign_api_key
            workshop.synplaisign_owner_password = locked.synplaisign_owner_password
            workshop.synplaisign_webhook_id = locked.synplaisign_webhook_id
            workshop.synplaisign_webhook_secret = locked.synplaisign_webhook_secret
            return workshop
    except gateway.SynplaiSignGatewayError as exc:
        raise WorkshopSynplaiSignError(str(exc)) from exc
