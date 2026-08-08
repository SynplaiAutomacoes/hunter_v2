from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.finance.models.finance import (
    FiscalDocument,
    FiscalDocumentEvent,
    FiscalDocumentEventStatus,
    FiscalDocumentEventType,
    FiscalDocumentOrigin,
    FiscalDocumentPurpose,
    FiscalDocumentStatus,
    NfeItem,
)
from apps.core.infrastructure.providers import get_fiscal_service
from apps.core.domain.contracts.fiscal import FiscalServiceError
from apps.core.infrastructure.services.webmania.webmania_webhooks import process_pending_webhook_events
from apps.finance.services.nfe_events import NfeCorrectionError, reconcile_cce_event
from apps.finance.services.nfe_returns import NfeReturnError, reconcile_nfe_return_document


class Command(BaseCommand):
    help = "Reprocessa webhooks pendentes e reconcilia NF-es pendentes na Webmania."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--limit", type=int, default=50)

    def handle(self, *args, **options):
        limit = int(options.get("limit") or 50)
        processed_webhooks = process_pending_webhook_events(limit=limit)

        reconciled = 0
        reconciled_cce = 0
        reconciled_returns = 0
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

        pending_cce_events = (
            FiscalDocumentEvent.objects.filter(
                event_type=FiscalDocumentEventType.CCE,
                status__in=[FiscalDocumentEventStatus.SENT, FiscalDocumentEventStatus.PROCESSING, FiscalDocumentEventStatus.UNCERTAIN],
            )
            .exclude(remote_uuid="")
            .select_related("document", "document__workshop")
            .order_by("pk")[:limit]
        )
        for event in pending_cce_events:
            try:
                reconcile_cce_event(event=event)
            except NfeCorrectionError:
                failed += 1
            else:
                reconciled_cce += 1

        pending_returns = (
            FiscalDocument.objects.filter(
                origin=FiscalDocumentOrigin.DERIVED,
                purpose__in=[FiscalDocumentPurpose.RETURN, FiscalDocumentPurpose.REVERSAL],
                status__in=[FiscalDocumentStatus.PROCESSING, FiscalDocumentStatus.CONTINGENCY, FiscalDocumentStatus.UNCERTAIN],
            )
            .exclude(remote_uuid="")
            .select_related("workshop")
            .order_by("pk")[:limit]
        )
        for document in pending_returns:
            try:
                reconcile_nfe_return_document(document=document)
            except NfeReturnError:
                failed += 1
            else:
                reconciled_returns += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Webhooks processados: {processed_webhooks}. NF-es reconciliadas: {reconciled}. Cartas de correcao reconciliadas: {reconciled_cce}. Devolucoes/estornos reconciliados: {reconciled_returns}. Falhas: {failed}."
            )
        )
