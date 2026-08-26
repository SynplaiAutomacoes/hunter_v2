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
    EmissionLinkage,
    FiscalOperation,
    FiscalOperationGatewayForm,
    GatewayStep,
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
            value=FiscalOperation.NFE,
            label="NF-e",
            description="Nota Fiscal de Produto. Na próxima etapa você escolhe o fluxo de emissão.",
            icon="receipt_long",
        ),
        FiscalOperationCard(
            value=FiscalOperation.NFSE,
            label="NFS-e",
            description="Nota Fiscal de Serviço. Na próxima etapa você escolhe o fluxo de emissão.",
            icon="handyman",
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
    EXISTING_OPERATION_MESSAGES: ClassVar[dict[str, str]] = {
        FiscalOperation.CORRECTION: "Selecione uma NF-e e abra seus detalhes para usar o atalho Carta de Correção.",
        FiscalOperation.COMPLEMENTARY: "Selecione uma NF-e e abra seus detalhes para usar o atalho Nota Complementar.",
        FiscalOperation.ADJUSTMENT: "Selecione uma NF-e e abra seus detalhes para usar o atalho Nota de Ajuste.",
    }

    def _is_legacy_wizard_request(self) -> bool:
        return any(key in self.request.GET for key in self.LEGACY_WIZARD_QUERY_KEYS)

    def _selected_document(self) -> str:
        document = str(self.request.GET.get("fluxo") or "").strip().lower()
        return document if document in DOCUMENT_OPERATIONS else ""

    def _gateway_step(self) -> str:
        return GatewayStep.LINKAGE if self._selected_document() else GatewayStep.OPERATION

    def _linkage_step_url(self, *, note_mode: str) -> str:
        return f"{reverse('finance:emission_create')}?{urlencode({'fluxo': note_mode})}"

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
        selected_document = self._selected_document()
        if selected_document:
            initial["operation"] = selected_document
            initial["gateway_step"] = GatewayStep.LINKAGE
        else:
            initial["gateway_step"] = GatewayStep.OPERATION
        return initial

    def get_context_data(self, **kwargs: Any) -> dict[str, object]:
        context = super().get_context_data(**kwargs)
        selected_document = self._selected_document()
        gateway_step = self._gateway_step()
        context["operation_cards"] = self.OPERATION_CARDS
        context["linkage_cards"] = self.LINKAGE_CARDS
        context["gateway_step"] = gateway_step
        context["selected_document"] = selected_document
        context["selected_document_label"] = "NFS-e" if selected_document == FiscalOperation.NFSE else "NF-e"
        context["operation_step_url"] = reverse("finance:emission_create")
        return context

    def form_valid(self, form: FiscalOperationGatewayForm) -> HttpResponse:
        operation = str(form.cleaned_data["operation"])
        linkage = str(form.cleaned_data.get("linkage") or "")
        gateway_step = str(form.cleaned_data.get("gateway_step") or GatewayStep.OPERATION)

        if operation in DOCUMENT_OPERATIONS and gateway_step == GatewayStep.OPERATION:
            return HttpResponseRedirect(self._linkage_step_url(note_mode=operation))

        if operation in DOCUMENT_OPERATIONS:
            if linkage == EmissionLinkage.STANDALONE:
                return HttpResponseRedirect(self._standalone_wizard_url(note_mode=operation))
            return HttpResponseRedirect(self._normal_wizard_url(note_mode=operation))

        if operation == FiscalOperation.RETURN:
            return HttpResponseRedirect(reverse("finance:purchase_return_create"))

        messages.info(self.request, self.EXISTING_OPERATION_MESSAGES[operation])
        query = urlencode({"tipo": "nfe", "operacao": operation})
        return HttpResponseRedirect(f"{reverse('finance:issued_documents_list')}?{query}")
