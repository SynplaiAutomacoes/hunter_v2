from __future__ import annotations

from typing import Any

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import CreateView, DetailView, ListView

from apps.collaborators.models import WorkshopCollaborator
from apps.core.infrastructure.query_filters import QueryParamFilter, apply_query_param_filters
from apps.core.presentation.mixins import HtmxTemplateResponseMixin
from apps.core.presentation.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.tickets.application.services.attachments import TicketAttachmentError, attachment_download_url, prepare_uploaded_file
from apps.tickets.application.services.chat import TicketChatError, post_ticket_message
from apps.tickets.application.services.ws_auth import issue_ticket_chat_ws_token
from apps.tickets.application.services.workflow import TicketWorkflowError, TicketWorkflowService
from apps.tickets.constants import MAX_ATTACHMENT_BYTES, MAX_RECORDING_SECONDS, STATUS_BADGE_CLASSES
from apps.tickets.models import FINAL_STATUSES, NON_FINAL_STATUSES, Ticket, TicketAttachmentSource, TicketStatus
from apps.tickets.permissions import (
    can_access_all_tickets,
    can_act_as_assignee,
    can_view_ticket,
    is_developer,
    is_system_admin,
)
from apps.tickets.presentation.forms import (
    TicketCreateForm,
    TicketMessageForm,
    TicketReassignForm,
    TicketRejectForm,
    TicketStatusUpdateForm,
)
from apps.workshops.util.workshops import get_active_workshop_or_404

User = get_user_model()

TICKET_STATUS_VALUES: frozenset[str] = frozenset(value for value, _label in TicketStatus.choices)


def _developer_user_queryset():
    return User.objects.filter(pk__in=WorkshopCollaborator.objects.filter(is_developer=True, is_active=True, user__isnull=False).values_list("user_id", flat=True)).order_by("username")


def _get_selected_ticket_status_values(request: HttpRequest) -> list[str]:
    selected: list[str] = []
    seen: set[str] = set()
    for raw_value in request.GET.getlist("status"):
        value = str(raw_value or "").strip()
        if not value or value not in TICKET_STATUS_VALUES or value in seen:
            continue
        seen.add(value)
        selected.append(value)
    return selected


def _collect_prepared_attachments(request: HttpRequest, *, default_source: str = TicketAttachmentSource.UPLOAD):
    prepared = []
    screen_recordings = list(request.FILES.getlist("screen_recording"))
    uploads = list(request.FILES.getlist("attachments"))

    for uploaded in screen_recordings:
        prepared.append(prepare_uploaded_file(uploaded=uploaded, source=TicketAttachmentSource.SCREEN_RECORDING))
    for uploaded in uploads:
        prepared.append(prepare_uploaded_file(uploaded=uploaded, source=default_source))
    return prepared


class DeveloperOrAdminRequiredMixin(UserPassesTestMixin):
    raise_exception = True

    def test_func(self) -> bool:
        return can_access_all_tickets(self.request.user)

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        return HttpResponseForbidden("Acesso restrito a desenvolvedores e administradores do sistema.")


class MyTicketListView(LoginRequiredMixin, HtmxTemplateResponseMixin, ListView):
    model = Ticket
    template_name = "tickets/my_list.html"
    htmx_template_name = "tickets/partials/my_table.html"
    context_object_name = "tickets"

    def get_queryset(self):
        qs = Ticket.objects.filter(created_by=self.request.user).select_related("workshop", "assignee", "created_by")
        selected_statuses = _get_selected_ticket_status_values(self.request)
        if selected_statuses:
            qs = qs.filter(status__in=selected_statuses)
        else:
            qs = qs.filter(status__in=NON_FINAL_STATUSES)
        return qs.order_by("-created_at")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["tickets"] = self.get_queryset()
        context["fields"] = [
            TableColumn("#", attr="pk", search_by="pk"),
            TableColumn("Título", attr="title", search_by=("title", "problem")),
            TableColumn("Status", attr="status_badge", search_by="status", sort_by="status", format="status_badge"),
            TableColumn("Oficina", attr="workshop.name", search_by="workshop__name"),
            TableColumn("Responsável", attr="assignee_display", search_by="assignee__username", sortable=False),
            TableColumn("Criado em", attr="created_at", searchable=False),
        ]
        context["actions"] = [TableActionDefaults.view("tickets:ticket_detail")]
        context["status_choices"] = TicketStatus.choices
        context["selected_status_values"] = _get_selected_ticket_status_values(self.request)
        context["status_badge_classes"] = STATUS_BADGE_CLASSES
        context["can_access_all_tickets"] = can_access_all_tickets(self.request.user)
        return context


