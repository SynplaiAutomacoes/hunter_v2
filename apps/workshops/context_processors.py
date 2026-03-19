from apps.workshops.models.workshops import Workshop
from apps.workshops.util.workshops import is_workshop_director, is_workshop_manager


def active_workshops(request):
    cached_payload = getattr(request, "_active_workshops_payload", None)
    if cached_payload is not None:
        return cached_payload

    if not request.user.is_authenticated or not getattr(request.user, "account_id", None):
        payload = {
            "active_workshops": Workshop.objects.none(),
            "active_workshop_id": None,
            "active_workshop_is_director": False,
            "active_workshop_is_manager": False,
        }
        setattr(request, "_active_workshops_payload", payload)
        return payload

    workshops_qs = (
        Workshop.objects.filter(
            account_id=request.user.account_id,
            is_active=True,
            members__user=request.user,
            members__is_active=True,
        )
        .distinct()
        .order_by("name")
    )

    workshops = list(workshops_qs)
    workshop_ids = [workshop.pk for workshop in workshops]

    active_workshop_id = request.session.get("active_workshop_id")

    if active_workshop_id not in workshop_ids:
        active_workshop_id = workshop_ids[0] if workshop_ids else None
        if active_workshop_id is None:
            request.session.pop("active_workshop_id", None)
        else:
            request.session["active_workshop_id"] = active_workshop_id

    active_workshop_is_director = False
    active_workshop_is_manager = False
    if active_workshop_id is not None:
        active_workshop = next((workshop for workshop in workshops if workshop.pk == active_workshop_id), None)
        if active_workshop is not None:
            active_workshop_is_director = is_workshop_director(user=request.user, workshop=active_workshop, request=request)
            if not active_workshop_is_director:
                active_workshop_is_manager = is_workshop_manager(user=request.user, workshop=active_workshop, request=request)

    payload = {
        "active_workshops": workshops,
        "active_workshop_id": active_workshop_id,
        "active_workshop_is_director": active_workshop_is_director,
        "active_workshop_is_manager": active_workshop_is_manager,
    }
    setattr(request, "_active_workshops_payload", payload)
    return payload
