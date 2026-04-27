from typing import cast

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.core.navigation import CHECKLIST_CREATE_FAVORITE_PAGE
from apps.core.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.core.views import HtmxDeleteResponseMixin, HtmxTemplateResponseMixin, PageFavoriteMixin
from apps.workshops.mixin import WorkshopScopedMixin

from .forms import ChecklistForm
from .models import Checklist, ChecklistItem
from .services.files import (
    ChecklistFileStorageError,
    StoredChecklistFile,
    delete_checklist_pdf_file,
    read_checklist_pdf_file,
    save_checklist_pdf_file,
)
from .util import extract_checklist_items, VALID_RESPONSE_TYPES, build_showtoast_trigger


class ChecklistListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = Checklist
    template_name = "checklists/checklist_list.html"
    context_object_name = "checklists"
    htmx_template_name = "checklists/partials/checklist_table.html"

    def get_queryset(self):
        return super().get_queryset().order_by("-criado_em")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["fields"] = [
            TableColumn(str(Checklist.name.field.verbose_name), attr=Checklist.name.field.name),
            TableColumn(str(Checklist.checklist_type.field.verbose_name), attr="get_checklist_type_display"),
            TableColumn(str(Checklist.criado_em.field.verbose_name), attr=Checklist.criado_em.field.name),
        ]
        context["actions"] = [
            TableActionDefaults.view(
                "checklist:checklist_preview_modal",
                hx_target="#modal-container",
                hx_swap="innerHTML",
                hx_push_url="false",
            ),
            TableActionDefaults.edit("checklist:checklist_update"),
            TableActionDefaults.delete("checklist:checklist_delete"),
        ]
        return context


class ChecklistPreviewModalView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Checklist
    workshop_permission_codename = "view_checklist"

    def get(self, request, pk):
        checklist = get_object_or_404(Checklist, pk=pk, workshop=self.workshop)
        context = {
            "checklist": checklist,
            "preview_url": reverse("checklist:checklist_preview", args=[checklist.pk]),
        }
        return render(request, "checklists/partials/checklist_preview_modal.html", context)


@method_decorator(xframe_options_exempt, name="dispatch")
class ChecklistPreviewView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Checklist
    workshop_permission_codename = "view_checklist"

    def get(self, request, pk):
        checklist = get_object_or_404(Checklist.objects.prefetch_related("items"), pk=pk, workshop=self.workshop)

        if checklist.source == Checklist.ChecklistSource.PDF:
            file_id = str(checklist.pdf_file_key or "").strip()
            if not file_id:
                return HttpResponse("Checklist sem PDF importado.", status=404)

            try:
                stored_pdf = read_checklist_pdf_file(file_id=file_id)
            except ChecklistFileStorageError as exc:
                return HttpResponse(str(exc), status=404)

            response = HttpResponse(stored_pdf.content, content_type="application/pdf")
            response["Content-Disposition"] = f'inline; filename="{stored_pdf.filename}"'
            return response

        checklist_rows = []
        group_number_by_name: dict[str, int] = {}
        item_counter_by_group: dict[str, int] = {}
        next_group_number = 1

        for checklist_item in checklist.items.all().order_by("order", "id"):
            group_name = (checklist_item.group or "").strip() or "Geral"
            item_description = (checklist_item.description or "").strip() or "-"

            if group_name not in group_number_by_name:
                group_number_by_name[group_name] = next_group_number
                item_counter_by_group[group_name] = 0
                next_group_number += 1

            item_counter_by_group[group_name] += 1
            group_number = group_number_by_name[group_name]
            item_number_in_group = item_counter_by_group[group_name]
            checklist_rows.append(
                {
                    "index": f"{group_number}.{item_number_in_group}",
                    "description": f"{group_name} - {item_description}",
                    "response_type": checklist_item.response_type,
                }
            )

        return render(
            request,
            "checklists/checklist_preview.html",
            {
                "checklist": checklist,
                "checklist_rows": checklist_rows,
            },
        )


