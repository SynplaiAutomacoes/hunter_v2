from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP, Decimal

from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.decorators import method_decorator
from django.utils import timezone

from django.urls import reverse
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views import View
from django.views.generic import DetailView, ListView

from apps.core.domain.contracts.fiscal import FiscalServiceError
from apps.core.infrastructure.providers import get_fiscal_service
from apps.core.infrastructure.services.webmania.emission import compute_service_discount_for_nfse
from apps.finance.services.pricing import build_slider_allocation_for_workorder
from apps.core.presentation.forms import CoreForm
from apps.core.presentation.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.core.presentation.mixins import HtmxTemplateResponseMixin
from apps.finance.forms import NfseRequestStep1Form, NfseRequestStep2Form, NfseRequestStep3Form
from apps.finance.forms.emission_ui import format_money
from apps.finance.models.finance import NfseItem, NfseRequest, NfseRequestStatus, TaxClassNfse
from apps.finance.views.navigation import build_detail_url_with_preserved_origin, build_issued_documents_back_url
from apps.finance.views.request_workflow import (
    SharedEmissionRequestCreateBaseView,
    SharedEmissionRequestUpdateBaseView,
    build_preview_hidden_fields,
    render_emission_preview_modal,
)
from apps.workshops.mixin import WorkshopScopedMixin


logger = logging.getLogger(__name__)


def _join_address(*parts: object) -> str:
    return " - ".join(str(part).strip() for part in parts if str(part or "").strip()) or "-"


def _fmt_money(value: Decimal) -> str:
    value = value.quantize(Decimal("0.01"))
    integer_part, decimal_part = f"{value:.2f}".split(".")
    grouped_integer = f"{int(integer_part):,}".replace(",", ".")
    return f"{grouped_integer},{decimal_part}"


