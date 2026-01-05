from __future__ import annotations

from apps.workshops.models import Workshop


def active_workshops(request):
    workshops = Workshop.objects.filter(is_active=True).order_by("name")
    workshop_ids = workshops.values_list("pk", flat=True)

    active_workshop_id = request.session.get("active_workshop_id")

    if active_workshop_id not in workshop_ids:
        active_workshop_id = workshop_ids[0] if workshop_ids else None
        if active_workshop_id is None:
            request.session.pop("active_workshop_id", None)
        else:
            request.session["active_workshop_id"] = active_workshop_id

    return {
        "active_workshops": workshops,
        "active_workshop_id": active_workshop_id,
    }
