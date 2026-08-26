from __future__ import annotations

import json
import logging

from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.urls import reverse
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views import View
from django.views.generic import DetailView, ListView

from apps.core.presentation.forms import CoreForm
from apps.core.presentation.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.core.presentation.mixins import HtmxTemplateResponseMixin
from apps.finance.forms import NfeRequestStep1Form, NfeRequestStep2Form, NfeRequestStep3Form
from apps.finance.models.finance import (
    FiscalDocument,
    FiscalDocumentEvent,
    FiscalDocumentEventType,
    FiscalDocumentLinkRole,
    FiscalDocumentPurpose,
    NfeItem,
    NfeRequest,
    NfeRequestStatus,
)
from apps.core.infrastructure.providers import get_fiscal_service
from apps.core.domain.contracts.fiscal import FiscalServiceError
from apps.core.infrastructure.services.webmania.webmania_documents import WebmaniaDocumentDownloadError, download_webmania_document
from apps.finance.services.nfe_events import NfeCorrectionError, emit_nfe_correction, is_nfe_item_eligible_for_cce
from apps.finance.services.nfe_returns import NfeReturnError, create_and_emit_nfe_return_from_item, is_local_nfe_eligible_for_return
from apps.finance.views.ncm_validation import (
    build_invalid_ncm_modal_context_for_nfe_request,
    pop_invalid_ncm_modal_context,
    store_invalid_ncm_modal_context,
)
from apps.finance.views.navigation import build_detail_url_with_preserved_origin, build_issued_documents_back_url, build_issued_documents_list_url
from apps.finance.views.request_workflow import (
    SharedEmissionRequestCreateBaseView,
    SharedEmissionRequestUpdateBaseView,
    build_preview_hidden_fields,
    render_emission_preview_modal,
)
from apps.workshops.mixin import WorkshopScopedMixin
from apps.workshops.util.workshops import has_workshop_perm


logger = logging.getLogger(__name__)


class NfeCancelForm(CoreForm):
    reason = forms.CharField(min_length=15, max_length=255)


class NfeInvalidateForm(CoreForm):
    reason = forms.CharField(min_length=15, max_length=255)


class NfeCorrectionForm(CoreForm):
    correction = forms.CharField(min_length=15, max_length=1000)
    confirm_legal_restrictions = forms.BooleanField(required=True)


class NfeReturnForm(CoreForm):
    RETURN_SCOPE_TOTAL = "total"
    RETURN_SCOPE_PARTIAL = "partial"

    purpose = forms.ChoiceField(choices=((FiscalDocumentPurpose.RETURN, "Devolução"), (FiscalDocumentPurpose.REVERSAL, "Estorno")))
    return_scope = forms.ChoiceField(required=False, choices=((RETURN_SCOPE_TOTAL, "Total"), (RETURN_SCOPE_PARTIAL, "Parcial")))
    natureza_operacao = forms.CharField(max_length=60)
    codigo_cfop = forms.CharField(max_length=10)
    classe_imposto = forms.CharField(required=False, max_length=30)
    produtos_json = forms.CharField(required=False, widget=forms.Textarea)
    volume = forms.IntegerField(required=False, min_value=1, max_value=999999999999999)
    informacoes_complementares = forms.CharField(required=False, max_length=5000)
    informacoes_fisco = forms.CharField(required=False, max_length=2000)
    confirm_return = forms.BooleanField(required=True)

    def clean_produtos_json(self) -> list[dict[str, object]]:
        raw_value = str(self.cleaned_data.get("produtos_json") or "").strip()
        if not raw_value:
            return []
        try:
            products = json.loads(raw_value)
        except ValueError as exc:
            raise forms.ValidationError("Informe os produtos em JSON válido.") from exc
        if not isinstance(products, list):
            raise forms.ValidationError("Produtos devem ser uma lista JSON.")
        return products

    def clean(self) -> dict[str, object]:
        cleaned_data = super().clean()
        purpose = str(cleaned_data.get("purpose") or "").strip()
        return_scope = str(cleaned_data.get("return_scope") or self.RETURN_SCOPE_TOTAL).strip()
        products = cleaned_data.get("produtos_json") or []
        if purpose == FiscalDocumentPurpose.RETURN and return_scope == self.RETURN_SCOPE_PARTIAL and not products:
            self.add_error("produtos_json", "Informe os produtos e quantidades para devolução parcial.")
        if purpose == FiscalDocumentPurpose.REVERSAL or return_scope == self.RETURN_SCOPE_TOTAL:
            cleaned_data["produtos_json"] = []
        return cleaned_data


