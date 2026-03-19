from django.contrib.auth import get_user_model
from django.http import Http404

from apps.collaborators.models import WorkshopMember
from apps.workshops.models.workshops import Workshop

User = get_user_model()


def get_active_workshop_or_404(request) -> Workshop:
    cached_workshop = getattr(request, "_active_workshop_obj", None)
    if cached_workshop is not None:
        return cached_workshop

    workshop_id = request.session.get("active_workshop_id")
    if not workshop_id:
        raise Http404

    if not getattr(request.user, "account_id", None):
        raise Http404

    qs = Workshop.objects.filter(
        pk=workshop_id,
        account_id=request.user.account_id,
        is_active=True,
    )

    workshop = qs.first()
    if not workshop:
        raise Http404

    # Colaborador precisa ser membro da oficina
    if not WorkshopMember.objects.filter(
        user=request.user,
        workshop=workshop,
        is_active=True,
    ).exists():
        raise Http404

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

    is_director = WorkshopMember.objects.filter(
        user=user,
        workshop=workshop,
        is_active=True,
        role__name__iexact="Diretor",
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
        role__name__iexact="Gerente",
    ).exists()

    if request is not None and cache is not None:
        cache[cache_key] = is_manager

    return is_manager


def has_workshop_perm(*, user: User, workshop: Workshop, app_label: str, model: str, codename: str, request=None) -> bool:
    if getattr(workshop, "account_id", None) != getattr(user, "account_id", None):
        return False

    if is_workshop_director(user=user, workshop=workshop, request=request):
        return True

    if is_workshop_manager(user=user, workshop=workshop, request=request):
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
