from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from apps.finance.models.finance import FiscalDocument, FiscalDocumentComplementaryType, FiscalDocumentOrigin, FiscalDocumentPurpose, FiscalDocumentStatus, FiscalDocumentType, FiscalEmissionAttempt, FiscalEmissionAttemptStatus, FiscalEmissionOperationType, NfeItem, NfseItem
from apps.finance.services.nfe_adjustment import NfeAdjustmentError, reconcile_nfe_adjustment_document
from apps.finance.services.nfe_complementary import NfeComplementaryError, reconcile_nfe_complementary_document
from apps.finance.services.nfe_consulta import NfeConsultaError, reconcile_nfe_item
from apps.finance.services.nfe_returns import NfeReturnError, reconcile_nfe_return_document
from apps.finance.services.nfce_emission import NfceEmissionError, reconcile_nfce_document
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
        reconciled_nfe_returns = 0
        reconciled_nfe_complementary = 0
        reconciled_nfe_adjustment = 0
        reconciled_nfce = 0
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

        pending_nfe_return_documents = FiscalDocument.objects.filter(
            origin=FiscalDocumentOrigin.DERIVED,
            purpose__in=[FiscalDocumentPurpose.RETURN, FiscalDocumentPurpose.REVERSAL],
            status__in=[FiscalDocumentStatus.PROCESSING, FiscalDocumentStatus.CONTINGENCY, FiscalDocumentStatus.UNCERTAIN],
        ).select_related("workshop").order_by("pk")[:limit]
        for pending_return_document in pending_nfe_return_documents:
            try:
                reconcile_nfe_return_document(document=pending_return_document)
            except NfeReturnError:
                failed += 1
            else:
                reconciled_nfe_returns += 1

        pending_nfe_complementary_documents = FiscalDocument.objects.filter(
            origin=FiscalDocumentOrigin.LOCAL,
            purpose=FiscalDocumentPurpose.COMPLEMENTARY,
            complementary_type=FiscalDocumentComplementaryType.PRICE_QUANTITY,
            status__in=[FiscalDocumentStatus.PROCESSING, FiscalDocumentStatus.CONTINGENCY, FiscalDocumentStatus.UNCERTAIN],
        ).select_related("workshop").order_by("pk")[:limit]
        for pending_complementary_document in pending_nfe_complementary_documents:
            try:
                reconcile_nfe_complementary_document(document=pending_complementary_document)
            except NfeComplementaryError:
                failed += 1
            else:
                reconciled_nfe_complementary += 1

        pending_nfe_adjustment_documents = FiscalDocument.objects.filter(
            origin=FiscalDocumentOrigin.MANUAL,
            purpose=FiscalDocumentPurpose.ADJUSTMENT,
            status__in=[FiscalDocumentStatus.PROCESSING, FiscalDocumentStatus.CONTINGENCY, FiscalDocumentStatus.UNCERTAIN],
        ).select_related("workshop").order_by("pk")[:limit]
        for pending_adjustment_document in pending_nfe_adjustment_documents:
            try:
                reconcile_nfe_adjustment_document(document=pending_adjustment_document)
            except NfeAdjustmentError:
                failed += 1
            else:
                reconciled_nfe_adjustment += 1

        pending_nfce_documents = FiscalDocument.objects.filter(
            document_type=FiscalDocumentType.NFCE,
            origin=FiscalDocumentOrigin.MANUAL,
            purpose=FiscalDocumentPurpose.NORMAL,
            status__in=[FiscalDocumentStatus.PROCESSING, FiscalDocumentStatus.CONTINGENCY, FiscalDocumentStatus.UNCERTAIN],
        ).select_related("workshop").order_by("pk")[:limit]
        for pending_nfce_document in pending_nfce_documents:
            try:
                reconcile_nfce_document(document=pending_nfce_document)
            except NfceEmissionError:
                failed += 1
            else:
                reconciled_nfce += 1

        pending_nfse_items = NfseItem.objects.filter(status__in=["processando", "contingencia", "agendado"]).select_related("workshop", "request").order_by("pk")[:limit]
        for pending_nfse_item in pending_nfse_items:
            try:
                reconcile_nfse_item(item=pending_nfse_item)
            except NfseConsultaError:
                failed += 1
            else:
                reconciled_nfse += 1

        uncertain_checked = 0
        uncertain_attempts = FiscalEmissionAttempt.objects.filter(status=FiscalEmissionAttemptStatus.UNCERTAIN).select_related("workshop", "fiscal_document").order_by("pk")[:limit]
        for attempt in uncertain_attempts:
            if attempt.document_kind == "nfe":
                if attempt.fiscal_document_id and attempt.operation_type == FiscalEmissionOperationType.ADJUSTMENT:
                    try:
                        reconcile_nfe_adjustment_document(document=attempt.fiscal_document)
                    except (NfeAdjustmentError, AttributeError):
                        failed += 1
                    else:
                        uncertain_checked += 1
                    continue

                if attempt.fiscal_document_id and attempt.operation_type == FiscalEmissionOperationType.COMPLEMENTARY_PRICE_QUANTITY:
                    try:
                        reconcile_nfe_complementary_document(document=attempt.fiscal_document)
                    except (NfeComplementaryError, AttributeError):
                        failed += 1
                    else:
                        uncertain_checked += 1
                    continue

                if attempt.fiscal_document_id and attempt.operation_type in {FiscalEmissionOperationType.RETURN, FiscalEmissionOperationType.REVERSAL}:
                    try:
                        reconcile_nfe_return_document(document=attempt.fiscal_document)
                    except (NfeReturnError, AttributeError):
                        failed += 1
                    else:
                        uncertain_checked += 1
                    continue

                nfe_item = NfeItem.objects.filter(request_id=attempt.request_id, workshop=attempt.workshop).order_by("-pk").first()
                if nfe_item is not None:
                    try:
                        reconcile_nfe_item(item=nfe_item)
                    except NfeConsultaError:
                        failed += 1
                    else:
                        uncertain_checked += 1
                continue

            if attempt.document_kind == "nfce":
                if attempt.fiscal_document_id and attempt.operation_type == FiscalEmissionOperationType.NFCE_EMISSION:
                    try:
                        reconcile_nfce_document(document=attempt.fiscal_document)
                    except (NfceEmissionError, AttributeError):
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

        self.stdout.write(self.style.SUCCESS(f"Webhooks processados: {processed_webhooks}. NF-es reconciliadas: {reconciled_nfe}. Devolucoes/estornos reconciliados: {reconciled_nfe_returns}. Complementares reconciliadas: {reconciled_nfe_complementary}. Ajustes reconciliados: {reconciled_nfe_adjustment}. NFC-es reconciliadas: {reconciled_nfce}. NFS-es reconciliadas: {reconciled_nfse}. Tentativas incertas consultadas: {uncertain_checked}. Falhas: {failed}."))
