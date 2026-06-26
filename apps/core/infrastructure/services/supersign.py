from __future__ import annotations

import json
import logging
from typing import Any

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from apps.finance.services.workorder_financial_movements import sync_workorder_financial_movement
from apps.workorder.models import WorkOrder


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
    }
    return alias_map.get(normalized, normalized)


def extract_supersign_event(payload: dict[str, Any]) -> str:
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
    elif isinstance(payload, list):
        if not payload:
            return "[]"
        return "[" + _payload_structure(payload[0], depth + 1, max_depth) + (", ...]" if len(payload) > 1 else "]")
    else:
        return f"{type(payload).__name__}({len(str(payload))})"


def extract_supersign_envelope_id(payload: dict[str, Any]) -> str:
    direct = _find_first_string(payload, ("envelopeId", "envelope_id", "envelopeID"))
    if direct:
        logger.debug("supersign_extract_envelope_id_direct", extra={"envelope_id": direct, "found_at_key": "envelopeId/envelope_id/envelopeID"})
        return direct

    queue: list[Any] = [payload]
    while queue:
        current = queue.pop(0)
        if isinstance(current, dict):
            envelope_obj = current.get("envelope")
            if isinstance(envelope_obj, dict):
                envelope_id = envelope_obj.get("id")
                if isinstance(envelope_id, str) and envelope_id.strip():
                    logger.debug("supersign_extract_envelope_id_nested", extra={"envelope_id": envelope_id.strip()})
                    return envelope_id.strip()
            for value in current.values():
                if isinstance(value, (dict, list)):
                    queue.append(value)
        elif isinstance(current, list):
            queue.extend(current)

    logger.warning("supersign_extract_envelope_id_failed", extra={"payload_structure": _payload_structure(payload)})
    return ""


def validate_supersign_webhook_request(request: HttpRequest) -> HttpResponse | None:
    auth_header = request.headers.get("Authorization", "")
    expected_api_key = getattr(settings, "SUPERSIGN_API_KEY", "")
    expected_auth = f"Bearer {expected_api_key}" if expected_api_key else ""

    if expected_auth and auth_header and auth_header != expected_auth:
        logger.warning("supersign_webhook_auth_failed", extra={"ip": request.META.get("REMOTE_ADDR")})
        return JsonResponse({"error": "invalid_authorization"}, status=403)

    account_id = request.headers.get("x-account-id", "")
    expected_account_id = getattr(settings, "SUPERSIGN_ACCOUNT_ID", "")
    if expected_account_id and account_id and account_id != expected_account_id:
        logger.warning("supersign_webhook_account_mismatch", extra={"received_account_id": account_id, "expected_account_id": expected_account_id})
        return JsonResponse({"error": "invalid_account"}, status=403)

    return None


def parse_supersign_webhook_body(request: HttpRequest) -> dict[str, Any]:
    payload = json.loads(request.body or b"{}")
    return payload if isinstance(payload, dict) else {}


def process_supersign_webhook_payload(*, payload: dict[str, Any]) -> HttpResponse:
    from apps.budget.models import Budget, SignatureStatus
    from apps.workorder.models import WorkOrderSignatureStatus

    event_name = extract_supersign_event(payload)
    envelope_id = extract_supersign_envelope_id(payload)
    logger.info("supersign_webhook_parsed", extra={"event": event_name, "envelope_id": envelope_id, "payload_structure": _payload_structure(payload)})

    if not envelope_id:
        logger.warning("supersign_webhook_missing_envelope_id", extra={"event": event_name, "payload_keys": list(payload.keys())})
        return HttpResponse(status=200)

    budget = Budget.objects.filter(signature_external_id=envelope_id).first()
    workorder = WorkOrder.objects.filter(signature_external_id=envelope_id).first()
    if budget is None and workorder is None:
        budget_by_doc = Budget.objects.filter(signature_document_id=envelope_id).first()
        workorder_by_doc = WorkOrder.objects.filter(signature_document_id=envelope_id).first()
        recent_budget = Budget.objects.filter(signature_request_status=SignatureStatus.SENT).order_by("-signature_sent_at").values("id", "signature_external_id", "signature_document_id", "signature_sent_at")[:3]
        recent_workorder = WorkOrder.objects.filter(signature_request_status=WorkOrderSignatureStatus.SENT).order_by("-signature_sent_at").values("id", "signature_external_id", "signature_document_id", "signature_sent_at")[:3]
        logger.info(
            "supersign_webhook_no_matching_document",
            extra={
                "event": event_name,
                "envelope_id": envelope_id,
                "payload_structure": _payload_structure(payload),
                "matched_by_document_id": bool(budget_by_doc or workorder_by_doc),
                "recent_sent_budgets": list(recent_budget),
                "recent_sent_workorders": list(recent_workorder),
            },
        )
        return HttpResponse(status=200)

    if event_name != "ENVELOPE_COMPLETED":
        logger.info("supersign_webhook_event_ignored", extra={"event": event_name, "budget_id": budget.pk if budget is not None else None, "workorder_id": workorder.pk if workorder is not None else None})
        return HttpResponse(status=200)

    try:
        if budget is not None:
            if not budget.approve():
                budget.mark_signature_approved()
                logger.info("supersign_webhook_budget_already_approved", extra={"budget_id": budget.pk, "envelope_id": envelope_id})
            else:
                logger.info("supersign_webhook_budget_approved", extra={"budget_id": budget.pk, "envelope_id": envelope_id})

        if workorder is not None:
            workorder.mark_signature_approved()
            sync_workorder_financial_movement(workorder=workorder)
            logger.info("supersign_webhook_workorder_approved", extra={"workorder_id": workorder.pk, "envelope_id": envelope_id})
    except Exception:
        logger.exception("supersign_webhook_processing_failed", extra={"budget_id": budget.pk if budget is not None else None, "workorder_id": workorder.pk if workorder is not None else None, "envelope_id": envelope_id})
        return HttpResponse(status=500)

    return HttpResponse(status=200)


@method_decorator(csrf_exempt, name="dispatch")
class SuperSignWebhookView(View):
    def get(self, request: HttpRequest) -> JsonResponse:
        logger.info("supersign_webhook_ping")
        return JsonResponse({"ok": True, "message": "webhook online"}, status=200)

    def post(self, request: HttpRequest) -> HttpResponse:
        logger.info("supersign_webhook_received", extra={"content_type": request.content_type})

        validation_response = validate_supersign_webhook_request(request)
        if validation_response is not None:
            return validation_response

        try:
            payload = parse_supersign_webhook_body(request)
        except json.JSONDecodeError:
            logger.warning("supersign_webhook_invalid_json")
            return JsonResponse({"error": "invalid_json"}, status=400)

        return process_supersign_webhook_payload(payload=payload)
