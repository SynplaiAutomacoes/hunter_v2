"""HTMX views for resolving duplicate services when adding kits/services."""

from __future__ import annotations

import json
import logging
from typing import cast

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import render
from django.views import View

from apps.budget.models import Budget
from apps.budget.services.duplicate_service_resolution import (
    apply_duplicate_service_resolution,
    filter_conflicts_touching_items,
    find_duplicate_service_conflicts,
    get_conflict_for_service,
    rollback_added_budget_items,
)
from apps.workshops.mixin import WorkshopScopedMixin

from .shared import (
    _build_concurrent_budget_lock_response,
    _build_locked_budget_response,
    _check_concurrent_budget_lock,
    _get_budget_for_workshop,
    _get_current_step_from_referer,
    _is_budget_edit_locked,
    _step_redirect_response,
    reset_steps_after_step_4,
    sync_linked_workorder_from_budget,
)

logger = logging.getLogger(__name__)


def _redirect_to_step4(request, budget: Budget) -> HttpResponse:
    return cast(HttpResponse, _step_redirect_response(request, budget, fallback_step=4))


def _parse_id_list(raw_value: str | list[str] | None) -> list[int]:
    if raw_value is None:
        return []
    if isinstance(raw_value, list):
        parts: list[str] = []
        for entry in raw_value:
            parts.extend(str(entry).split(","))
    else:
        parts = str(raw_value).split(",")
    result: list[int] = []
    for part in parts:
        value = part.strip()
        if not value:
            continue
        try:
            result.append(int(value))
        except ValueError:
            continue
    return list(dict.fromkeys(result))


def render_duplicate_service_queue(
    request,
    *,
    budget: Budget,
    service_ids: list[int],
    rollback_item_ids: list[int],
    current_index: int = 0,
    close_parent: bool = False,
    htmx_target: str = "#modal-container",
    error_message: str | None = None,
) -> HttpResponse:
    if not service_ids:
        return _redirect_to_step4(request, budget)

    index = max(0, min(int(current_index), len(service_ids) - 1))
    service_id = service_ids[index]
    conflict = get_conflict_for_service(budget, service_id=service_id)
    if conflict is None:
        remaining = [sid for sid in service_ids if sid != service_id]
        if not remaining:
            return _redirect_to_step4(request, budget)
        return render_duplicate_service_queue(
            request,
            budget=budget,
            service_ids=remaining,
            rollback_item_ids=rollback_item_ids,
            current_index=0,
            close_parent=close_parent,
            htmx_target=htmx_target,
            error_message=error_message,
        )

    current_step = _get_current_step_from_referer(request, budget.current_step)
    context = {
        "budget": budget,
        "conflict": conflict,
        "service_ids": service_ids,
        "rollback_item_ids": rollback_item_ids,
        "current_index": index,
        "total_items": len(service_ids),
        "remaining_after_current": max(len(service_ids) - index - 1, 0),
        "current_step": current_step,
        "htmx_target": htmx_target,
        "error_message": error_message,
    }
    response = render(request, "budget/partials/modals/modal_duplicate_service_queue.html", context)
    if close_parent:
        response["HX-Trigger-After-Swap"] = json.dumps({"closeParentBudgetModal": True})
    return cast(HttpResponse, response)


def maybe_render_duplicate_service_queue_after_add(
    request,
    *,
    budget: Budget,
    created_item_ids: list[int],
    close_parent: bool = False,
) -> HttpResponse | None:
    if not created_item_ids:
        return None
    conflicts = filter_conflicts_touching_items(
        find_duplicate_service_conflicts(budget),
        item_ids=created_item_ids,
    )
    if not conflicts:
        return None
    htmx_target = "#child-modal-container" if close_parent else "#modal-container"
    return render_duplicate_service_queue(
        request,
        budget=budget,
        service_ids=[conflict.service_id for conflict in conflicts],
        rollback_item_ids=created_item_ids,
        current_index=0,
        close_parent=close_parent,
        htmx_target=htmx_target,
    )


