from __future__ import annotations

from argparse import ArgumentParser
import logging

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.urls import reverse

from apps.core.documents.services import SignatureDeliveryServiceError, ensure_signature_webhook
from apps.core.documents.signature import build_absolute_app_url


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Create/update SuperSign webhook endpoint for ENVELOPE_COMPLETED"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Falha o comando caso o webhook nao possa ser sincronizado.",
        )

    def handle(self, *args: object, **options: object) -> None:
        strict = bool(options["strict"])

        if not getattr(settings, "APP_BASE_URL", "").rstrip("/"):
            warning_message = "APP_BASE_URL nao configurado; usando fallback local para sincronizar webhook"
            logger.warning(warning_message)
            self.stderr.write(self.style.WARNING(warning_message))

        webhook_url = build_absolute_app_url(path=reverse("budget:supersign_webhook"))
        try:
            webhook = ensure_signature_webhook(webhook_url=webhook_url)
        except SignatureDeliveryServiceError as exc:
            message = f"SuperSign webhook nao sincronizado: {webhook_url}. Motivo: {exc}"
            logger.warning(message)
            if strict:
                raise CommandError(message) from exc
            self.stderr.write(self.style.WARNING(message))
            return

        self.stdout.write(self.style.SUCCESS(f"SuperSign webhook sincronizado: {webhook.get('id', '-')} -> {webhook_url}"))
