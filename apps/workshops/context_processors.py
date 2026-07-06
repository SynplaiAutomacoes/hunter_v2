from django.http import Http404

from apps.workshops.models.workshops import Workshop
from apps.workshops.util.workshops import DIRECTOR_ROLE_PATTERN, MANAGER_ROLE_PATTERN, get_cached_workshop_member, get_active_workshop_or_404, role_name_matches


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

    try:
        active_workshop = get_active_workshop_or_404(request)
    except Http404:
        active_workshop = None

    memberships = getattr(request, "_workshop_memberships_cache", None)
    if memberships is None:
        active_workshop = None
        workshops: list[Workshop] = []
    else:
        workshops = [membership.workshop for membership in memberships]

    workshop_ids = [workshop.pk for workshop in workshops]

    active_workshop_id = getattr(active_workshop, "pk", None)

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
        active_member = get_cached_workshop_member(request=request, workshop=active_workshop) if active_workshop is not None else None
        active_role_name = getattr(getattr(active_member, "role", None), "name", None)
        active_workshop_is_director = role_name_matches(role_name=active_role_name, pattern=DIRECTOR_ROLE_PATTERN)
        if not active_workshop_is_director:
            active_workshop_is_manager = role_name_matches(role_name=active_role_name, pattern=MANAGER_ROLE_PATTERN)

    payload = {
        "active_workshops": workshops,
        "active_workshop_id": active_workshop_id,
        "active_workshop_is_director": active_workshop_is_director,
        "active_workshop_is_manager": active_workshop_is_manager,
    }
    setattr(request, "_active_workshops_payload", payload)
    return payload
