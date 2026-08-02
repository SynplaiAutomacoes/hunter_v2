from __future__ import annotations

import logging

from django.conf import settings
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


def _default_webhook_url() -> str:
    return build_absolute_app_url(path=reverse("budget:signature_webhook"))


def _ensure_workshop_webhook(*, workshop: Workshop, api_key: str, webhook_url: str) -> None:
    expected_events = ["ENVELOPE_COMPLETED"]
    existing = gateway.list_webhooks(api_key=api_key)
    for webhook in existing:
        webhook_events = webhook.get("events")
        if webhook.get("url") == webhook_url and isinstance(webhook_events, list) and all(event in webhook_events for event in expected_events):
            webhook_id = str(webhook.get("id") or "").strip()
            update_fields: list[str] = []
            if webhook_id and workshop.synplaisign_webhook_id != webhook_id:
                workshop.synplaisign_webhook_id = webhook_id
                update_fields.append("synplaisign_webhook_id")
            if update_fields:
                workshop.save(update_fields=update_fields)
            # Existing remote webhook matches — never rotate secret.
            return

    # Only create a new webhook (and secret) when none matches the target URL.
    # If the workshop already has a secret but no matching remote webhook, we still
    # need a new remote registration; the new secret replaces the stale local one.
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


def provision_workshop_synplaisign(*, workshop: Workshop, webhook_url: str | None = None) -> Workshop:
    """Create SynplaiSign API key + webhook for a workshop when missing.

    Requires ``SYNPLAISIGN_MASTER_KEY`` for ``POST /api-keys``.
    """
    master_key = str(getattr(settings, "SYNPLAISIGN_MASTER_KEY", "") or "").strip()
    if not master_key:
        raise WorkshopSynplaiSignError("SYNPLAISIGN_MASTER_KEY nao configurado")

    resolved_webhook_url = (webhook_url or _default_webhook_url()).strip()

    try:
        with transaction.atomic():
            locked = Workshop.objects.select_for_update().get(pk=workshop.pk)
            api_key = decrypt_secret(locked.synplaisign_api_key)
            if api_key:
                logger.info(
                    "synplaisign_api_key_already_present",
                    extra={"workshop_id": locked.pk, "api_key_id": locked.synplaisign_api_key_id},
                )
            else:
                created = gateway.create_api_key(
                    master_key=master_key,
                    name=f"workshop-{locked.pk}-{str(locked.name)[:40]}",
                )
                key_id = str(created.get("id") or "").strip()
                raw_key = str(created.get("key") or "").strip()
                if not raw_key:
                    raise WorkshopSynplaiSignError("SynplaiSign nao retornou a API key")
                locked.synplaisign_api_key_id = key_id
                locked.synplaisign_api_key = encrypt_secret(raw_key)
                locked.save(update_fields=["synplaisign_api_key_id", "synplaisign_api_key"])
                api_key = raw_key
                logger.info(
                    "synplaisign_api_key_provisioned",
                    extra={"workshop_id": locked.pk, "api_key_id": key_id},
                )

            # Never rotates an existing API key; only ensures webhook for the current key.
            _ensure_workshop_webhook(workshop=locked, api_key=api_key, webhook_url=resolved_webhook_url)

            locked.refresh_from_db()
            workshop.synplaisign_api_key_id = locked.synplaisign_api_key_id
            workshop.synplaisign_api_key = locked.synplaisign_api_key
            workshop.synplaisign_webhook_id = locked.synplaisign_webhook_id
            workshop.synplaisign_webhook_secret = locked.synplaisign_webhook_secret
            return workshop
    except gateway.SynplaiSignGatewayError as exc:
        raise WorkshopSynplaiSignError(str(exc)) from exc
