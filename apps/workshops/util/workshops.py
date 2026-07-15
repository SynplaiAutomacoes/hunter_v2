from __future__ import annotations

import re

from django.contrib.auth import get_user_model
from django.http import Http404

from apps.collaborators.models import WorkshopMember
from apps.workshops.models.workshops import Workshop

User = get_user_model()

DIRECTOR_ROLE_PATTERN = re.compile(r"^\s*diretor\s*$", re.IGNORECASE)
MANAGER_ROLE_PATTERN = re.compile(r"^\s*gerente\s*$", re.IGNORECASE)


def _get_cached_workshop_memberships(*, request, account_id: int) -> list[WorkshopMember]:
    cached_memberships = getattr(request, "_workshop_memberships_cache", None)
    if cached_memberships is not None:
        return cached_memberships

    memberships = list(
        WorkshopMember.objects.filter(
            user=request.user,
            is_active=True,
            workshop__account_id=account_id,
            workshop__is_active=True,
        )
        .select_related("workshop", "role")
        .order_by("workshop__name", "workshop__pk")
    )
    setattr(request, "_workshop_memberships_cache", memberships)
    setattr(request, "_workshop_member_by_workshop_id", {membership.workshop_id: membership for membership in memberships})
    return memberships


def get_cached_workshop_member(*, request, workshop: Workshop) -> WorkshopMember | None:
    member_by_workshop_id = getattr(request, "_workshop_member_by_workshop_id", None)
    if member_by_workshop_id is not None:
        return member_by_workshop_id.get(getattr(workshop, "pk", None))

    account_id = getattr(request.user, "account_id", None)
    if not account_id:
        return None

    _get_cached_workshop_memberships(request=request, account_id=account_id)
    member_by_workshop_id = getattr(request, "_workshop_member_by_workshop_id", None)
    if member_by_workshop_id is None:
        return None
    return member_by_workshop_id.get(getattr(workshop, "pk", None))


def role_name_matches(*, role_name: str | None, pattern: re.Pattern[str]) -> bool:
    if not role_name:
        return False
    return bool(pattern.match(role_name))


def get_active_workshop_or_404(request) -> Workshop:
    cached_workshop = getattr(request, "_active_workshop_obj", None)
    if cached_workshop is not None:
        return cached_workshop

    account_id = getattr(request.user, "account_id", None)
    if not account_id:
        raise Http404

    memberships = _get_cached_workshop_memberships(request=request, account_id=account_id)
    workshop_by_id = {membership.workshop_id: membership.workshop for membership in memberships}

    workshop_id = request.session.get("active_workshop_id")
    workshop = workshop_by_id.get(workshop_id)
    if workshop is None and memberships:
        workshop = memberships[0].workshop

    if workshop is None:
        request.session.pop("active_workshop_id", None)
        raise Http404

    # Only dirty the session when the active workshop actually changes.
    if request.session.get("active_workshop_id") != workshop.pk:
        request.session["active_workshop_id"] = workshop.pk
    setattr(request, "_active_workshop_obj", workshop)
    return workshop


def is_workshop_director(*, user: User, workshop: Workshop, request=None) -> bool:
    if getattr(workshop, "account_id", None) != getattr(user, "account_id", None):
        return False

    workshop_id = getattr(workshop, "id", None)
    cache_key = ("director", workshop_id)
    cache: dict[tuple[object, ...], bool] | None = None
    if request is not None:
        cache = getattr(request, "_workshop_role_cache", None)
        if cache is None:
            cache = {}
            setattr(request, "_workshop_role_cache", cache)
        elif cache_key in cache:
            return cache[cache_key]

        membership = get_cached_workshop_member(request=request, workshop=workshop)
        if membership is not None:
            is_director = role_name_matches(role_name=getattr(getattr(membership, "role", None), "name", None), pattern=DIRECTOR_ROLE_PATTERN)
            cache[cache_key] = is_director
            return is_director

    is_director = WorkshopMember.objects.filter(
        user=user,
        workshop=workshop,
        is_active=True,
        role__name__iregex=DIRECTOR_ROLE_PATTERN.pattern,
    ).exists()

    if request is not None and cache is not None:
        cache[cache_key] = is_director

    return is_director


def is_workshop_manager(*, user: User, workshop: Workshop, request=None) -> bool:
    if getattr(workshop, "account_id", None) != getattr(user, "account_id", None):
        return False

    workshop_id = getattr(workshop, "id", None)
    cache_key = ("manager", workshop_id)
    cache: dict[tuple[object, ...], bool] | None = None
    if request is not None:
        cache = getattr(request, "_workshop_role_cache", None)
        if cache is None:
            cache = {}
            setattr(request, "_workshop_role_cache", cache)
        elif cache_key in cache:
            return cache[cache_key]

        membership = get_cached_workshop_member(request=request, workshop=workshop)
        if membership is not None:
            is_manager = role_name_matches(role_name=getattr(getattr(membership, "role", None), "name", None), pattern=MANAGER_ROLE_PATTERN)
            cache[cache_key] = is_manager
            return is_manager

    is_manager = WorkshopMember.objects.filter(
        user=user,
        workshop=workshop,
        is_active=True,
        role__name__iregex=MANAGER_ROLE_PATTERN.pattern,
    ).exists()

    if request is not None and cache is not None:
        cache[cache_key] = is_manager

    return is_manager


def has_workshop_perm(*, user: User, workshop: Workshop, app_label: str, model: str, codename: str, request=None) -> bool:
    if getattr(workshop, "account_id", None) != getattr(user, "account_id", None):
        return False

    if user.is_superuser:
        return True

    if getattr(user, "is_account_owner", False):
        return True

    if is_workshop_director(user=user, workshop=workshop, request=request):
        return True

    workshop_id = getattr(workshop, "id", None)
    permission_key = (workshop_id, app_label, model, codename)
    cache: dict[tuple[object, ...], bool] | None = None
    if request is not None:
        cache = getattr(request, "_workshop_perm_cache", None)
        if cache is None:
            cache = {}
            setattr(request, "_workshop_perm_cache", cache)
        elif permission_key in cache:
            return cache[permission_key]

    has_permission = WorkshopMember.objects.filter(
        user=user,
        workshop=workshop,
        is_active=True,
        role__permissions__content_type__app_label=app_label,
        role__permissions__content_type__model=model,
        role__permissions__codename=codename,
    ).exists()

    if request is not None and cache is not None:
        cache[permission_key] = has_permission

    return has_permission


def can_view_payroll_details(*, user: User, workshop: Workshop, request=None) -> bool:
    if getattr(workshop, "account_id", None) != getattr(user, "account_id", None):
        return False

    if user.is_superuser:
        return True

    if getattr(user, "is_account_owner", False):
        return True

    if is_workshop_director(user=user, workshop=workshop, request=request):
        return True

    permission_key = (getattr(workshop, "id", None), "collaborators", "collaboratorpayroll", "view_payroll_details")
    cache: dict[tuple[object, ...], bool] | None = None
    if request is not None:
        cache = getattr(request, "_workshop_perm_cache", None)
        if cache is None:
            cache = {}
            setattr(request, "_workshop_perm_cache", cache)
        elif permission_key in cache:
            return cache[permission_key]

    has_permission = WorkshopMember.objects.filter(
        user=user,
        workshop=workshop,
        is_active=True,
        role__permissions__content_type__app_label="collaborators",
        role__permissions__content_type__model="collaboratorpayroll",
        role__permissions__codename="view_payroll_details",
    ).exists()

    if request is not None and cache is not None:
        cache[permission_key] = has_permission

    return has_permission
