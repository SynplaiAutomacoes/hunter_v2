from __future__ import annotations

import logging
from typing import Any

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import QuerySet
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views import View
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.budget.models import Budget, SignatureStatus
from apps.core.domain.contracts.documents import DocumentPayload, SignatureTokenError
from apps.core.domain.contracts.signature import SignatureServiceError
from apps.core.infrastructure.pdf.renderer import build_pdf_http_response
from apps.core.infrastructure.providers import get_signature_service
from apps.core.infrastructure.services.signature_download import download_signed_pdf
from apps.workshops.services.synplaisign import WorkshopSynplaiSignError, get_workshop_synplaisign_api_key
from apps.core.infrastructure.query_filters import QueryParamFilter, apply_query_param_filters
from apps.core.infrastructure.search import apply_text_search
from apps.core.presentation.mixins import HtmxDeleteResponseMixin, HtmxTemplateResponseMixin
from apps.core.presentation.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.terms.documents.provider import render_term_pdf_document
from apps.terms.forms import WorkshopTermTemplateForm
from apps.terms.models import BudgetTermSigning, TermTemplateType, WorkOrderTermSigning, WorkshopTermTemplate
from apps.terms.pdf_context import build_term_pdf_context
from apps.terms.selectors import get_default_term_template, update_budget_term_template, update_workorder_term_template
from apps.terms.services.signature import (
    BUDGET_TERM_SIGNATURE_DOCUMENT_ID_KEY,
    BUDGET_TERM_SIGNATURE_TOKEN_SALT,
    WORKORDER_TERM_SIGNATURE_DOCUMENT_ID_KEY,
    WORKORDER_TERM_SIGNATURE_TOKEN_SALT,
    TermSignatureError,
    send_budget_term_for_signature,
    send_workorder_term_for_signature,
)
from apps.workorder.models import WorkOrder
from apps.workshops.mixin import WorkshopScopedMixin
from apps.workshops.util.workshops import get_active_workshop_or_404


logger = logging.getLogger(__name__)


class WorkshopTermTemplateListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = WorkshopTermTemplate
    template_name = "terms/term_template_list.html"
    context_object_name = "term_templates"
    htmx_template_name = "terms/partials/term_template_table.html"

    def get_queryset(self) -> QuerySet[WorkshopTermTemplate]:
        queryset = super().get_queryset()
        search_query = str(self.request.GET.get("q") or "").strip()
        if search_query:
            queryset = apply_text_search(queryset, search_value=search_query, lookups=("name", "document_title"))
        queryset = apply_query_param_filters(
            queryset,
            params=self.request.GET,
            filter_configs=(
                QueryParamFilter(
                    param_name="template_type",
                    lookup="template_type",
                    kind="choice",
                    allowed_values=frozenset(str(choice.value) for choice in TermTemplateType),
                ),
                QueryParamFilter(param_name="is_active", lookup="is_active", kind="boolean"),
            ),
        )
        return queryset.order_by("template_type", "name")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["fields"] = [
            TableColumn("Nome", attr="name"),
            TableColumn("Tipo", attr="template_type_display", searchable=False),
            TableColumn("Padrão", attr="is_default"),
            TableColumn("Ativo", attr="is_active"),
            TableColumn("Criado em", attr="created_at_display"),
        ]
        context["actions"] = [
            TableActionDefaults.edit("terms:term_template_update"),
            TableActionDefaults.delete("terms:term_template_delete"),
        ]
        return context


class WorkshopTermTemplateCreateView(LoginRequiredMixin, WorkshopScopedMixin, CreateView):
    model = WorkshopTermTemplate
    form_class = WorkshopTermTemplateForm
    template_name = "terms/term_template_form.html"
    success_url = reverse_lazy("terms:term_template_list")

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def form_valid(self, form: WorkshopTermTemplateForm) -> HttpResponse:
        form.instance.workshop = self.workshop
        messages.success(self.request, "Termo cadastrado com sucesso.")
        return super().form_valid(form)


class WorkshopTermTemplateUpdateView(LoginRequiredMixin, WorkshopScopedMixin, UpdateView):
    model = WorkshopTermTemplate
    form_class = WorkshopTermTemplateForm
    template_name = "terms/term_template_form.html"
    success_url = reverse_lazy("terms:term_template_list")

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def form_valid(self, form: WorkshopTermTemplateForm) -> HttpResponse:
        messages.success(self.request, "Termo atualizado com sucesso.")
        return super().form_valid(form)


