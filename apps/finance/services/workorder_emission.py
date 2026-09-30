from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from django.urls import reverse

from apps.finance.models.finance import NfeRequest, NfeRequestStatus, NfseRequest, NfseRequestStatus
from apps.finance.services.pricing import build_slider_allocation_for_workorder
from apps.workorder.models import WorkOrder, WorkOrderStatus

EmissionUiMode = Literal["emit", "view_single", "partial_choice", "view_both"]


@dataclass(slots=True, frozen=True)
class WorkOrderEmissionUiState:
    mode: EmissionUiMode
    button_label: str
    opens_modal: bool
    has_nfe: bool
    has_nfse: bool
    can_emit_nfe: bool
    can_emit_nfse: bool
    nfe_request_id: int | None
    nfse_request_id: int | None
    emit_url: str
    emit_missing_url: str
    nfe_detail_url: str
    nfse_detail_url: str
    direct_url: str
    missing_note_label: str
    existing_note_label: str


def _emission_create_url(*, workorder_id: int, note_mode: str = "") -> str:
    url = f"{reverse('finance:emission_create')}?workorder={workorder_id}&reset=1"
    if note_mode:
        url = f"{url}&tipo={note_mode}"
    return url


def get_workorder_emission_ui_state(*, workorder: WorkOrder) -> WorkOrderEmissionUiState | None:
    """Return emission button UI state for an approved work order, or None if not applicable."""
    if workorder.status != WorkOrderStatus.APPROVED:
        return None

    # Notas canceladas/inutilizadas/apagadas não devem bloquear nova emissão.
    _NFE_INACTIVE_STATUSES = (NfeRequestStatus.CANCELED, NfeRequestStatus.INVALIDATED)
    _NFSE_INACTIVE_STATUSES = (NfseRequestStatus.CANCELED,)

    nfe_request = (
        NfeRequest.objects.filter(workorder=workorder, soft_deleted_at__isnull=True)
        .exclude(status__in=_NFE_INACTIVE_STATUSES)
        .order_by("-pk")
        .first()
    )
    nfse_request = (
        NfseRequest.objects.filter(workorder=workorder, soft_deleted_at__isnull=True)
        .exclude(status__in=_NFSE_INACTIVE_STATUSES)
        .order_by("-pk")
        .first()
    )
    has_nfe = nfe_request is not None
    has_nfse = nfse_request is not None
    nfe_request_id = nfe_request.pk if nfe_request is not None else None
    nfse_request_id = nfse_request.pk if nfse_request is not None else None

    allocation = build_slider_allocation_for_workorder(workorder=workorder)
    can_emit_nfe = allocation.products_target > 0
    can_emit_nfse = allocation.services_target > 0
    both_types_possible = can_emit_nfe and can_emit_nfse

    nfe_detail_url = reverse("finance:nfe_detail", kwargs={"pk": nfe_request_id}) if nfe_request_id is not None else ""
    nfse_detail_url = reverse("finance:nfse_detail", kwargs={"pk": nfse_request_id}) if nfse_request_id is not None else ""
    emit_url = _emission_create_url(workorder_id=workorder.pk)

    if has_nfe and has_nfse:
        return WorkOrderEmissionUiState(
            mode="view_both",
            button_label="Ver Nota",
            opens_modal=True,
            has_nfe=True,
            has_nfse=True,
            can_emit_nfe=can_emit_nfe,
            can_emit_nfse=can_emit_nfse,
            nfe_request_id=nfe_request_id,
            nfse_request_id=nfse_request_id,
            emit_url=emit_url,
            emit_missing_url="",
            nfe_detail_url=nfe_detail_url,
            nfse_detail_url=nfse_detail_url,
            direct_url="",
            missing_note_label="",
            existing_note_label="",
        )

    if has_nfe or has_nfse:
        if both_types_possible:
            missing_mode = "nfse" if has_nfe else "nfe"
            missing_label = "Nota Fiscal de Serviço" if missing_mode == "nfse" else "Nota Fiscal de Produto"
            existing_label = "Nota Fiscal de Produto" if has_nfe else "Nota Fiscal de Serviço"
            existing_url = nfe_detail_url if has_nfe else nfse_detail_url
            return WorkOrderEmissionUiState(
                mode="partial_choice",
                button_label="Ver Nota",
                opens_modal=True,
                has_nfe=has_nfe,
                has_nfse=has_nfse,
                can_emit_nfe=can_emit_nfe,
                can_emit_nfse=can_emit_nfse,
                nfe_request_id=nfe_request_id,
                nfse_request_id=nfse_request_id,
                emit_url=emit_url,
                emit_missing_url=_emission_create_url(workorder_id=workorder.pk, note_mode=missing_mode),
                nfe_detail_url=nfe_detail_url,
                nfse_detail_url=nfse_detail_url,
                direct_url=existing_url,
                missing_note_label=missing_label,
                existing_note_label=existing_label,
            )

        existing_url = nfe_detail_url if has_nfe else nfse_detail_url
        return WorkOrderEmissionUiState(
            mode="view_single",
            button_label="Ver Nota",
            opens_modal=False,
            has_nfe=has_nfe,
            has_nfse=has_nfse,
            can_emit_nfe=can_emit_nfe,
            can_emit_nfse=can_emit_nfse,
            nfe_request_id=nfe_request_id,
            nfse_request_id=nfse_request_id,
            emit_url=emit_url,
            emit_missing_url="",
            nfe_detail_url=nfe_detail_url,
            nfse_detail_url=nfse_detail_url,
            direct_url=existing_url,
            missing_note_label="",
            existing_note_label="Nota Fiscal de Produto" if has_nfe else "Nota Fiscal de Serviço",
        )

    return WorkOrderEmissionUiState(
        mode="emit",
        button_label="Emitir Nota",
        opens_modal=False,
        has_nfe=False,
        has_nfse=False,
        can_emit_nfe=can_emit_nfe,
        can_emit_nfse=can_emit_nfse,
        nfe_request_id=None,
        nfse_request_id=None,
        emit_url=emit_url,
        emit_missing_url="",
        nfe_detail_url="",
        nfse_detail_url="",
        direct_url=emit_url,
        missing_note_label="",
        existing_note_label="",
    )
