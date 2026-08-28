from __future__ import annotations

import logging
from typing import cast

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.budget.models import Budget
from apps.core.infrastructure.services.signature import build_signature_whatsapp_skip_note
from apps.core.infrastructure.services.signature_download import download_signed_pdf
from apps.core.domain.contracts.signature import SignatureServiceError
from apps.core.presentation.mixins import HtmxDeleteResponseMixin, HtmxTemplateResponseMixin, PageFavoriteMixin
from apps.core.presentation.navigation import TERM_CREATE_FAVORITE_PAGE
from apps.core.presentation.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.terms.documents import render_term_signature_html
from apps.terms.forms import TermTemplateForm
from apps.terms.models import BudgetTermSigning, TermBullet, TermKind, TermSource, TermSignatureStatus, TermTemplate, TermTopic
from apps.terms.util import (
    build_showtoast_trigger,
    can_toggle_term_signed_pdf,
    extract_term_sections,
    new_topic_key,
    resolve_term_modal_urls,
    term_signature_status_badge,
)
from apps.terms.services.files import (
    StoredTermFile,
    TermFileStorageError,
    delete_term_pdf_file,
    read_term_pdf_file,
)
from apps.terms.services.signature import TermSignatureError, send_term_for_signature
from apps.workshops.mixin import WorkshopScopedMixin
from apps.workshops.services.synplaisign import WorkshopSynplaiSignError, get_workshop_synplaisign_api_key

logger = logging.getLogger(__name__)


def _showtoast_trigger(toast_type: str, message: str) -> str:
    return build_showtoast_trigger(toast_type, message)


def _safe_delete_term_file(*, file_id: str) -> None:
    if not str(file_id or "").strip():
        return
    try:
        delete_term_pdf_file(file_id=file_id)
    except TermFileStorageError:
        return


def _replace_term_sections(*, template: TermTemplate, source: str, post_data) -> None:
    template.topics.all().delete()
    if source != TermSource.HTML:
        return
    sections = extract_term_sections(post_data)
    for topic_index, section in enumerate(sections):
        topic = TermTopic.objects.create(template=template, title=section["title"], order=topic_index)
        for item_index, text in enumerate(section["items"]):
            TermBullet.objects.create(topic=topic, text=text, order=item_index)


def _delete_files_after_commit(file_ids: list[str]) -> None:
    for file_id in file_ids:
        _safe_delete_term_file(file_id=file_id)


def _apply_source_fields(*, template: TermTemplate, source: str, staged_file: StoredTermFile | None) -> None:
    template.source = source
    if source == TermSource.PDF and staged_file is not None:
        template.pdf_file_key = staged_file.file_id
        template.pdf_file_name = staged_file.filename
        template.pdf_content_type = staged_file.content_type
        template.pdf_uploaded_at = staged_file.uploaded_at
        template.body_html = ""
        return
    if source == TermSource.HTML:
        template.pdf_file_key = ""
        template.pdf_file_name = ""
        template.pdf_content_type = ""
        template.pdf_uploaded_at = None
        template.body_html = ""
        return


class TermTemplateListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = TermTemplate
    template_name = "terms/term_list.html"
    context_object_name = "terms"
    htmx_template_name = "terms/partials/term_table.html"

    def get_queryset(self):
        return super().get_queryset().order_by("-criado_em")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["fields"] = [
            TableColumn(str(TermTemplate.name.field.verbose_name), attr=TermTemplate.name.field.name),
            TableColumn(str(TermTemplate.kind.field.verbose_name), attr="get_kind_display"),
            TableColumn(str(TermTemplate.source.field.verbose_name), attr="get_source_display"),
            TableColumn(str(TermTemplate.is_active.field.verbose_name), attr=TermTemplate.is_active.field.name),
        ]
        context["actions"] = [
            TableActionDefaults.view(
                "terms:term_preview_modal",
                hx_target="#modal-container",
                hx_swap="innerHTML",
                hx_push_url="false",
            ),
            TableActionDefaults.edit("terms:term_update"),
            TableActionDefaults.delete("terms:term_delete"),
        ]
        return context


class TermTemplatePreviewModalView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = TermTemplate
    workshop_permission_codename = "view_termtemplate"

    def get(self, request, pk):
        term = get_object_or_404(TermTemplate, pk=pk, workshop=self.workshop)
        context = {
            "term": term,
            "preview_url": reverse("terms:term_preview", args=[term.pk]),
        }
        return render(request, "terms/partials/term_preview_modal.html", context)


@method_decorator(xframe_options_exempt, name="dispatch")
class TermTemplatePreviewView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = TermTemplate
    workshop_permission_codename = "view_termtemplate"

    def get(self, request, pk):
        term = get_object_or_404(TermTemplate.objects.prefetch_related("topics__bullets"), pk=pk, workshop=self.workshop)
        if term.source == TermSource.PDF:
            file_id = str(term.pdf_file_key or "").strip()
            if not file_id:
                return HttpResponse("Termo sem PDF importado.", status=404)
            try:
                stored_pdf = read_term_pdf_file(file_id=file_id)
            except TermFileStorageError as exc:
                return HttpResponse(str(exc), status=404)
            response = HttpResponse(stored_pdf.content, content_type="application/pdf")
            response["Content-Disposition"] = f'inline; filename="{stored_pdf.filename}"'
            return response

        html = render_term_signature_html(template=term, budget=None, request=request)
        return HttpResponse(html)