def _can_invalidate_nfe_request(*, nfe_request: NfeRequest, latest_item: NfeItem | None) -> bool:
    if nfe_request.status == NfeRequestStatus.INVALIDATED:
        return False
    if nfe_request.reserved_number is None or nfe_request.reserved_series is None:
        return False
    if latest_item is None:
        return True

    status = str(getattr(latest_item, "status", "")).strip().lower()
    return status in {"reprovado", "denegado"}


class NfeRequestListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = NfeRequest
    workshop_permission_model = "nfserequest"
    workshop_permission_codename = "view_nfserequest"
    template_name = "finance/nfe_request_list.html"
    context_object_name = "nfe_requests"
    htmx_template_name = "finance/partials/nfe_request_table.html"

    def get_queryset(self):
        return super().get_queryset().select_related("workorder", "workorder__budget", "workorder__budget__customer", "workorder__budget__vehicle").prefetch_related("items").order_by("-criado_em", "-pk")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["fields"] = [
            TableColumn("ID", attr="id"),
            TableColumn("Numero", attr="number_display_listing", search_by="reserved_number"),
            TableColumn("Ordem de Servico", attr="workorder_reference", search_by="workorder__id"),
            TableColumn("Cliente", attr="customer_name", search_by=("recipient_name", "workorder__budget__customer__name")),
            TableColumn("Criado em", attr=NfeRequest.criado_em.field.name),
            TableColumn("Status", attr="nfe_request_status_badge", search_by="status", format="status_badge"),
        ]
        context["actions"] = [
            TableActionDefaults.view("finance:nfe_detail"),
            TableActionDefaults.edit("finance:nfe_update"),
        ]
        return context


def _format_item_status_badge(status: str) -> dict[str, str]:
    status_map = {
        "processando": {"text": "Processando", "class": "badge-soft badge-warning"},
        "aprovado": {"text": "Aprovado", "class": "badge-success"},
        "reprovado": {"text": "Reprovado", "class": "badge-error"},
        "cancelado": {"text": "Cancelado", "class": "badge-soft badge-error"},
        "denegado": {"text": "Denegado", "class": "badge-soft badge-error"},
        "contingencia": {"text": "Contingência", "class": "badge-soft badge-warning"},
    }
    return status_map.get(str(status or "").strip().lower(), {"text": str(status or "-") or "-", "class": "badge-ghost"})


def _build_field(label: str, value: object) -> dict[str, str]:
    normalized = str(value or "-").strip() or "-"
    return {"label": label, "value": normalized}


def _user_can_issue_cce(*, user, workshop, request) -> bool:
    return has_workshop_perm(
        user=user,
        workshop=workshop,
        app_label="finance",
        model="fiscaldocumentevent",
        codename="issue_nfe_correction",
        request=request,
    )


def _user_can_issue_return(*, user, workshop, request) -> bool:
    return has_workshop_perm(
        user=user,
        workshop=workshop,
        app_label="finance",
        model="fiscaldocument",
        codename="issue_nfe_return",
        request=request,
    )


def _user_can_issue_reversal(*, user, workshop, request) -> bool:
    return has_workshop_perm(
        user=user,
        workshop=workshop,
        app_label="finance",
        model="fiscaldocument",
        codename="issue_nfe_reversal",
        request=request,
    )


