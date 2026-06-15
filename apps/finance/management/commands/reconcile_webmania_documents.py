from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.finance.models.finance import NfeItem
from apps.core.infrastructure.providers import get_fiscal_service
from apps.core.domain.contracts.fiscal import FiscalServiceError
from apps.core.infrastructure.services.webmania.webmania_webhooks import process_pending_webhook_events


class Command(BaseCommand):
    help = "Reprocessa webhooks pendentes e reconcilia NF-es pendentes na Webmania."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--limit", type=int, default=50)

    def handle(self, *args, **options):
        limit = int(options.get("limit") or 50)
        processed_webhooks = process_pending_webhook_events(limit=limit)

        reconciled = 0
        failed = 0
        service = get_fiscal_service()
        pending_items = NfeItem.objects.filter(status__in=["processando", "contingencia"]).select_related("workshop", "request").order_by("pk")[:limit]
        for item in pending_items:
            try:
                service.reconcile_nfe_item(item=item)
            except FiscalServiceError:
                failed += 1
            else:
                reconciled += 1

        self.stdout.write(self.style.SUCCESS(f"Webhooks processados: {processed_webhooks}. NF-es reconciliadas: {reconciled}. Falhas: {failed}."))