class ResolveDuplicateServiceStepView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Budget
    workshop_permission_codename = "add_budget"

    def post(self, request, budget_id):
        budget = _get_budget_for_workshop(self.workshop, budget_id)
        if not _check_concurrent_budget_lock(request, budget):
            return _build_concurrent_budget_lock_response(request, budget)
        if _is_budget_edit_locked(budget):
            return _build_locked_budget_response(request, budget, fallback_step=4)

        service_ids = _parse_id_list(request.POST.get("service_ids"))
        rollback_item_ids = _parse_id_list(request.POST.get("rollback_item_ids"))
        try:
            current_index = int(request.POST.get("current_index") or 0)
        except (TypeError, ValueError):
            current_index = 0

        try:
            service_id = int(request.POST.get("service_id") or 0)
        except (TypeError, ValueError):
            service_id = 0

        keep_source_key = str(request.POST.get("keep_source_key") or "").strip()
        htmx_target = str(request.POST.get("htmx_target") or "#modal-container").strip() or "#modal-container"
        kit_loser_actions: dict[str, str] = {}
        for key, value in request.POST.items():
            if key.startswith("kit_action_"):
                source_key = key.removeprefix("kit_action_")
                kit_loser_actions[source_key] = str(value)

        if not service_id or not keep_source_key:
            return render_duplicate_service_queue(
                request,
                budget=budget,
                service_ids=service_ids,
                rollback_item_ids=rollback_item_ids,
                current_index=current_index,
                htmx_target=htmx_target,
                error_message="Selecione qual ocorrência do serviço deve ser mantida.",
            )

        try:
            apply_duplicate_service_resolution(
                budget=budget,
                service_id=service_id,
                keep_source_key=keep_source_key,
                kit_loser_actions=kit_loser_actions,
            )
        except ValueError as exc:
            return render_duplicate_service_queue(
                request,
                budget=budget,
                service_ids=service_ids,
                rollback_item_ids=rollback_item_ids,
                current_index=current_index,
                htmx_target=htmx_target,
                error_message=str(exc),
            )

        reset_steps_after_step_4(budget)
        sync_linked_workorder_from_budget(budget)

        remaining = [sid for sid in service_ids if sid != service_id]
        # Re-scan in case earlier resolution cleared later conflicts.
        still_conflicting = {
            conflict.service_id
            for conflict in filter_conflicts_touching_items(
                find_duplicate_service_conflicts(budget),
                item_ids=rollback_item_ids,
            )
        }
        remaining = [sid for sid in remaining if sid in still_conflicting]

        if not remaining:
            return _redirect_to_step4(request, budget)

        return render_duplicate_service_queue(
            request,
            budget=budget,
            service_ids=remaining,
            rollback_item_ids=rollback_item_ids,
            current_index=0,
            htmx_target=htmx_target,
        )


class CancelDuplicateServiceQueueView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Budget
    workshop_permission_codename = "add_budget"

    def post(self, request, budget_id):
        budget = _get_budget_for_workshop(self.workshop, budget_id)
        if not _check_concurrent_budget_lock(request, budget):
            return _build_concurrent_budget_lock_response(request, budget)
        if _is_budget_edit_locked(budget):
            return _build_locked_budget_response(request, budget, fallback_step=4)

        rollback_item_ids = _parse_id_list(request.POST.get("rollback_item_ids"))
        try:
            rollback_added_budget_items(budget=budget, item_ids=rollback_item_ids)
        except Exception:
            logger.exception(
                "budget_duplicate_service_rollback_failed",
                extra={"budget_id": budget_id, "rollback_item_ids": rollback_item_ids[:20]},
            )
        reset_steps_after_step_4(budget)
        sync_linked_workorder_from_budget(budget)
        return _redirect_to_step4(request, budget)
