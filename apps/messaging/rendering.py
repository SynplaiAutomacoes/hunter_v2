from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from django.utils import timezone

from apps.core.templatetags.format_tags import money_br, phone_br


TOKEN_PATTERN = re.compile(r"%%(?P<key>[a-z0-9_-]+)%%", re.IGNORECASE)
MISSING = object()


@dataclass(frozen=True)
class VariableContext:
    customer: Any = None
    vehicle: Any = None
    budget: Any = None
    workorder: Any = None
    workshop: Any = None
    appointment: Any = None
    extras: dict[str, Any] = field(default_factory=dict)


def resolve_variable_context(
    *,
    customer: Any = None,
    vehicle: Any = None,
    budget: Any = None,
    workorder: Any = None,
    workshop: Any = None,
    appointment: Any = None,
    extras: dict[str, Any] | None = None,
) -> VariableContext:
    resolved_workshop = workshop
    resolved_budget = budget or getattr(workorder, "budget", None)
    resolved_customer = customer or getattr(resolved_budget, "customer", None) or getattr(appointment, "customer", None)
    resolved_vehicle = vehicle or getattr(resolved_budget, "vehicle", None) or getattr(appointment, "vehicle", None)
    resolved_appointment = appointment

    if resolved_workshop is None:
        resolved_workshop = (
            getattr(workorder, "workshop", None)
            or getattr(resolved_budget, "workshop", None)
            or getattr(resolved_customer, "workshop", None)
            or getattr(resolved_vehicle, "workshop", None)
            or getattr(resolved_appointment, "workshop", None)
        )

    return VariableContext(
        customer=resolved_customer,
        vehicle=resolved_vehicle,
        budget=resolved_budget,
        workorder=workorder,
        workshop=resolved_workshop,
        appointment=resolved_appointment,
        extras=dict(extras or {}),
    )


def format_variable_value(value: Any) -> str:
    if value is None:
        return ""

    if isinstance(value, datetime):
        if timezone.is_aware(value):
            value = timezone.localtime(value)
        return value.strftime("%d/%m/%Y %H:%M")

    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")

    if hasattr(value, "amount"):
        return str(money_br(value))

    return str(value)


def format_phone_value(value: Any) -> str:
    return phone_br(value)


def render_message_template(
    template: str,
    *,
    customer: Any = None,
    vehicle: Any = None,
    budget: Any = None,
    workorder: Any = None,
    workshop: Any = None,
    appointment: Any = None,
    extras: dict[str, Any] | None = None,
) -> str:
    from apps.messaging.variables import get_variable_definition_map, resolve_variable

    context = resolve_variable_context(
        customer=customer,
        vehicle=vehicle,
        budget=budget,
        workorder=workorder,
        workshop=workshop,
        appointment=appointment,
        extras=extras,
    )
    variable_definitions = get_variable_definition_map()
    normalized_extras = {str(key).lower().replace("-", "_"): value for key, value in context.extras.items()}
    # Also keep hyphen keys as-is for exact match.
    for key, value in context.extras.items():
        normalized_extras[str(key).lower()] = value

    def replace(match: re.Match[str]) -> str:
        key = match.group("key").lower()
        underscore_key = key.replace("-", "_")

        if key in normalized_extras or underscore_key in normalized_extras:
            raw = normalized_extras.get(key, normalized_extras.get(underscore_key))
            if raw is MISSING:
                return match.group(0)
            return format_variable_value(raw)

        definition = variable_definitions.get(underscore_key) or variable_definitions.get(key)
        if definition is None:
            return match.group(0)

        resolved_value = resolve_variable(definition, context)
        if resolved_value is MISSING:
            return match.group(0)
        return str(resolved_value)

    return TOKEN_PATTERN.sub(replace, str(template or ""))
