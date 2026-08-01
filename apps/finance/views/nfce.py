from __future__ import annotations

import json

from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, HttpResponse
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import FormView, ListView

from apps.core.presentation.forms import CoreForm
from apps.finance.models.finance import FiscalDocument, FiscalDocumentEvent, FiscalDocumentEventType, FiscalDocumentOrigin, FiscalDocumentPurpose, FiscalDocumentType, FiscalNumberInutilization
from apps.finance.services.nfce_cancellation import NfceCancellationError, cancel_nfce_document, is_nfce_document_eligible_for_cancellation
from apps.finance.services.nfce_emission import NfceEmissionError, create_and_emit_nfce, validate_nfce_configuration
from apps.finance.services.nfce_inutilization import NfceInutilizationError, create_and_transmit_nfce_inutilization
from apps.core.infrastructure.services.webmania.webmania_documents import WebmaniaDocumentDownloadError, download_webmania_document
from apps.workshops.mixin import WorkshopScopedMixin
from apps.workshops.util.workshops import has_workshop_perm


class NfceManualEmissionForm(CoreForm):
    environment = forms.ChoiceField(choices=(("2", "Homologacao"), ("1", "Producao")))
    natureza_operacao = forms.CharField(max_length=120, initial="Venda ao consumidor")
    cliente_json = forms.CharField(required=False, widget=forms.Textarea)
    produtos_json = forms.CharField(widget=forms.Textarea)
    payment_method = forms.ChoiceField(choices=(("01", "Dinheiro"), ("03", "Cartao de credito"), ("04", "Cartao de debito"), ("17", "PIX"), ("99", "Outros")))
    confirm_nfce = forms.BooleanField(required=True)

    def clean_cliente_json(self):
        raw_value = str(self.cleaned_data.get("cliente_json") or "").strip()
        if not raw_value:
            return {}
        try:
            customer = json.loads(raw_value)
        except ValueError as exc:
            raise forms.ValidationError("Informe consumidor/cliente em JSON valido.") from exc
        if not isinstance(customer, dict):
            raise forms.ValidationError("Consumidor/cliente deve ser um objeto JSON.")
        return customer

    def clean_produtos_json(self):
        raw_value = str(self.cleaned_data.get("produtos_json") or "").strip()
        try:
            products = json.loads(raw_value)
        except ValueError as exc:
            raise forms.ValidationError("Informe produtos em JSON valido.") from exc
        if not isinstance(products, list):
            raise forms.ValidationError("Produtos devem ser uma lista JSON.")
        return products


class NfceCancellationForm(CoreForm):
    motivo = forms.CharField(min_length=15, max_length=255, widget=forms.Textarea)
    confirm_cancel = forms.BooleanField(required=True)


class NfceInutilizationForm(CoreForm):
    environment = forms.ChoiceField(choices=(("2", "Homologacao"), ("1", "Producao")))
    series = forms.CharField(max_length=10)
    sequence_start = forms.IntegerField(min_value=1)
    sequence_end = forms.IntegerField(min_value=1, required=False)
    reason = forms.CharField(min_length=15, max_length=255, widget=forms.Textarea)
    confirm_local_limitation = forms.BooleanField(required=True)

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get("sequence_start")
        end = cleaned_data.get("sequence_end") or start
        if start is not None and end is not None and int(start) > int(end):
            raise forms.ValidationError("A sequencia inicial nao pode ser maior que a final.")
        cleaned_data["sequence_end"] = end
        return cleaned_data


def _user_can_issue_nfce(*, user, workshop, request) -> bool:
    return has_workshop_perm(user=user, workshop=workshop, app_label="finance", model="fiscaldocument", codename="issue_nfce", request=request)


def _user_can_cancel_nfce(*, user, workshop, request) -> bool:
    return has_workshop_perm(user=user, workshop=workshop, app_label="finance", model="fiscaldocument", codename="cancel_nfce", request=request)


def _user_can_inutilize_nfce(*, user, workshop, request) -> bool:
    return has_workshop_perm(user=user, workshop=workshop, app_label="finance", model="fiscalnumberinutilization", codename="inutilize_nfce_numbering", request=request)


def _user_can_download_nfce_inutilization(*, user, workshop, request) -> bool:
    return has_workshop_perm(user=user, workshop=workshop, app_label="finance", model="fiscalnumberinutilization", codename="download_nfce_inutilization", request=request)


def _user_can_view_nfce_inutilization_payload(*, user, workshop, request) -> bool:
    return has_workshop_perm(user=user, workshop=workshop, app_label="finance", model="fiscalnumberinutilization", codename="view_nfce_inutilization_payload", request=request)


