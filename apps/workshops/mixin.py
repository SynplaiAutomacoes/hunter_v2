from __future__ import annotations

from django.core.exceptions import PermissionDenied, ImproperlyConfigured
from django.views.generic import ListView, CreateView, UpdateView, DeleteView

from apps.workshops.util.workshops import get_active_workshop_or_404, has_workshop_perm


class WorkshopScopedMixin:
    """Mixin para views que SEMPRE devem operar na oficina ativa.

    - Define `self.workshop` via sessão
    - Valida permissão por oficina
    - Filtra o queryset por `workshop=self.workshop`
    """

    workshop_permission_codename: str | None = None
    workshop_permission_app_label: str | None = None  # default: model._meta.app_label
    workshop_permission_model: str | None = None  # default: self.model._meta.model_name

    def dispatch(self, request, *args, **kwargs):
        self.workshop = get_active_workshop_or_404(request)

        model_name = self.workshop_permission_model
        if model_name is None:
            model = getattr(self, "model", None)
            if model is None:
                raise ImproperlyConfigured("Defina `model` na view ou `workshop_permission_model` no mixin.")
            model_name = model._meta.model_name

        if isinstance(self, ListView):
            action = "view"
        elif isinstance(self, CreateView):
            action = "add"
        elif isinstance(self, UpdateView):
            action = "change"
        elif isinstance(self, DeleteView):
            action = "delete"
        else:
            action = None

        if action is None and self.workshop_permission_codename is None:
            raise ImproperlyConfigured("Defina `workshop_permission_codename` na view.")

        if not has_workshop_perm(
            user=request.user,
            workshop=self.workshop,
            app_label=self.workshop_permission_app_label or model._meta.app_label,
            model=model_name,
            codename=self.workshop_permission_codename or f"{action}_{model_name}",
        ):
            raise PermissionDenied

        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(workshop=self.workshop)
