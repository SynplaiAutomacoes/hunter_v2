from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.budget.service import build_supersign_webhook_url, ensure_supersign_webhook


class Command(BaseCommand):
    help = "Create/update SuperSign webhook endpoint for ENVELOPE_COMPLETED"

    def handle(self, *args, **options):
        webhook_url = build_supersign_webhook_url()
        webhook = ensure_supersign_webhook(webhook_url=webhook_url)
        self.stdout.write(self.style.SUCCESS(f"SuperSign webhook sincronizado: {webhook.get('id', '-')} -> {webhook_url}"))