class ChecklistCreateView(PageFavoriteMixin, LoginRequiredMixin, WorkshopScopedMixin, CreateView):
    model = Checklist
    form_class = ChecklistForm
    template_name = "checklists/checklist_create.html"
    success_url = reverse_lazy("checklist:checklist_list")
    favorite_page_definition = CHECKLIST_CREATE_FAVORITE_PAGE

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def form_valid(self, form):
        try:
            checklist_items = extract_checklist_items(self.request.POST)
        except ValueError as error:
            form.add_error(None, str(error))
            return self.form_invalid(form)

        checklist_source = form.cleaned_data["source"]
        uploaded_pdf = form.cleaned_data.get("imported_pdf")

        if checklist_source == Checklist.ChecklistSource.MANUAL and not checklist_items:
            form.add_error(None, "Adicione itens para criar o checklist manual.")
            return self.form_invalid(form)

        if checklist_source == Checklist.ChecklistSource.PDF and uploaded_pdf is None:
            form.add_error("imported_pdf", "Envie um arquivo PDF para importar o checklist.")
            return self.form_invalid(form)

        staged_file: StoredChecklistFile | None = None
        if checklist_source == Checklist.ChecklistSource.PDF and uploaded_pdf is not None:
            try:
                staged_file = save_checklist_pdf_file(workshop_id=self.workshop.pk, uploaded_file=uploaded_pdf)
            except ChecklistFileStorageError as error:
                form.add_error("imported_pdf", str(error))
                return self.form_invalid(form)

        with transaction.atomic():
            try:
                checklist_obj = cast(Checklist, form.save(commit=False))
                checklist_obj.workshop = self.workshop
                checklist_obj.source = checklist_source

                if checklist_source == Checklist.ChecklistSource.PDF and staged_file is not None:
                    checklist_obj.pdf_file_key = staged_file.file_id
                    checklist_obj.pdf_file_name = staged_file.filename
                    checklist_obj.pdf_content_type = staged_file.content_type
                    checklist_obj.pdf_uploaded_at = staged_file.uploaded_at
                else:
                    checklist_obj.pdf_file_key = ""
                    checklist_obj.pdf_file_name = ""
                    checklist_obj.pdf_content_type = ""
                    checklist_obj.pdf_uploaded_at = None

                checklist_obj.save()
                self.object = checklist_obj

                if checklist_source == Checklist.ChecklistSource.MANUAL:
                    ChecklistItem.objects.bulk_create(
                        [
                            ChecklistItem(
                                checklist=checklist_obj,
                                group=item["group"],
                                description=item["description"],
                                response_type=item["response_type"],
                                order=index,
                            )
                            for index, item in enumerate(checklist_items)
                        ]
                    )
            except Exception:
                if staged_file is not None:
                    _safe_delete_checklist_file(file_id=staged_file.file_id)
                raise

        return HttpResponseRedirect(self.get_success_url())


