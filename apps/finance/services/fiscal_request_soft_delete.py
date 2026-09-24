from __future__ import annotations

from typing import Literal

from django.db.models import Exists, OuterRef, QuerySet
from django.utils import timezone

from apps.finance.models.finance import (
    NfeItem,
    NfeRequest,
    NfeRequestStatus,
    NfseItem,
    NfseRequest,
    NfseRequestStatus,
)

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


class FiscalRequestSoftDeleteError(Exception):
    """Raised when a fiscal request cannot be soft-deleted."""


def active_nfe_requests(*, queryset: QuerySet[NfeRequest] | None = None) -> QuerySet[NfeRequest]:
    qs = queryset if queryset is not None else NfeRequest.objects.all()
    return qs.filter(soft_deleted_at__isnull=True)


def active_nfse_requests(*, queryset: QuerySet[NfseRequest] | None = None) -> QuerySet[NfseRequest]:
    qs = queryset if queryset is not None else NfseRequest.objects.all()
    return qs.filter(soft_deleted_at__isnull=True)


def is_nfe_request_soft_deletable(*, nfe_request: NfeRequest) -> bool:
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
    if getattr(nfse_request, "soft_deleted_at", None) is not None:
        return False
    if str(nfse_request.status) not in NFSE_SOFT_DELETABLE_STATUSES:
        return False
    if nfse_request.reserved_rps_number is not None:
        return False
    if NfseItem.objects.filter(request_id=nfse_request.pk).exists():
        return False
    return True


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


def soft_delete_fiscal_request(*, kind: FiscalRequestKind, request_obj: NfeRequest | NfseRequest, user=None) -> NfeRequest | NfseRequest:
    if kind == "nfe":
        return soft_delete_nfe_request(nfe_request=request_obj, user=user)  # type: ignore[arg-type]
    return soft_delete_nfse_request(nfse_request=request_obj, user=user)  # type: ignore[arg-type]


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
