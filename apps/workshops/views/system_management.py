from __future__ import annotations

import json
import logging
from typing import Any
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.urls import reverse_lazy
from django.views.generic import FormView, TemplateView

from apps.collaborators.models import WorkshopMember
from apps.notifications.domain.services.notification_service import NotificationService
from apps.workshops.forms.system_management import NotificationBroadcastForm
from apps.workshops.models.workshops import Workshop

logger = logging.getLogger(__name__)
User = get_user_model()


class SystemManagementMixin(LoginRequiredMixin):
    """
    Garante acesso estrito à página Gerenciar Sistema somente se o username estiver em settings.SYSTEM_ADMIN_USERNAMES.
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        admin_usernames = getattr(settings, "SYSTEM_ADMIN_USERNAMES", [])
        if request.user.username not in admin_usernames:
            raise PermissionDenied("Acesso restrito ao gerenciamento do sistema.")
        return super().dispatch(request, *args, **kwargs)


class SystemManageDashboardView(SystemManagementMixin, TemplateView):
    template_name = "workshops/system/manage.html"


class NotificationBroadcastView(SystemManagementMixin, FormView):
    template_name = "workshops/system/broadcast_form.html"
    form_class = NotificationBroadcastForm
    success_url = reverse_lazy("workshops:system_manage")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)

        # Buscar todos os membros ativos das oficinas para preenchimento de modais e relações
        memberships = (
            WorkshopMember.objects.filter(
                is_active=True,
                user__is_active=True,
                workshop__is_active=True,
            )
            .select_related("user", "workshop", "role")
            .order_by("user__first_name", "user__username")
        )

        workshop_members_map: dict[str, list[dict[str, str]]] = {}
        user_workshops_map: dict[str, list[str]] = {}
        user_info_map: dict[str, dict[str, Any]] = {}

        for m in memberships:
            w_id = str(m.workshop_id)
            u_id = str(m.user_id)
            user_display = m.user.get_full_name() or m.user.username
            role_name = m.role.name if m.role else "Sem cargo"

            if w_id not in workshop_members_map:
                workshop_members_map[w_id] = []

            workshop_members_map[w_id].append({
                "id": u_id,
                "name": user_display,
                "username": m.user.username,
                "role": role_name,
            })

            if u_id not in user_workshops_map:
                user_workshops_map[u_id] = []
            user_workshops_map[u_id].append(w_id)

            if u_id not in user_info_map:
                user_info_map[u_id] = {
                    "id": u_id,
                    "name": user_display,
                    "username": m.user.username,
                    "roles": [role_name] if m.role else [],
                    "workshops": [m.workshop.name],
                }
            else:
                if m.role and role_name not in user_info_map[u_id]["roles"]:
                    user_info_map[u_id]["roles"].append(role_name)
                if m.workshop.name not in user_info_map[u_id]["workshops"]:
                    user_info_map[u_id]["workshops"].append(m.workshop.name)

        context.update({
            "workshop_members_json": json.dumps(workshop_members_map),
            "user_workshops_json": json.dumps(user_workshops_map),
            "user_info_json": json.dumps(user_info_map),
        })
        return context

    def form_valid(self, form: NotificationBroadcastForm):
        workshops = form.cleaned_data.get("workshops")
        selected_users = form.cleaned_data.get("users")
        workshop_targets_raw = self.request.POST.get("workshop_targets_data", "")
        tipo = form.cleaned_data.get("tipo", "info")
        title = form.cleaned_data["title"]
        message = form.cleaned_data["message"]

        workshop_custom_members: dict[str, list[str]] = {}
        if workshop_targets_raw:
            try:
                workshop_custom_members = json.loads(workshop_targets_raw)
            except Exception as e:
                logger.warning("Erro ao decodificar workshop_targets_data: %s", e)

        targets: list[tuple[Workshop, User]] = []
        covered_pairs: set[tuple[int, int]] = set()

        # 1. Processar destinatários das oficinas selecionadas
        if workshops:
            for workshop in workshops:
                w_id_str = str(workshop.id)
                if w_id_str in workshop_custom_members:
                    allowed_user_ids = [
                        int(u_id) for u_id in workshop_custom_members[w_id_str] if str(u_id).isdigit()
                    ]
                    members = WorkshopMember.objects.filter(
                        workshop=workshop,
                        user_id__in=allowed_user_ids,
                        is_active=True,
                        user__is_active=True,
                    ).select_related("user", "workshop")
                else:
                    members = WorkshopMember.objects.filter(
                        workshop=workshop,
                        is_active=True,
                        user__is_active=True,
                    ).select_related("user", "workshop")

                for m in members:
                    pair = (m.workshop.id, m.user.id)
                    if pair not in covered_pairs:
                        covered_pairs.add(pair)
                        targets.append((m.workshop, m.user))

        # 2. Processar usuários específicos
        if selected_users:
            for user in selected_users:
                user_memberships = WorkshopMember.objects.filter(
                    user=user,
                    is_active=True,
                    workshop__is_active=True,
                ).select_related("workshop", "user")

                if user_memberships.exists():
                    for m in user_memberships:
                        pair = (m.workshop.id, m.user.id)
                        if pair not in covered_pairs:
                            covered_pairs.add(pair)
                            targets.append((m.workshop, m.user))
                else:
                    # Caso de usuário sem vínculo direto de oficina ativa, tentar primeira oficina ativa
                    first_workshop = Workshop.objects.filter(is_active=True).first()
                    if first_workshop:
                        pair = (first_workshop.id, user.id)
                        if pair not in covered_pairs:
                            covered_pairs.add(pair)
                            targets.append((first_workshop, user))

        if not targets:
            messages.error(self.request, "Nenhum destinatário válido foi encontrado com os critérios selecionados.")
            return self.form_invalid(form)

        NotificationService.create_notification(
            title=title,
            message=message,
            sender=self.request.user,
            tipo=tipo,
            targets=targets,
            metadata={"broadcast": True, "tipo": tipo},
        )

        messages.success(
            self.request,
            f"Notificação enviada com sucesso para {len(targets)} destinatário(s).",
        )
        return super().form_valid(form)
