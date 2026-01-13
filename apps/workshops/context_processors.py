from apps.workshops.models.workshops import Workshop


def active_workshops(request):
    if not request.user.is_authenticated or not getattr(request.user, "account_id", None):
        return {
            "active_workshops": Workshop.objects.none(),
            "active_workshop_id": None,
        }

    workshops = (
        Workshop.objects.filter(
            account=request.user.account,
            is_active=True,
            members__user=request.user,
            members__is_active=True,
        )
        .distinct()
        .order_by("name")
    )

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