class ChecklistUpdateView(LoginRequiredMixin, WorkshopScopedMixin, UpdateView):
    model = Checklist
    form_class = ChecklistForm
    template_name = "checklists/checklist_update.html"
    success_url = reverse_lazy("checklist:checklist_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def form_valid(self, form):
        try:
            checklist_items = extract_checklist_items(self.request.POST)
        except ValueError as error:
            form.add_error(None, str(error))
            return self.form_invalid(form)

        previous_file_id = str(self.object.pdf_file_key or "").strip()
        checklist_source = form.cleaned_data["source"]
        uploaded_pdf = form.cleaned_data.get("imported_pdf")

        if checklist_source == Checklist.ChecklistSource.MANUAL and not checklist_items:
            form.add_error(None, "Adicione itens para criar o checklist manual.")
            return self.form_invalid(form)

        if checklist_source == Checklist.ChecklistSource.PDF and uploaded_pdf is None and not previous_file_id:
            form.add_error("imported_pdf", "Envie um arquivo PDF para importar o checklist.")
            return self.form_invalid(form)

        staged_file: StoredChecklistFile | None = None
        if checklist_source == Checklist.ChecklistSource.PDF and uploaded_pdf is not None:
            try:
                staged_file = save_checklist_pdf_file(workshop_id=self.workshop.pk, uploaded_file=uploaded_pdf)
            except ChecklistFileStorageError as error:
                form.add_error("imported_pdf", str(error))
                return self.form_invalid(form)

        with transaction.atomic():
            try:
                checklist_obj = cast(Checklist, form.save(commit=False))
                checklist_obj.workshop = self.workshop
                checklist_obj.source = checklist_source
                checklist_obj.save()
                self.object = checklist_obj

                ChecklistItem.objects.filter(checklist=checklist_obj).delete()
                files_to_remove_after_commit: list[str] = []

                if checklist_source == Checklist.ChecklistSource.MANUAL:
                    ChecklistItem.objects.bulk_create(
                        [
                            ChecklistItem(
                                checklist=checklist_obj,
                                group=item["group"],
                                description=item["description"],
                                response_type=item["response_type"],
                                order=index,
                            )
                            for index, item in enumerate(checklist_items)
                        ]
                    )

                    if previous_file_id:
                        files_to_remove_after_commit.append(previous_file_id)

                    checklist_obj.pdf_file_key = ""
                    checklist_obj.pdf_file_name = ""
                    checklist_obj.pdf_content_type = ""
                    checklist_obj.pdf_uploaded_at = None
                    checklist_obj.save(update_fields=["pdf_file_key", "pdf_file_name", "pdf_content_type", "pdf_uploaded_at"])
                elif staged_file is not None:
                    checklist_obj.pdf_file_key = staged_file.file_id
                    checklist_obj.pdf_file_name = staged_file.filename
                    checklist_obj.pdf_content_type = staged_file.content_type
                    checklist_obj.pdf_uploaded_at = staged_file.uploaded_at
                    checklist_obj.save(update_fields=["pdf_file_key", "pdf_file_name", "pdf_content_type", "pdf_uploaded_at"])
                    if previous_file_id and previous_file_id != staged_file.file_id:
                        files_to_remove_after_commit.append(previous_file_id)

                if files_to_remove_after_commit:
                    transaction.on_commit(lambda: _delete_files_after_commit(files_to_remove_after_commit))
            except Exception:
                if staged_file is not None:
                    _safe_delete_checklist_file(file_id=staged_file.file_id)
                raise

        return HttpResponseRedirect(self.get_success_url())


class ChecklistDeleteView(LoginRequiredMixin, WorkshopScopedMixin, HtmxDeleteResponseMixin, DeleteView):
    model = Checklist
    success_url = reverse_lazy("checklist:checklist_list")
    htmx_template_name = "checklists/partials/checklist_delete_modal.html"
    htmx_trigger = "checklists-table-refresh"

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        file_id = str(self.object.pdf_file_key or "").strip()
        response = super().delete(request, *args, **kwargs)
        _safe_delete_checklist_file(file_id=file_id)
        return response


class AddChecklistItemRowView(LoginRequiredMixin, View):
    def post(self, request):
        group = (request.POST.get("agrupamento_input") or "").strip()
        description = (request.POST.get("item_input") or "").strip()
        response_type = (request.POST.get("tipo_resposta_select") or "").strip()

        if not group:
            response = HttpResponse("", status=200)
            response["HX-Trigger"] = build_showtoast_trigger("warning", "Informe o agrupamento antes de adicionar ao checklist.")
            return response

        if not description:
            response = HttpResponse("", status=200)
            response["HX-Trigger"] = build_showtoast_trigger("warning", "Informe o item antes de adicionar ao checklist.")
            return response

        if response_type not in VALID_RESPONSE_TYPES:
            response = HttpResponse("", status=200)
            response["HX-Trigger"] = build_showtoast_trigger("warning", "Selecione um tipo de resposta valido para o item.")
            return response

        response_type_display = dict(ChecklistItem.TIPO_RESPOSTA_CHOICES).get(response_type)

        context = {
            "group": group,
            "description": description,
            "response_type": response_type,
            "response_type_display": response_type_display,
        }

        return render(request, "checklists/partials/item_row.html", context)


def _safe_delete_checklist_file(*, file_id: str) -> None:
    if not str(file_id or "").strip():
        return

    try:
        delete_checklist_pdf_file(file_id=file_id)
    except ChecklistFileStorageError:
        return


def _delete_files_after_commit(file_ids: list[str]) -> None:
    for file_id in file_ids:
        _safe_delete_checklist_file(file_id=file_id)
