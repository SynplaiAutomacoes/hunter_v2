from __future__ import annotations

from django.core.exceptions import PermissionDenied, ImproperlyConfigured
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView

from apps.workshops.util.workshops import get_active_workshop_or_404, has_workshop_perm


class WorkshopScopedMixin:
    """Mixin para views com escopo de oficina.

    Por padrao resolve `self.workshop` pela oficina ativa na sessao.
    Com `resolve_workshop_from_url_pk = True`, usa o `pk` da URL (mesmo escopo
    da tela de edicao da oficina).
    """

    workshop_permission_codename: str | None = None
    workshop_permission_app_label: str | None = None  # default: model._meta.app_label
    workshop_permission_model: str | None = None  # default: self.model._meta.model_name
    workshop_permission_fallbacks: tuple[tuple[str, str, str], ...] = ()
    resolve_workshop_from_url_pk: bool = False

    def _resolve_workshop(self, request, kwargs):
        if not self.resolve_workshop_from_url_pk:
            return get_active_workshop_or_404(request)

        # Lazy import avoids circular imports with workshops views module.
        from apps.workshops.views.workshops import _get_user_workshop_queryset

        pk = kwargs.get("pk")
        if pk is None:
            raise Http404
        return get_object_or_404(_get_user_workshop_queryset(request), pk=pk)

    def dispatch(self, request, *args, **kwargs):
        self.workshop = self._resolve_workshop(request, kwargs)

        model = getattr(self, "model", None)
        model_name = self.workshop_permission_model
        if model_name is None:
            if model is None:
                raise ImproperlyConfigured("Defina `model` na view ou `workshop_permission_model` no mixin.")
            model_name = model._meta.model_name

        if self.workshop_permission_app_label is None and model is None:
            raise ImproperlyConfigured("Defina `model` na view ou `workshop_permission_app_label` no mixin.")

        if isinstance(self, (ListView, DetailView)):
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

        app_label = self.workshop_permission_app_label
        if app_label is None and model is not None:
            app_label = model._meta.app_label
        if app_label is None:
            raise ImproperlyConfigured("Defina `workshop_permission_app_label` no mixin.")

        has_permission = has_workshop_perm(
            user=request.user,
            workshop=self.workshop,
            app_label=app_label,
            model=model_name,
            codename=self.workshop_permission_codename or f"{action}_{model_name}",
            request=request,
        )
        if not has_permission:
            for fallback_app_label, fallback_model, fallback_codename in self.workshop_permission_fallbacks:
                if has_workshop_perm(
                    user=request.user,
                    workshop=self.workshop,
                    app_label=fallback_app_label,
                    model=fallback_model,
                    codename=fallback_codename,
                    request=request,
                ):
                    has_permission = True
                    break

        if not has_permission:
            raise PermissionDenied

        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(workshop=self.workshop)
