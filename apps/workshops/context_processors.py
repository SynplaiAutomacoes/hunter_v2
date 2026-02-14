from apps.workshops.models.workshops import Workshop


def active_workshops(request):
    cached_payload = getattr(request, "_active_workshops_payload", None)
    if cached_payload is not None:
        return cached_payload

    if not request.user.is_authenticated or not getattr(request.user, "account_id", None):
        payload = {
            "active_workshops": Workshop.objects.none(),
            "active_workshop_id": None,
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

    payload = {
        "active_workshops": workshops,
        "active_workshop_id": active_workshop_id,
    }
    setattr(request, "_active_workshops_payload", payload)
    return payload
