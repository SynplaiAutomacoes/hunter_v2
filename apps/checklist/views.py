import json
from itertools import zip_longest

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.core.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.core.views import HtmxDeleteResponseMixin, HtmxTemplateResponseMixin
from apps.workshops.mixin import WorkshopScopedMixin

from .forms import ChecklistForm
from .models import Checklist, ChecklistItem

VALID_RESPONSE_TYPES = {choice[0] for choice in ChecklistItem.TIPO_RESPOSTA_CHOICES}


def _extract_checklist_items(post_data):
    agrupamentos = post_data.getlist("agrupamento")
    descricoes = post_data.getlist("descricao")
    tipos = post_data.getlist("tipo_resposta")

    parsed_items = []
    for group, description, response_type in zip_longest(agrupamentos, descricoes, tipos, fillvalue=""):
        cleaned_group = (group or "").strip()
        cleaned_description = (description or "").strip()
        cleaned_response_type = (response_type or "").strip()

        if not cleaned_description:
            continue
        if not cleaned_group:
            raise ValueError("Todos os itens devem possuir um agrupamento.")
        if cleaned_response_type not in VALID_RESPONSE_TYPES:
            continue

        parsed_items.append(
            {
                "group": cleaned_group,
                "description": cleaned_description,
                "response_type": cleaned_response_type,
            }
        )

    return parsed_items


class ChecklistListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = Checklist
    template_name = "checklists/checklist_list.html"
    context_object_name = "checklists"
    htmx_template_name = "checklists/partials/checklist_table.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["fields"] = [
            TableColumn(Checklist.name.field.verbose_name, attr=Checklist.name.field.name),
            TableColumn(Checklist.criado_em.field.verbose_name, attr=Checklist.criado_em.field.name),
        ]
        context["actions"] = [
            TableActionDefaults.edit("checklist:checklist_update"),
            TableActionDefaults.delete("checklist:checklist_delete"),
        ]
        return context


class ChecklistCreateView(LoginRequiredMixin, WorkshopScopedMixin, CreateView):
    model = Checklist
    form_class = ChecklistForm
    template_name = "checklists/checklist_create.html"
    success_url = reverse_lazy("checklist:checklist_list")

    def form_valid(self, form):
        try:
            checklist_items = _extract_checklist_items(self.request.POST)
        except ValueError as error:
            form.add_error(None, str(error))
            return self.form_invalid(form)

        with transaction.atomic():
            form.instance.workshop = self.workshop
            response = super().form_valid(form)

            ChecklistItem.objects.bulk_create(
                [
                    ChecklistItem(
                        checklist=self.object,
                        group=item["group"],
                        description=item["description"],
                        response_type=item["response_type"],
                        order=index,
                    )
                    for index, item in enumerate(checklist_items)
                ]
            )
            return response


class ChecklistUpdateView(LoginRequiredMixin, WorkshopScopedMixin, UpdateView):
    model = Checklist
    form_class = ChecklistForm
    template_name = "checklists/checklist_update.html"
    success_url = reverse_lazy("checklist:checklist_list")

    def form_valid(self, form):
        try:
            checklist_items = _extract_checklist_items(self.request.POST)
        except ValueError as error:
            form.add_error(None, str(error))
            return self.form_invalid(form)

        with transaction.atomic():
            response = super().form_valid(form)
            self.object.items.all().delete()

            ChecklistItem.objects.bulk_create(
                [
                    ChecklistItem(
                        checklist=self.object,
                        group=item["group"],
                        description=item["description"],
                        response_type=item["response_type"],
                        order=index,
                    )
                    for index, item in enumerate(checklist_items)
                ]
            )
            return response


class ChecklistDeleteView(LoginRequiredMixin, WorkshopScopedMixin, HtmxDeleteResponseMixin, DeleteView):
    model = Checklist
    success_url = reverse_lazy("checklist:checklist_list")
    htmx_template_name = "checklists/partials/checklist_delete_modal.html"
    htmx_trigger = "checklists-table-refresh"


class AddChecklistItemRowView(LoginRequiredMixin, View):
    def post(self, request):
        group = (request.POST.get("agrupamento_input") or "").strip()
        description = (request.POST.get("item_input") or "").strip()
        response_type = (request.POST.get("tipo_resposta_select") or "").strip()

        if not group:
            response = HttpResponse("", status=200)
            response["HX-Trigger"] = json.dumps(
                {
                    "showToast": {
                        "type": "warning",
                        "message": "Informe o agrupamento antes de adicionar ao checklist.",
                    }
                }
            )
            return response

        if not description:
            response = HttpResponse("", status=200)
            response["HX-Trigger"] = json.dumps(
                {
                    "showToast": {
                        "type": "warning",
                        "message": "Informe o item antes de adicionar ao checklist.",
                    }
                }
            )
            return response

        if response_type not in VALID_RESPONSE_TYPES:
            response = HttpResponse("", status=200)
            response["HX-Trigger"] = json.dumps(
                {
                    "showToast": {
                        "type": "warning",
                        "message": "Selecione um tipo de resposta valido para o item.",
                    }
                }
            )
            return response

        response_type_display = dict(ChecklistItem.TIPO_RESPOSTA_CHOICES).get(response_type)

        context = {
            "group": group,
            "description": description,
            "response_type": response_type,
            "response_type_display": response_type_display,
        }

        return render(request, "checklists/partials/item_row.html", context)
