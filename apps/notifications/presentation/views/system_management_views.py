from __future__ import annotations

from typing import Any
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.shortcuts import render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import FormView, TemplateView

from apps.collaborators.models import WorkshopMember
from apps.notifications.forms import NotificationBroadcastForm
from apps.notifications.domain.services.notification_service import NotificationService
from apps.workshops.models.workshops import Workshop

User = get_user_model()


class SystemManagementMixin:
    """
    Garante acesso estrito à página Gerenciar Sistema somente se o username estiver em settings.SYSTEM_ADMIN_USERNAMES.
    """

    def dispatch(self, request, *args, **kwargs):
        admin_usernames = getattr(settings, "SYSTEM_ADMIN_USERNAMES", [])
        if not request.user.is_authenticated or request.user.username not in admin_usernames:
            raise PermissionDenied("Acesso restrito ao gerenciamento do sistema.")
        return super().dispatch(request, *args, **kwargs)


class SystemManageDashboardView(SystemManagementMixin, TemplateView):
    template_name = "notifications/system/manage.html"


class NotificationUsersOptionsView(SystemManagementMixin, View):
    """
    Retorna a partial HTMX com a lista de usuários filtrados pelas oficinas selecionadas.
    """

    def get(self, request):
        raw_workshop_ids = request.GET.getlist("workshops")
        workshop_ids = [int(w_id) for w_id in raw_workshop_ids if w_id.isdigit()]

        if workshop_ids:
            memberships = (
                WorkshopMember.objects.filter(
                    workshop_id__in=workshop_ids,
                    is_active=True,
                    user__is_active=True,
                )
                .select_related("user")
                .order_by("user__username")
            )
            users = list({m.user for m in memberships})
        else:
            users = list(User.objects.filter(is_active=True).order_by("username"))

        return render(
            request,
            "notifications/system/partials/user_selector.html",
            {"users": users},
        )


class NotificationBroadcastView(SystemManagementMixin, FormView):
    template_name = "notifications/system/broadcast_form.html"
    form_class = NotificationBroadcastForm
    success_url = reverse_lazy("notifications:system_manage")

    def form_valid(self, form):
        workshops = form.cleaned_data.get("workshops")
        selected_users = form.cleaned_data.get("users")
        title = form.cleaned_data["title"]
        message = form.cleaned_data["message"]

        targets: list[tuple[Workshop, User]] = []

        if workshops and selected_users:
            memberships = WorkshopMember.objects.filter(
                workshop__in=workshops,
                user__in=selected_users,
                is_active=True,
                user__is_active=True,
                workshop__is_active=True,
            ).select_related("workshop", "user")
            for m in memberships:
                targets.append((m.workshop, m.user))

        elif workshops:
            memberships = WorkshopMember.objects.filter(
                workshop__in=workshops,
                is_active=True,
                user__is_active=True,
                workshop__is_active=True,
            ).select_related("workshop", "user")
            for m in memberships:
                targets.append((m.workshop, m.user))

        elif selected_users:
            memberships = WorkshopMember.objects.filter(
                user__in=selected_users,
                is_active=True,
                user__is_active=True,
                workshop__is_active=True,
            ).select_related("workshop", "user")
            for m in memberships:
                targets.append((m.workshop, m.user))

        if not targets:
            messages.error(self.request, "Nenhum destinatário válido foi encontrado com os critérios selecionados.")
            return self.form_invalid(form)

        NotificationService.create_notification(
            title=title,
            message=message,
            sender=self.request.user,
            targets=targets,
            metadata={"broadcast": True},
        )

        messages.success(
            self.request,
            f"Notificação enviada com sucesso para {len(targets)} destinatário(s).",
        )
        return super().form_valid(form)
