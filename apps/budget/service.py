import os

from django.core import signing
from django.urls import reverse
from django.conf import settings


def build_signature_payload(budget) -> dict:
    return {
        "budget_id": budget.id,
        "version": budget.signature_token_version,
    }

def build_signature_file_url(*, budget, request=None) -> str:
    payload = build_signature_payload(budget)
    token = signing.dumps(payload, salt="budget-signature-file")
    path = reverse("budget:signature-file", args=[token])

    if request is not None:
        return request.build_absolute_uri(path)

    base_url = getattr(settings, "APP_BASE_URL", "").rstrip("/") or os.getenv("APP_BASE_URL", "")
    if not base_url:
        base_url = "http://localhost:8000"

    return f"{base_url}{path}"