class NfceDocumentListView(LoginRequiredMixin, WorkshopScopedMixin, ListView):
    model = FiscalDocument
    workshop_permission_app_label = "finance"
    workshop_permission_model = "fiscaldocument"
    workshop_permission_codename = "view_nfce"
    template_name = "finance/nfce_document_list.html"
    context_object_name = "nfce_documents"

    def get_queryset(self):
        return (
            FiscalDocument.objects.filter(
                workshop=self.workshop,
                document_type=FiscalDocumentType.NFCE,
                origin=FiscalDocumentOrigin.MANUAL,
                purpose=FiscalDocumentPurpose.NORMAL,
            )
            .select_related("requested_by")
            .prefetch_related("events")
            .order_by("-criado_em", "-pk")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        can_issue = _user_can_issue_nfce(user=self.request.user, workshop=self.workshop, request=self.request)
        config_ready = False
        if can_issue:
            try:
                validate_nfce_configuration(workshop=self.workshop, environment=2)
            except NfceEmissionError:
                config_ready = False
            else:
                config_ready = True
        context["can_issue_nfce"] = can_issue and config_ready
        context["can_cancel_nfce"] = _user_can_cancel_nfce(user=self.request.user, workshop=self.workshop, request=self.request)
        context["can_inutilize_nfce"] = _user_can_inutilize_nfce(user=self.request.user, workshop=self.workshop, request=self.request)
        context["can_download_nfce_inutilization"] = _user_can_download_nfce_inutilization(user=self.request.user, workshop=self.workshop, request=self.request)
        context["can_view_nfce_inutilization_payload"] = _user_can_view_nfce_inutilization_payload(user=self.request.user, workshop=self.workshop, request=self.request)
        context["nfce_inutilizations"] = FiscalNumberInutilization.objects.filter(workshop=self.workshop, document_type=FiscalDocumentType.NFCE).select_related("requested_by").order_by("-criado_em", "-pk")[:20]
        return context


class NfceManualEmissionView(LoginRequiredMixin, WorkshopScopedMixin, FormView):
    form_class = NfceManualEmissionForm
    workshop_permission_app_label = "finance"
    workshop_permission_model = "fiscaldocument"
    workshop_permission_codename = "issue_nfce"
    template_name = "finance/nfce_manual_form.html"

    def get_success_url(self) -> str:
        return reverse("finance:nfce_list")

    def form_valid(self, form):
        try:
            validate_nfce_configuration(workshop=self.workshop, environment=int(form.cleaned_data["environment"]))
            create_and_emit_nfce(
                workshop=self.workshop,
                requested_by=self.request.user,
                environment=int(form.cleaned_data["environment"]),
                natureza_operacao=str(form.cleaned_data["natureza_operacao"]),
                products=form.cleaned_data["produtos_json"],
                customer=form.cleaned_data["cliente_json"],
                payment_method=str(form.cleaned_data["payment_method"]),
                legal_confirmation=bool(form.cleaned_data["confirm_nfce"]),
                request=self.request,
            )
        except NfceEmissionError as exc:
            messages.error(self.request, str(exc))
            return self.form_invalid(form)
        messages.success(self.request, "NFC-e enviada com sucesso.")
        return redirect(self.get_success_url())


class NfceCancellationView(LoginRequiredMixin, WorkshopScopedMixin, FormView):
    form_class = NfceCancellationForm
    workshop_permission_app_label = "finance"
    workshop_permission_model = "fiscaldocument"
    workshop_permission_codename = "cancel_nfce"
    template_name = "finance/nfce_cancellation_form.html"

    def get_document(self) -> FiscalDocument:
        return get_object_or_404(
            FiscalDocument,
            pk=self.kwargs.get("pk"),
            workshop=self.workshop,
            document_type=FiscalDocumentType.NFCE,
            origin=FiscalDocumentOrigin.MANUAL,
            purpose=FiscalDocumentPurpose.NORMAL,
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["document"] = self.get_document()
        context["eligible"] = is_nfce_document_eligible_for_cancellation(context["document"])
        return context

    def get_success_url(self) -> str:
        return reverse("finance:nfce_list")

    def form_valid(self, form):
        document = self.get_document()
        try:
            cancel_nfce_document(document=document, reason=str(form.cleaned_data["motivo"]), requested_by=self.request.user, request=self.request)
        except NfceCancellationError as exc:
            messages.error(self.request, str(exc))
            return self.form_invalid(form)
        messages.success(self.request, "Cancelamento da NFC-e enviado com sucesso.")
        return redirect(self.get_success_url())


class NfceInutilizationView(LoginRequiredMixin, WorkshopScopedMixin, FormView):
    form_class = NfceInutilizationForm
    workshop_permission_app_label = "finance"
    workshop_permission_model = "fiscalnumberinutilization"
    workshop_permission_codename = "inutilize_nfce_numbering"
    template_name = "finance/nfce_inutilization_form.html"

    def get_success_url(self) -> str:
        return reverse("finance:nfce_list")

    def form_valid(self, form):
        try:
            create_and_transmit_nfce_inutilization(
                workshop=self.workshop,
                requested_by=self.request.user,
                environment=int(form.cleaned_data["environment"]),
                series=str(form.cleaned_data["series"]),
                sequence_start=int(form.cleaned_data["sequence_start"]),
                sequence_end=int(form.cleaned_data["sequence_end"]),
                reason=str(form.cleaned_data["reason"]),
                local_limitation_confirmation=bool(form.cleaned_data["confirm_local_limitation"]),
            )
        except NfceInutilizationError as exc:
            messages.error(self.request, str(exc))
            return self.form_invalid(form)
        messages.success(self.request, "Inutilizacao de numeracao NFC-e enviada com sucesso.")
        return redirect(self.get_success_url())


class NfceDocumentDownloadView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "fiscaldocument"
    workshop_permission_codename = "download_nfce"

    document_fields = {
        "xml": ("xml_url", "xml"),
        "danfe": ("danfe_url", "pdf"),
    }

    def get(self, request, *args, **kwargs):
        document_kind = str(kwargs.get("document") or "").strip().lower()
        if document_kind not in self.document_fields:
            raise Http404("Documento nao suportado")
        document = get_object_or_404(
            FiscalDocument,
            pk=kwargs.get("pk"),
            workshop=self.workshop,
            document_type=FiscalDocumentType.NFCE,
            origin=FiscalDocumentOrigin.MANUAL,
            purpose=FiscalDocumentPurpose.NORMAL,
        )
        field_name, extension = self.document_fields[document_kind]
        document_url = str(getattr(document, field_name, "") or "").strip()
        try:
            downloaded = download_webmania_document(workshop=self.workshop, url=document_url)
        except WebmaniaDocumentDownloadError as exc:
            return HttpResponse(str(exc), status=502, content_type="text/plain; charset=utf-8")
        response = HttpResponse(downloaded.content, content_type=downloaded.content_type)
        identifier = str(document.number or document.access_key or document.remote_uuid or document.pk or "documento").strip().replace(" ", "-")
        response["Content-Disposition"] = f'attachment; filename="nfce-{document_kind}-{identifier}.{extension}"'
        return response


class NfceCancellationDownloadView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "fiscaldocument"
    workshop_permission_codename = "download_nfce"

    def get(self, request, *args, **kwargs):
        event = get_object_or_404(
            FiscalDocumentEvent.objects.select_related("document"),
            pk=kwargs.get("event_pk"),
            document_id=kwargs.get("pk"),
            document__workshop=self.workshop,
            document__document_type=FiscalDocumentType.NFCE,
            document__origin=FiscalDocumentOrigin.MANUAL,
            document__purpose=FiscalDocumentPurpose.NORMAL,
            event_type=FiscalDocumentEventType.CANCELLATION,
        )
        try:
            downloaded = download_webmania_document(workshop=self.workshop, url=str(event.xml_url or "").strip())
        except WebmaniaDocumentDownloadError as exc:
            return HttpResponse(str(exc), status=502, content_type="text/plain; charset=utf-8")
        response = HttpResponse(downloaded.content, content_type=downloaded.content_type)
        identifier = str(event.document.number or event.document.access_key or event.document.remote_uuid or event.document.pk or "documento").strip().replace(" ", "-")
        response["Content-Disposition"] = f'attachment; filename="nfce-cancelamento-{identifier}.xml"'
        return response


class NfceDocumentPayloadView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "fiscaldocument"
    workshop_permission_codename = "view_nfce_payload"

    def get(self, request, *args, **kwargs):
        document = get_object_or_404(
            FiscalDocument,
            pk=kwargs.get("pk"),
            workshop=self.workshop,
            document_type=FiscalDocumentType.NFCE,
            origin=FiscalDocumentOrigin.MANUAL,
            purpose=FiscalDocumentPurpose.NORMAL,
        )
        return JsonResponse(
            {
                "request_payload": document.request_payload or {},
                "response_payload": document.response_payload or {},
            }
        )


class NfceInutilizationDownloadView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "fiscalnumberinutilization"
    workshop_permission_codename = "download_nfce_inutilization"

    def get(self, request, *args, **kwargs):
        inutilization = get_object_or_404(FiscalNumberInutilization, pk=kwargs.get("pk"), workshop=self.workshop, document_type=FiscalDocumentType.NFCE)
        try:
            downloaded = download_webmania_document(workshop=self.workshop, url=str(inutilization.xml_url or "").strip())
        except WebmaniaDocumentDownloadError as exc:
            return HttpResponse(str(exc), status=502, content_type="text/plain; charset=utf-8")
        response = HttpResponse(downloaded.content, content_type=downloaded.content_type)
        sequence = str(inutilization.sequence_start) if inutilization.sequence_start == inutilization.sequence_end else f"{inutilization.sequence_start}-{inutilization.sequence_end}"
        response["Content-Disposition"] = f'attachment; filename="nfce-inutilizacao-{inutilization.series}-{sequence}.xml"'
        return response


class NfceInutilizationPayloadView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "fiscalnumberinutilization"
    workshop_permission_codename = "view_nfce_inutilization_payload"

    def get(self, request, *args, **kwargs):
        inutilization = get_object_or_404(FiscalNumberInutilization, pk=kwargs.get("pk"), workshop=self.workshop, document_type=FiscalDocumentType.NFCE)
        return JsonResponse(
            {
                "request_payload": inutilization.request_payload or {},
                "response_payload": inutilization.response_payload or {},
            }
        )
