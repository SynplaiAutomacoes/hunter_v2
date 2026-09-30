from __future__ import annotations

from typing import Literal

from django.db.models import Exists, OuterRef, QuerySet
from django.utils import timezone

from apps.finance.models.finance import (
    FiscalDocumentStatus,
    FiscalEmissionAttemptStatus,
    NfeItem,
    NfeRequest,
    NfeRequestStatus,
    NfseItem,
    NfseRequest,
    NfseRequestStatus,
)
from apps.finance.models.purchase_return import PurchaseReturnRequest, PurchaseReturnRequestStatus

FiscalRequestKind = Literal["nfe", "nfse"]

NFE_SOFT_DELETABLE_STATUSES: frozenset[str] = frozenset(
    {
        NfeRequestStatus.WAITING_WO,
        NfeRequestStatus.CHECKING_CLIENT,
        NfeRequestStatus.CHECKING_PRODUCTS,
    }
)
NFSE_SOFT_DELETABLE_STATUSES: frozenset[str] = frozenset(
    {
        NfseRequestStatus.WAITING_WO,
        NfseRequestStatus.CHECKING_CLIENT,
        NfseRequestStatus.CHECKING_SERVICES,
    }
)
PURCHASE_RETURN_SOFT_DELETABLE_STATUSES: frozenset[str] = frozenset(
    {
        PurchaseReturnRequestStatus.DRAFT,
        PurchaseReturnRequestStatus.READY,
    }
)
_PURCHASE_RETURN_REMOTE_ATTEMPT_STATUSES: frozenset[str] = frozenset(
    {
        FiscalEmissionAttemptStatus.SENT,
        FiscalEmissionAttemptStatus.SUCCEEDED,
        FiscalEmissionAttemptStatus.UNCERTAIN,
    }
)


class FiscalRequestSoftDeleteError(Exception):
    """Raised when a fiscal request cannot be soft-deleted."""


def active_nfe_requests(*, queryset: QuerySet[NfeRequest] | None = None) -> QuerySet[NfeRequest]:
    qs = queryset if queryset is not None else NfeRequest.objects.all()
    return qs.filter(soft_deleted_at__isnull=True)


def active_nfse_requests(*, queryset: QuerySet[NfseRequest] | None = None) -> QuerySet[NfseRequest]:
    qs = queryset if queryset is not None else NfseRequest.objects.all()
    return qs.filter(soft_deleted_at__isnull=True)


def active_purchase_return_requests(*, queryset: QuerySet[PurchaseReturnRequest] | None = None) -> QuerySet[PurchaseReturnRequest]:
    qs = queryset if queryset is not None else PurchaseReturnRequest.objects.all()
    return qs.filter(soft_deleted_at__isnull=True)


def is_nfe_request_soft_deletable(*, nfe_request: NfeRequest) -> bool:
    """True when the NF-e draft never reached Webmania (no remote item / reserved number)."""
    if getattr(nfe_request, "soft_deleted_at", None) is not None:
        return False
    if str(nfe_request.status) not in NFE_SOFT_DELETABLE_STATUSES:
        return False
    if nfe_request.reserved_number is not None:
        return False
    if NfeItem.objects.filter(request_id=nfe_request.pk).exists():
        return False
    return True


def is_nfse_request_soft_deletable(*, nfse_request: NfseRequest) -> bool:
    """True when the NFS-e draft never reached Webmania (no remote item / reserved RPS)."""
    if getattr(nfse_request, "soft_deleted_at", None) is not None:
        return False
    if str(nfse_request.status) not in NFSE_SOFT_DELETABLE_STATUSES:
        return False
    if nfse_request.reserved_rps_number is not None:
        return False
    if NfseItem.objects.filter(request_id=nfse_request.pk).exists():
        return False
    return True


def purchase_return_has_remote_identity(*, return_request: PurchaseReturnRequest) -> bool:
    document = getattr(return_request, "fiscal_document", None)
    if document is None:
        return False
    return bool(str(document.remote_uuid or "").strip() or str(document.access_key or "").strip())