class NfeRequestDetailView(LoginRequiredMixin, WorkshopScopedMixin, DetailView):
    model = NfeRequest
    workshop_permission_model = "nfserequest"
    workshop_permission_codename = "view_nfserequest"
    template_name = "finance/nfe_request_detail.html"
    context_object_name = "nfe_request"

    def get_queryset(self):
        return super().get_queryset().select_related("workorder", "workorder__budget", "workorder__budget__customer", "workorder__budget__vehicle").prefetch_related("items")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        latest_item = self.object.items.order_by("-id").first()
        can_cancel = bool(latest_item and str(getattr(latest_item, "status", "")).strip().lower() in {"aprovado", "contingencia"})
        can_invalidate = _can_invalidate_nfe_request(nfe_request=self.object, latest_item=latest_item)
        can_issue_cce = bool(latest_item and is_nfe_item_eligible_for_cce(latest_item) and _user_can_issue_cce(user=self.request.user, workshop=self.workshop, request=self.request))
        eligible_for_return = bool(latest_item and is_local_nfe_eligible_for_return(latest_item))
        can_issue_return = bool(eligible_for_return and _user_can_issue_return(user=self.request.user, workshop=self.workshop, request=self.request))
        can_issue_reversal = bool(eligible_for_return and _user_can_issue_reversal(user=self.request.user, workshop=self.workshop, request=self.request))
        cce_events = FiscalDocumentEvent.objects.none()
        return_documents = FiscalDocument.objects.none()
        if latest_item is not None:
            cce_events = FiscalDocumentEvent.objects.filter(
                document__workshop=self.workshop,
                document__legacy_nfe_item=latest_item,
                event_type=FiscalDocumentEventType.CCE,
            ).order_by("event_sequence")
            return_documents = (
                FiscalDocument.objects.filter(
                    links_from__related_document__legacy_nfe_item=latest_item,
                    links_from__role__in=[FiscalDocumentLinkRole.RETURNS, FiscalDocumentLinkRole.REVERSES],
                )
                .distinct()
                .order_by("criado_em")
            )
        fallback_back_url = build_issued_documents_list_url(note_type="nfe")
        context.update(
            {
                "back_url": build_issued_documents_back_url(query_params=self.request.GET, fallback_url=fallback_back_url),
                "latest_item": latest_item,
                "can_cancel": can_cancel,
                "request_fields": [
                    _build_field("ID da requisição", self.object.pk),
                    _build_field("Ordem de serviço", self.object.workorder_reference),
                    _build_field("Cliente", self.object.customer_name),
                    _build_field("Classe de imposto", self.object.tax_class),
                    _build_field("Número da Nota Fiscal de Produto", self.object.reserved_number),
                    _build_field("Série da Nota Fiscal de Produto", self.object.reserved_series),
                    _build_field("Criado em", self.object.criado_em.strftime("%d/%m/%Y %H:%M") if self.object.criado_em else "-"),
                    _build_field("Atualizado em", self.object.atualizado_em.strftime("%d/%m/%Y %H:%M") if self.object.atualizado_em else "-"),
                ],
                "latest_item_status_badge": _format_item_status_badge(getattr(latest_item, "status", "")),
                "can_invalidate": can_invalidate,
                "can_issue_cce": can_issue_cce,
                "cce_form": NfeCorrectionForm(),
                "cce_events": cce_events,
                "can_issue_return": can_issue_return,
                "can_issue_reversal": can_issue_reversal,
                "nfe_return_form": NfeReturnForm(),
                "return_documents": return_documents,
            }
        )
        return context


class NfeCorrectionIssueView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "fiscaldocumentevent"
    workshop_permission_codename = "issue_nfe_correction"

    def post(self, request, *args, **kwargs):
        nfe_request = get_object_or_404(NfeRequest, pk=kwargs.get("pk"), workshop=self.workshop)
        latest_item = nfe_request.items.order_by("-id").first()
        if not is_nfe_item_eligible_for_cce(latest_item):
            messages.error(request, "Carta de correcao permitida somente para NF-e autorizada com chave de acesso ou UUID valido.")
            return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfe_detail", pk=nfe_request.pk, query_params=request.GET))

        form = NfeCorrectionForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Informe a correcao entre 15 e 1000 caracteres e confirme as restricoes legais.")
            return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfe_detail", pk=nfe_request.pk, query_params=request.GET))

        try:
            emit_nfe_correction(
                nfe_item=latest_item,
                correction_text=str(form.cleaned_data["correction"]),
                requested_by=request.user,
                request=request,
            )
        except NfeCorrectionError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Carta de correcao enviada com sucesso.")

        return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfe_detail", pk=nfe_request.pk, query_params=request.GET))


