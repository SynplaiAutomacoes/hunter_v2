from __future__ import annotations

from typing import Any

from apps.core.domain.contracts.fiscal import FiscalServiceError
from apps.core.infrastructure.providers import get_fiscal_service
from apps.core.infrastructure.services.webmania.nfe_consulta import NfeConsultaError, reconcile_nfe_item
from apps.core.infrastructure.services.webmania.nfse_consulta import NfseConsultaError, reconcile_nfse_batch, reconcile_nfse_item
from apps.core.infrastructure.services.webmania.webmania_webhooks import process_pending_webhook_events
from apps.finance.models.finance import (
    FiscalDocument,
    FiscalDocumentComplementaryType,
    FiscalDocumentEvent,
    FiscalDocumentEventStatus,
    FiscalDocumentEventType,
    FiscalDocumentOrigin,
    FiscalDocumentPurpose,
    FiscalDocumentStatus,
    FiscalDocumentType,
    FiscalEmissionAttempt,
    FiscalEmissionAttemptStatus,
    FiscalEmissionOperationType,
    NfeItem,
    NfseBatch,
    NfseCancellation,
    NfseItem,
    NfseManifestation,
    NfseSubstitution,
)
from apps.finance.services.nfe_adjustment import NfeAdjustmentError, reconcile_nfe_adjustment_document
from apps.finance.services.nfe_complementary import NfeComplementaryError, reconcile_nfe_complementary_document
from apps.finance.services.nfe_credit import NfeCreditError, reconcile_nfe_credit_document
from apps.finance.services.nfe_credit_cancellation import NfeCreditCancellationError, reconcile_nfe_credit_cancellation
from apps.finance.services.nfe_debit import NfeDebitError, reconcile_nfe_debit_document
from apps.finance.services.nfe_debit_cancellation import NfeDebitCancellationError, reconcile_nfe_debit_cancellation
from apps.finance.services.nfe_events import NfeCorrectionError, reconcile_cce_event
from apps.finance.services.nfe_returns import NfeReturnError, reconcile_nfe_return_document
from apps.finance.services.transport_requests import TransportRequestError, reconcile_transport_document
from apps.finance.services.nfce_cancellation import NfceCancellationError, reconcile_nfce_cancellation_event
from apps.finance.services.nfce_emission import NfceEmissionError, reconcile_nfce_document
from apps.finance.services.nfse_cancellation import NfseCancellationError, reconcile_nfse_cancellation
from apps.finance.services.nfse_manifestation import NfseManifestationError, reconcile_nfse_manifestation
from apps.finance.services.nfse_substitution import NfseSubstitutionError, reconcile_nfse_substitution
from django.core.management.base import BaseCommand, CommandParser


