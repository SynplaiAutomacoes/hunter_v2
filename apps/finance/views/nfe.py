from __future__ import annotations

import logging
import json

from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
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
from apps.finance.forms.fiscal_gateway import FiscalOperation
from apps.finance.models.finance import FiscalDocument, FiscalDocumentEvent, FiscalDocumentEventType, FiscalDocumentLinkRole, FiscalDocumentPurpose, NfeEmissionOrigin, NfeItem, NfeRequest, NfeRequestStatus
from apps.core.infrastructure.providers import get_fiscal_service
from apps.core.infrastructure.services.webmania.webmania_documents import WebmaniaDocumentDownloadError, download_webmania_document
from apps.core.domain.contracts.fiscal import FiscalServiceError
from apps.finance.services.fiscal_attempts import sanitize_fiscal_payload
from apps.finance.services.nfe_events import NfeCorrectionError, emit_nfe_correction, has_active_cce_event_for_nfe_item, is_nfe_item_eligible_for_cce
from apps.finance.services.nfe_adjustment import NfeAdjustmentError, create_and_emit_nfe_adjustment, validate_adjustment_tax_regime
from apps.finance.services.nfe_complementary import NfeComplementaryError, create_and_emit_nfe_complementary_price_quantity_from_item, is_local_nfe_eligible_for_complementary
from apps.finance.services.nfe_ibs_cbs_events import (
    IBS_CBS_EVENT_112110,
    IBS_CBS_EVENT_112130,
    IBS_CBS_EVENT_112150,
    NfeIbsCbsEventError,
    cancel_ibs_cbs_event_112110,
    cancel_ibs_cbs_event_112130,
    cancel_ibs_cbs_event_112150,
    emit_ibs_cbs_event_112110,
    emit_ibs_cbs_event_112130,
    emit_ibs_cbs_event_112150,
    is_document_eligible_for_ibs_cbs_event_112110,
    is_document_eligible_for_ibs_cbs_event_112130,
    is_document_eligible_for_ibs_cbs_event_112150,
)
from apps.finance.services.nfe_returns import NfeReturnError, create_and_emit_nfe_return_from_item, is_local_nfe_eligible_for_return
from apps.finance.views.ncm_validation import build_invalid_ncm_modal_context, pop_invalid_ncm_modal_context, store_invalid_ncm_modal_context
from apps.finance.views.navigation import build_detail_url_with_preserved_origin, build_issued_documents_back_url
from apps.finance.views.request_workflow import (
    SharedEmissionRequestCreateBaseView,
    SharedEmissionRequestUpdateBaseView,
    build_preview_hidden_fields,
    render_emission_preview_modal,
)
from apps.workshops.mixin import WorkshopScopedMixin
from apps.workshops.util.workshops import get_active_workshop_or_404, has_workshop_perm


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

    purpose = forms.ChoiceField(choices=((FiscalDocumentPurpose.RETURN, "Devolucao"), (FiscalDocumentPurpose.REVERSAL, "Estorno")))
    return_scope = forms.ChoiceField(required=False, choices=((RETURN_SCOPE_TOTAL, "Total"), (RETURN_SCOPE_PARTIAL, "Parcial")))
    natureza_operacao = forms.CharField(max_length=60)
    codigo_cfop = forms.CharField(max_length=10)
    classe_imposto = forms.CharField(required=False, max_length=30)
    produtos_json = forms.CharField(required=False, widget=forms.Textarea)
    volume = forms.IntegerField(required=False, min_value=1, max_value=999999999999999)
    informacoes_complementares = forms.CharField(required=False, max_length=5000)
    informacoes_fisco = forms.CharField(required=False, max_length=2000)
    confirm_return = forms.BooleanField(required=True)

    def clean_produtos_json(self):
        raw_value = str(self.cleaned_data.get("produtos_json") or "").strip()
        if not raw_value:
            return []
        try:
            products = json.loads(raw_value)
        except ValueError as exc:
            raise forms.ValidationError("Informe os produtos em JSON valido.") from exc
        if not isinstance(products, list):
            raise forms.ValidationError("Produtos devem ser uma lista JSON.")
        return products

    def clean(self):
        cleaned_data = super().clean()
        purpose = str(cleaned_data.get("purpose") or "").strip()
        return_scope = str(cleaned_data.get("return_scope") or self.RETURN_SCOPE_TOTAL).strip()
        products = cleaned_data.get("produtos_json") or []
        if purpose == FiscalDocumentPurpose.RETURN and return_scope == self.RETURN_SCOPE_PARTIAL and not products:
            self.add_error("produtos_json", "Informe os produtos e quantidades para devolucao parcial.")
        if purpose == FiscalDocumentPurpose.REVERSAL or return_scope == self.RETURN_SCOPE_TOTAL:
            cleaned_data["produtos_json"] = []
        return cleaned_data


class NfeComplementaryPriceQuantityForm(CoreForm):
    operacao = forms.CharField(max_length=20)
    natureza_operacao = forms.CharField(max_length=120)
    codigo_cfop = forms.CharField(max_length=10)
    itens_json = forms.CharField(widget=forms.Textarea)
    confirm_complementary = forms.BooleanField(required=True)

    def clean_itens_json(self):
        raw_value = str(self.cleaned_data.get("itens_json") or "").strip()
        try:
            items = json.loads(raw_value)
        except ValueError as exc:
            raise forms.ValidationError("Informe os itens em JSON valido.") from exc
        if not isinstance(items, list):
            raise forms.ValidationError("Itens devem ser uma lista JSON.")
        return items


class NfeAdjustmentForm(CoreForm):
    operacao = forms.ChoiceField(choices=(("0", "Entrada"), ("1", "Saida")))
    natureza_operacao = forms.CharField(max_length=60)
    codigo_cfop = forms.CharField(max_length=10)
    valor_icms = forms.DecimalField(min_value=0, decimal_places=2, max_digits=15)
    valor_icms_st = forms.DecimalField(required=False, min_value=0, decimal_places=2, max_digits=15)
    situacao_tributaria = forms.CharField(max_length=4)
    cliente_json = forms.CharField(widget=forms.Textarea)
    informacoes_fisco = forms.CharField(required=False, max_length=2000)
    informacoes_complementares = forms.CharField(required=False, max_length=5000)
    confirm_adjustment = forms.BooleanField(required=True)
    confirm_not_sc_es_reversal = forms.BooleanField(required=True)

    def clean_cliente_json(self):
        raw_value = str(self.cleaned_data.get("cliente_json") or "").strip()
        try:
            client = json.loads(raw_value)
        except ValueError as exc:
            raise forms.ValidationError("Informe o cliente em JSON valido.") from exc
        if not isinstance(client, dict) or not client:
            raise forms.ValidationError("Cliente deve ser um objeto JSON.")
        return client


