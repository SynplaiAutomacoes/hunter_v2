from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404
from django.template.response import TemplateResponse
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.iam.utils import get_or_create_director_role
from apps.core.views import HtmxDeleteResponseMixin, HtmxTemplateResponseMixin
from apps.core.templatetags.table_tags import TableColumn
from apps.core.tables import TableActionDefaults
from apps.workshops.forms import WorkshopForm
from apps.workshops.models import Workshop
from apps.collaborators.models import WorkshopMember

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

    # Owner enxerga tudo na conta
    if request.user.account.owner_id == request.user.id:
        return workshop

    # Colaborador precisa ser membro da oficina
    if not WorkshopMember.objects.filter(
        user=request.user,
        workshop=workshop,
        is_active=True,
    ).exists():
        raise Http404

    return workshop


def has_workshop_perm(*, user: User, workshop: Workshop, app_label: str, model: str, codename: str) -> bool:
    if not getattr(user, "account_id", None):
        return False

    if workshop.account_id != user.account_id:
        return False

    if user.account.owner_id == user.id:
        return True

    return WorkshopMember.objects.filter(
        user=user,
        workshop=workshop,
        is_active=True,
        role__permissions__content_type__app_label=app_label,
        role__permissions__content_type__model=model,
        role__permissions__codename=codename,
    ).exists()


class WorkshopCreateView(LoginRequiredMixin, CreateView):
    model = Workshop
    form_class = WorkshopForm
    template_name = "workshops/workshop_create.html"
    success_url = reverse_lazy("workshops:list")

    def dispatch(self, request, *args, **kwargs):
        if not getattr(request.user, "account_id", None):
            raise PermissionDenied

        if request.user.account.owner_id != request.user.id:
            raise PermissionDenied

        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        if not getattr(self.request.user, "account_id", None):
            raise PermissionDenied

        with transaction.atomic():
            form.instance.account = self.request.user.account
            response = super().form_valid(form)

            director_role = get_or_create_director_role(account=self.request.user.account)
            WorkshopMember.objects.get_or_create(
                user=self.request.user,
                workshop=self.object,
                defaults={
                    "role": director_role,
                    "is_active": True,
                },
            )

        return response


class WorkshopUpdateView(LoginRequiredMixin, UpdateView):
    model = Workshop
    form_class = WorkshopForm
    template_name = "workshops/workshop_update.html"
    success_url = reverse_lazy("workshops:list")

    def get_queryset(self):
        if not getattr(self.request.user, "account_id", None):
            return super().get_queryset().none()

        qs = super().get_queryset().filter(account=self.request.user.account, is_active=True)
        if self.request.user.account.owner_id == self.request.user.id:
            return qs

        return qs.filter(
            members__user=self.request.user,
            members__is_active=True,
            members__role__permissions__content_type__app_label="workshops",
            members__role__permissions__content_type__model="workshop",
            members__role__permissions__codename="change_workshop",
        ).distinct()


class WorkshopDeleteView(LoginRequiredMixin, HtmxDeleteResponseMixin, DeleteView):
    model = Workshop
    success_url = reverse_lazy("workshops:list")

    htmx_template_name = "workshops/partials/workshop_delete_modal.html"
    htmx_trigger = "workshops-table-refresh"

    def get_queryset(self):
        if not getattr(self.request.user, "account_id", None):
            return super().get_queryset().none()

        qs = super().get_queryset().filter(account=self.request.user.account, is_active=True)
        if self.request.user.account.owner_id == self.request.user.id:
            return qs

        return qs.filter(
            members__user=self.request.user,
            members__is_active=True,
            members__role__permissions__content_type__app_label="workshops",
            members__role__permissions__content_type__model="workshop",
            members__role__permissions__codename="delete_workshop",
        ).distinct()


class WorkshopListView(LoginRequiredMixin, HtmxTemplateResponseMixin, ListView):
    model = Workshop
    template_name = "workshops/workshop_list.html"
    context_object_name = "workshops"

    htmx_template_name = "workshops/partials/workshop_table.html"

    def get_queryset(self):
        if not getattr(self.request.user, "account_id", None):
            return super().get_queryset().none()

        qs = super().get_queryset().filter(account=self.request.user.account, is_active=True)
        if self.request.user.account.owner_id == self.request.user.id:
            return qs

        return qs.filter(
            members__user=self.request.user,
            members__is_active=True,
            members__role__permissions__content_type__app_label="workshops",
            members__role__permissions__content_type__model="workshop",
            members__role__permissions__codename="view_workshop",
        ).distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["fields"] = [
            TableColumn(
                label=Workshop.name.field.verbose_name,
                attr=Workshop.name.field.name,
            ),
            TableColumn(
                label=Workshop.cnpj.field.verbose_name,
                attr=Workshop.cnpj.field.name,
                format="cnpj",
            ),
            TableColumn(
                label=Workshop.is_active.field.verbose_name,
                attr=Workshop.is_active.field.name,
            ),
        ]

        context["actions"] = [
            TableActionDefaults.edit("workshops:update"),
            TableActionDefaults.delete("workshops:delete"),
        ]

        return context


class UpdateNavbarWorkshopSelectView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        workshop_id = request.POST.get("workshop_id")

        if workshop_id:
            try:
                workshop_id_int = int(workshop_id)
            except (TypeError, ValueError):
                workshop_id_int = None

            if (
                workshop_id_int is not None
                and Workshop.objects.filter(
                    pk=workshop_id_int,
                    account=request.user.account,
                    is_active=True,
                ).exists()
            ):
                if (
                    request.user.account.owner_id != request.user.id
                    and not WorkshopMember.objects.filter(
                        user=request.user,
                        workshop_id=workshop_id_int,
                        is_active=True,
                        workshop__is_active=True,
                    ).exists()
                ):
                    request.session.pop("active_workshop_id", None)
                    return TemplateResponse(request, "navbar/partials/workshop_select.html", {})

                request.session["active_workshop_id"] = workshop_id_int
            else:
                request.session.pop("active_workshop_id", None)

        return TemplateResponse(request, "navbar/partials/workshop_select.html", {})