class NfeReturnIssueView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nfserequest"
    workshop_permission_codename = "view_nfserequest"

    def post(self, request, *args, **kwargs):
        nfe_request = get_object_or_404(NfeRequest, pk=kwargs.get("pk"), workshop=self.workshop)
        latest_item = nfe_request.items.order_by("-id").first()
        if not is_local_nfe_eligible_for_return(latest_item):
            messages.error(request, "Devolução ou estorno permitidos somente para NF-e autorizada com chave de acesso válida.")
            return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfe_detail", pk=nfe_request.pk, query_params=request.GET))

        form = NfeReturnForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Informe finalidade, CFOP, natureza da operação e produtos válidos para devolução ou estorno.")
            return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfe_detail", pk=nfe_request.pk, query_params=request.GET))

        purpose = str(form.cleaned_data["purpose"])
        can_issue = _user_can_issue_reversal(user=request.user, workshop=self.workshop, request=request) if purpose == FiscalDocumentPurpose.REVERSAL else _user_can_issue_return(user=request.user, workshop=self.workshop, request=request)
        if not can_issue:
            messages.error(request, "Usuário sem permissão específica para esta operação fiscal.")
            return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfe_detail", pk=nfe_request.pk, query_params=request.GET))

        try:
            create_and_emit_nfe_return_from_item(
                item=latest_item,
                purpose=purpose,
                products=form.cleaned_data["produtos_json"],
                requested_by=request.user,
                natureza_operacao=str(form.cleaned_data["natureza_operacao"]),
                codigo_cfop=str(form.cleaned_data["codigo_cfop"]),
                classe_imposto=str(form.cleaned_data.get("classe_imposto") or ""),
                volume=form.cleaned_data.get("volume"),
                informacoes_complementares=str(form.cleaned_data.get("informacoes_complementares") or ""),
                informacoes_fisco=str(form.cleaned_data.get("informacoes_fisco") or ""),
                request=request,
            )
        except NfeReturnError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Devolução ou estorno enviado para a Webmania.")

        return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfe_detail", pk=nfe_request.pk, query_params=request.GET))


class NfeRequestCancelView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nfserequest"
    workshop_permission_codename = "change_nfserequest"

    def post(self, request, *args, **kwargs):
        nfe_request = get_object_or_404(NfeRequest, pk=kwargs.get("pk"), workshop=self.workshop)
        latest_item = nfe_request.items.order_by("-id").first()
        if latest_item is None:
            messages.error(request, "A Nota Fiscal de Produto ainda nao possui item sincronizado para cancelamento.")
            return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfe_detail", pk=nfe_request.pk, query_params=request.GET))

        status = str(getattr(latest_item, "status", "")).strip().lower()
        if status not in {"aprovado", "contingencia"}:
            messages.error(request, "Somente Nota Fiscal de Produto aprovada ou em contingencia pode ser cancelada.")
            return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfe_detail", pk=nfe_request.pk, query_params=request.GET))

        form = NfeCancelForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Informe um motivo de cancelamento entre 15 e 255 caracteres.")
            return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfe_detail", pk=nfe_request.pk, query_params=request.GET))

        reason = str(form.cleaned_data["reason"]).strip()

        service = get_fiscal_service()
        try:
            response_payload = service.cancel_nfe(
                workshop=self.workshop,
                access_key=str(latest_item.access_key or ""),
                event_uuid=str(latest_item.uuid),
                reason=reason,
            )
        except FiscalServiceError as exc:
            messages.error(request, str(exc))
            return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfe_detail", pk=nfe_request.pk, query_params=request.GET))

        latest_item.status = "cancelado"
        latest_item.reason = str(response_payload.get("motivo") or reason)
        latest_item.raw_payload = response_payload
        xml_url = str(response_payload.get("xml") or "").strip()
        if xml_url:
            latest_item.xml_url = xml_url
        latest_item.save(update_fields=["status", "reason", "raw_payload", "xml_url"])

        nfe_request.set_status(NfeRequestStatus.CANCELED)
        messages.success(request, "Nota Fiscal de Produto cancelada com sucesso.")
        return redirect(build_issued_documents_back_url(query_params=request.GET, fallback_url=build_issued_documents_list_url(note_type="nfe")))


