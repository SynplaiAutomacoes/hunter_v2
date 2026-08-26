from __future__ import annotations

from typing import Any

from django.http import HttpRequest
from django.urls import reverse

from apps.catalog.product_issues import normalize_ncm
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


def find_first_standalone_line_with_invalid_ncm(*, lines: list[dict[str, Any]]) -> dict[str, Any] | None:
    for line in lines:
        if len(normalize_ncm(line.get("ncm"))) != 8:
            return line
    return None


def build_standalone_invalid_ncm_modal_context(
    *,
    line: dict[str, Any],
    return_url: str = "",
    items_step_url: str = "",
) -> dict[str, str]:
    product_name = str(line.get("description") or "Produto").strip() or "Produto"
    product_id = line.get("product_id")
    if product_id:
        return {
            "title": "NCM Inválido",
            "subtitle": f"O produto {product_name} não tem um NCM válido. Para conformidade fiscal, preencha o campo do produto.",
            "action_label": "Editar produto",
            "action_url": append_query_params(
                url=reverse("catalog:product_update", kwargs={"pk": int(product_id)}),
                params={"next": return_url},
            ),
        }
    return {
        "title": "NCM Inválido",
        "subtitle": f"O item {product_name} não tem um NCM válido (8 dígitos). Remova o item e adicione novamente com NCM correto.",
        "action_label": "Voltar aos itens",
        "action_url": items_step_url or return_url,
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
