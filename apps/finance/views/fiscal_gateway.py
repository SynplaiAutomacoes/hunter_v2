from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.views.generic import FormView

from apps.finance.forms.fiscal_gateway import (
    DOCUMENT_OPERATIONS,
    EMISSION_LINKAGE_CHOICES,
    LINKAGE_VALUES,
    NOTE_DOCUMENTS,
    EmissionLinkage,
    FiscalOperation,
    FiscalOperationGatewayForm,
    GatewayStep,
    NoteDocument,
)
from apps.finance.views.emission import EmissionRequestCreateView
from apps.workshops.mixin import WorkshopScopedMixin


@dataclass(frozen=True, slots=True)
class FiscalOperationCard:
    value: str
    label: str
    description: str
    icon: str


class FiscalOperationGatewayView(LoginRequiredMixin, WorkshopScopedMixin, FormView):
    template_name = "finance/fiscal_operation_gateway.html"
    form_class = FiscalOperationGatewayForm
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nfserequest"
    workshop_permission_codename = "view_nfserequest"

    LEGACY_WIZARD_QUERY_KEYS: ClassVar[frozenset[str]] = frozenset({"tipo", "note_mode", "step", "reset", "close", "preview"})
    OPERATION_CARDS: ClassVar[tuple[FiscalOperationCard, ...]] = (
        FiscalOperationCard(
            value=FiscalOperation.EMISSION,
            label="Nota Fiscal",
            description="Emita NF-e ou NFS-e. Nas próximas etapas você escolhe o vínculo e o tipo de documento.",
            icon="receipt_long",
        ),
        FiscalOperationCard(
            value=FiscalOperation.RETURN,
            label="Nota de Devolução",
            description="Seleciona uma NF-e de entrada vinculada ao estoque e emite a devolução sem depender de Ordem de Serviço.",
            icon="assignment_return",
        ),
        FiscalOperationCard(
            value=FiscalOperation.CORRECTION,
            label="Carta de Correção",
            description="Abre a Central de Notas para selecionar a NF-e e emitir a CC-e pelo fluxo existente.",
            icon="edit_note",
        ),
        FiscalOperationCard(
            value=FiscalOperation.COMPLEMENTARY,
            label="Nota Complementar",
            description="Abre a Central de Notas para selecionar a NF-e e usar a emissão complementar existente.",
            icon="add_notes",
        ),
        FiscalOperationCard(
            value=FiscalOperation.ADJUSTMENT,
            label="Nota de Ajuste",
            description="Abre a Central de Notas para acessar a operação de ajuste já disponível no detalhe da NF-e.",
            icon="tune",
        ),
    )
    LINKAGE_CARDS: ClassVar[tuple[FiscalOperationCard, ...]] = (
        FiscalOperationCard(
            value=EmissionLinkage.WORKORDER,
            label="Vinculada a uma O.S.",
            description="Usa o fluxo atual com Ordem de Serviço, cliente e itens já registrados no sistema.",
            icon="assignment",
        ),
        FiscalOperationCard(
            value=EmissionLinkage.STANDALONE,
            label="Emissão avulsa",
            description="Emite sem Ordem de Serviço e sem cadastrar o destinatário como cliente.",
            icon="person_add",
        ),
    )
    DOCUMENT_CARDS: ClassVar[tuple[FiscalOperationCard, ...]] = (
        FiscalOperationCard(
            value=NoteDocument.NFE,
            label="Produto (NF-e)",
            description="Nota Fiscal eletrônica de produtos e mercadorias.",
            icon="inventory_2",
        ),
        FiscalOperationCard(
            value=NoteDocument.NFSE,
            label="Serviço (NFS-e)",
            description="Nota Fiscal de Serviço eletrônica.",
            icon="handyman",
        ),
    )
    EXISTING_OPERATION_MESSAGES: ClassVar[dict[str, str]] = {
        FiscalOperation.CORRECTION: "Selecione uma NF-e e abra seus detalhes para usar o atalho Carta de Correção.",
        FiscalOperation.COMPLEMENTARY: "Selecione uma NF-e e abra seus detalhes para usar o atalho Nota Complementar.",
        FiscalOperation.ADJUSTMENT: "Selecione uma NF-e e abra seus detalhes para usar o atalho Nota de Ajuste.",
    }

    def _is_legacy_wizard_request(self) -> bool:
        return any(key in self.request.GET for key in self.LEGACY_WIZARD_QUERY_KEYS)

    def _selected_linkage(self) -> str:
        linkage = str(self.request.GET.get("vinculo") or "").strip().lower()
        return linkage if linkage in LINKAGE_VALUES else ""

    def _gateway_step(self) -> str:
        if self._selected_linkage():
            return GatewayStep.DOCUMENT
        if str(self.request.GET.get("etapa") or "").strip().lower() == GatewayStep.LINKAGE:
            return GatewayStep.LINKAGE
        # Backward-compatible query used by older links.
        legacy_fluxo = str(self.request.GET.get("fluxo") or "").strip().lower()
        if legacy_fluxo in NOTE_DOCUMENTS or legacy_fluxo == "emission":
            return GatewayStep.LINKAGE
        return GatewayStep.OPERATION

    def _linkage_step_url(self) -> str:
        return f"{reverse('finance:emission_create')}?{urlencode({'etapa': GatewayStep.LINKAGE})}"

    def _document_step_url(self, *, linkage: str) -> str:
        return f"{reverse('finance:emission_create')}?{urlencode({'etapa': GatewayStep.DOCUMENT, 'vinculo': linkage})}"

    def _normal_wizard_url(self, *, preserve_query: bool = False, note_mode: str = "") -> str:
        url = reverse("finance:emission_normal")
        if preserve_query and self.request.GET:
            return f"{url}?{self.request.GET.urlencode()}"
        query: dict[str, str] = {"reset": "1"}
        if note_mode:
            query["tipo"] = note_mode
        return f"{url}?{urlencode(query)}"

    def _standalone_wizard_url(self, *, note_mode: str) -> str:
        query = urlencode({"reset": "1", "note_mode": note_mode})
        return f"{reverse('finance:standalone_emission')}?{query}"

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if self._is_legacy_wizard_request():
            return HttpResponseRedirect(self._normal_wizard_url(preserve_query=True))
        return super().get(request, *args, **kwargs)

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if self._is_legacy_wizard_request():
            return EmissionRequestCreateView.as_view()(request, *args, **kwargs)
        return super().post(request, *args, **kwargs)

    def get_initial(self) -> dict[str, Any]:
        initial = super().get_initial()
        gateway_step = self._gateway_step()
        initial["gateway_step"] = gateway_step
        if gateway_step in {GatewayStep.LINKAGE, GatewayStep.DOCUMENT}:
            initial["operation"] = FiscalOperation.EMISSION
        selected_linkage = self._selected_linkage()
        if selected_linkage:
            initial["linkage"] = selected_linkage
        return initial

    def get_context_data(self, **kwargs: Any) -> dict[str, object]:
        context = super().get_context_data(**kwargs)
        gateway_step = self._gateway_step()
        selected_linkage = self._selected_linkage()
        context["operation_cards"] = self.OPERATION_CARDS
        context["linkage_cards"] = self.LINKAGE_CARDS
        context["document_cards"] = self.DOCUMENT_CARDS
        context["gateway_step"] = gateway_step
        context["selected_linkage"] = selected_linkage
        context["selected_linkage_label"] = (
            next((label for value, label in EMISSION_LINKAGE_CHOICES if value == selected_linkage), "")
        )
        context["operation_step_url"] = reverse("finance:emission_create")
        context["linkage_step_url"] = self._linkage_step_url()
        return context

    def form_valid(self, form: FiscalOperationGatewayForm) -> HttpResponse:
        operation = str(form.cleaned_data["operation"])
        linkage = str(form.cleaned_data.get("linkage") or "")
        note_document = str(form.cleaned_data.get("note_document") or "")
        gateway_step = str(form.cleaned_data.get("gateway_step") or GatewayStep.OPERATION)

        if operation in DOCUMENT_OPERATIONS and gateway_step == GatewayStep.OPERATION:
            return HttpResponseRedirect(self._linkage_step_url())

        if operation in DOCUMENT_OPERATIONS and gateway_step == GatewayStep.LINKAGE:
            return HttpResponseRedirect(self._document_step_url(linkage=linkage))

        if operation in DOCUMENT_OPERATIONS and gateway_step == GatewayStep.DOCUMENT:
            if linkage == EmissionLinkage.STANDALONE:
                return HttpResponseRedirect(self._standalone_wizard_url(note_mode=note_document))
            return HttpResponseRedirect(self._normal_wizard_url(note_mode=note_document))

        if operation == FiscalOperation.RETURN:
            return HttpResponseRedirect(reverse("finance:purchase_return_create"))

        messages.info(self.request, self.EXISTING_OPERATION_MESSAGES[operation])
        query = urlencode({"tipo": "nfe", "operacao": operation})
        return HttpResponseRedirect(f"{reverse('finance:issued_documents_list')}?{query}")
