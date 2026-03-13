from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied

from apps.collaborators.models import WorkshopMember


class AccountOwnerRequiredMixin(LoginRequiredMixin):
    """Restringe acesso ao dono da conta (tenant)."""

    def dispatch(self, request, *args, **kwargs):
        if not getattr(request.user, "account_id", None):
            raise PermissionDenied

        if request.user.account.owner_id != request.user.id:
            raise PermissionDenied

        return super().dispatch(request, *args, **kwargs)


class AccountOwnerOrDirectorRequiredMixin(LoginRequiredMixin):
    """Permite acesso ao dono da conta OU usuários com cargo de Diretor."""

    def dispatch(self, request, *args, **kwargs):
        user = request.user

        if not getattr(user, "account_id", None):
            raise PermissionDenied

        is_owner = user.account.owner_id == user.id
        is_director = WorkshopMember.objects.filter(user=user, role__name__iexact="Diretor", is_active=True).exists()

        if not (is_owner or is_director):
            raise PermissionDenied

        return super().dispatch(request, *args, **kwargs)
