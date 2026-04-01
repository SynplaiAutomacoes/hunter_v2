from __future__ import annotations

from typing import Any

from django.http import HttpRequest
from django.urls import reverse

from apps.finance.views.navigation import append_query_params
from apps.workorder.models import WorkOrder


NFE_INVALID_NCM_MODAL_ERROR = "__nfe_invalid_ncm_modal__"
NFE_INVALID_NCM_MODAL_SESSION_KEY = "finance.nfe_invalid_ncm_modal"


def build_invalid_ncm_modal_context(*, workorder: WorkOrder, return_url: str = "") -> dict[str, str] | None:
    invalid_issue = next(iter(workorder.product_issue_summary.invalid_ncm_issues), None)
    if invalid_issue is None:
        return None

    product_name = str(invalid_issue.description or "Produto").strip() or "Produto"
    return {
        "title": "NCM Inválido",
        "subtitle": f"O produto {product_name} não tem um NCM válido. Para conformidade fiscal, preencha o campo do produto.",
        "action_label": "Editar produto",
        "action_url": append_query_params(
            url=reverse("catalog:product_update", kwargs={"pk": invalid_issue.product_id}),
            params={"next": return_url},
        ),
    }


def store_invalid_ncm_modal_context(*, request: HttpRequest, modal_context: dict[str, Any]) -> None:
    request.session[NFE_INVALID_NCM_MODAL_SESSION_KEY] = modal_context
    request.session.modified = True


def pop_invalid_ncm_modal_context(*, request: HttpRequest) -> dict[str, Any] | None:
    modal_context = request.session.pop(NFE_INVALID_NCM_MODAL_SESSION_KEY, None)
    request.session.modified = True
    if isinstance(modal_context, dict):
        return modal_context
    return None