def _calc_retencao(base: Decimal, rate: Decimal | None) -> str:
    if rate is None or rate <= 0:
        return "-"
    amount = (base * rate / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if amount <= 0:
        return "-"
    return _fmt_money(amount)


def _build_nfse_preview_data(nfse_request: NfseRequest) -> dict[str, object]:
    workorder = nfse_request.workorder
    customer = workorder.budget.customer
    workshop = nfse_request.workshop
    company = getattr(workshop, "webmania_company", None)
    tax_class = TaxClassNfse.objects.filter(workshop=workshop, reference=nfse_request.tax_class).first()
    emission_time = timezone.localtime()
    rps_number = str(nfse_request.reserved_rps_number or "-")
    rps_series = str(nfse_request.reserved_rps_series or "-")
    description = nfse_request.service_description.strip()
    if nfse_request.additional_information.strip():
        description = f"{description}\n\n{nfse_request.additional_information.strip()}".strip()

    provider_name = str(getattr(company, "razao_social", "") or getattr(company, "nome_completo", "") or workshop.name).strip()
    provider_address = _join_address(
        f"{getattr(company, 'endereco', '')} {getattr(company, 'numero', '')}".strip() if company else workshop.address,
        getattr(company, "complemento", "") if company else "",
        getattr(company, "bairro", "") if company else "",
        f"CEP: {getattr(company, 'cep', '')}" if company and getattr(company, "cep", "") else "",
    )
    customer_address = _join_address(
        f"{customer.logradouro}, {customer.numero}",
        customer.complemento,
        customer.bairro,
        f"CEP: {customer.cep}" if customer.cep else "",
    )

    allocation = build_slider_allocation_for_workorder(
        workorder=nfse_request.workorder,
        persisted_slider=getattr(nfse_request, "pricing_slider", None),
    )
    gross_amount = allocation.services_target.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    service_discount = compute_service_discount_for_nfse(
        workorder=nfse_request.workorder,
        discount_type_override=str(getattr(nfse_request, "discount_type_override", "") or ""),
    )
    net_amount = (gross_amount - service_discount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    iss_rate = getattr(tax_class, "iss", None)
    pis_rate = getattr(tax_class, "pis", None)
    cofins_rate = getattr(tax_class, "cofins", None)
    inss_rate = getattr(tax_class, "inss", None)
    ir_rate = getattr(tax_class, "ir", None)
    csll_rate = getattr(tax_class, "csll", None)
    retencao_pis_cofins = str(getattr(tax_class, "retencao_pis_cofins", "") or "").strip().upper()
    usar_retencao_pis_cofins = retencao_pis_cofins == "S"

    def _aliquota_str(rate: Decimal | None) -> str:
        if rate is None:
            return "-"
        return _fmt_money(rate)

    preview_data = {
        "numero": "PRÉVIA",
        "emissao": emission_time.strftime("%d/%m/%Y %H:%M:%S"),
        "codigo": "SEM VALOR FISCAL",
        "rps": f"RPS Nº {rps_number} Série {rps_series}, emitido em {emission_time.strftime('%d/%m/%Y %H:%M:%S')}",
        "hash": "DOCUMENTO SEM VALOR FISCAL",
        "identificador": "PRÉVIA LOCAL — NÃO TRANSMITIDA À PREFEITURA",
        "municipio_prestacao": str(getattr(company, "cidade", "") or "-"),
        "prestador": {
            "cnpj": workshop.webmania_company_document_display,
            "im": str(getattr(company, "im", "") or "-"),
            "nome": provider_name or "-",
            "endereco": provider_address,
            "municipio": str(getattr(company, "cidade", "") or "-") if company else "-",
            "uf": str(getattr(company, "uf", "") or workshop.uf or "-"),
        },
        "tomador": {
            "nome": customer.name or "-",
            "cnpj": customer.cpf_or_cnpj_formatted or "-",
            "im": str(customer.municipal_registration or "-"),
            "endereco": customer_address,
            "municipio": customer.cidade or "-",
            "uf": customer.estado or "-",
            "email": customer.email or "-",
        },
        "descricao": description or f"Prestação de serviço referente à OS #{workorder.pk}",
        "total": format_money(net_amount),
        "tributos": "Consulte a tributação aplicável após a emissão",
        "codigo_servico": str(getattr(tax_class, "codigo_servico", "") or "-"),
        "descricao_servico": str(getattr(tax_class, "description", "") or "Serviços prestados"),
        "outras_informacoes": "Documento de prévia gerado localmente. Não possui valor fiscal e não foi transmitido à prefeitura.",
        "valor_servicos": format_money(gross_amount),
        "valor_deducoes": _fmt_money(service_discount) if service_discount > 0 else "0,00",
        "base_calculo": _fmt_money(net_amount),
        "aliquota_iss": _aliquota_str(iss_rate),
        "valor_iss": _calc_retencao(net_amount, iss_rate),
        "valor_irrf": _calc_retencao(net_amount, ir_rate),
        "valor_cofins": _calc_retencao(net_amount, cofins_rate) if usar_retencao_pis_cofins else "-",
        "valor_pis": _calc_retencao(net_amount, pis_rate) if usar_retencao_pis_cofins else "-",
        "valor_ipi": "-",
        "valor_inss": _calc_retencao(net_amount, inss_rate),
        "valor_csll": _calc_retencao(net_amount, csll_rate),
        "descricao_csll": "Contribuição Social sobre o Lucro Líquido" if csll_rate and csll_rate > 0 else "-",
        "credito_nfp": "0,00",
        "numero_inscricao_obra": "-",
    }
    return preview_data


class NfseCancelForm(CoreForm):
    REASON_CHOICES = [
        ("", "Selecione o motivo"),
        ("1", "Erro na emissao"),
        ("2", "Servico nao prestado"),
        ("4", "Duplicidade da nota"),
    ]

    reason_code = forms.ChoiceField(choices=REASON_CHOICES, required=True)

    def clean_reason_code(self) -> int:
        value = str(self.cleaned_data.get("reason_code") or "").strip()
        if value not in {"1", "2", "4"}:
            raise forms.ValidationError("Selecione um motivo para cancelar a Nota Fiscal de Serviço.")
        return int(value)


class NfseRequestListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = NfseRequest
    template_name = "finance/nfse_request_list.html"
    context_object_name = "nfse_requests"
    htmx_template_name = "finance/partials/nfse_request_table.html"

    def get_queryset(self):
        return super().get_queryset().select_related("workorder", "workorder__budget", "workorder__budget__customer", "workorder__budget__vehicle").prefetch_related("items").order_by("-criado_em", "-pk")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        logger.info(
            "nfse_list_loaded workshop_id=%s user_id=%s total_items=%s",
            getattr(self.workshop, "pk", None),
            getattr(self.request.user, "id", None),
            len(context.get("object_list") or []),
        )
        context["fields"] = [
            TableColumn("ID", attr="id"),
            TableColumn("RPS", attr="rps_number_display", search_by="reserved_rps_number"),
            TableColumn("Ordem de Serviço", attr="workorder", search_by="workorder__id"),
            TableColumn("Cliente", attr="customer_name", search_by="workorder__budget__customer__name"),
            TableColumn("Criado em", attr=NfseRequest.criado_em.field.name),
            TableColumn("Status", attr="nfse_request_status_badge", search_by="status", format="status_badge"),
        ]
        context["actions"] = [
            TableActionDefaults.view("finance:nfse_detail"),
            TableActionDefaults.edit("finance:nfse_update"),
        ]
        return context


def _format_item_status_badge(status: str) -> dict[str, str]:
    status_map = {
        "processando": {"text": "Processando", "class": "badge-soft badge-warning"},
        "aprovado": {"text": "Aprovado", "class": "badge-success"},
        "agendado": {"text": "Agendado", "class": "badge-soft badge-warning"},
        "reprovado": {"text": "Reprovado", "class": "badge-error"},
        "cancelado": {"text": "Cancelado", "class": "badge-soft badge-error"},
        "contingencia": {"text": "Contingência", "class": "badge-soft badge-warning"},
    }
    return status_map.get(str(status or "").strip().lower(), {"text": str(status or "-") or "-", "class": "badge-ghost"})


def _build_field(label: str, value: object) -> dict[str, str]:
    normalized = str(value or "-").strip() or "-"
    return {"label": label, "value": normalized}


class NfseRequestDetailView(LoginRequiredMixin, WorkshopScopedMixin, DetailView):
    model = NfseRequest
    template_name = "finance/nfse_request_detail.html"
    context_object_name = "nfse_request"

    def get_queryset(self):
        return super().get_queryset().select_related("workorder", "workorder__budget", "workorder__budget__customer", "workorder__budget__vehicle").prefetch_related("items", "batches")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        latest_item = self.object.items.order_by("-id").first()
        latest_batch = self.object.batches.order_by("-id").first()
        can_cancel = bool(latest_item and str(getattr(latest_item, "status", "")).strip().lower() in {"aprovado", "agendado", "contingencia"})
        fallback_back_url = reverse("finance:nfse_list")
        context.update(
            {
                "back_url": build_issued_documents_back_url(query_params=self.request.GET, fallback_url=fallback_back_url),
                "latest_item": latest_item,
                "latest_batch": latest_batch,
                "can_cancel": can_cancel,
                "request_fields": [
                    _build_field("ID da requisição", self.object.pk),
                    _build_field("Ordem de serviço", self.object.workorder),
                    _build_field("Cliente", self.object.customer_name),
                    _build_field("Classe de imposto", self.object.tax_class),
                    _build_field("Número da Nota Fiscal de Serviço", self.object.reserved_rps_number),
                    _build_field("Série da Nota Fiscal de Serviço", self.object.reserved_rps_series),
                    _build_field("Discriminação", self.object.service_description),
                    _build_field("Criado em", self.object.criado_em.strftime("%d/%m/%Y %H:%M") if self.object.criado_em else "-"),
                    _build_field("Atualizado em", self.object.atualizado_em.strftime("%d/%m/%Y %H:%M") if self.object.atualizado_em else "-"),
                ],
                "latest_item_status_badge": _format_item_status_badge(getattr(latest_item, "status", "")),
            }
        )
        return context


class NfseRequestCancelView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nfserequest"
    workshop_permission_codename = "change_nfserequest"

    def post(self, request, *args, **kwargs):
        nfse_request = get_object_or_404(NfseRequest, pk=kwargs.get("pk"), workshop=self.workshop)
        latest_item = nfse_request.items.order_by("-id").first()
        if latest_item is None:
            messages.error(request, "A Nota Fiscal de Serviço ainda nao possui item sincronizado para cancelamento.")
            return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfse_detail", pk=nfse_request.pk, query_params=request.GET))

        status = str(getattr(latest_item, "status", "")).strip().lower()
        if status not in {"aprovado", "agendado", "contingencia"}:
            messages.error(request, "Somente Nota Fiscal de Serviço aprovada, agendada ou em contingencia pode ser cancelada.")
            return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfse_detail", pk=nfse_request.pk, query_params=request.GET))

        form = NfseCancelForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Selecione um motivo para cancelar a Nota Fiscal de Serviço.")
            return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfse_detail", pk=nfse_request.pk, query_params=request.GET))

        reason_code = int(form.cleaned_data["reason_code"])
        reason_label = dict(NfseCancelForm.REASON_CHOICES).get(str(reason_code), "Cancelamento solicitado")

        service = get_fiscal_service()
        try:
            response_payload = service.cancel_nfse(
                workshop=self.workshop,
                event_uuid=str(latest_item.uuid),
                reason_code=reason_code,
            )
        except FiscalServiceError as exc:
            messages.error(request, str(exc))
            return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfse_detail", pk=nfse_request.pk, query_params=request.GET))

        latest_item.status = "cancelado"
        latest_item.reason = str(response_payload.get("motivo") or reason_label)
        latest_item.raw_payload = response_payload
        xml_url = str(response_payload.get("xml") or "").strip()
        if xml_url:
            latest_item.xml_url = xml_url
        latest_item.save(update_fields=["status", "reason", "raw_payload", "xml_url"])

        nfse_request.set_status(NfseRequestStatus.CANCELED)
        messages.success(request, "Nota Fiscal de Serviço cancelada com sucesso.")
        return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfse_detail", pk=nfse_request.pk, query_params=request.GET))


class NfseRequestReconcileView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nfserequest"
    workshop_permission_codename = "change_nfserequest"

    def post(self, request, *args, **kwargs):
        nfse_request = get_object_or_404(NfseRequest, pk=kwargs.get("pk"), workshop=self.workshop)
        item = nfse_request.items.order_by("-id").first()
        if item is None:
            messages.error(request, "A Nota Fiscal de Serviço ainda nao possui um item sincronizado para consulta.")
            return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfse_detail", pk=nfse_request.pk, query_params=request.GET))

        service = get_fiscal_service()
        try:
            service.reconcile_nfse_item(item=item)
        except FiscalServiceError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Status da Nota Fiscal de Serviço atualizado com sucesso.")

        return redirect(build_detail_url_with_preserved_origin(view_name="finance:nfse_detail", pk=nfse_request.pk, query_params=request.GET))


class NfseDocumentDownloadView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nfserequest"
    workshop_permission_codename = "view_nfserequest"

    document_fields = {
        "xml": ("xml_url", "xml"),
        "pdf_nfse": ("pdf_nfse_url", "pdf"),
        "pdf_rps": ("pdf_rps_url", "pdf"),
    }

    def get(self, request, *args, **kwargs):
        nfse_request = get_object_or_404(NfseRequest, pk=kwargs.get("pk"), workshop=self.workshop)
        document_kind = str(kwargs.get("document") or "").strip().lower()
        if document_kind not in self.document_fields:
            raise Http404("Documento nao suportado")

        item = nfse_request.items.order_by("-id").first()
        if item is None:
            raise Http404("Documento ainda nao disponivel")

        field_name, extension = self.document_fields[document_kind]
        document_url = str(getattr(item, field_name, "") or "").strip()

        service = get_fiscal_service()
        try:
            downloaded = service.download_document(workshop=self.workshop, url=document_url)
        except FiscalServiceError as exc:
            logger.exception(
                "nfse_document_download_failed",
                extra={"nfse_request_id": nfse_request.pk, "workshop_id": self.workshop.pk, "document_kind": document_kind},
            )
            return HttpResponse(str(exc), status=502, content_type="text/plain; charset=utf-8")

        response = HttpResponse(downloaded.content, content_type=downloaded.content_type)
        response["Content-Disposition"] = self._build_content_disposition(item=item, document_kind=document_kind, extension=extension)
        return response

    @staticmethod
    def _build_content_disposition(*, item: NfseItem, document_kind: str, extension: str) -> str:
        identifier = str(item.number or item.rps_number or item.uuid or "documento").strip()
        safe_identifier = identifier.replace(" ", "-")
        return f'attachment; filename="nfse-{document_kind}-{safe_identifier}.{extension}"'


@method_decorator(xframe_options_exempt, name="dispatch")
class NfsePreviewPdfView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nfserequest"
    workshop_permission_codename = "view_nfserequest"

    def get(self, request, *args, **kwargs):
        nfse_request = get_object_or_404(
            NfseRequest.objects.select_related("workshop__webmania_company", "workorder__budget__customer"),
            pk=kwargs.get("pk"),
            workshop=self.workshop,
        )
        response = render(request, "pdf/nf_html_com_marca_dagua.html", {"nfse_preview": _build_nfse_preview_data(nfse_request)})
        response["Cache-Control"] = "no-store"
        return response


class NfseRequestCreateView(SharedEmissionRequestCreateBaseView):
    model = NfseRequest
    template_name = "finance/nfse_request_form.html"
    partial_template_name = "finance/partials/nfse_step_content.html"
    preview_template_name = "finance/partials/nfse_step3_preview.html"
    step3_form_class = NfseRequestStep3Form
    preview_initial_fields = ("pricing_slider", "tax_class", "service_description", "additional_information")
    tax_class_kind = "nfse"
    tax_class_warning_message = "Nao foi possivel carregar classes de imposto de Nota Fiscal de Serviço: {error}"
    success_redirect_name = "finance:nfse_list"
    status_by_step = {
        1: NfseRequestStatus.CHECKING_CLIENT,
        2: NfseRequestStatus.CHECKING_SERVICES,
    }

    steps_definition = [
        {"title": "Selecionar OS", "form_class": NfseRequestStep1Form},
        {"title": "Conferir Cliente", "form_class": NfseRequestStep2Form},
        {"title": "Conferir Serviços", "form_class": NfseRequestStep3Form},
    ]

    def _finalize_emission(self) -> bool:
        logger.info(
            "nfse_finalize_started nfse_request_id=%s workshop_id=%s user_id=%s",
            getattr(self.object, "pk", None),
            getattr(self.workshop, "pk", None),
            getattr(self.request.user, "id", None),
        )
        service = get_fiscal_service()
        try:
            response_payload = service.emit_nfse(nfse_request=self.object, request=self.request)
            service.sync_nfse_emission_response(nfse_request=self.object, response_payload=response_payload)

            if not self.object.update_status_based_on_request(response_payload.get("status")):
                self.object.set_status(NfseRequestStatus.PROCESSING)

            messages.success(self.request, "Solicitação de Nota Fiscal de Serviço enviada com sucesso.")
            logger.info(
                "nfse_finalize_succeeded nfse_request_id=%s workshop_id=%s user_id=%s status=%s",
                getattr(self.object, "pk", None),
                getattr(self.workshop, "pk", None),
                getattr(self.request.user, "id", None),
                str(getattr(self.object, "status", "")),
            )
            return True
        except FiscalServiceError as exc:
            logger.exception("Falha ao emitir NFS-e", extra={"nfse_request_id": self.object.pk})
            messages.error(self.request, str(exc))
            return False

    def _build_preview_response(self, *, form) -> HttpResponse:
        return render_emission_preview_modal(
            request=self.request,
            title="Prévia da Nota Fiscal de Serviço",
            description="Confira o documento antes de transmitir a Nota Fiscal de Serviço para o Sefaz.",
            previews=[{"label": "Nota Fiscal de Serviço", "embed_url": reverse("finance:nfse_preview_pdf", kwargs={"pk": self.object.pk})}],
            transmit_url=self._step_url(step=self.get_current_step()),
            hidden_fields=build_preview_hidden_fields(cleaned_data=form.cleaned_data),
        )


class NfseRequestUpdateView(SharedEmissionRequestUpdateBaseView, NfseRequestCreateView):
    update_url_name = "finance:nfse_update"
    missing_update_redirect_name = "finance:nfse_list"
