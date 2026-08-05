from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from apps.finance.services.workorder_financial_movements import sync_workorder_financial_movement
from apps.workorder.approval import approve_workorder_with_stock
from apps.workorder.models import WorkOrder, WorkOrderStatus


logger = logging.getLogger(__name__)


def _find_first_string(payload: dict[str, Any], keys: tuple[str, ...]) -> str:
    queue: list[Any] = [payload]
    while queue:
        current = queue.pop(0)
        if isinstance(current, dict):
            for key, value in current.items():
                if key in keys and isinstance(value, str) and value.strip():
                    return value.strip()
                if isinstance(value, (dict, list)):
                    queue.append(value)
        elif isinstance(current, list):
            queue.extend(current)
    return ""


def _normalize_event_name(raw_event: str) -> str:
    normalized = raw_event.strip().upper().replace(".", "_").replace("-", "_")
    alias_map = {
        "ENVELOPE_COMPLETED": "ENVELOPE_COMPLETED",
        "DOCUMENT_COMPLETED": "ENVELOPE_COMPLETED",
        "ENVELOPE_COMPLETE": "ENVELOPE_COMPLETED",
        "DOCUMENT_DECLINED": "DOCUMENT_DECLINED",
        "DOCUMENT_DECLINE": "DOCUMENT_DECLINED",
        "ENVELOPE_DECLINED": "DOCUMENT_DECLINED",
    }
    return alias_map.get(normalized, normalized)


def extract_signature_event(payload: dict[str, Any]) -> str:
    raw_event = _find_first_string(payload, ("event", "eventType", "type", "name", "status"))
    if not raw_event:
        return ""
    return _normalize_event_name(raw_event)


def _payload_structure(payload: Any, depth: int = 0, max_depth: int = 3) -> str:
    if depth > max_depth:
        return "..."
    if isinstance(payload, dict):
        parts = []
        for key, value in payload.items():
            child = _payload_structure(value, depth + 1, max_depth)
            parts.append(f"{key}: {child}")
        return "{" + ", ".join(parts) + "}"
    if isinstance(payload, list):
        if not payload:
            return "[]"
        return "[" + _payload_structure(payload[0], depth + 1, max_depth) + (", ...]" if len(payload) > 1 else "]")
    return f"{type(payload).__name__}({len(str(payload))})"


def extract_signature_envelope_id(payload: dict[str, Any]) -> str:
    direct = _find_first_string(payload, ("envelopeId", "envelope_id", "envelopeID"))
    if direct:
        return direct

    queue: list[Any] = [payload]
    while queue:
        current = queue.pop(0)
        if isinstance(current, dict):
            envelope_obj = current.get("envelope")
            if isinstance(envelope_obj, dict):
                envelope_id = envelope_obj.get("id")
                if isinstance(envelope_id, str) and envelope_id.strip():
                    return envelope_id.strip()
            for value in current.values():
                if isinstance(value, (dict, list)):
                    queue.append(value)
        elif isinstance(current, list):
            queue.extend(current)
    return ""