class WorkshopTermTemplateDeleteView(LoginRequiredMixin, WorkshopScopedMixin, HtmxDeleteResponseMixin, DeleteView):
    model = WorkshopTermTemplate
    success_url = reverse_lazy("terms:term_template_list")


class WorkshopTermTemplateDuplicateView(LoginRequiredMixin, WorkshopScopedMixin, View):
    def post(self, request, pk: int) -> HttpResponse:
        source = get_object_or_404(WorkshopTermTemplate, pk=pk, workshop=self.workshop)
        duplicate = WorkshopTermTemplate.objects.create(
            workshop=self.workshop,
            template_type=source.template_type,
            name=f"{source.name} (cópia)",
            document_title=source.document_title,
            subtitle=source.subtitle,
            intro_text=source.intro_text,
            primary_color=source.primary_color,
            accent_color=source.accent_color,
            text_color=source.text_color,
            muted_color=source.muted_color,
            is_active=True,
            is_default=False,
            content=source.content,
        )
        messages.success(request, f"Termo duplicado como “{duplicate.name}”.")
        return redirect("terms:term_template_update", pk=duplicate.pk)


@xframe_options_exempt
def term_template_preview(request, pk: int):
    workshop = get_active_workshop_or_404(request)
    term_template = get_object_or_404(WorkshopTermTemplate, pk=pk, workshop=workshop)
    context = build_term_pdf_context(term_template=term_template, workshop=workshop)
    return render(request, "terms/pdf/term_document.html", context)


@xframe_options_exempt
def budget_term_preview(request, budget_id: int):
    workshop = get_active_workshop_or_404(request)
    budget: Budget = get_object_or_404(Budget.objects.select_related("customer", "vehicle", "workshop"), pk=budget_id, workshop=workshop)
    term_template_id = request.GET.get("term_template")
    signing = BudgetTermSigning.objects.filter(budget=budget).select_related("term_template").first()
    if term_template_id and signing and not signing.is_signature_locked:
        try:
            signing = update_budget_term_template(budget=budget, term_template_id=int(term_template_id))
        except (ValueError, TypeError):
            pass
    elif signing is None and term_template_id:
        try:
            signing = update_budget_term_template(budget=budget, term_template_id=int(term_template_id))
        except (ValueError, TypeError):
            signing = None

    term_template = signing.term_template if signing else get_default_term_template(workshop=workshop, template_type=TermTemplateType.VEHICLE_RECEIPT)
    if term_template is None:
        raise Http404("Nenhum termo cadastrado.")

    snapshot = signing.content_snapshot if signing and signing.is_signature_locked and signing.content_snapshot else None
    context = build_term_pdf_context(
        term_template=term_template,
        snapshot=snapshot,
        workshop=workshop,
        customer=budget.customer,
        vehicle=budget.vehicle,
    )
    return render(request, "terms/pdf/term_document.html", context)


class SendBudgetTermSignatureView(LoginRequiredMixin, WorkshopScopedMixin, View):
    def post(self, request, budget_id: int) -> JsonResponse:
        budget: Budget = get_object_or_404(Budget.objects.select_related("customer", "workshop"), pk=budget_id, workshop=self.workshop)
        term_template_id = request.POST.get("term_template")
        try:
            signing = update_budget_term_template(
                budget=budget,
                term_template_id=int(term_template_id) if term_template_id else None,
            )
        except (ValueError, TypeError) as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)

        if signing is None:
            return JsonResponse({"ok": False, "error": "Selecione um termo de recebimento."}, status=400)

        if signing.signature_request_status == SignatureStatus.SENDING:
            return JsonResponse({"ok": False, "error": "O envio do termo ainda está em processamento."}, status=409)

        if signing.signature_request_status == SignatureStatus.APPROVED:
            return JsonResponse({"ok": False, "error": "Este termo já foi assinado."}, status=409)

        with transaction.atomic():
            locked = BudgetTermSigning.objects.select_for_update().get(pk=signing.pk)
            locked.mark_signature_sending()

        try:
            result = send_budget_term_for_signature(signing=locked)
        except TermSignatureError as exc:
            locked.mark_signature_failed()
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)

        locked.mark_signature_sent(result.envelope_id, document_id=result.document_id)
        locked.regenerate_signature_token()
        return JsonResponse({"ok": True, "message": "Termo enviado para assinatura do cliente."})


