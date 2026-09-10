from __future__ import annotations

from typing import Any
from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views import View
from django.views.generic import ListView

from apps.core.presentation.mixins import HtmxTemplateResponseMixin
from apps.core.presentation.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableAction, TableColumn
from apps.notifications.domain.services.notification_service import NotificationService
from apps.notifications.models import NotificationRecipient
from apps.workshops.util.workshops import get_active_workshop_or_404


class NotificationDropdownView(LoginRequiredMixin, View):
    """
    Retorna a partial HTML com as últimas N notificações do usuário na workshop ativa.
    """

    def get(self, request: HttpRequest) -> HttpResponse:
        try:
            workshop = get_active_workshop_or_404(request)
        except Http404:
            return render(request, "notifications/partials/dropdown.html", {"recipients": [], "unread_count": 0})

        limit = getattr(settings, "NOTIFICATIONS_DROPDOWN_LIMIT", 5)
        recipients = list(
            NotificationService.get_user_notifications(
                user=request.user,
                workshop=workshop,
                limit=limit,
            )
        )
        unread_count = NotificationService.get_unread_count(user=request.user, workshop=workshop)

        return render(
            request,
            "notifications/partials/dropdown.html",
            {
                "recipients": recipients,
                "unread_count": unread_count,
            },
        )


class NotificationListView(LoginRequiredMixin, HtmxTemplateResponseMixin, ListView):
    """
    Página de listagem completa de notificações do usuário na workshop ativa.
    """

    model = NotificationRecipient
    template_name = "notifications/list.html"
    htmx_template_name = "notifications/partials/table_partial.html"
    context_object_name = "recipients"
    paginate_by = 15

    def get_queryset(self):
        workshop = get_active_workshop_or_404(self.request)
        qs = (
            NotificationRecipient.objects.filter(
                user=self.request.user,
                workshop=workshop,
            )
            .select_related("notification", "notification__sender", "workshop")
            .order_by("-criado_em")
        )

        status_filter = self.request.GET.get("status")
        if status_filter == "unread":
            qs = qs.filter(is_read=False)
        elif status_filter == "read":
            qs = qs.filter(is_read=True)

        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(notification__title__icontains=q)
                | Q(notification__message__icontains=q)
                | Q(notification__sender__username__icontains=q)
            )

        return qs

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        workshop = get_active_workshop_or_404(self.request)

        columns = [
            TableColumn(
                label="Título",
                attr="notification.title",
                sortable=False,
                searchable=False,
            ),
            TableColumn(
                label="Mensagem",
                attr="notification.message",
                sortable=False,
                searchable=False,
            ),
            TableColumn(
                label="Status",
                attr=lambda r: "Lida" if r.is_read else "Nova",
                sortable=False,
                searchable=False,
            ),
            TableColumn(
                label="Data",
                attr="criado_em",
                sortable=False,
                searchable=False,
            ),
        ]

        actions = [
            TableAction(
                label="Marcar como lida",
                url_name="notifications:mark_read_single",
                icon="mark_email_read",
                a_class="btn btn-ghost btn-xs text-primary",
                aria_label="Marcar como lida",
                hx_target="#notifications-table-wrapper",
                visible=lambda r: not r.is_read,
            ),
            TableActionDefaults.delete("notifications:delete"),
        ]

        context.update(
            {
                "columns": columns,
                "actions": actions,
                "status_filter": self.request.GET.get("status", "all"),
                "search_query": self.request.GET.get("q", ""),
                "unread_count": NotificationService.get_unread_count(user=self.request.user, workshop=workshop),
            }
        )
        return context


class NotificationMarkReadView(LoginRequiredMixin, View):
    """
    Marca notificações como lidas.
    """

    def _mark_read(self, request: HttpRequest, pk: int | None = None) -> HttpResponse:
        workshop = get_active_workshop_or_404(request)
        if pk is not None:
            notification_ids = [pk]
        else:
            raw_ids = request.POST.getlist("id") or request.POST.getlist("notification_ids") or request.GET.getlist("id") or [request.POST.get("id") or request.GET.get("id")]
            notification_ids = []
            for raw_id in raw_ids:
                if raw_id:
                    try:
                        notification_ids.append(int(raw_id))
                    except ValueError:
                        pass

        if notification_ids:
            NotificationService.mark_as_read(
                user=request.user,
                workshop=workshop,
                notification_ids=notification_ids,
            )

        response = HttpResponse(status=200)
        response["HX-Trigger"] = "notifications-updated"
        return response

    def post(self, request: HttpRequest, pk: int | None = None) -> HttpResponse:
        return self._mark_read(request, pk)

    def get(self, request: HttpRequest, pk: int | None = None) -> HttpResponse:
        return self._mark_read(request, pk)


class NotificationMarkAllReadView(LoginRequiredMixin, View):
    """
    Marca todas as notificações da workshop ativa como lidas.
    """

    def post(self, request: HttpRequest) -> HttpResponse:
        workshop = get_active_workshop_or_404(request)
        NotificationService.mark_all_as_read(user=request.user, workshop=workshop)

        response = HttpResponse(status=200)
        response["HX-Trigger"] = "notifications-updated"
        return response


class NotificationDeleteView(LoginRequiredMixin, View):
    """
    Exclui um destinatário de notificação com modal de confirmação.
    """

    def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        recipient = get_object_or_404(NotificationRecipient, id=pk, user=request.user)
        context = {
            "object": recipient.notification.title,
            "delete_title": "Excluir Notificação",
            "delete_subtitle": "Esta ação removerá a notificação da sua lista.",
            "delete_warning_title": "Confirmar exclusão",
            "delete_warning_text": "Tem certeza que deseja excluir a notificação",
            "modal_id": f"delete-modal-{pk}",
            "hx_post": request.path,
        }
        return render(request, "notifications/partials/delete_modal.html", context)

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        recipient = get_object_or_404(NotificationRecipient, id=pk, user=request.user)
        NotificationService.delete_notification(user=request.user, notification_id=recipient.id)

        response = HttpResponse(status=200)
        response["HX-Trigger"] = "notifications-updated"
        return response


class NotificationUnreadCountView(LoginRequiredMixin, View):
    """
    Retorna o contador de notificações não lidas em JSON (usado no polling).
    """

    def get(self, request: HttpRequest) -> JsonResponse:
        try:
            workshop = get_active_workshop_or_404(request)
            count = NotificationService.get_unread_count(user=request.user, workshop=workshop)
        except Exception:
            count = 0

        return JsonResponse({"count": count})