class Command(BaseCommand):
    help = "Reprocessa webhooks pendentes e reconcilia NF-es pendentes na Webmania."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--limit", type=int, default=50)

    def handle(self, *args: Any, **options: Any) -> None:
        limit = int(options.get("limit") or 50)
        processed_webhooks = process_pending_webhook_events(limit=limit)

        reconciled_nfe = 0
        reconciled_cce = 0
        reconciled_nfe_returns = 0
        reconciled_nfe_transport = 0
        reconciled_nfe_complementary = 0
        reconciled_nfe_adjustment = 0
        reconciled_nfe_credit = 0
        reconciled_nfe_debit = 0
        reconciled_nfe_credit_cancellations = 0
        reconciled_nfe_debit_cancellations = 0
        reconciled_nfce = 0
        reconciled_nfce_cancellations = 0
        reconciled_nfse = 0
        reconciled_nfse_batches = 0
        failed = 0
        service = get_fiscal_service()
        pending_items = NfeItem.objects.filter(status__in=["processando", "contingencia"]).select_related("workshop", "request").order_by("pk")[:limit]
        for pending_nfe_item in pending_items:
            try:
                service.reconcile_nfe_item(item=pending_nfe_item)
            except FiscalServiceError:
                failed += 1
            else:
                reconciled_nfe += 1

        pending_cce_events = (
            FiscalDocumentEvent.objects.filter(
                event_type=FiscalDocumentEventType.CCE,
                status__in=[FiscalDocumentEventStatus.SENT, FiscalDocumentEventStatus.PROCESSING, FiscalDocumentEventStatus.UNCERTAIN],
            )
            .exclude(remote_uuid="")
            .select_related("document", "document__workshop")
            .order_by("pk")[:limit]
        )
        for pending_cce_event in pending_cce_events:
            try:
                reconcile_cce_event(event=pending_cce_event)
            except NfeCorrectionError:
                failed += 1
            else:
                reconciled_cce += 1

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

        pending_transport_documents = FiscalDocument.objects.filter(
            transport_request__isnull=False,
            status__in=[FiscalDocumentStatus.PROCESSING, FiscalDocumentStatus.CONTINGENCY, FiscalDocumentStatus.UNCERTAIN],
        ).select_related("workshop").order_by("pk")[:limit]
        for pending_transport_document in pending_transport_documents:
            try:
                reconcile_transport_document(document=pending_transport_document)
            except TransportRequestError:
                failed += 1
            else:
                reconciled_nfe_transport += 1

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

        pending_nfe_credit_documents = FiscalDocument.objects.filter(
            origin=FiscalDocumentOrigin.DERIVED,
            purpose=FiscalDocumentPurpose.CREDIT,
            fiscal_purpose_type="1",
            status__in=[FiscalDocumentStatus.PROCESSING, FiscalDocumentStatus.CONTINGENCY, FiscalDocumentStatus.UNCERTAIN],
        ).select_related("workshop").order_by("pk")[:limit]
        for pending_credit_document in pending_nfe_credit_documents:
            try:
                reconcile_nfe_credit_document(document=pending_credit_document)
            except NfeCreditError:
                failed += 1
            else:
                reconciled_nfe_credit += 1

        pending_nfe_debit_documents = FiscalDocument.objects.filter(
            origin=FiscalDocumentOrigin.DERIVED,
            purpose=FiscalDocumentPurpose.DEBIT,
            fiscal_purpose_type="4",
            status__in=[FiscalDocumentStatus.PROCESSING, FiscalDocumentStatus.CONTINGENCY, FiscalDocumentStatus.UNCERTAIN],
        ).select_related("workshop").order_by("pk")[:limit]
        for pending_debit_document in pending_nfe_debit_documents:
            try:
                reconcile_nfe_debit_document(document=pending_debit_document)
            except NfeDebitError:
                failed += 1
            else:
                reconciled_nfe_debit += 1

        pending_credit_cancellations = FiscalDocumentEvent.objects.filter(
            event_type=FiscalDocumentEventType.CANCELLATION,
            event_payload_type="nfe_credit_cancellation",
            document__purpose=FiscalDocumentPurpose.CREDIT,
            document__fiscal_purpose_type="1",
            status__in=[FiscalDocumentEventStatus.SENT, FiscalDocumentEventStatus.PROCESSING, FiscalDocumentEventStatus.UNCERTAIN],
        ).select_related("document", "document__workshop").order_by("pk")[:limit]
        for cancellation_event in pending_credit_cancellations:
            try:
                reconcile_nfe_credit_cancellation(event=cancellation_event)
            except NfeCreditCancellationError:
                failed += 1
            else:
                reconciled_nfe_credit_cancellations += 1

        pending_debit_cancellations = FiscalDocumentEvent.objects.filter(
            event_type=FiscalDocumentEventType.CANCELLATION,
            event_payload_type="nfe_debit_cancellation",
            document__purpose=FiscalDocumentPurpose.DEBIT,
            document__fiscal_purpose_type="4",
            status__in=[FiscalDocumentEventStatus.SENT, FiscalDocumentEventStatus.PROCESSING, FiscalDocumentEventStatus.UNCERTAIN],
        ).select_related("document", "document__workshop").order_by("pk")[:limit]
        for cancellation_event in pending_debit_cancellations:
            try:
                reconcile_nfe_debit_cancellation(event=cancellation_event)
            except NfeDebitCancellationError:
                failed += 1
            else:
                reconciled_nfe_debit_cancellations += 1

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

        pending_nfce_cancellation_events = FiscalDocumentEvent.objects.filter(
            event_type=FiscalDocumentEventType.CANCELLATION,
            document__document_type=FiscalDocumentType.NFCE,
            status__in=[FiscalDocumentEventStatus.SENT, FiscalDocumentEventStatus.PROCESSING, FiscalDocumentEventStatus.UNCERTAIN],
        ).select_related("document", "document__workshop").order_by("pk")[:limit]
        for pending_cancellation_event in pending_nfce_cancellation_events:
            try:
                reconcile_nfce_cancellation_event(event=pending_cancellation_event)
            except NfceCancellationError:
                failed += 1
            else:
                reconciled_nfce_cancellations += 1

        reconciled_batch_item_ids: set[int] = set()
        pending_nfse_batches = NfseBatch.objects.filter(status__in=["processando", "contingencia", "agendado"]).select_related("workshop", "request").order_by("pk")[:limit]
        for pending_nfse_batch in pending_nfse_batches:
            try:
                reconcile_nfse_batch(batch=pending_nfse_batch)
            except NfseConsultaError:
                failed += 1
            else:
                reconciled_nfse_batches += 1
                reconciled_batch_item_ids.update(pending_nfse_batch.items.values_list("pk", flat=True))

        pending_nfse_items = NfseItem.objects.filter(status__in=["processando", "contingencia", "agendado"]).exclude(pk__in=reconciled_batch_item_ids).select_related("workshop", "request").order_by("pk")[:limit]
        for pending_nfse_item in pending_nfse_items:
            try:
                reconcile_nfse_item(item=pending_nfse_item)
            except NfseConsultaError:
                failed += 1
            else:
                reconciled_nfse += 1

        uncertain_checked = 0
        pending_nfse_substitutions = NfseSubstitution.objects.filter(status=FiscalEmissionAttemptStatus.SENT, uuid_replacement__isnull=False).select_related("workshop", "preview", "original_nfse").order_by("pk")[:limit]
        for pending_substitution in pending_nfse_substitutions:
            try:
                reconcile_nfse_substitution(substitution=pending_substitution)
            except NfseSubstitutionError:
                failed += 1
            else:
                uncertain_checked += 1

        uncertain_attempts = FiscalEmissionAttempt.objects.filter(status=FiscalEmissionAttemptStatus.UNCERTAIN).select_related("workshop", "fiscal_document").order_by("pk")[:limit]
        for attempt in uncertain_attempts:
            if attempt.document_kind == "nfe":
                if attempt.fiscal_document_event_id and attempt.operation_type == FiscalEmissionOperationType.CCE:
                    continue

                if attempt.fiscal_document_event_id and attempt.operation_type == FiscalEmissionOperationType.NFE_DEBIT_CANCELLATION:
                    try:
                        reconcile_nfe_debit_cancellation(event=attempt.fiscal_document_event)
                    except (NfeDebitCancellationError, AttributeError):
                        failed += 1
                    else:
                        uncertain_checked += 1
                    continue

                if attempt.fiscal_document_event_id and attempt.operation_type == FiscalEmissionOperationType.NFE_CREDIT_CANCELLATION:
                    try:
                        reconcile_nfe_credit_cancellation(event=attempt.fiscal_document_event)
                    except (NfeCreditCancellationError, AttributeError):
                        failed += 1
                    else:
                        uncertain_checked += 1
                    continue

                if attempt.fiscal_document_id and attempt.operation_type == FiscalEmissionOperationType.NFE_CREDIT_EMISSION:
                    try:
                        reconcile_nfe_credit_document(document=attempt.fiscal_document)
                    except (NfeCreditError, AttributeError):
                        failed += 1
                    else:
                        uncertain_checked += 1
                    continue

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

                if attempt.fiscal_document_id and attempt.operation_type == FiscalEmissionOperationType.TRANSPORT:
                    try:
                        reconcile_transport_document(document=attempt.fiscal_document)
                    except (TransportRequestError, AttributeError):
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
                if attempt.fiscal_document_event_id and attempt.operation_type == FiscalEmissionOperationType.NFCE_CANCELLATION:
                    try:
                        reconcile_nfce_cancellation_event(event=attempt.fiscal_document_event)
                    except (NfceCancellationError, AttributeError):
                        failed += 1
                    else:
                        uncertain_checked += 1
                    continue

                if attempt.fiscal_document_id and attempt.operation_type == FiscalEmissionOperationType.NFCE_EMISSION:
                    try:
                        reconcile_nfce_document(document=attempt.fiscal_document)
                    except (NfceEmissionError, AttributeError):
                        failed += 1
                    else:
                        uncertain_checked += 1
                continue

            if attempt.document_kind == "nfse":
                if attempt.operation_type == FiscalEmissionOperationType.NFSE_SUBSTITUTION and attempt.request_model == NfseSubstitution.__name__:
                    substitution = NfseSubstitution.objects.filter(pk=attempt.request_id, workshop=attempt.workshop).select_related("original_nfse", "preview").first()
                    if substitution is not None:
                        try:
                            reconcile_nfse_substitution(substitution=substitution)
                        except NfseSubstitutionError:
                            failed += 1
                        else:
                            uncertain_checked += 1
                    continue

                if attempt.operation_type == FiscalEmissionOperationType.NFSE_CANCELLATION and attempt.request_model == NfseCancellation.__name__:
                    cancellation = NfseCancellation.objects.filter(pk=attempt.request_id, workshop=attempt.workshop).select_related("item", "request").first()
                    if cancellation is not None:
                        try:
                            reconcile_nfse_cancellation(cancellation=cancellation)
                        except NfseCancellationError:
                            failed += 1
                        else:
                            uncertain_checked += 1
                    continue

                if attempt.operation_type == FiscalEmissionOperationType.NFSE_MANIFESTATION and attempt.request_model == NfseManifestation.__name__:
                    manifestation = NfseManifestation.objects.filter(pk=attempt.request_id, workshop=attempt.workshop).select_related("nfse_item").first()
                    if manifestation is not None:
                        try:
                            reconcile_nfse_manifestation(manifestation=manifestation)
                        except NfseManifestationError:
                            failed += 1
                        else:
                            uncertain_checked += 1
                    continue

                nfse_item = NfseItem.objects.filter(request_id=attempt.request_id, workshop=attempt.workshop).order_by("-pk").first()
                if nfse_item is not None:
                    try:
                        reconcile_nfse_item(item=nfse_item)
                    except NfseConsultaError:
                        failed += 1
                    else:
                        uncertain_checked += 1
                    continue

                nfse_batch = NfseBatch.objects.filter(request_id=attempt.request_id, workshop=attempt.workshop).order_by("-pk").first()
                if nfse_batch is not None:
                    try:
                        reconcile_nfse_batch(batch=nfse_batch)
                    except NfseConsultaError:
                        failed += 1
                    else:
                        uncertain_checked += 1

        self.stdout.write(self.style.SUCCESS(f"Webhooks processados: {processed_webhooks}. NF-es reconciliadas: {reconciled_nfe}. Cartas de correcao reconciliadas: {reconciled_cce}. Devolucoes/estornos reconciliados: {reconciled_nfe_returns}. Notas de Transporte reconciliadas: {reconciled_nfe_transport}. Complementares reconciliadas: {reconciled_nfe_complementary}. Ajustes reconciliados: {reconciled_nfe_adjustment}. Creditos tipo 1 reconciliados: {reconciled_nfe_credit}. Debitos tipo 4 reconciliados: {reconciled_nfe_debit}. Cancelamentos de credito reconciliados: {reconciled_nfe_credit_cancellations}. Cancelamentos de debito reconciliados: {reconciled_nfe_debit_cancellations}. NFC-es reconciliadas: {reconciled_nfce}. Cancelamentos NFC-e reconciliados: {reconciled_nfce_cancellations}. Lotes NFS-e reconciliados: {reconciled_nfse_batches}. NFS-es reconciliadas: {reconciled_nfse}. Tentativas incertas consultadas: {uncertain_checked}. Falhas: {failed}."))