def purchase_return_reached_webmania(*, return_request: PurchaseReturnRequest) -> bool:
    """True when a purchase-return intention already contacted Webmania."""
    if purchase_return_has_remote_identity(return_request=return_request):
        return True
    document = getattr(return_request, "fiscal_document", None)
    if document is None:
        return False
    return document.emission_attempts.filter(status__in=_PURCHASE_RETURN_REMOTE_ATTEMPT_STATUSES).exists()


def is_purchase_return_soft_deletable(*, return_request: PurchaseReturnRequest) -> bool:
    """True when the Nota de Devolução draft never reached Webmania."""
    if getattr(return_request, "soft_deleted_at", None) is not None:
        return False
    if str(return_request.status) not in PURCHASE_RETURN_SOFT_DELETABLE_STATUSES:
        return False
    return not purchase_return_reached_webmania(return_request=return_request)


def annotate_nfe_soft_deletable(queryset: QuerySet[NfeRequest]) -> QuerySet[NfeRequest]:
    has_remote_item = Exists(NfeItem.objects.filter(request_id=OuterRef("pk")))
    return queryset.annotate(_has_remote_item=has_remote_item)


def annotate_nfse_soft_deletable(queryset: QuerySet[NfseRequest]) -> QuerySet[NfseRequest]:
    has_remote_item = Exists(NfseItem.objects.filter(request_id=OuterRef("pk")))
    return queryset.annotate(_has_remote_item=has_remote_item)


def soft_delete_nfe_request(*, nfe_request: NfeRequest, user=None) -> NfeRequest:
    if not is_nfe_request_soft_deletable(nfe_request=nfe_request):
        raise FiscalRequestSoftDeleteError(
            "Só é possível apagar rascunhos que ainda não foram enviados à Webmania e não possuem numeração reservada."
        )
    nfe_request.soft_deleted_at = timezone.now()
    nfe_request.soft_deleted_by = user
    nfe_request.save(update_fields=["soft_deleted_at", "soft_deleted_by", "atualizado_em"])
    return nfe_request


def soft_delete_nfse_request(*, nfse_request: NfseRequest, user=None) -> NfseRequest:
    if not is_nfse_request_soft_deletable(nfse_request=nfse_request):
        raise FiscalRequestSoftDeleteError(
            "Só é possível apagar rascunhos que ainda não foram enviados à Webmania e não possuem numeração reservada."
        )
    nfse_request.soft_deleted_at = timezone.now()
    nfse_request.soft_deleted_by = user
    nfse_request.save(update_fields=["soft_deleted_at", "soft_deleted_by", "atualizado_em"])
    return nfse_request


def soft_delete_purchase_return_request(*, return_request: PurchaseReturnRequest, user=None) -> PurchaseReturnRequest:
    if not is_purchase_return_soft_deletable(return_request=return_request):
        raise FiscalRequestSoftDeleteError(
            "Só é possível apagar Notas de Devolução que ainda não foram enviadas à Webmania."
        )
    return_request.soft_deleted_at = timezone.now()
    return_request.soft_deleted_by = user
    return_request.save(update_fields=["soft_deleted_at", "soft_deleted_by", "atualizado_em"])
    return return_request


def soft_delete_fiscal_request(*, kind: FiscalRequestKind, request_obj: NfeRequest | NfseRequest, user=None) -> NfeRequest | NfseRequest:
    if kind == "nfe":
        return soft_delete_nfe_request(nfe_request=request_obj, user=user)  # type: ignore[arg-type]
    return soft_delete_nfse_request(nfse_request=request_obj, user=user)  # type: ignore[arg-type]


