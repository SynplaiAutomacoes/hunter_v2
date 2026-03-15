from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.finance.models.finance import NfeItem
from apps.finance.services.nfe_consulta import NfeConsultaError, reconcile_nfe_item
from apps.finance.services.webmania_webhooks import process_pending_webhook_events


class Command(BaseCommand):
    help = "Reprocessa webhooks pendentes e reconcilia NF-es pendentes na Webmania."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--limit", type=int, default=50)

    def handle(self, *args, **options):
        limit = int(options.get("limit") or 50)
        processed_webhooks = process_pending_webhook_events(limit=limit)

        reconciled = 0
        failed = 0
        pending_items = NfeItem.objects.filter(status__in=["processando", "contingencia"]).select_related("workshop", "request").order_by("pk")[:limit]
        for item in pending_items:
            try:
                reconcile_nfe_item(item=item)
            except NfeConsultaError:
                failed += 1
            else:
                reconciled += 1

        self.stdout.write(self.style.SUCCESS(f"Webhooks processados: {processed_webhooks}. NF-es reconciliadas: {reconciled}. Falhas: {failed}."))