class NfeRequestReconcileView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nfserequest"
    workshop_permission_codename = "change_nfserequest"

    def post(self, request, *args, **kwargs):
        nfe_request = get_object_or_404(NfeRequest, pk=kwargs.get("pk"), workshop=self.workshop)
        item = nfe_request.items.order_by("-id").first()
        if item is None:
            messages.error(request, "A Nota Fiscal de Produto ainda nao possui um item sincronizado para consulta.")
            return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfe_detail", pk=nfe_request.pk, query_params=request.GET))

        service = get_fiscal_service()
        try:
            service.reconcile_nfe_item(item=item)
        except FiscalServiceError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Status da Nota Fiscal de Produto atualizado com sucesso.")

        return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfe_detail", pk=nfe_request.pk, query_params=request.GET))


class NfeRequestInvalidateView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nfserequest"
    workshop_permission_codename = "change_nfserequest"

    def post(self, request, *args, **kwargs):
        nfe_request = get_object_or_404(NfeRequest, pk=kwargs.get("pk"), workshop=self.workshop)
        latest_item = nfe_request.items.order_by("-id").first()

        if not _can_invalidate_nfe_request(nfe_request=nfe_request, latest_item=latest_item):
            messages.error(request, "A numeracao desta Nota Fiscal de Produto nao pode ser inutilizada no estado atual.")
            return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfe_detail", pk=nfe_request.pk, query_params=request.GET))

        form = NfeInvalidateForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Informe um motivo de inutilizacao entre 15 e 255 caracteres.")
            return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfe_detail", pk=nfe_request.pk, query_params=request.GET))

        reason = str(form.cleaned_data["reason"]).strip()

        service = get_fiscal_service()
        try:
            response_payload = service.invalidate_nfe_number(
                workshop=self.workshop,
                number=int(nfe_request.reserved_number),
                reason=reason,
                series=int(nfe_request.reserved_series),
            )
        except FiscalServiceError as exc:
            messages.error(request, str(exc))
            return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfe_detail", pk=nfe_request.pk, query_params=request.GET))

        raw_log_payload = response_payload.get("log")
        nfe_request.invalidation_reason = str(response_payload.get("motivo") or reason)
        nfe_request.invalidation_xml_url = str(response_payload.get("xml") or "")
        nfe_request.invalidation_log_payload = raw_log_payload if isinstance(raw_log_payload, dict) else ({"raw": raw_log_payload} if raw_log_payload not in (None, "") else {})
        nfe_request.invalidated_at = timezone.now()
        nfe_request.save(update_fields=["invalidation_reason", "invalidation_xml_url", "invalidation_log_payload", "invalidated_at"])
        nfe_request.set_status(NfeRequestStatus.INVALIDATED)

        messages.success(request, "Numeracao da Nota Fiscal de Produto inutilizada com sucesso.")
        return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfe_detail", pk=nfe_request.pk, query_params=request.GET))


class NfeDocumentDownloadView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nfserequest"
    workshop_permission_codename = "view_nfserequest"

    document_fields = {
        "xml": ("xml_url", "xml"),
        "danfe": ("danfe_url", "pdf"),
        "danfe_simples": ("danfe_simple_url", "pdf"),
        "danfe_etiqueta": ("danfe_label_url", "pdf"),
    }

    def get(self, request, *args, **kwargs):
        nfe_request = get_object_or_404(NfeRequest, pk=kwargs.get("pk"), workshop=self.workshop)
        document_kind = str(kwargs.get("document") or "").strip().lower()
        if document_kind not in self.document_fields:
            raise Http404("Documento nao suportado")

        item = nfe_request.items.order_by("-id").first()
        if item is None:
            raise Http404("Documento ainda nao disponivel")

        field_name, extension = self.document_fields[document_kind]
        document_url = str(getattr(item, field_name, "") or "").strip()

        service = get_fiscal_service()
        try:
            downloaded = service.download_document(workshop=self.workshop, url=document_url)
        except FiscalServiceError as exc:
            logger.exception(
                "nfe_document_download_failed",
                extra={"nfe_request_id": nfe_request.pk, "workshop_id": self.workshop.pk, "document_kind": document_kind},
            )
            return HttpResponse(str(exc), status=502, content_type="text/plain; charset=utf-8")

        response = HttpResponse(downloaded.content, content_type=downloaded.content_type)
        response["Content-Disposition"] = self._build_content_disposition(item=item, document_kind=document_kind, extension=extension)
        return response

    @staticmethod
    def _build_content_disposition(*, item: NfeItem, document_kind: str, extension: str) -> str:
        identifier = str(item.number or item.access_key or item.uuid or "documento").strip()
        safe_identifier = identifier.replace(" ", "-")
        return f'attachment; filename="nfe-{document_kind}-{safe_identifier}.{extension}"'


