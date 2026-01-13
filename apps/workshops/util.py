from django.contrib.auth import get_user_model
from django.http import Http404

from apps.collaborators.models import WorkshopMember
from apps.workshops.models.workshops import Workshop

User = get_user_model()


def get_active_workshop_or_404(request) -> Workshop:
    workshop_id = request.session.get("active_workshop_id")
    if not workshop_id:
        raise Http404

    if not getattr(request.user, "account_id", None):
        raise Http404

    qs = Workshop.objects.filter(
        pk=workshop_id,
        account=request.user.account,
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

    return workshop


def has_workshop_perm(*, user: User, workshop: Workshop, app_label: str, model: str, codename: str) -> bool:
    if workshop.account_id != user.account_id:
        return False

    return WorkshopMember.objects.filter(
        user=user,
        workshop=workshop,
        is_active=True,
        role__permissions__content_type__app_label=app_label,
        role__permissions__content_type__model=model,
        role__permissions__codename=codename,
    ).exists()
