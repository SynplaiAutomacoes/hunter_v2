from __future__ import annotations

from typing import Any

from django.http import HttpRequest

from apps.finance.models.financial_movement import FinancialMovement
from apps.workshops.models.workshops import Workshop
from apps.workshops.util.workshops import can_view_payroll_details


PAYROLL_REDACTED_LABEL = "Salario do Colaborador"


def viewer_can_view_payroll_details(*, user: Any, workshop: Workshop, request: HttpRequest | None = None) -> bool:
    return can_view_payroll_details(user=user, workshop=workshop, request=request)


def resolve_payroll_movement_display(*, movement: FinancialMovement, user: Any, workshop: Workshop, request: HttpRequest | None = None) -> tuple[str, str]:
    agent = movement.report_agent_display
    description = movement.report_description_display

    if movement.payroll_id is None:
        return agent, description

    if viewer_can_view_payroll_details(user=user, workshop=workshop, request=request):
        return agent, description

    return PAYROLL_REDACTED_LABEL, _build_redacted_payroll_description(movement=movement)


def apply_payroll_visibility_to_dre_rows(*, rows: list[dict[str, Any]], user: Any, workshop: Workshop, request: HttpRequest | None = None) -> list[dict[str, Any]]:
    if viewer_can_view_payroll_details(user=user, workshop=workshop, request=request):
        return rows

    for row in rows:
        _sanitize_dre_details(details=row.get("details", []))
    return rows


def _sanitize_dre_details(*, details: list[dict[str, Any]]) -> None:
    for detail in details:
        nested_detail = detail.get("detail")
        if isinstance(nested_detail, dict):
            _sanitize_dre_detail(detail=nested_detail)
        else:
            _sanitize_dre_detail(detail=detail)

        children = detail.get("children")
        if isinstance(children, list):
            _sanitize_dre_details(details=children)


def _sanitize_dre_detail(*, detail: dict[str, Any]) -> None:
    movement = detail.get("movement")
    if not isinstance(movement, FinancialMovement) or movement.payroll_id is None:
        return

    detail["summary"] = _build_redacted_payroll_description(movement=movement)


def _build_redacted_payroll_description(*, movement: FinancialMovement) -> str:
    payroll = getattr(movement, "payroll", None)
    if payroll is None:
        return PAYROLL_REDACTED_LABEL
    return f"{PAYROLL_REDACTED_LABEL} - {payroll.reference_month:02d}/{payroll.reference_year}"