class NfeCorrectionDownloadView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "fiscaldocumentevent"
    workshop_permission_codename = "download_nfe_correction"

    document_fields = {
        "xml": ("xml_url", "xml"),
        "dacce": ("dacce_url", "pdf"),
    }

    def get(self, request, *args, **kwargs):
        nfe_request = get_object_or_404(NfeRequest, pk=kwargs.get("pk"), workshop=self.workshop)
        document_kind = str(kwargs.get("document") or "").strip().lower()
        if document_kind not in self.document_fields:
            raise Http404("Documento nao suportado")

        event = get_object_or_404(
            FiscalDocumentEvent.objects.select_related("document", "document__legacy_nfe_item"),
            pk=kwargs.get("event_pk"),
            document__workshop=self.workshop,
            document__legacy_nfe_item__request=nfe_request,
            event_type=FiscalDocumentEventType.CCE,
        )
        field_name, extension = self.document_fields[document_kind]
        document_url = str(getattr(event, field_name, "") or "").strip()

        try:
            downloaded = download_webmania_document(workshop=self.workshop, url=document_url)
        except WebmaniaDocumentDownloadError as exc:
            return HttpResponse(str(exc), status=502, content_type="text/plain; charset=utf-8")

        response = HttpResponse(downloaded.content, content_type=downloaded.content_type)
        identifier = str(event.remote_uuid or event.document.access_key or event.pk or "documento").strip().replace(" ", "-")
        response["Content-Disposition"] = f'attachment; filename="nfe-cce-{document_kind}-{identifier}.{extension}"'
        return response


class NfeReturnDownloadView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "fiscaldocument"
    workshop_permission_codename = "download_nfe_return"

    document_fields = {
        "xml": ("xml_url", "xml"),
        "danfe": ("danfe_url", "pdf"),
    }

    def get(self, request, *args, **kwargs):
        nfe_request = get_object_or_404(NfeRequest, pk=kwargs.get("pk"), workshop=self.workshop)
        document_kind = str(kwargs.get("document") or "").strip().lower()
        if document_kind not in self.document_fields:
            raise Http404("Documento não suportado")

        document = get_object_or_404(
            FiscalDocument.objects.filter(links_from__related_document__legacy_nfe_item__request=nfe_request).distinct(),
            pk=kwargs.get("document_pk"),
            workshop=self.workshop,
            purpose__in=[FiscalDocumentPurpose.RETURN, FiscalDocumentPurpose.REVERSAL],
        )
        field_name, extension = self.document_fields[document_kind]
        document_url = str(getattr(document, field_name, "") or "").strip()

        try:
            downloaded = download_webmania_document(workshop=self.workshop, url=document_url)
        except WebmaniaDocumentDownloadError as exc:
            return HttpResponse(str(exc), status=502, content_type="text/plain; charset=utf-8")

        response = HttpResponse(downloaded.content, content_type=downloaded.content_type)
        identifier = str(document.number or document.access_key or document.remote_uuid or document.pk or "documento").strip().replace(" ", "-")
        response["Content-Disposition"] = f'attachment; filename="nfe-{document.purpose}-{document_kind}-{identifier}.{extension}"'
        return response


@method_decorator(xframe_options_exempt, name="dispatch")
class NfePreviewPdfView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nfserequest"
    workshop_permission_codename = "view_nfserequest"

    def get(self, request, *args, **kwargs):
        nfe_request = get_object_or_404(NfeRequest, pk=kwargs.get("pk"), workshop=self.workshop)

        service = get_fiscal_service()
        try:
            downloaded = service.download_nfe_preview_document(nfe_request=nfe_request, request=request)
        except FiscalServiceError as exc:
            logger.exception(
                "nfe_preview_download_failed",
                extra={"nfe_request_id": nfe_request.pk, "workshop_id": self.workshop.pk},
            )
            response = render(
                request,
                "finance/partials/preview_error.html",
                {
                    "title": "Não foi possível gerar a prévia da NF-e",
                    "message": str(exc),
                },
            )
            response["Cache-Control"] = "no-store"
            response.status_code = 422
            return response

        response = HttpResponse(downloaded.content, content_type=downloaded.content_type)
        response["Content-Disposition"] = self._build_content_disposition(nfe_request=nfe_request)
        response["Cache-Control"] = "no-store"
        return response

    @staticmethod
    def _build_content_disposition(*, nfe_request: NfeRequest) -> str:
        identifier = str(getattr(nfe_request, "reserved_number", "") or nfe_request.pk or "documento").strip()
        safe_identifier = identifier.replace(" ", "-")
        return f'inline; filename="nfe-previa-{safe_identifier}.pdf"'