class TermTemplateCreateView(PageFavoriteMixin, LoginRequiredMixin, WorkshopScopedMixin, CreateView):
    model = TermTemplate
    form_class = TermTemplateForm
    template_name = "terms/term_create.html"
    success_url = reverse_lazy("terms:term_list")
    favorite_page_definition = TERM_CREATE_FAVORITE_PAGE

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def form_valid(self, form):
        try:
            sections = extract_term_sections(self.request.POST)
        except ValueError as error:
            form.add_error(None, str(error))
            return self.form_invalid(form)
        if not sections:
            form.add_error(None, "Adicione pelo menos um tópico com texto.")
            return self.form_invalid(form)

        with transaction.atomic():
            term = cast(TermTemplate, form.save(commit=False))
            term.workshop = self.workshop
            _apply_source_fields(template=term, source=TermSource.HTML, staged_file=None)
            term.save()
            _replace_term_sections(template=term, source=TermSource.HTML, post_data=self.request.POST)
            self.object = term
        return HttpResponseRedirect(self.get_success_url())


class TermTemplateUpdateView(LoginRequiredMixin, WorkshopScopedMixin, UpdateView):
    model = TermTemplate
    form_class = TermTemplateForm
    template_name = "terms/term_update.html"
    success_url = reverse_lazy("terms:term_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def form_valid(self, form):
        previous_file_id = str(self.object.pdf_file_key or "").strip()
        try:
            sections = extract_term_sections(self.request.POST)
        except ValueError as error:
            form.add_error(None, str(error))
            return self.form_invalid(form)
        if not sections:
            form.add_error(None, "Adicione pelo menos um tópico com texto.")
            return self.form_invalid(form)

        files_to_remove: list[str] = []
        with transaction.atomic():
            term = cast(TermTemplate, form.save(commit=False))
            term.workshop = self.workshop
            _apply_source_fields(template=term, source=TermSource.HTML, staged_file=None)
            if previous_file_id:
                files_to_remove.append(previous_file_id)
            term.save()
            _replace_term_sections(template=term, source=TermSource.HTML, post_data=self.request.POST)
            self.object = term
            if files_to_remove:
                transaction.on_commit(lambda: _delete_files_after_commit(files_to_remove))
        return HttpResponseRedirect(self.get_success_url())


class TermTemplateDeleteView(LoginRequiredMixin, WorkshopScopedMixin, HtmxDeleteResponseMixin, DeleteView):
    model = TermTemplate
    success_url = reverse_lazy("terms:term_list")
    htmx_template_name = "terms/partials/term_delete_modal.html"
    htmx_trigger = "terms-table-refresh"

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        file_id = str(self.object.pdf_file_key or "").strip()
        response = super().delete(request, *args, **kwargs)
        _safe_delete_term_file(file_id=file_id)
        return response


class AddTermTopicView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = TermTemplate
    workshop_permission_codename = "add_termtemplate"

    def post(self, request):
        return render(
            request,
            "terms/partials/topic_card.html",
            {"topic_key": new_topic_key(), "title": "", "items": [""]},
        )


class AddTermItemView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = TermTemplate
    workshop_permission_codename = "add_termtemplate"

    def post(self, request):
        topic_key = str(request.POST.get("topic_key") or "").strip()
        if not topic_key:
            response = HttpResponse("", status=200)
            response["HX-Trigger"] = _showtoast_trigger("warning", "Não foi possível adicionar o texto neste tópico.")
            return response
        return render(request, "terms/partials/topic_item_row.html", {"topic_key": topic_key, "item_text": ""})


class BudgetTermMixin(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Budget
    workshop_permission_app_label = "budget"
    workshop_permission_model = "budget"
    workshop_permission_codename = "change_budget"

    def _get_budget(self, budget_id: int) -> Budget:
        return get_object_or_404(
            Budget.objects.select_related("customer", "vehicle", "workshop"),
            pk=budget_id,
            workshop=self.workshop,
        )


def _render_budget_term_modal(*, request, workshop, budget, template_id: int | None = None):
    templates = list(
        TermTemplate.objects.filter(
            workshop=workshop,
            is_active=True,
            kind__in=[TermKind.RECEIPT, TermKind.WARRANTY],
        ).order_by("name")
    )
    selected = None
    if template_id is not None:
        selected = next((item for item in templates if item.pk == template_id), None)
    elif len(templates) == 1:
        selected = templates[0]

    signing = None
    term_modal_urls = None
    signature_status_badge = term_signature_status_badge(None)
    if selected is not None:
        signing = BudgetTermSigning.objects.filter(budget=budget, template=selected).first()
        signature_status_badge = term_signature_status_badge(signing)
        can_toggle = can_toggle_term_signed_pdf(signing)
        term_modal_urls = resolve_term_modal_urls(
            budget_id=budget.pk,
            template_id=selected.pk,
            can_toggle_signed_pdf=can_toggle,
        )

    return render(
        request,
        "terms/partials/budget_term_modal.html",
        {
            "budget": budget,
            "templates": templates,
            "selected": selected,
            "signing": signing,
            "signature_status_badge": signature_status_badge,
            "term_modal_urls": term_modal_urls,
        },
    )


class BudgetTermModalView(BudgetTermMixin):
    def get(self, request, budget_id: int, template_id: int | None = None):
        budget = self._get_budget(budget_id)
        return _render_budget_term_modal(request=request, workshop=self.workshop, budget=budget, template_id=template_id)


@method_decorator(xframe_options_exempt, name="dispatch")
class BudgetTermPreviewView(BudgetTermMixin):
    def get(self, request, budget_id: int, template_id: int):
        budget = self._get_budget(budget_id)
        template = get_object_or_404(TermTemplate.objects.prefetch_related("topics__bullets"), pk=template_id, workshop=self.workshop)
        if template.source == TermSource.PDF:
            file_id = str(template.pdf_file_key or "").strip()
            if not file_id:
                return HttpResponse("Termo sem PDF importado.", status=404)
            try:
                stored_pdf = read_term_pdf_file(file_id=file_id)
            except TermFileStorageError as exc:
                return HttpResponse(str(exc), status=404)
            response = HttpResponse(stored_pdf.content, content_type="application/pdf")
            response["Content-Disposition"] = f'inline; filename="{stored_pdf.filename}"'
            return response
        html = render_term_signature_html(template=template, budget=budget, request=request)
        return HttpResponse(html)


class BudgetTermSendView(BudgetTermMixin):
    def post(self, request, budget_id: int, template_id: int):
        budget = self._get_budget(budget_id)
        template = get_object_or_404(TermTemplate.objects.prefetch_related("topics__bullets"), pk=template_id, workshop=self.workshop, is_active=True)
        if not template.can_send_for_signature:
            response = HttpResponse("", status=200)
            response["HX-Trigger"] = _showtoast_trigger("warning", "Este termo não pode ser enviado para assinatura.")
            return response

        with transaction.atomic():
            signing, _created = BudgetTermSigning.objects.select_for_update().get_or_create(
                budget=budget,
                template=template,
                defaults={"workshop": self.workshop},
            )
            if signing.signature_request_status == TermSignatureStatus.SENDING:
                response = HttpResponse("", status=200)
                response["HX-Trigger"] = _showtoast_trigger("info", "O envio do termo ainda está em processamento.")
                return response
            if signing.signature_request_status == TermSignatureStatus.APPROVED:
                response = HttpResponse("", status=200)
                response["HX-Trigger"] = _showtoast_trigger("info", "Este termo já foi assinado.")
                return response
            is_resend = signing.can_resend
            signing.mark_signature_sending()

        try:
            result = send_term_for_signature(budget=budget, template=template, request=request)
        except TermSignatureError as exc:
            signing.mark_signature_failed()
            logger.exception("term_signature_send_failed", extra={"budget_id": budget.pk, "template_id": template.pk})
            response = HttpResponse("", status=200)
            response["HX-Trigger"] = _showtoast_trigger("error", str(exc))
            return response

        signing.rendered_html = render_term_signature_html(template=template, budget=budget, request=request)
        signing.save(update_fields=["rendered_html"])
        signing.mark_signature_sent(result.envelope_id, document_id=result.document_id)

        message = "Termo reenviado para assinatura do cliente." if is_resend else "Termo enviado para assinatura do cliente."
        customer_phone = getattr(budget.customer, "phone", "") if budget.customer else ""
        message += build_signature_whatsapp_skip_note(workshop=budget.workshop, phone=customer_phone)
        html_response = _render_budget_term_modal(
            request=request,
            workshop=self.workshop,
            budget=budget,
            template_id=template_id,
        )
        html_response["HX-Trigger"] = _showtoast_trigger("success", message)
        return html_response


class BudgetTermSignedPdfView(BudgetTermMixin):
    workshop_permission_codename = "view_budget"

    def get(self, request, budget_id: int, template_id: int):
        budget = self._get_budget(budget_id)
        template = get_object_or_404(TermTemplate, pk=template_id, workshop=self.workshop)
        signing = get_object_or_404(BudgetTermSigning, budget=budget, template=template)
        if not signing.signature_external_id and not signing.signature_document_id:
            return HttpResponse("Termo ainda não possui documento assinado.", status=404)
        try:
            api_key = get_workshop_synplaisign_api_key(budget.workshop)
            pdf_bytes = download_signed_pdf(
                document_id=signing.signature_document_id or None,
                envelope_id=signing.signature_external_id or None,
                synplaisign_api_key=api_key,
            )
        except (WorkshopSynplaiSignError, SignatureServiceError) as exc:
            return HttpResponse(str(exc) or "Erro ao carregar PDF assinado", status=502)
        should_download = request.GET.get("download") == "1"
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        disposition = "attachment" if should_download else "inline"
        response["Content-Disposition"] = f'{disposition}; filename="termo-{template.pk}-orcamento-{budget.pk}.pdf"'
        return response
