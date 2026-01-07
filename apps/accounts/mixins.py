from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied


class AccountOwnerRequiredMixin(LoginRequiredMixin):
    """Restringe acesso ao dono da conta (tenant)."""

    def dispatch(self, request, *args, **kwargs):
        if not getattr(request.user, "account_id", None):
            raise PermissionDenied

        if request.user.account.owner_id != request.user.id:
            raise PermissionDenied

        return super().dispatch(request, *args, **kwargs)