def build_synplaisign_webhook_signature(*, body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def validate_signature_webhook_hmac(*, body: bytes, secret: str, received_signature: str) -> bool:
    expected = build_synplaisign_webhook_signature(body=body, secret=secret)
    return hmac.compare_digest(expected, received_signature)


def validate_signature_webhook_request(request: HttpRequest, *, workshop_secret: str = "") -> HttpResponse | None:
    """Validate HMAC using workshop secret, with optional global fallback."""
    expected_secret = str(workshop_secret or "").strip()
    if not expected_secret:
        expected_secret = str(getattr(settings, "SYNPLAISIGN_WEBHOOK_SECRET", "") or "").strip()
    if not expected_secret:
        return None

    received = str(request.headers.get("x-synplai-signature") or "").strip()
    if not received:
        logger.warning("signature_webhook_missing_hmac", extra={"ip": request.META.get("REMOTE_ADDR")})
        return JsonResponse({"error": "invalid_signature"}, status=403)

    if not validate_signature_webhook_hmac(body=request.body or b"", secret=expected_secret, received_signature=received):
        logger.warning("signature_webhook_hmac_failed", extra={"ip": request.META.get("REMOTE_ADDR")})
        return JsonResponse({"error": "invalid_signature"}, status=403)

    return None


def parse_signature_webhook_body(request: HttpRequest) -> dict[str, Any]:
    payload = json.loads(request.body or b"{}")
    return payload if isinstance(payload, dict) else {}


def _resolve_workshop_for_envelope(envelope_id: str):
    from apps.budget.models import Budget

    budget = Budget.objects.select_related("workshop").filter(signature_external_id=envelope_id).first()
    if budget is not None:
        return budget.workshop, budget, None

    workorder = WorkOrder.objects.select_related("workshop").filter(signature_external_id=envelope_id).first()
    if workorder is not None:
        return workorder.workshop, None, workorder
    return None, None, None


def _reject_budget_from_decline(*, budget, envelope_id: str) -> None:
    from apps.budget.models import BudgetStatus

    if budget.status == BudgetStatus.REJECTED:
        logger.info(
            "signature_webhook_budget_already_rejected",
            extra={"budget_id": budget.pk, "envelope_id": envelope_id},
        )
        return

    has_active_workorder = budget.workorders.exclude(status=WorkOrderStatus.CANCELLED).exists()
    if has_active_workorder:
        logger.info(
            "signature_webhook_budget_decline_skipped_active_workorder",
            extra={"budget_id": budget.pk, "envelope_id": envelope_id},
        )
        return

    if budget.is_status_locked:
        logger.info(
            "signature_webhook_budget_decline_skipped_locked",
            extra={"budget_id": budget.pk, "envelope_id": envelope_id, "status": budget.status},
        )
        return

    budget.status = BudgetStatus.REJECTED
    budget.save(update_fields=["status"])
    logger.info("signature_webhook_budget_rejected", extra={"budget_id": budget.pk, "envelope_id": envelope_id})


def _reject_workorder_from_decline(*, workorder, envelope_id: str) -> None:
    if workorder.status == WorkOrderStatus.REJECTED:
        logger.info(
            "signature_webhook_workorder_already_rejected",
            extra={"workorder_id": workorder.pk, "envelope_id": envelope_id},
        )
        return

    if workorder.is_status_locked:
        logger.info(
            "signature_webhook_workorder_decline_skipped_locked",
            extra={"workorder_id": workorder.pk, "envelope_id": envelope_id, "status": workorder.status},
        )
        return

    workorder.reject(reason="Documento recusado pelo signatário")
    logger.info("signature_webhook_workorder_rejected", extra={"workorder_id": workorder.pk, "envelope_id": envelope_id})


def process_signature_webhook_payload(*, payload: dict[str, Any], budget=None, workorder=None) -> HttpResponse:
    from apps.budget.models import Budget, SignatureStatus
    from apps.workorder.models import WorkOrderSignatureStatus

    event_name = extract_signature_event(payload)
    envelope_id = extract_signature_envelope_id(payload)
    logger.info(
        "signature_webhook_parsed",
        extra={"event": event_name, "envelope_id": envelope_id, "payload_structure": _payload_structure(payload)},
    )

    if not envelope_id:
        logger.warning("signature_webhook_missing_envelope_id", extra={"event": event_name, "payload_keys": list(payload.keys())})
        return HttpResponse(status=200)

    if budget is None and workorder is None:
        budget = Budget.objects.filter(signature_external_id=envelope_id).first()
        workorder = WorkOrder.objects.filter(signature_external_id=envelope_id).first()

    if budget is None and workorder is None:
        recent_budget = Budget.objects.filter(signature_request_status=SignatureStatus.SENT).order_by("-signature_sent_at").values(
            "id", "signature_external_id", "signature_document_id", "signature_sent_at"
        )[:3]
        recent_workorder = WorkOrder.objects.filter(signature_request_status=WorkOrderSignatureStatus.SENT).order_by("-signature_sent_at").values(
            "id", "signature_external_id", "signature_document_id", "signature_sent_at"
        )[:3]
        logger.info(
            "signature_webhook_no_matching_document",
            extra={
                "event": event_name,
                "envelope_id": envelope_id,
                "recent_sent_budgets": list(recent_budget),
                "recent_sent_workorders": list(recent_workorder),
            },
        )
        return HttpResponse(status=200)

    if event_name == "DOCUMENT_DECLINED":
        try:
            if budget is not None:
                _reject_budget_from_decline(budget=budget, envelope_id=envelope_id)
            if workorder is not None:
                _reject_workorder_from_decline(workorder=workorder, envelope_id=envelope_id)
        except Exception:
            logger.exception(
                "signature_webhook_decline_processing_failed",
                extra={
                    "budget_id": budget.pk if budget is not None else None,
                    "workorder_id": workorder.pk if workorder is not None else None,
                    "envelope_id": envelope_id,
                },
            )
            return HttpResponse(status=500)
        return HttpResponse(status=200)

    if event_name != "ENVELOPE_COMPLETED":
        logger.info(
            "signature_webhook_event_ignored",
            extra={
                "event": event_name,
                "budget_id": budget.pk if budget is not None else None,
                "workorder_id": workorder.pk if workorder is not None else None,
            },
        )
        return HttpResponse(status=200)

    try:
        if budget is not None:
            if not budget.approve():
                budget.mark_signature_approved()
                logger.info("signature_webhook_budget_already_approved", extra={"budget_id": budget.pk, "envelope_id": envelope_id})
            else:
                logger.info("signature_webhook_budget_approved", extra={"budget_id": budget.pk, "envelope_id": envelope_id})

        if workorder is not None:
            can_finalize_workorder = workorder.is_fully_paid or workorder.budget_type in ("warranty", "courtesy")
            has_warranty_plan = bool(workorder.warranty_plan)
            if (can_finalize_workorder and has_warranty_plan) or workorder.status == WorkOrderStatus.APPROVED:
                approve_workorder_with_stock(workorder=workorder, signature_approved=True)
                sync_workorder_financial_movement(workorder=workorder)
                from apps.messaging.application.services.satisfaction_survey import schedule_satisfaction_survey_for_workorder

                workorder.refresh_from_db()
                schedule_satisfaction_survey_for_workorder(workorder)
                logger.info("signature_webhook_workorder_approved", extra={"workorder_id": workorder.pk, "envelope_id": envelope_id})
            else:
                workorder.mark_signature_approved()
                logger.info(
                    "signature_webhook_workorder_signature_approved_pending_completion",
                    extra={
                        "workorder_id": workorder.pk,
                        "envelope_id": envelope_id,
                        "missing_warranty_plan": not has_warranty_plan,
                    },
                )
    except Exception:
        logger.exception(
            "signature_webhook_processing_failed",
            extra={
                "budget_id": budget.pk if budget is not None else None,
                "workorder_id": workorder.pk if workorder is not None else None,
                "envelope_id": envelope_id,
            },
        )
        return HttpResponse(status=500)

    return HttpResponse(status=200)


@method_decorator(csrf_exempt, name="dispatch")
class SignatureWebhookView(View):
    def get(self, request: HttpRequest) -> JsonResponse:
        logger.info("signature_webhook_ping")
        return JsonResponse({"ok": True, "message": "webhook online"}, status=200)

    def post(self, request: HttpRequest) -> HttpResponse:
        from apps.workshops.services.synplaisign import get_workshop_synplaisign_webhook_secret

        logger.info("signature_webhook_received", extra={"content_type": request.content_type})

        try:
            payload = parse_signature_webhook_body(request)
        except json.JSONDecodeError:
            logger.warning("signature_webhook_invalid_json")
            return JsonResponse({"error": "invalid_json"}, status=400)

        envelope_id = extract_signature_envelope_id(payload)
        workshop, budget, workorder = (None, None, None)
        if envelope_id:
            workshop, budget, workorder = _resolve_workshop_for_envelope(envelope_id)

        workshop_secret = ""
        if workshop is not None:
            workshop_secret = get_workshop_synplaisign_webhook_secret(workshop)

        validation_response = validate_signature_webhook_request(request, workshop_secret=workshop_secret)
        if validation_response is not None:
            return validation_response

        return process_signature_webhook_payload(payload=payload, budget=budget, workorder=workorder)


# Backward-compatible aliases during SuperSign → SynplaiSign cutover.
SuperSignWebhookView = SignatureWebhookView
extract_supersign_event = extract_signature_event
extract_supersign_envelope_id = extract_signature_envelope_id
validate_supersign_webhook_request = validate_signature_webhook_request
parse_supersign_webhook_body = parse_signature_webhook_body
process_supersign_webhook_payload = process_signature_webhook_payload
