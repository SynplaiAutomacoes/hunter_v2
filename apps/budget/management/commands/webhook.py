from __future__ import annotations

from django.core.management.base import BaseCommand
from django.urls import reverse

from apps.core.documents.services import ensure_signature_webhook
from apps.core.documents.signature import build_absolute_app_url


class Command(BaseCommand):
    help = "Create/update SuperSign webhook endpoint for ENVELOPE_COMPLETED"

    def handle(self, *args, **options):
        webhook_url = build_absolute_app_url(path=reverse("budget:supersign_webhook"))
        webhook = ensure_signature_webhook(webhook_url=webhook_url)
        self.stdout.write(self.style.SUCCESS(f"SuperSign webhook sincronizado: {webhook.get('id', '-')} -> {webhook_url}"))