class NfeRequestCreateView(SharedEmissionRequestCreateBaseView):
    model = NfeRequest
    workshop_permission_model = "nfserequest"
    workshop_permission_codename = "view_nfserequest"
    template_name = "finance/nfe_request_form.html"
    partial_template_name = "finance/partials/nfe_step_content.html"
    preview_template_name = "finance/partials/nfe_step3_preview.html"
    step3_form_class = NfeRequestStep3Form
    preview_initial_fields = ("pricing_slider", "tax_class", "additional_information")
    tax_class_kind = "nfe"
    tax_class_warning_message = "Nao foi possivel carregar classes de imposto de Nota Fiscal de Produto: {error}"
    success_redirect_name = "finance:issued_documents_list"
    status_by_step = {
        1: NfeRequestStatus.CHECKING_CLIENT,
        2: NfeRequestStatus.CHECKING_PRODUCTS,
    }

    steps_definition = [
        {"title": "Selecionar OS", "form_class": NfeRequestStep1Form},
        {"title": "Conferir Cliente", "form_class": NfeRequestStep2Form},
        {"title": "Conferir Produtos", "form_class": NfeRequestStep3Form},
    ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["ncm_invalid_modal"] = pop_invalid_ncm_modal_context(request=self.request)
        return context

    def _finalize_emission(self) -> bool:
        invalid_ncm_modal = build_invalid_ncm_modal_context_for_nfe_request(
            nfe_request=self.object,
            return_url=self.request.get_full_path(),
        )
        if invalid_ncm_modal is not None:
            store_invalid_ncm_modal_context(request=self.request, modal_context=invalid_ncm_modal)
            return False

        service = get_fiscal_service()
        try:
            response_payload = service.emit_nfe(nfe_request=self.object, request=self.request)
            service.sync_nfe_emission_response(nfe_request=self.object, response_payload=response_payload)

            if not self.object.update_status_based_on_request(response_payload.get("status")):
                self.object.set_status(NfeRequestStatus.PROCESSING)

            messages.success(self.request, "Solicitacao de Nota Fiscal de Produto enviada com sucesso.")
            return True
        except FiscalServiceError as exc:
            logger.exception("Falha ao emitir NF-e", extra={"nfe_request_id": self.object.pk})
            messages.error(self.request, str(exc))
            return False

    def _build_preview_response(self, *, form) -> HttpResponse:
        invalid_ncm_modal = build_invalid_ncm_modal_context_for_nfe_request(
            nfe_request=self.object,
            return_url=self.request.get_full_path(),
        )
        if invalid_ncm_modal is not None:
            store_invalid_ncm_modal_context(request=self.request, modal_context=invalid_ncm_modal)
            step_url = self._step_url(step=self.get_current_step())
            if self.request.htmx:
                response = HttpResponse()
                response["HX-Redirect"] = step_url
                return response
            return redirect(step_url)

        return render_emission_preview_modal(
            request=self.request,
            title="Prévia da Nota Fiscal de Produto",
            description="Confira o documento antes de transmitir a Nota Fiscal de Produto para a Webmania.",
            previews=[{"label": "DANFE", "embed_url": reverse("finance:nfe_preview_pdf", kwargs={"pk": self.object.pk})}],
            transmit_url=self._step_url(step=self.get_current_step()),
            hidden_fields=build_preview_hidden_fields(cleaned_data=form.cleaned_data),
        )


class NfeRequestUpdateView(SharedEmissionRequestUpdateBaseView, NfeRequestCreateView):
    update_url_name = "finance:nfe_update"
    missing_update_redirect_name = "finance:issued_documents_list"
