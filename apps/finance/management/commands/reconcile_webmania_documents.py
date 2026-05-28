from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from apps.finance.models.finance import FiscalEmissionAttempt, FiscalEmissionAttemptStatus, NfeItem, NfseItem
from apps.finance.services.nfe_consulta import NfeConsultaError, reconcile_nfe_item
from apps.finance.services.nfse_consulta import NfseConsultaError, reconcile_nfse_item
from apps.finance.services.webmania_webhooks import process_pending_webhook_events


class Command(BaseCommand):
    help = "Reprocessa webhooks pendentes e reconcilia NF-es pendentes na Webmania."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--limit", type=int, default=50)

    def handle(self, *args: Any, **options: Any) -> None:
        limit = int(options.get("limit") or 50)
        processed_webhooks = process_pending_webhook_events(limit=limit)

        reconciled_nfe = 0
        reconciled_nfse = 0
        failed = 0
        pending_items = NfeItem.objects.filter(status__in=["processando", "contingencia"]).select_related("workshop", "request").order_by("pk")[:limit]
        for pending_nfe_item in pending_items:
            try:
                reconcile_nfe_item(item=pending_nfe_item)
            except NfeConsultaError:
                failed += 1
            else:
                reconciled_nfe += 1

        pending_nfse_items = NfseItem.objects.filter(status__in=["processando", "contingencia", "agendado"]).select_related("workshop", "request").order_by("pk")[:limit]
        for pending_nfse_item in pending_nfse_items:
            try:
                reconcile_nfse_item(item=pending_nfse_item)
            except NfseConsultaError:
                failed += 1
            else:
                reconciled_nfse += 1

        uncertain_checked = 0
        uncertain_attempts = FiscalEmissionAttempt.objects.filter(status=FiscalEmissionAttemptStatus.UNCERTAIN).select_related("workshop").order_by("pk")[:limit]
        for attempt in uncertain_attempts:
            if attempt.document_kind == "nfe":
                nfe_item = NfeItem.objects.filter(request_id=attempt.request_id, workshop=attempt.workshop).order_by("-pk").first()
                if nfe_item is not None:
                    try:
                        reconcile_nfe_item(item=nfe_item)
                    except NfeConsultaError:
                        failed += 1
                    else:
                        uncertain_checked += 1
                continue

            if attempt.document_kind == "nfse":
                nfse_item = NfseItem.objects.filter(request_id=attempt.request_id, workshop=attempt.workshop).order_by("-pk").first()
                if nfse_item is not None:
                    try:
                        reconcile_nfse_item(item=nfse_item)
                    except NfseConsultaError:
                        failed += 1
                    else:
                        uncertain_checked += 1

        self.stdout.write(self.style.SUCCESS(f"Webhooks processados: {processed_webhooks}. NF-es reconciliadas: {reconciled_nfe}. NFS-es reconciliadas: {reconciled_nfse}. Tentativas incertas consultadas: {uncertain_checked}. Falhas: {failed}."))
