from __future__ import annotations

import json
import uuid
from typing import Any

from django.http import QueryDict


def new_topic_key() -> str:
    return uuid.uuid4().hex[:12]


def extract_term_sections(post_data: QueryDict) -> list[dict[str, Any]]:
    order = [str(value).strip() for value in post_data.getlist("topic_order") if str(value).strip()]
    if not order:
        keys = [key[len("topic_title_") :] for key in post_data.keys() if str(key).startswith("topic_title_")]
        order = keys

    sections: list[dict[str, Any]] = []
    for key in order:
        title = str(post_data.get(f"topic_title_{key}") or "").strip()
        items = [str(item).strip() for item in post_data.getlist(f"topic_item_{key}") if str(item).strip()]
        if not title and not items:
            continue
        if not title:
            raise ValueError("Informe o título de todos os tópicos.")
        if not items:
            raise ValueError("Cada tópico precisa de pelo menos um texto.")
        sections.append({"key": key, "title": title, "items": items})
    return sections


def build_showtoast_trigger(toast_type: str, message: str) -> str:
    return json.dumps({"showToast": {"type": toast_type, "message": message}})