def soft_delete_wizard_draft_requests(*, workshop, state: dict, user=None) -> list[NfeRequest | NfseRequest]:
    """Soft-delete pre-emit drafts referenced by an emission wizard session.

    Used when the user restarts emission before sending to Webmania, so orphan
    drafts do not remain in Central de Notas or block the OS emission dropdown.
    Already-emitted / reserved / remote-synced requests are left untouched.
    """
    deleted: list[NfeRequest | NfseRequest] = []
    if not isinstance(state, dict):
        return deleted

    nfe_request_id = state.get("nfe_request_id")
    if nfe_request_id:
        nfe_request = NfeRequest.objects.filter(pk=nfe_request_id, workshop=workshop).first()
        if nfe_request is not None and is_nfe_request_soft_deletable(nfe_request=nfe_request):
            deleted.append(soft_delete_nfe_request(nfe_request=nfe_request, user=user))

    nfse_request_id = state.get("nfse_request_id")
    if nfse_request_id:
        nfse_request = NfseRequest.objects.filter(pk=nfse_request_id, workshop=workshop).first()
        if nfse_request is not None and is_nfse_request_soft_deletable(nfse_request=nfse_request):
            deleted.append(soft_delete_nfse_request(nfse_request=nfse_request, user=user))

    return deleted


def is_soft_deletable_from_row(*, kind: FiscalRequestKind, request_obj: NfeRequest | NfseRequest) -> bool:
    """Prefer annotated `_has_remote_item` when present to avoid N+1 queries on list rows."""
    has_remote = getattr(request_obj, "_has_remote_item", None)
    if kind == "nfe":
        if getattr(request_obj, "soft_deleted_at", None) is not None:
            return False
        if str(request_obj.status) not in NFE_SOFT_DELETABLE_STATUSES:
            return False
        if getattr(request_obj, "reserved_number", None) is not None:
            return False
        if has_remote is None:
            return not NfeItem.objects.filter(request_id=request_obj.pk).exists()
        return not bool(has_remote)

    if getattr(request_obj, "soft_deleted_at", None) is not None:
        return False
    if str(request_obj.status) not in NFSE_SOFT_DELETABLE_STATUSES:
        return False
    if getattr(request_obj, "reserved_rps_number", None) is not None:
        return False
    if has_remote is None:
        return not NfseItem.objects.filter(request_id=request_obj.pk).exists()
    return not bool(has_remote)


def release_unreachable_purchase_return_reservation(*, return_request: PurchaseReturnRequest) -> PurchaseReturnRequest:
    """Release quantity reservation for a stuck return that has no remote identity.

    Used when reissuing UNCERTAIN intentions that cannot be reconciled because
    Webmania never returned uuid/chave.
    """
    from apps.finance.services.fiscal_attempts import mark_attempt_failed
    from apps.finance.services.nfe_returns import RESERVING_RETURN_STATUSES

    document = getattr(return_request, "fiscal_document", None)
    if document is None:
        return return_request
    if purchase_return_has_remote_identity(return_request=return_request):
        raise FiscalRequestSoftDeleteError("Não é possível liberar uma Nota de Devolução que já possui identificador remoto.")

    message = "Intenção liberada para nova emissão: resposta remota sem identificador seguro."
    if document.status in RESERVING_RETURN_STATUSES or document.status == FiscalDocumentStatus.PROCESSING:
        document.status = FiscalDocumentStatus.REPROVED
        document.remote_status = FiscalDocumentStatus.REPROVED
        document.response_payload = {**(document.response_payload or {}), "error": message}
        document.save(update_fields=["status", "remote_status", "response_payload", "atualizado_em"])

    for attempt in document.emission_attempts.exclude(status=FiscalEmissionAttemptStatus.FAILED).order_by("pk"):
        mark_attempt_failed(attempt=attempt, error_message=message, response_payload=document.response_payload or None)

    if return_request.status == PurchaseReturnRequestStatus.UNCERTAIN:
        return_request.status = PurchaseReturnRequestStatus.REJECTED
        return_request.save(update_fields=["status", "atualizado_em"])
    return return_request
