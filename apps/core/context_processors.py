from __future__ import annotations

from apps.workshops.models import Workshop


def active_workshops(request):
    return {
        "active_workshops": Workshop.objects.filter(is_active=True).order_by("name"),
    }