class AllTicketListView(LoginRequiredMixin, DeveloperOrAdminRequiredMixin, HtmxTemplateResponseMixin, ListView):
    model = Ticket
    template_name = "tickets/all_list.html"
    htmx_template_name = "tickets/partials/all_table.html"
    context_object_name = "tickets"

    def get_queryset(self):
        qs = Ticket.objects.all().select_related("workshop", "assignee", "created_by")
        qs = apply_query_param_filters(
            qs,
            params=self.request.GET,
            filter_configs=[
                QueryParamFilter(param_name="status", lookup="status", kind="choice", allowed_values=TICKET_STATUS_VALUES),
            ],
        )
        workshop_id = (self.request.GET.get("workshop") or "").strip()
        if workshop_id.isdigit():
            qs = qs.filter(workshop_id=int(workshop_id))
        assignee_id = (self.request.GET.get("assignee") or "").strip()
        if assignee_id.isdigit():
            qs = qs.filter(assignee_id=int(assignee_id))
        return qs.order_by("-created_at")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["tickets"] = self.get_queryset()
        context["fields"] = [
            TableColumn("#", attr="pk", search_by="pk"),
            TableColumn("Título", attr="title", search_by=("title", "problem", "created_by__username")),
            TableColumn("Status", attr="status_badge", search_by="status", sort_by="status", format="status_badge"),
            TableColumn("Oficina", attr="workshop.name", search_by="workshop__name"),
            TableColumn("Aberto por", attr="created_by_display", search_by="created_by__username", sortable=False),
            TableColumn("Responsável", attr="assignee_display", search_by="assignee__username", sortable=False),
            TableColumn("Criado em", attr="created_at", searchable=False),
        ]
        context["actions"] = [TableActionDefaults.view("tickets:ticket_detail")]
        context["status_choices"] = TicketStatus.choices
        context["selected_status_values"] = _get_selected_ticket_status_values(self.request)
        context["selected_assignee_id"] = (self.request.GET.get("assignee") or "").strip()
        context["status_badge_classes"] = STATUS_BADGE_CLASSES
        context["is_developer"] = is_developer(self.request.user)
        context["developer_users"] = _developer_user_queryset()
        return context


class TicketCreateView(LoginRequiredMixin, CreateView):
    model = Ticket
    form_class = TicketCreateForm
    template_name = "tickets/create.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["max_attachment_bytes"] = MAX_ATTACHMENT_BYTES
        context["max_recording_seconds"] = MAX_RECORDING_SECONDS
        return context

    def form_valid(self, form: TicketCreateForm) -> HttpResponse:
        workshop = get_active_workshop_or_404(request=self.request)
        try:
            attachments = _collect_prepared_attachments(self.request)
        except TicketAttachmentError as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)

        try:
            ticket = TicketWorkflowService.create_ticket(
                workshop=workshop,
                created_by=self.request.user,
                title=form.cleaned_data["title"],
                problem=form.cleaned_data["problem"],
                reproduction_steps=form.cleaned_data["reproduction_steps"],
                attachments=attachments,
            )
        except TicketWorkflowError as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)

        messages.success(self.request, "Chamado aberto com sucesso.")
        return redirect("tickets:ticket_detail", pk=ticket.pk)


class TicketDetailView(LoginRequiredMixin, DetailView):
    model = Ticket
    template_name = "tickets/detail.html"
    context_object_name = "ticket"

    def get_queryset(self):
        return Ticket.objects.select_related("workshop", "created_by", "assignee").prefetch_related(
            "attachments",
            "messages__author",
            "status_history",
        )

    def get_object(self, queryset=None):
        ticket = super().get_object(queryset)
        if not can_view_ticket(user=self.request.user, ticket=ticket):
            raise Http404("Chamado não encontrado.")
        return ticket

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        ticket: Ticket = context["ticket"]
        user = self.request.user
        context["status_badge_classes"] = STATUS_BADGE_CLASSES
        context["is_owner"] = ticket.created_by_id == user.pk
        context["is_developer"] = is_developer(user)
        context["is_system_admin"] = is_system_admin(user)
        context["is_assignee"] = can_act_as_assignee(user=user, ticket=ticket)
        context["can_capture"] = is_developer(user) and ticket.assignee_id is None and not ticket.is_final
        context["can_reassign"] = is_developer(user) and ticket.assignee_id is not None and not ticket.is_final
        context["can_change_status"] = can_act_as_assignee(user=user, ticket=ticket) and not ticket.is_final
        context["can_approve_or_reject"] = ticket.created_by_id == user.pk and ticket.status == TicketStatus.AGUARDANDO_VALIDACAO
        context["can_add_attachments"] = (ticket.created_by_id == user.pk or is_developer(user)) and not ticket.is_final
        context["status_form"] = TicketStatusUpdateForm()
        context["reject_form"] = TicketRejectForm()
        context["message_form"] = TicketMessageForm()
        context["reassign_form"] = TicketReassignForm()
        context["developer_users"] = _developer_user_queryset().exclude(pk=ticket.assignee_id)
        context["max_attachment_bytes"] = MAX_ATTACHMENT_BYTES
        context["max_recording_seconds"] = MAX_RECORDING_SECONDS
        context["chat_ws_token"] = issue_ticket_chat_ws_token(user_id=int(user.pk), ticket_id=int(ticket.pk))
        context["chat_ws_base_url"] = str(getattr(settings, "TICKET_CHAT_WS_BASE_URL", None) or getattr(settings, "MESSAGE_DISPATCH_WS_BASE_URL", "") or "").strip()
        context["final_statuses"] = FINAL_STATUSES
        context["attachments_with_urls"] = [
            {
                "attachment": attachment,
                "url": attachment_download_url(attachment=attachment),
            }
            for attachment in ticket.attachments.all()
        ]
        return context