@xframe_options_exempt
def budget_term_signature_preview(request, token: str):
    try:
        payload = get_signature_service().parse_signature_token(
            token=token,
            token_salt=BUDGET_TERM_SIGNATURE_TOKEN_SALT,
            document_id_key=BUDGET_TERM_SIGNATURE_DOCUMENT_ID_KEY,
        )
    except SignatureTokenError as exc:
        raise Http404(str(exc)) from exc

    signing = get_object_or_404(
        BudgetTermSigning.objects.select_related("budget", "budget__customer", "budget__vehicle", "budget__workshop", "term_template"),
        pk=payload.document_id,
        signature_token_version=payload.version,
        signature_token_active=True,
    )
    context = build_term_pdf_context(
        term_template=signing.term_template,
        snapshot=signing.content_snapshot or None,
        workshop=signing.budget.workshop,
        customer=signing.budget.customer,
        vehicle=signing.budget.vehicle,
    )
    return render(request, "terms/pdf/term_document.html", context)


@xframe_options_exempt
def budget_term_signature_file(request, token: str):
    try:
        payload = get_signature_service().parse_signature_token(
            token=token,
            token_salt=BUDGET_TERM_SIGNATURE_TOKEN_SALT,
            document_id_key=BUDGET_TERM_SIGNATURE_DOCUMENT_ID_KEY,
        )
    except SignatureTokenError as exc:
        raise Http404(str(exc)) from exc

    signing = get_object_or_404(BudgetTermSigning, pk=payload.document_id, signature_token_version=payload.version, signature_token_active=True)

    if signing.signature_request_status == SignatureStatus.APPROVED and signing.signature_external_id:
        try:
            api_key = get_workshop_synplaisign_api_key(signing.budget.workshop)
            pdf_bytes = download_signed_pdf(
                document_id=signing.signature_document_id,
                envelope_id=signing.signature_external_id,
                synplaisign_api_key=api_key,
            )
            document = DocumentPayload(content=pdf_bytes, filename=f"termo-recebimento-{signing.budget_id}.pdf")
            return build_pdf_http_response(document=document, download=request.GET.get("download") == "1")
        except (SignatureServiceError, WorkshopSynplaiSignError):
            logger.exception("budget_term_signed_download_failed", extra={"signing_id": signing.pk})

    context = build_term_pdf_context(
        term_template=signing.term_template,
        snapshot=signing.content_snapshot or None,
        workshop=signing.budget.workshop,
        customer=signing.budget.customer,
        vehicle=signing.budget.vehicle,
    )
    document = render_term_pdf_document(context=context, filename=f"termo-recebimento-{signing.budget_id}.pdf")
    return build_pdf_http_response(document=document, download=request.GET.get("download") == "1")


@xframe_options_exempt
def workorder_term_preview(request, workorder_id: int):
    workshop = get_active_workshop_or_404(request)
    workorder: WorkOrder = get_object_or_404(
        WorkOrder.objects.select_related("budget", "budget__customer", "budget__vehicle", "workshop"),
        pk=workorder_id,
        workshop=workshop,
    )
    term_template_id = request.GET.get("term_template")
    signing = WorkOrderTermSigning.objects.filter(workorder=workorder).select_related("term_template").first()
    if term_template_id and signing and not signing.is_signature_locked:
        try:
            signing = update_workorder_term_template(workorder=workorder, term_template_id=int(term_template_id))
        except (ValueError, TypeError):
            pass
    elif signing is None and term_template_id:
        try:
            signing = update_workorder_term_template(workorder=workorder, term_template_id=int(term_template_id))
        except (ValueError, TypeError):
            signing = None

    term_template = signing.term_template if signing else get_default_term_template(workshop=workshop, template_type=TermTemplateType.WARRANTY)
    if term_template is None:
        raise Http404("Nenhum termo de garantia cadastrado.")

    snapshot = signing.content_snapshot if signing and signing.is_signature_locked and signing.content_snapshot else None
    budget = workorder.budget
    context = build_term_pdf_context(
        term_template=term_template,
        snapshot=snapshot,
        workshop=workshop,
        customer=budget.customer if budget else None,
        vehicle=budget.vehicle if budget else None,
        warranty_plan_display=getattr(workorder, "warranty_plan_display", "") or "",
    )
    return render(request, "terms/pdf/term_document.html", context)


