from __future__ import annotations

from apps.workorder.models import WorkOrderDiscountType


def resolve_emission_discount_type_override(*, note_mode: str, explicit_override: str = "") -> str:
    """Resolve which discount split to use for the current emission note mode.

    - Only NF-e: apply the full discount on products.
    - Only NFS-e: apply the full discount on services.
    - Both: keep the workorder split, or an explicit override from the mismatch modal.
    """
    mode = str(note_mode or "").strip().lower()
    if mode == "nfe":
        return str(WorkOrderDiscountType.PRODUCTS)
    if mode == "nfse":
        return str(WorkOrderDiscountType.SERVICES)
    return str(explicit_override or "")