class NfeIbsCbsEvent112150Form(CoreForm):
    data_previsao_entrega = forms.DateField(input_formats=["%Y-%m-%d"])
    confirm_ibs_cbs_event_112150 = forms.BooleanField(required=True)


class NfeIbsCbsEvent112130Form(CoreForm):
    item = forms.IntegerField(min_value=1, max_value=999)
    valor_ibs = forms.DecimalField(min_value=0, decimal_places=2, max_digits=15)
    valor_cbs = forms.DecimalField(min_value=0, decimal_places=2, max_digits=15)
    quantidade_perecimento = forms.DecimalField(min_value=0, decimal_places=4, max_digits=15)
    unidade_perecimento = forms.CharField(min_length=1, max_length=6)
    valor_ibs_estorno = forms.DecimalField(min_value=0, decimal_places=2, max_digits=15)
    valor_cbs_estorno = forms.DecimalField(min_value=0, decimal_places=2, max_digits=15)
    confirm_ibs_cbs_event_112130 = forms.BooleanField(required=True)

    def clean_unidade_perecimento(self):
        return str(self.cleaned_data.get("unidade_perecimento") or "").strip().upper()

    def to_event_items(self) -> list[dict[str, object]]:
        return [
            {
                "item": self.cleaned_data["item"],
                "valor_ibs": self.cleaned_data["valor_ibs"],
                "valor_cbs": self.cleaned_data["valor_cbs"],
                "quantidade_perecimento": self.cleaned_data["quantidade_perecimento"],
                "unidade_perecimento": self.cleaned_data["unidade_perecimento"],
                "valor_ibs_estorno": self.cleaned_data["valor_ibs_estorno"],
                "valor_cbs_estorno": self.cleaned_data["valor_cbs_estorno"],
            }
        ]


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
    workshop_permission_model = "nferequest"
    workshop_permission_codename = "view_nferequest"
    workshop_permission_fallbacks = (("finance", "nfserequest", "view_nfserequest"),)
    template_name = "finance/nfe_request_list.html"
    context_object_name = "nfe_requests"
    htmx_template_name = "finance/partials/nfe_request_table.html"

    def get_queryset(self):
        return super().get_queryset().select_related("workorder", "workorder__budget", "workorder__budget__customer", "workorder__budget__vehicle", "manual_recipient").prefetch_related("items").order_by("-criado_em", "-pk")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["fields"] = [
            TableColumn("ID", attr="id"),
            TableColumn("Numero", attr="number_display", search_by="reserved_number"),
            TableColumn("Ordem de Servico", attr="workorder", search_by="workorder__id"),
            TableColumn("Cliente", attr="customer_name", search_by="workorder__budget__customer__name"),
            TableColumn("Criado em", attr=NfeRequest.criado_em.field.name),
            TableColumn("Status", attr="nfe_request_status_badge", search_by="status", format="status_badge"),
        ]
        context["actions"] = [
            TableActionDefaults.view("finance:nfe_detail"),
            TableActionDefaults.edit("finance:nfe_update", visible=lambda nfe_request: nfe_request.emission_origin == NfeEmissionOrigin.WORK_ORDER),
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


def _user_can_view_cce_payload(*, user, workshop, request) -> bool:
    return has_workshop_perm(
        user=user,
        workshop=workshop,
        app_label="finance",
        model="fiscaldocumentevent",
        codename="view_nfe_correction_payload",
        request=request,
    )


def _user_can_change_legacy_nfe_request(*, user, workshop, request) -> bool:
    return has_workshop_perm(
        user=user,
        workshop=workshop,
        app_label="finance",
        model="nferequest",
        codename="change_nferequest",
        request=request,
    ) or has_workshop_perm(
        user=user,
        workshop=workshop,
        app_label="finance",
        model="nfserequest",
        codename="change_nfserequest",
        request=request,
    )


def _user_can_view_legacy_nfe_request(*, user, workshop, request) -> bool:
    return has_workshop_perm(
        user=user,
        workshop=workshop,
        app_label="finance",
        model="nferequest",
        codename="view_nferequest",
        request=request,
    )


def _user_has_nferequest_permission(*, user, workshop, request, codename: str) -> bool:
    return has_workshop_perm(
        user=user,
        workshop=workshop,
        app_label="finance",
        model="nferequest",
        codename=codename,
        request=request,
    )


def _user_can_cancel_nferequest(*, user, workshop, request) -> bool:
    return _user_has_nferequest_permission(user=user, workshop=workshop, request=request, codename="cancel_nferequest") or _user_can_change_legacy_nfe_request(user=user, workshop=workshop, request=request)


def _user_can_invalidate_nferequest_numbering(*, user, workshop, request) -> bool:
    return _user_has_nferequest_permission(user=user, workshop=workshop, request=request, codename="invalidate_nferequest_numbering") or _user_can_change_legacy_nfe_request(user=user, workshop=workshop, request=request)


def _user_can_download_nferequest_xml(*, user, workshop, request) -> bool:
    return (
        _user_has_nferequest_permission(user=user, workshop=workshop, request=request, codename="download_nferequest_xml")
        or _user_can_view_legacy_nfe_request(user=user, workshop=workshop, request=request)
        or _user_can_change_legacy_nfe_request(user=user, workshop=workshop, request=request)
    )


def _user_can_download_nferequest_pdf(*, user, workshop, request) -> bool:
    return (
        _user_has_nferequest_permission(user=user, workshop=workshop, request=request, codename="download_nferequest_pdf")
        or _user_can_view_legacy_nfe_request(user=user, workshop=workshop, request=request)
        or _user_can_change_legacy_nfe_request(user=user, workshop=workshop, request=request)
    )


def _user_can_view_nferequest_payload(*, user, workshop, request) -> bool:
    return _user_has_nferequest_permission(user=user, workshop=workshop, request=request, codename="view_nferequest_payload") or _user_can_change_legacy_nfe_request(user=user, workshop=workshop, request=request)


def _user_can_view_nferequest_remote_response(*, user, workshop, request) -> bool:
    return _user_has_nferequest_permission(user=user, workshop=workshop, request=request, codename="view_nferequest_remote_response") or _user_can_change_legacy_nfe_request(user=user, workshop=workshop, request=request)


def _user_can_issue_return(*, user, workshop, request) -> bool:
    return has_workshop_perm(
        user=user,
        workshop=workshop,
        app_label="finance",
        model="fiscaldocument",
        codename="issue_nfe_return",
        request=request,
    )


def _user_can_view_return_payload(*, user, workshop, request) -> bool:
    return has_workshop_perm(
        user=user,
        workshop=workshop,
        app_label="finance",
        model="fiscaldocument",
        codename="view_nfe_return_payload",
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


def _user_can_issue_complementary_price_quantity(*, user, workshop, request) -> bool:
    return has_workshop_perm(
        user=user,
        workshop=workshop,
        app_label="finance",
        model="fiscaldocument",
        codename="issue_nfe_complementary_price_quantity",
        request=request,
    )


def _user_can_issue_adjustment(*, user, workshop, request) -> bool:
    return has_workshop_perm(
        user=user,
        workshop=workshop,
        app_label="finance",
        model="fiscaldocument",
        codename="issue_nfe_adjustment",
        request=request,
    )


def _user_can_issue_ibs_cbs_event(*, user, workshop, request) -> bool:
    return has_workshop_perm(
        user=user,
        workshop=workshop,
        app_label="finance",
        model="fiscaldocumentevent",
        codename="issue_ibs_cbs_event",
        request=request,
    )


def _user_can_cancel_ibs_cbs_event(*, user, workshop, request) -> bool:
    return has_workshop_perm(
        user=user,
        workshop=workshop,
        app_label="finance",
        model="fiscaldocumentevent",
        codename="cancel_ibs_cbs_event",
        request=request,
    )


class NfeRequestDetailView(LoginRequiredMixin, WorkshopScopedMixin, DetailView):
    model = NfeRequest
    workshop_permission_model = "nferequest"
    workshop_permission_codename = "view_nferequest"
    workshop_permission_fallbacks = (("finance", "nfserequest", "view_nfserequest"),)
    template_name = "finance/nfe_request_detail.html"
    context_object_name = "nfe_request"

    def get_queryset(self):
        return super().get_queryset().select_related("workorder", "workorder__budget", "workorder__budget__customer", "workorder__budget__vehicle", "manual_recipient").prefetch_related("items")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        latest_item = self.object.items.order_by("-id").first()
        can_cancel_nferequest = _user_can_cancel_nferequest(user=self.request.user, workshop=self.workshop, request=self.request)
        can_invalidate_nferequest_numbering = _user_can_invalidate_nferequest_numbering(user=self.request.user, workshop=self.workshop, request=self.request)
        can_download_nferequest_xml = _user_can_download_nferequest_xml(user=self.request.user, workshop=self.workshop, request=self.request)
        can_download_nferequest_pdf = _user_can_download_nferequest_pdf(user=self.request.user, workshop=self.workshop, request=self.request)
        can_cancel = bool(can_cancel_nferequest and latest_item and str(getattr(latest_item, "status", "")).strip().lower() in {"aprovado", "contingencia"})
        can_invalidate = bool(can_invalidate_nferequest_numbering and _can_invalidate_nfe_request(nfe_request=self.object, latest_item=latest_item))
        can_issue_cce = bool(latest_item and is_nfe_item_eligible_for_cce(latest_item) and not has_active_cce_event_for_nfe_item(item=latest_item) and _user_can_issue_cce(user=self.request.user, workshop=self.workshop, request=self.request))
        can_view_cce_payload = _user_can_view_cce_payload(user=self.request.user, workshop=self.workshop, request=self.request)
        can_issue_return = bool(latest_item and is_local_nfe_eligible_for_return(latest_item) and _user_can_issue_return(user=self.request.user, workshop=self.workshop, request=self.request))
        can_issue_reversal = bool(latest_item and is_local_nfe_eligible_for_return(latest_item) and _user_can_issue_reversal(user=self.request.user, workshop=self.workshop, request=self.request))
        can_view_return_payload = _user_can_view_return_payload(user=self.request.user, workshop=self.workshop, request=self.request)
        can_issue_complementary_price_quantity = bool(latest_item and is_local_nfe_eligible_for_complementary(latest_item) and _user_can_issue_complementary_price_quantity(user=self.request.user, workshop=self.workshop, request=self.request))
        can_issue_adjustment = _user_can_issue_adjustment(user=self.request.user, workshop=self.workshop, request=self.request)
        requested_operation = str(self.request.GET.get("operacao") or "").strip().lower()
        operation_entrypoints = {
            FiscalOperation.RETURN: ("Devolução", "return_nfe_modal", can_issue_return or can_issue_reversal),
            FiscalOperation.CORRECTION: ("Carta de Correção", "cce_nfe_modal", can_issue_cce),
            FiscalOperation.COMPLEMENTARY: ("Nota Complementar", "complementary_nfe_modal", can_issue_complementary_price_quantity),
            FiscalOperation.ADJUSTMENT: ("Nota de Ajuste", "adjustment_nfe_modal", can_issue_adjustment),
        }
        operation_entrypoint = operation_entrypoints.get(requested_operation)
        fiscal_document = FiscalDocument.objects.filter(workshop=self.workshop, legacy_nfe_item=latest_item).first() if latest_item is not None else None
        can_issue_ibs_cbs_event_112110 = bool(fiscal_document and is_document_eligible_for_ibs_cbs_event_112110(fiscal_document) and _user_can_issue_ibs_cbs_event(user=self.request.user, workshop=self.workshop, request=self.request))
        can_issue_ibs_cbs_event_112130 = bool(fiscal_document and is_document_eligible_for_ibs_cbs_event_112130(fiscal_document) and _user_can_issue_ibs_cbs_event(user=self.request.user, workshop=self.workshop, request=self.request))
        can_issue_ibs_cbs_event_112150 = bool(fiscal_document and is_document_eligible_for_ibs_cbs_event_112150(fiscal_document) and _user_can_issue_ibs_cbs_event(user=self.request.user, workshop=self.workshop, request=self.request))
        can_cancel_ibs_cbs_event_112110 = _user_can_cancel_ibs_cbs_event(user=self.request.user, workshop=self.workshop, request=self.request)
        can_cancel_ibs_cbs_event_112130 = can_cancel_ibs_cbs_event_112110
        can_cancel_ibs_cbs_event_112150 = can_cancel_ibs_cbs_event_112110
        cce_events = FiscalDocumentEvent.objects.none()
        ibs_cbs_events = FiscalDocumentEvent.objects.none()
        ibs_cbs_cancellation_events = FiscalDocumentEvent.objects.none()
        return_documents = FiscalDocument.objects.none()
        complementary_documents = FiscalDocument.objects.none()
        adjustment_documents = FiscalDocument.objects.none()
        if latest_item is not None:
            cce_events = FiscalDocumentEvent.objects.filter(document__workshop=self.workshop, document__legacy_nfe_item=latest_item, event_type=FiscalDocumentEventType.CCE).order_by("event_sequence")
            ibs_cbs_events = FiscalDocumentEvent.objects.filter(document__workshop=self.workshop, document__legacy_nfe_item=latest_item, event_type=FiscalDocumentEventType.IBS_CBS).order_by("event_code", "event_sequence")
            ibs_cbs_cancellation_events = FiscalDocumentEvent.objects.filter(document__workshop=self.workshop, document__legacy_nfe_item=latest_item, event_type=FiscalDocumentEventType.IBS_CBS_CANCELLATION).select_related("related_event").order_by("related_event__event_code", "related_event__event_sequence", "event_sequence")
            return_documents = FiscalDocument.objects.filter(links_from__related_document__legacy_nfe_item=latest_item, links_from__role__in=[FiscalDocumentLinkRole.RETURNS, FiscalDocumentLinkRole.REVERSES]).distinct().order_by("criado_em")
            complementary_documents = FiscalDocument.objects.filter(links_from__related_document__legacy_nfe_item=latest_item, links_from__role=FiscalDocumentLinkRole.COMPLEMENTS, purpose=FiscalDocumentPurpose.COMPLEMENTARY).distinct().order_by("criado_em")
            adjustment_documents = FiscalDocument.objects.filter(links_from__related_document__legacy_nfe_item=latest_item, links_from__role=FiscalDocumentLinkRole.ADJUSTS, purpose=FiscalDocumentPurpose.ADJUSTMENT).distinct().order_by("criado_em")
        fallback_back_url = reverse("finance:nfe_list")
        context.update(
            {
                "back_url": build_issued_documents_back_url(query_params=self.request.GET, fallback_url=fallback_back_url),
                "latest_item": latest_item,
                "can_cancel": can_cancel,
                "request_fields": [
                    _build_field("ID da requisição", self.object.pk),
                    _build_field("Origem", self.object.get_emission_origin_display()),
                    _build_field("Ordem de serviço", self.object.workorder),
                    _build_field("Cliente", self.object.customer_name),
                    _build_field("Classe de imposto", self.object.tax_class),
                    _build_field("Número da Nota Fiscal de Produto", self.object.reserved_number),
                    _build_field("Série da Nota Fiscal de Produto", self.object.reserved_series),
                    _build_field("Criado em", self.object.criado_em.strftime("%d/%m/%Y %H:%M") if self.object.criado_em else "-"),
                    _build_field("Atualizado em", self.object.atualizado_em.strftime("%d/%m/%Y %H:%M") if self.object.atualizado_em else "-"),
                ],
                "latest_item_status_badge": _format_item_status_badge(getattr(latest_item, "status", "")),
                "can_invalidate": can_invalidate,
                "can_download_nferequest_xml": can_download_nferequest_xml,
                "can_download_nferequest_pdf": can_download_nferequest_pdf,
                "can_view_nferequest_payload": _user_can_view_nferequest_payload(user=self.request.user, workshop=self.workshop, request=self.request),
                "can_view_nferequest_remote_response": _user_can_view_nferequest_remote_response(user=self.request.user, workshop=self.workshop, request=self.request),
                "can_issue_cce": can_issue_cce,
                "can_view_cce_payload": can_view_cce_payload,
                "can_issue_return": can_issue_return,
                "can_issue_reversal": can_issue_reversal,
                "can_view_return_payload": can_view_return_payload,
                "can_issue_complementary_price_quantity": can_issue_complementary_price_quantity,
                "can_issue_adjustment": can_issue_adjustment,
                "gateway_operation_label": operation_entrypoint[0] if operation_entrypoint else "",
                "gateway_operation_modal_id": operation_entrypoint[1] if operation_entrypoint and operation_entrypoint[2] else "",
                "gateway_operation_unavailable": bool(operation_entrypoint and not operation_entrypoint[2]),
                "can_issue_ibs_cbs_event_112110": can_issue_ibs_cbs_event_112110,
                "can_issue_ibs_cbs_event_112130": can_issue_ibs_cbs_event_112130,
                "can_issue_ibs_cbs_event_112150": can_issue_ibs_cbs_event_112150,
                "can_cancel_ibs_cbs_event_112110": can_cancel_ibs_cbs_event_112110,
                "can_cancel_ibs_cbs_event_112130": can_cancel_ibs_cbs_event_112130,
                "can_cancel_ibs_cbs_event_112150": can_cancel_ibs_cbs_event_112150,
                "ibs_cbs_event_code_112110": IBS_CBS_EVENT_112110,
                "ibs_cbs_event_code_112130": IBS_CBS_EVENT_112130,
                "ibs_cbs_event_code_112150": IBS_CBS_EVENT_112150,
                "cce_form": NfeCorrectionForm(),
                "cce_events": cce_events,
                "ibs_cbs_events": ibs_cbs_events,
                "ibs_cbs_cancellation_events": ibs_cbs_cancellation_events,
                "nfe_return_form": NfeReturnForm(),
                "return_documents": return_documents,
                "nfe_complementary_form": NfeComplementaryPriceQuantityForm(),
                "complementary_documents": complementary_documents,
                "nfe_adjustment_form": NfeAdjustmentForm(),
                "ibs_cbs_event_112130_form": NfeIbsCbsEvent112130Form(),
                "adjustment_documents": adjustment_documents,
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
            messages.success(request, "Carta de correcao enviada para a Webmania.")

        return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfe_detail", pk=nfe_request.pk, query_params=request.GET))


class NfeIbsCbsEvent112110IssueView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "fiscaldocumentevent"
    workshop_permission_codename = "issue_ibs_cbs_event"

    def post(self, request, *args, **kwargs):
        nfe_request = get_object_or_404(NfeRequest, pk=kwargs.get("pk"), workshop=self.workshop)
        latest_item = nfe_request.items.order_by("-id").first()
        document = FiscalDocument.objects.filter(workshop=self.workshop, legacy_nfe_item=latest_item).first() if latest_item is not None else None
        if document is None:
            messages.error(request, "Evento IBS/CBS 112110 exige documento fiscal local projetado e autorizado.")
            return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfe_detail", pk=nfe_request.pk, query_params=request.GET))

        if request.POST.get("confirm_ibs_cbs_event_112110") != "on":
            messages.error(request, "Confirme a responsabilidade fiscal antes de registrar o evento IBS/CBS.")
            return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfe_detail", pk=nfe_request.pk, query_params=request.GET))

        try:
            emit_ibs_cbs_event_112110(document=document, requested_by=request.user, request=request)
        except NfeIbsCbsEventError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Evento IBS/CBS 112110 enviado para a Webmania.")
        return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfe_detail", pk=nfe_request.pk, query_params=request.GET))


class NfeIbsCbsEvent112150IssueView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "fiscaldocumentevent"
    workshop_permission_codename = "issue_ibs_cbs_event"

    def post(self, request, *args, **kwargs):
        nfe_request = get_object_or_404(NfeRequest, pk=kwargs.get("pk"), workshop=self.workshop)
        latest_item = nfe_request.items.order_by("-id").first()
        document = FiscalDocument.objects.filter(workshop=self.workshop, legacy_nfe_item=latest_item).first() if latest_item is not None else None
        if document is None:
            messages.error(request, "Evento IBS/CBS 112150 exige documento fiscal local projetado e autorizado.")
            return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfe_detail", pk=nfe_request.pk, query_params=request.GET))

        form = NfeIbsCbsEvent112150Form(request.POST)
        if not form.is_valid():
            messages.error(request, "Informe a data de previsao de entrega no formato YYYY-MM-DD e confirme a responsabilidade fiscal.")
            return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfe_detail", pk=nfe_request.pk, query_params=request.GET))

        try:
            emit_ibs_cbs_event_112150(document=document, delivery_forecast_date=form.cleaned_data["data_previsao_entrega"], requested_by=request.user, request=request)
        except NfeIbsCbsEventError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Evento IBS/CBS 112150 enviado para a Webmania.")
        return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfe_detail", pk=nfe_request.pk, query_params=request.GET))


class NfeIbsCbsEvent112130IssueView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "fiscaldocumentevent"
    workshop_permission_codename = "issue_ibs_cbs_event"

    def post(self, request, *args, **kwargs):
        nfe_request = get_object_or_404(NfeRequest, pk=kwargs.get("pk"), workshop=self.workshop)
        latest_item = nfe_request.items.order_by("-id").first()
        document = FiscalDocument.objects.filter(workshop=self.workshop, legacy_nfe_item=latest_item).first() if latest_item is not None else None
        if document is None:
            messages.error(request, "Evento IBS/CBS 112130 exige documento fiscal local projetado e autorizado.")
            return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfe_detail", pk=nfe_request.pk, query_params=request.GET))

        form = NfeIbsCbsEvent112130Form(request.POST)
        if not form.is_valid():
            messages.error(request, "Informe item, valores IBS/CBS, controle de perecimento e confirme a responsabilidade fiscal.")
            return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfe_detail", pk=nfe_request.pk, query_params=request.GET))

        try:
            emit_ibs_cbs_event_112130(document=document, items=form.to_event_items(), requested_by=request.user, request=request)
        except NfeIbsCbsEventError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Evento IBS/CBS 112130 enviado para a Webmania.")
        return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfe_detail", pk=nfe_request.pk, query_params=request.GET))


class NfeIbsCbsEvent112110CancelView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "fiscaldocumentevent"
    workshop_permission_codename = "cancel_ibs_cbs_event"

    def post(self, request, *args, **kwargs):
        nfe_request = get_object_or_404(NfeRequest, pk=kwargs.get("pk"), workshop=self.workshop)
        event = get_object_or_404(
            FiscalDocumentEvent.objects.select_related("document", "document__legacy_nfe_item"),
            pk=kwargs.get("event_pk"),
            document__workshop=self.workshop,
            document__legacy_nfe_item__request=nfe_request,
            event_type__in=[FiscalDocumentEventType.IBS_CBS, FiscalDocumentEventType.IBS_CBS_CANCELLATION],
            event_code=IBS_CBS_EVENT_112110,
        )
        if request.POST.get("confirm_ibs_cbs_event_cancel_112110") != "on":
            messages.error(request, "Confirme a responsabilidade fiscal antes de cancelar o evento IBS/CBS.")
            return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfe_detail", pk=nfe_request.pk, query_params=request.GET))

        try:
            cancel_ibs_cbs_event_112110(event=event, requested_by=request.user, request=request)
        except NfeIbsCbsEventError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Cancelamento do evento IBS/CBS 112110 enviado para a Webmania.")
        return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfe_detail", pk=nfe_request.pk, query_params=request.GET))


class NfeIbsCbsEvent112150CancelView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "fiscaldocumentevent"
    workshop_permission_codename = "cancel_ibs_cbs_event"

    def post(self, request, *args, **kwargs):
        nfe_request = get_object_or_404(NfeRequest, pk=kwargs.get("pk"), workshop=self.workshop)
        event = get_object_or_404(
            FiscalDocumentEvent.objects.select_related("document", "document__legacy_nfe_item"),
            pk=kwargs.get("event_pk"),
            document__workshop=self.workshop,
            document__legacy_nfe_item__request=nfe_request,
            event_type=FiscalDocumentEventType.IBS_CBS,
            event_code=IBS_CBS_EVENT_112150,
        )
        if request.POST.get("confirm_ibs_cbs_event_cancel_112150") != "on":
            messages.error(request, "Confirme a responsabilidade fiscal antes de cancelar o evento IBS/CBS.")
            return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfe_detail", pk=nfe_request.pk, query_params=request.GET))

        try:
            cancel_ibs_cbs_event_112150(event=event, requested_by=request.user, request=request)
        except NfeIbsCbsEventError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Cancelamento do evento IBS/CBS 112150 enviado para a Webmania.")
        return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfe_detail", pk=nfe_request.pk, query_params=request.GET))


class NfeIbsCbsEvent112130CancelView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "fiscaldocumentevent"
    workshop_permission_codename = "cancel_ibs_cbs_event"

    def post(self, request, *args, **kwargs):
        nfe_request = get_object_or_404(NfeRequest, pk=kwargs.get("pk"), workshop=self.workshop)
        event = get_object_or_404(
            FiscalDocumentEvent.objects.select_related("document", "document__legacy_nfe_item"),
            pk=kwargs.get("event_pk"),
            document__workshop=self.workshop,
            document__legacy_nfe_item__request=nfe_request,
            event_type=FiscalDocumentEventType.IBS_CBS,
            event_code=IBS_CBS_EVENT_112130,
        )
        if request.POST.get("confirm_ibs_cbs_event_cancel_112130") != "on":
            messages.error(request, "Confirme a responsabilidade fiscal antes de cancelar o evento IBS/CBS.")
            return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfe_detail", pk=nfe_request.pk, query_params=request.GET))

        try:
            cancel_ibs_cbs_event_112130(event=event, requested_by=request.user, request=request)
        except NfeIbsCbsEventError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Cancelamento do evento IBS/CBS 112130 enviado para a Webmania.")
        return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfe_detail", pk=nfe_request.pk, query_params=request.GET))


class NfeReturnIssueView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nferequest"
    workshop_permission_codename = "view_nferequest"
    workshop_permission_fallbacks = (("finance", "nfserequest", "view_nfserequest"),)

    def post(self, request, *args, **kwargs):
        nfe_request = get_object_or_404(NfeRequest, pk=kwargs.get("pk"), workshop=self.workshop)
        latest_item = nfe_request.items.order_by("-id").first()
        if not is_local_nfe_eligible_for_return(latest_item):
            messages.error(request, "Devolucao ou estorno permitidos somente para NF-e autorizada com chave de acesso valida.")
            return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfe_detail", pk=nfe_request.pk, query_params=request.GET))

        form = NfeReturnForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Informe finalidade, CFOP, natureza da operacao e produtos validos para devolucao ou estorno.")
            return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfe_detail", pk=nfe_request.pk, query_params=request.GET))

        purpose = str(form.cleaned_data["purpose"])
        if purpose == FiscalDocumentPurpose.REVERSAL:
            has_permission = _user_can_issue_reversal(user=request.user, workshop=self.workshop, request=request)
        else:
            has_permission = _user_can_issue_return(user=request.user, workshop=self.workshop, request=request)
        if not has_permission:
            messages.error(request, "Usuario sem permissao especifica para esta operacao fiscal.")
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
            messages.success(request, "Devolucao ou estorno enviado para a Webmania.")

        return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfe_detail", pk=nfe_request.pk, query_params=request.GET))


class NfeComplementaryPriceQuantityIssueView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "fiscaldocument"
    workshop_permission_codename = "issue_nfe_complementary_price_quantity"

    def post(self, request, *args, **kwargs):
        nfe_request = get_object_or_404(NfeRequest, pk=kwargs.get("pk"), workshop=self.workshop)
        latest_item = nfe_request.items.order_by("-id").first()
        if not is_local_nfe_eligible_for_complementary(latest_item):
            messages.error(request, "Nota Complementar permitida somente para NF-e local autorizada com chave ou UUID valido.")
            return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfe_detail", pk=nfe_request.pk, query_params=request.GET))

        form = NfeComplementaryPriceQuantityForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Informe operacao, CFOP, natureza, itens validos e confirme a emissao da Nota Complementar.")
            return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfe_detail", pk=nfe_request.pk, query_params=request.GET))

        try:
            create_and_emit_nfe_complementary_price_quantity_from_item(
                item=latest_item,
                items=form.cleaned_data["itens_json"],
                requested_by=request.user,
                operacao=str(form.cleaned_data["operacao"]),
                natureza_operacao=str(form.cleaned_data["natureza_operacao"]),
                codigo_cfop=str(form.cleaned_data["codigo_cfop"]),
                legal_confirmation=bool(form.cleaned_data["confirm_complementary"]),
                request=request,
            )
        except NfeComplementaryError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Nota Fiscal Complementar enviada para a Webmania.")

        return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfe_detail", pk=nfe_request.pk, query_params=request.GET))


class NfeAdjustmentIssueView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "fiscaldocument"
    workshop_permission_codename = "issue_nfe_adjustment"

    def post(self, request, *args, **kwargs):
        nfe_request = get_object_or_404(NfeRequest, pk=kwargs.get("pk"), workshop=self.workshop)
        latest_item = nfe_request.items.order_by("-id").first()
        related_document = FiscalDocument.objects.filter(workshop=self.workshop, legacy_nfe_item=latest_item).first() if latest_item is not None else None

        form = NfeAdjustmentForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Informe os dados obrigatorios da Nota Fiscal de Ajuste e confirme as restricoes fiscais.")
            return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfe_detail", pk=nfe_request.pk, query_params=request.GET))

        try:
            validate_adjustment_tax_regime(workshop=self.workshop)
            create_and_emit_nfe_adjustment(
                workshop=self.workshop,
                requested_by=request.user,
                operacao=form.cleaned_data["operacao"],
                natureza_operacao=str(form.cleaned_data["natureza_operacao"]),
                codigo_cfop=str(form.cleaned_data["codigo_cfop"]),
                valor_icms=form.cleaned_data["valor_icms"],
                valor_icms_st=form.cleaned_data.get("valor_icms_st"),
                situacao_tributaria=str(form.cleaned_data["situacao_tributaria"]),
                cliente=form.cleaned_data["cliente_json"],
                informacoes_fisco=str(form.cleaned_data.get("informacoes_fisco") or ""),
                informacoes_complementares=str(form.cleaned_data.get("informacoes_complementares") or ""),
                related_document=related_document,
                legal_confirmation=bool(form.cleaned_data["confirm_adjustment"]),
                estorno_sc_es_confirmation=bool(form.cleaned_data["confirm_not_sc_es_reversal"]),
                request=request,
            )
        except NfeAdjustmentError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Nota Fiscal de Ajuste enviada para a Webmania.")

        return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfe_detail", pk=nfe_request.pk, query_params=request.GET))


class NfeRequestCancelView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nferequest"
    workshop_permission_codename = "cancel_nferequest"
    workshop_permission_fallbacks = (("finance", "nferequest", "change_nferequest"), ("finance", "nfserequest", "change_nfserequest"))

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
        return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfe_detail", pk=nfe_request.pk, query_params=request.GET))


class NfeRequestReconcileView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nferequest"
    workshop_permission_codename = "change_nferequest"
    workshop_permission_fallbacks = (("finance", "nfserequest", "change_nfserequest"),)

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
    workshop_permission_model = "nferequest"
    workshop_permission_codename = "invalidate_nferequest_numbering"
    workshop_permission_fallbacks = (("finance", "nferequest", "change_nferequest"), ("finance", "nfserequest", "change_nfserequest"))

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


class NfeDocumentDownloadView(LoginRequiredMixin, View):
    document_fields = {
        "xml": ("xml_url", "xml"),
        "danfe": ("danfe_url", "pdf"),
        "danfe_simples": ("danfe_simple_url", "pdf"),
        "danfe_etiqueta": ("danfe_label_url", "pdf"),
    }

    def dispatch(self, request, *args, **kwargs):
        self.workshop = get_active_workshop_or_404(request)
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        nfe_request = get_object_or_404(NfeRequest, pk=kwargs.get("pk"), workshop=self.workshop)
        document_kind = str(kwargs.get("document") or "").strip().lower()
        if document_kind not in self.document_fields:
            raise Http404("Documento nao suportado")

        if document_kind == "xml":
            can_download = _user_can_download_nferequest_xml(user=request.user, workshop=self.workshop, request=request)
        else:
            can_download = _user_can_download_nferequest_pdf(user=request.user, workshop=self.workshop, request=request)
        if not can_download:
            raise PermissionDenied

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
            event_type="cce",
        )
        field_name, extension = self.document_fields[document_kind]
        document_url = str(getattr(event, field_name, "") or "").strip()

        try:
            downloaded = download_webmania_document(workshop=self.workshop, url=document_url)
        except WebmaniaDocumentDownloadError as exc:
            return HttpResponse(str(exc), status=502, content_type="text/plain; charset=utf-8")

        response = HttpResponse(downloaded.content, content_type=downloaded.content_type)
        response["Content-Disposition"] = self._build_content_disposition(event=event, document_kind=document_kind, extension=extension)
        return response

    @staticmethod
    def _build_content_disposition(*, event: FiscalDocumentEvent, document_kind: str, extension: str) -> str:
        identifier = str(event.remote_uuid or event.document.access_key or event.pk or "documento").strip()
        safe_identifier = identifier.replace(" ", "-")
        return f'attachment; filename="nfe-cce-{document_kind}-{safe_identifier}.{extension}"'


class NfeCorrectionPayloadView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "fiscaldocumentevent"
    workshop_permission_codename = "view_nfe_correction_payload"

    def get(self, request, *args, **kwargs):
        nfe_request = get_object_or_404(NfeRequest, pk=kwargs.get("pk"), workshop=self.workshop)
        event = get_object_or_404(
            FiscalDocumentEvent.objects.select_related("document", "document__legacy_nfe_item"),
            pk=kwargs.get("event_pk"),
            document__workshop=self.workshop,
            document__legacy_nfe_item__request=nfe_request,
            event_type=FiscalDocumentEventType.CCE,
        )
        return JsonResponse(
            {
                "request_payload": sanitize_fiscal_payload(event.request_payload or {}),
                "response_payload": sanitize_fiscal_payload(event.response_payload or {}),
                "status": event.status,
                "event_sequence": event.event_sequence,
            }
        )


class NfeIbsCbsEventDownloadView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "fiscaldocumentevent"
    workshop_permission_codename = "download_ibs_cbs_event"

    def get(self, request, *args, **kwargs):
        nfe_request = get_object_or_404(NfeRequest, pk=kwargs.get("pk"), workshop=self.workshop)
        event = get_object_or_404(
            FiscalDocumentEvent.objects.select_related("document", "document__legacy_nfe_item"),
            pk=kwargs.get("event_pk"),
            document__workshop=self.workshop,
            document__legacy_nfe_item__request=nfe_request,
            event_type__in=[FiscalDocumentEventType.IBS_CBS, FiscalDocumentEventType.IBS_CBS_CANCELLATION],
        )
        try:
            downloaded = download_webmania_document(workshop=self.workshop, url=str(event.xml_url or "").strip())
        except WebmaniaDocumentDownloadError as exc:
            return HttpResponse(str(exc), status=502, content_type="text/plain; charset=utf-8")

        response = HttpResponse(downloaded.content, content_type=downloaded.content_type)
        identifier = str(event.remote_uuid or event.document.access_key or event.pk or "documento").strip().replace(" ", "-")
        response["Content-Disposition"] = f'attachment; filename="nfe-ibs-cbs-evento-{event.event_code or "evento"}-{identifier}.xml"'
        return response


class NfeIbsCbsEventPayloadView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "fiscaldocumentevent"
    workshop_permission_codename = "view_ibs_cbs_event_payload"

    def get(self, request, *args, **kwargs):
        nfe_request = get_object_or_404(NfeRequest, pk=kwargs.get("pk"), workshop=self.workshop)
        event = get_object_or_404(
            FiscalDocumentEvent.objects.select_related("document", "document__legacy_nfe_item"),
            pk=kwargs.get("event_pk"),
            document__workshop=self.workshop,
            document__legacy_nfe_item__request=nfe_request,
            event_type__in=[FiscalDocumentEventType.IBS_CBS, FiscalDocumentEventType.IBS_CBS_CANCELLATION],
        )
        return JsonResponse(
            {
                "request_payload": event.request_payload or {},
                "response_payload": event.response_payload or {},
            }
        )


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
            raise Http404("Documento nao suportado")

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
        response["Content-Disposition"] = self._build_content_disposition(document=document, document_kind=document_kind, extension=extension)
        return response

    @staticmethod
    def _build_content_disposition(*, document: FiscalDocument, document_kind: str, extension: str) -> str:
        identifier = str(document.number or document.access_key or document.remote_uuid or document.pk or "documento").strip()
        safe_identifier = identifier.replace(" ", "-")
        return f'attachment; filename="nfe-{document.purpose}-{document_kind}-{safe_identifier}.{extension}"'


class NfeReturnPayloadView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "fiscaldocument"
    workshop_permission_codename = "view_nfe_return_payload"

    def get(self, request, *args, **kwargs):
        nfe_request = get_object_or_404(NfeRequest, pk=kwargs.get("pk"), workshop=self.workshop)
        document = get_object_or_404(
            FiscalDocument.objects.filter(links_from__related_document__legacy_nfe_item__request=nfe_request).distinct(),
            pk=kwargs.get("document_pk"),
            workshop=self.workshop,
            purpose__in=[FiscalDocumentPurpose.RETURN, FiscalDocumentPurpose.REVERSAL],
        )
        return JsonResponse(
            {
                "request_payload": document.request_payload or {},
                "response_payload": document.response_payload or {},
                "status": document.status,
                "purpose": document.purpose,
            }
        )


class NfeComplementaryDownloadView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "fiscaldocument"
    workshop_permission_codename = "download_nfe_complementary"

    document_fields = {
        "xml": ("xml_url", "xml"),
        "danfe": ("danfe_url", "pdf"),
    }

    def get(self, request, *args, **kwargs):
        nfe_request = get_object_or_404(NfeRequest, pk=kwargs.get("pk"), workshop=self.workshop)
        document_kind = str(kwargs.get("document") or "").strip().lower()
        if document_kind not in self.document_fields:
            raise Http404("Documento nao suportado")

        document = get_object_or_404(
            FiscalDocument.objects.filter(links_from__related_document__legacy_nfe_item__request=nfe_request).distinct(),
            pk=kwargs.get("document_pk"),
            workshop=self.workshop,
            purpose=FiscalDocumentPurpose.COMPLEMENTARY,
        )
        field_name, extension = self.document_fields[document_kind]
        document_url = str(getattr(document, field_name, "") or "").strip()

        try:
            downloaded = download_webmania_document(workshop=self.workshop, url=document_url)
        except WebmaniaDocumentDownloadError as exc:
            return HttpResponse(str(exc), status=502, content_type="text/plain; charset=utf-8")

        response = HttpResponse(downloaded.content, content_type=downloaded.content_type)
        identifier = str(document.number or document.access_key or document.remote_uuid or document.pk or "documento").strip().replace(" ", "-")
        response["Content-Disposition"] = f'attachment; filename="nfe-complementar-{document_kind}-{identifier}.{extension}"'
        return response


class NfeAdjustmentDownloadView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "fiscaldocument"
    workshop_permission_codename = "download_nfe_adjustment"

    document_fields = {
        "xml": ("xml_url", "xml"),
        "danfe": ("danfe_url", "pdf"),
    }

    def get(self, request, *args, **kwargs):
        nfe_request = get_object_or_404(NfeRequest, pk=kwargs.get("pk"), workshop=self.workshop)
        document_kind = str(kwargs.get("document") or "").strip().lower()
        if document_kind not in self.document_fields:
            raise Http404("Documento nao suportado")

        document = get_object_or_404(
            FiscalDocument.objects.filter(links_from__related_document__legacy_nfe_item__request=nfe_request, links_from__role=FiscalDocumentLinkRole.ADJUSTS).distinct(),
            pk=kwargs.get("document_pk"),
            workshop=self.workshop,
            purpose=FiscalDocumentPurpose.ADJUSTMENT,
        )
        field_name, extension = self.document_fields[document_kind]
        document_url = str(getattr(document, field_name, "") or "").strip()

        try:
            downloaded = download_webmania_document(workshop=self.workshop, url=document_url)
        except WebmaniaDocumentDownloadError as exc:
            return HttpResponse(str(exc), status=502, content_type="text/plain; charset=utf-8")

        response = HttpResponse(downloaded.content, content_type=downloaded.content_type)
        identifier = str(document.number or document.access_key or document.remote_uuid or document.pk or "documento").strip().replace(" ", "-")
        response["Content-Disposition"] = f'attachment; filename="nfe-ajuste-{document_kind}-{identifier}.{extension}"'
        return response


@method_decorator(xframe_options_exempt, name="dispatch")
class NfePreviewPdfView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nferequest"
    workshop_permission_codename = "view_nferequest"
    workshop_permission_fallbacks = (("finance", "nfserequest", "view_nfserequest"),)

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
            return HttpResponse(str(exc), status=502, content_type="text/plain; charset=utf-8")

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
    workshop_permission_model = "nferequest"
    workshop_permission_codename = "view_nferequest"
    workshop_permission_fallbacks = (("finance", "nfserequest", "view_nfserequest"),)
    template_name = "finance/nfe_request_form.html"
    partial_template_name = "finance/partials/nfe_step_content.html"
    preview_template_name = "finance/partials/nfe_step3_preview.html"
    step3_form_class = NfeRequestStep3Form
    preview_initial_fields = ("pricing_slider", "tax_class", "additional_information")
    tax_class_kind = "nfe"
    tax_class_warning_message = "Nao foi possivel carregar classes de imposto de Nota Fiscal de Produto: {error}"
    success_redirect_name = "finance:nfe_emit"
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
        invalid_ncm_modal = build_invalid_ncm_modal_context(workorder=self.object.workorder, return_url=self.request.get_full_path())
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
        invalid_ncm_modal = build_invalid_ncm_modal_context(workorder=self.object.workorder, return_url=self.request.get_full_path())
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
    missing_update_redirect_name = "finance:nfe_emit"