@xframe_options_exempt
def workorder_term_signature_preview(request, token: str):
    try:
        payload = get_signature_service().parse_signature_token(
            token=token,
            token_salt=WORKORDER_TERM_SIGNATURE_TOKEN_SALT,
            document_id_key=WORKORDER_TERM_SIGNATURE_DOCUMENT_ID_KEY,
        )
    except SignatureTokenError as exc:
        raise Http404(str(exc)) from exc

    signing = get_object_or_404(
        WorkOrderTermSigning.objects.select_related(
            "workorder",
            "workorder__budget",
            "workorder__budget__customer",
            "workorder__budget__vehicle",
            "workorder__workshop",
            "term_template",
        ),
        pk=payload.document_id,
        signature_token_version=payload.version,
        signature_token_active=True,
    )
    workorder = signing.workorder
    budget = workorder.budget
    context = build_term_pdf_context(
        term_template=signing.term_template,
        snapshot=signing.content_snapshot or None,
        workshop=workorder.workshop,
        customer=budget.customer if budget else None,
        vehicle=budget.vehicle if budget else None,
        warranty_plan_display=getattr(workorder, "warranty_plan_display", "") or "",
    )
    return render(request, "terms/pdf/term_document.html", context)


@xframe_options_exempt
def workorder_term_signature_file(request, token: str):
    try:
        payload = get_signature_service().parse_signature_token(
            token=token,
            token_salt=WORKORDER_TERM_SIGNATURE_TOKEN_SALT,
            document_id_key=WORKORDER_TERM_SIGNATURE_DOCUMENT_ID_KEY,
        )
    except SignatureTokenError as exc:
        raise Http404(str(exc)) from exc

    signing = get_object_or_404(
        WorkOrderTermSigning.objects.select_related("workorder", "workorder__budget", "workorder__workshop"),
        pk=payload.document_id,
        signature_token_version=payload.version,
        signature_token_active=True,
    )
    workorder = signing.workorder
    budget = workorder.budget

    if signing.signature_request_status == SignatureStatus.APPROVED and signing.signature_external_id:
        try:
            api_key = get_workshop_synplaisign_api_key(workorder.workshop)
            pdf_bytes = download_signed_pdf(
                document_id=signing.signature_document_id,
                envelope_id=signing.signature_external_id,
                synplaisign_api_key=api_key,
            )
            document = DocumentPayload(content=pdf_bytes, filename=f"termo-garantia-{workorder.pk}.pdf")
            return build_pdf_http_response(document=document, download=request.GET.get("download") == "1")
        except (SignatureServiceError, WorkshopSynplaiSignError):
            logger.exception("workorder_term_signed_download_failed", extra={"signing_id": signing.pk})

    context = build_term_pdf_context(
        term_template=signing.term_template,
        snapshot=signing.content_snapshot or None,
        workshop=workorder.workshop,
        customer=budget.customer if budget else None,
        vehicle=budget.vehicle if budget else None,
        warranty_plan_display=getattr(workorder, "warranty_plan_display", "") or "",
    )
    document = render_term_pdf_document(context=context, filename=f"termo-garantia-{workorder.pk}.pdf")
    return build_pdf_http_response(document=document, download=request.GET.get("download") == "1")


class SendWorkOrderTermSignatureView(LoginRequiredMixin, WorkshopScopedMixin, View):
    def post(self, request, workorder_id: int) -> JsonResponse:
        workorder: WorkOrder = get_object_or_404(WorkOrder.objects.select_related("budget", "budget__customer", "workshop"), pk=workorder_id, workshop=self.workshop)
        term_template_id = request.POST.get("term_template")
        if not term_template_id:
            return JsonResponse({"ok": False, "error": "Selecione um termo de garantia."}, status=400)

        term_template = get_object_or_404(
            WorkshopTermTemplate,
            pk=term_template_id,
            workshop=self.workshop,
            template_type=TermTemplateType.WARRANTY,
            is_active=True,
        )
        signing, _created = WorkOrderTermSigning.objects.get_or_create(
            workorder=workorder,
            defaults={"term_template": term_template},
        )
        if not signing.is_signature_locked and signing.term_template_id != term_template.pk:
            signing.term_template = term_template
            signing.save(update_fields=["term_template", "atualizado_em"])

        if signing.signature_request_status == SignatureStatus.APPROVED:
            return JsonResponse({"ok": False, "error": "Este termo já foi assinado."}, status=409)

        with transaction.atomic():
            locked = WorkOrderTermSigning.objects.select_for_update().get(pk=signing.pk)
            locked.mark_signature_sending()

        try:
            result = send_workorder_term_for_signature(signing=locked)
        except TermSignatureError as exc:
            locked.mark_signature_failed()
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)

        locked.mark_signature_sent(result.envelope_id, document_id=result.document_id)
        locked.regenerate_signature_token()
        return JsonResponse({"ok": True, "message": "Termo de garantia enviado para assinatura."})
