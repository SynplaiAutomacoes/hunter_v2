from django.contrib.auth import get_user_model
from django.http import Http404

from apps.collaborators.models import WorkshopMember
from apps.workshops.models.workshops import Workshop

User = get_user_model()


def get_active_workshop_or_404(request) -> Workshop:
    cached_workshop = getattr(request, "_active_workshop_obj", None)
    if cached_workshop is not None:
        return cached_workshop

    account_id = getattr(request.user, "account_id", None)
    if not account_id:
        raise Http404

    workshop = _get_valid_active_workshop(request=request, account_id=account_id)
    if workshop is None:
        workshop = _get_first_available_workshop(request=request, account_id=account_id)

    if workshop is None:
        request.session.pop("active_workshop_id", None)
        raise Http404

    request.session["active_workshop_id"] = workshop.pk
    setattr(request, "_active_workshop_obj", workshop)
    return workshop


def _get_valid_active_workshop(*, request, account_id: int) -> Workshop | None:
    workshop_id = request.session.get("active_workshop_id")
    if not workshop_id:
        return None

    workshop = (
        Workshop.objects.filter(
            pk=workshop_id,
            account_id=account_id,
            is_active=True,
            members__user=request.user,
            members__is_active=True,
        )
        .distinct()
        .first()
    )

    return workshop


def _get_first_available_workshop(*, request, account_id: int) -> Workshop | None:
    return (
        Workshop.objects.filter(
            account_id=account_id,
            is_active=True,
            members__user=request.user,
            members__is_active=True,
        )
        .order_by("name", "pk")
        .first()
    )


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

    is_director = WorkshopMember.objects.filter(
        user=user,
        workshop=workshop,
        is_active=True,
        role__name__iregex=r"^\s*diretor\s*$",
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

    is_manager = WorkshopMember.objects.filter(
        user=user,
        workshop=workshop,
        is_active=True,
        role__name__iregex=r"^\s*gerente\s*$",
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