class TicketCaptureView(LoginRequiredMixin, View):
    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        ticket = get_object_or_404(Ticket, pk=pk)
        if not can_view_ticket(user=request.user, ticket=ticket):
            raise Http404("Chamado não encontrado.")
        try:
            TicketWorkflowService.capture(ticket=ticket, actor=request.user)
            messages.success(request, "Chamado capturado.")
        except TicketWorkflowError as exc:
            messages.error(request, str(exc))
        return redirect("tickets:ticket_detail", pk=pk)


class TicketReassignView(LoginRequiredMixin, View):
    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        ticket = get_object_or_404(Ticket, pk=pk)
        if not can_view_ticket(user=request.user, ticket=ticket):
            raise Http404("Chamado não encontrado.")
        form = TicketReassignForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Selecione um desenvolvedor válido.")
            return redirect("tickets:ticket_detail", pk=pk)
        new_assignee = get_object_or_404(User, pk=form.cleaned_data["assignee_id"])
        try:
            TicketWorkflowService.reassign(ticket=ticket, actor=request.user, new_assignee=new_assignee)
            messages.success(request, "Chamado reatribuído.")
        except TicketWorkflowError as exc:
            messages.error(request, str(exc))
        return redirect("tickets:ticket_detail", pk=pk)


class TicketStatusUpdateView(LoginRequiredMixin, View):
    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        ticket = get_object_or_404(Ticket, pk=pk)
        if not can_view_ticket(user=request.user, ticket=ticket):
            raise Http404("Chamado não encontrado.")
        form = TicketStatusUpdateForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Dados inválidos para alteração de status.")
            return redirect("tickets:ticket_detail", pk=pk)
        try:
            TicketWorkflowService.set_operational_status(
                ticket=ticket,
                actor=request.user,
                new_status=form.cleaned_data["status"],
                cancellation_reason=form.cleaned_data.get("cancellation_reason") or "",
            )
            messages.success(request, "Status atualizado.")
        except TicketWorkflowError as exc:
            messages.error(request, str(exc))
        return redirect("tickets:ticket_detail", pk=pk)


class TicketApproveView(LoginRequiredMixin, View):
    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        ticket = get_object_or_404(Ticket, pk=pk)
        try:
            TicketWorkflowService.approve_solution(ticket=ticket, actor=request.user)
            messages.success(request, "Solução aprovada. Chamado fechado.")
        except TicketWorkflowError as exc:
            messages.error(request, str(exc))
        return redirect("tickets:ticket_detail", pk=pk)


class TicketRejectView(LoginRequiredMixin, View):
    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        ticket = get_object_or_404(Ticket, pk=pk)
        form = TicketRejectForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Informe o motivo da recusa.")
            return redirect("tickets:ticket_detail", pk=pk)
        try:
            attachments = _collect_prepared_attachments(request, default_source=TicketAttachmentSource.REJECTION)
        except TicketAttachmentError as exc:
            messages.error(request, str(exc))
            return redirect("tickets:ticket_detail", pk=pk)
        try:
            TicketWorkflowService.reject_solution(
                ticket=ticket,
                actor=request.user,
                reason=form.cleaned_data["reason"],
                attachments=attachments,
            )
            messages.success(request, "Solução reprovada.")
        except TicketWorkflowError as exc:
            messages.error(request, str(exc))
        return redirect("tickets:ticket_detail", pk=pk)


class TicketAttachmentUploadView(LoginRequiredMixin, View):
    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        ticket = get_object_or_404(Ticket, pk=pk)
        if not can_view_ticket(user=request.user, ticket=ticket):
            raise Http404("Chamado não encontrado.")
        try:
            attachments = _collect_prepared_attachments(request)
            if not attachments:
                messages.error(request, "Selecione ao menos um arquivo.")
            else:
                TicketWorkflowService.add_attachments(ticket=ticket, actor=request.user, attachments=attachments)
                messages.success(request, "Anexo(s) enviado(s).")
        except (TicketAttachmentError, TicketWorkflowError) as exc:
            messages.error(request, str(exc))
        return redirect("tickets:ticket_detail", pk=pk)


class TicketMessageCreateView(LoginRequiredMixin, View):
    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        ticket = get_object_or_404(Ticket, pk=pk)
        form = TicketMessageForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Mensagem inválida.")
            return redirect("tickets:ticket_detail", pk=pk)
        try:
            post_ticket_message(ticket=ticket, author=request.user, body=form.cleaned_data["body"])
        except TicketChatError as exc:
            messages.error(request, str(exc))
        if getattr(request, "htmx", False):
            return render(
                request,
                "tickets/partials/chat_messages.html",
                {"ticket": ticket, "messages": ticket.messages.select_related("author").all()},
            )
        return redirect("tickets:ticket_detail", pk=pk)
