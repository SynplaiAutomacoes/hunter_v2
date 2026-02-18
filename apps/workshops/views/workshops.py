from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpResponse
from django.template.response import TemplateResponse
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.iam.utils import get_or_create_director_role
from apps.core.views import HtmxDeleteResponseMixin, HtmxTemplateResponseMixin
from apps.core.templatetags.table_tags import TableColumn
from apps.core.tables import TableActionDefaults
from apps.workshops.forms.workshops import WorkshopForm
from apps.workshops.models.workshops import Workshop
from apps.collaborators.models import WorkshopMember
from apps.workshops.util.monthly_costs import create_default_monthly_costs


# TODO: Não permitir nome igual de oficina
class WorkshopCreateView(LoginRequiredMixin, CreateView):
    model = Workshop
    form_class = WorkshopForm
    template_name = "workshops/workshop_create.html"
    success_url = reverse_lazy("workshops:list")

    def dispatch(self, request, *args, **kwargs):
        if request.user.account.owner_id != request.user.id:
            raise PermissionDenied

        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
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

            create_default_monthly_costs(workshop=self.object)

        return response


class WorkshopUpdateView(LoginRequiredMixin, UpdateView):
    model = Workshop
    form_class = WorkshopForm
    template_name = "workshops/workshop_update.html"
    success_url = reverse_lazy("workshops:list")

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .filter(
                members__user=self.request.user,
                members__is_active=True,
                members__role__permissions__content_type__app_label="workshops",
                members__role__permissions__content_type__model="workshop",
                members__role__permissions__codename="change_workshop",
            )
            .distinct()
        )


class WorkshopDeleteView(LoginRequiredMixin, HtmxDeleteResponseMixin, DeleteView):
    model = Workshop
    success_url = reverse_lazy("workshops:list")

    htmx_template_name = "workshops/partials/workshop_delete_modal.html"
    htmx_trigger = "workshops-table-refresh"

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .filter(
                members__user=self.request.user,
                members__is_active=True,
                members__role__permissions__content_type__app_label="workshops",
                members__role__permissions__content_type__model="workshop",
                members__role__permissions__codename="delete_workshop",
            )
            .distinct()
        )


class WorkshopListView(LoginRequiredMixin, HtmxTemplateResponseMixin, ListView):
    model = Workshop
    template_name = "workshops/workshop_list.html"
    context_object_name = "workshops"

    htmx_template_name = "workshops/partials/workshop_table.html"

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .filter(
                members__user=self.request.user,
                members__is_active=True,
                members__role__permissions__content_type__app_label="workshops",
                members__role__permissions__content_type__model="workshop",
                members__role__permissions__codename="view_workshop",
            )
            .distinct()
        )

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
                label=Workshop.phone.field.verbose_name,
                attr=Workshop.phone.field.name,
                format="phone",
            ),
            TableColumn(
                label=Workshop.address.field.verbose_name,
                attr=Workshop.address.field.name,
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


class NavbarWorkshopSelectView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        workshop_id = request.POST.get("workshop_id")

        if workshop_id:
            try:
                workshop_id_int = int(workshop_id)
            except (TypeError, ValueError):
                workshop_id_int = None

            if workshop_id_int is not None and Workshop.objects.filter(pk=workshop_id_int, account=request.user.account, is_active=True).exists():
                if not WorkshopMember.objects.filter(user=request.user, workshop_id=workshop_id_int, is_active=True, workshop__is_active=True).exists():
                    request.session.pop("active_workshop_id", None)
                    return TemplateResponse(request, "navbar/partials/workshop_select.html", {})

                request.session["active_workshop_id"] = workshop_id_int
            else:
                request.session.pop("active_workshop_id", None)

        response = HttpResponse()
        response["HX-Refresh"] = "true"
        return response
