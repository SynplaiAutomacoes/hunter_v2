from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.views.generic import FormView

from apps.finance.forms.fiscal_gateway import FiscalOperation, FiscalOperationGatewayForm, NfeEmissionOriginGatewayForm
from apps.finance.models import NfeEmissionOrigin
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
            value=FiscalOperation.NORMAL,
            label="NF-e Normal",
            description="Continua no fluxo atual por Ordem de Serviço, sem alterar nenhuma etapa da emissão.",
            icon="receipt_long",
        ),
        FiscalOperationCard(
            value=FiscalOperation.RETURN,
            label="NF-e Devolução",
            description="Abre a Central de Notas para selecionar a NF-e e usar o fluxo existente de devolução ou estorno.",
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
    EXISTING_OPERATION_MESSAGES: ClassVar[dict[str, str]] = {
        FiscalOperation.RETURN: "Selecione uma NF-e e abra seus detalhes para usar o atalho Devolução/Estorno.",
        FiscalOperation.CORRECTION: "Selecione uma NF-e e abra seus detalhes para usar o atalho Carta de Correção.",
        FiscalOperation.COMPLEMENTARY: "Selecione uma NF-e e abra seus detalhes para usar o atalho Nota Complementar.",
        FiscalOperation.ADJUSTMENT: "Selecione uma NF-e e abra seus detalhes para usar o atalho Nota de Ajuste.",
    }

    def _is_legacy_wizard_request(self) -> bool:
        return any(key in self.request.GET for key in self.LEGACY_WIZARD_QUERY_KEYS)

    def _normal_wizard_url(self, *, preserve_query: bool = False) -> str:
        url = reverse("finance:emission_normal")
        if preserve_query and self.request.GET:
            return f"{url}?{self.request.GET.urlencode()}"
        return url

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if self._is_legacy_wizard_request():
            return HttpResponseRedirect(self._normal_wizard_url(preserve_query=True))
        return super().get(request, *args, **kwargs)

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if self._is_legacy_wizard_request():
            return EmissionRequestCreateView.as_view()(request, *args, **kwargs)
        return super().post(request, *args, **kwargs)

    def get_context_data(self, **kwargs: Any) -> dict[str, object]:
        context = super().get_context_data(**kwargs)
        context["operation_cards"] = self.OPERATION_CARDS
        return context

    def form_valid(self, form: FiscalOperationGatewayForm) -> HttpResponse:
        operation = str(form.cleaned_data["operation"])
        if operation == FiscalOperation.NORMAL:
            return HttpResponseRedirect(reverse("finance:emission_origin"))

        messages.info(self.request, self.EXISTING_OPERATION_MESSAGES[operation])
        query = urlencode({"tipo": "nfe", "operacao": operation})
        return HttpResponseRedirect(f"{reverse('finance:issued_documents_list')}?{query}")


class NfeEmissionOriginGatewayView(LoginRequiredMixin, WorkshopScopedMixin, FormView):
    template_name = "finance/nfe_emission_origin_gateway.html"
    form_class = NfeEmissionOriginGatewayForm
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nfserequest"
    workshop_permission_codename = "view_nfserequest"

    ORIGIN_CARDS: ClassVar[tuple[FiscalOperationCard, ...]] = (
        FiscalOperationCard(
            value=NfeEmissionOrigin.WORK_ORDER,
            label="Ordem de Serviço",
            description="Continua no wizard atual de NF-e, com os mesmos dados, validações e emissão.",
            icon="handyman",
        ),
        FiscalOperationCard(
            value=NfeEmissionOrigin.MANUAL,
            label="Manual",
            description="Identifica a nova origem arquitetural. O preenchimento manual será implementado em uma fase posterior.",
            icon="edit_document",
        ),
    )

    def get_initial(self) -> dict[str, object]:
        initial = super().get_initial()
        selected_origin = str(self.request.GET.get("origin") or "")
        if selected_origin in NfeEmissionOrigin.values:
            initial["origin"] = selected_origin
        return initial

    def get_context_data(self, **kwargs: Any) -> dict[str, object]:
        context = super().get_context_data(**kwargs)
        context["origin_cards"] = self.ORIGIN_CARDS
        context["manual_extension_pending"] = self.request.GET.get("origin") == NfeEmissionOrigin.MANUAL
        return context

    def form_valid(self, form: NfeEmissionOriginGatewayForm) -> HttpResponse:
        origin = str(form.cleaned_data["origin"])
        if origin == NfeEmissionOrigin.WORK_ORDER:
            query = urlencode({"reset": 1})
            return HttpResponseRedirect(f"{reverse('finance:emission_normal')}?{query}")

        return HttpResponseRedirect(reverse("finance:emission_manual"))
