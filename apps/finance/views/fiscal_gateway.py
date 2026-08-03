from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, cast
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.views.generic import FormView

from apps.finance.forms.fiscal_gateway import FISCAL_OPERATION_CHOICES, FiscalOperation, FiscalOperationGatewayForm, NfeEmissionOriginGatewayForm
from apps.finance.models import NfeEmissionOrigin
from apps.finance.views.emission import EmissionRequestCreateView
from apps.workshops.mixin import WorkshopScopedMixin
from apps.workshops.util.workshops import has_workshop_perm


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
            label="Nota Fiscal de Saída",
            description="Emita por Ordem de Serviço ou preencha uma NF-e manualmente.",
            icon="receipt_long",
        ),
        FiscalOperationCard(
            value=FiscalOperation.RETURN,
            label="Nota de Devolução",
            description="Pesquise uma NF-e de compra recebida e selecione os produtos da Nota de Devolução.",
            icon="assignment_return",
        ),
        FiscalOperationCard(
            value=FiscalOperation.CORRECTION,
            label="Carta de Correção",
            description="Selecione a NF-e original e informe a correção que deve ser registrada.",
            icon="edit_note",
        ),
        FiscalOperationCard(
            value=FiscalOperation.COMPLEMENTARY,
            label="Nota Complementar",
            description="Selecione a NF-e original e informe os valores ou quantidades complementares.",
            icon="add_notes",
        ),
        FiscalOperationCard(
            value=FiscalOperation.ADJUSTMENT,
            label="Nota de Ajuste",
            description="Selecione uma NF-e de referência e preencha os dados fiscais do ajuste.",
            icon="tune",
        ),
        FiscalOperationCard(
            value=FiscalOperation.TRANSPORT,
            label="Transporte",
            description="Emita uma NF-e por Ordem de Serviço com modalidade, transportador, veículo, volumes e reboques.",
            icon="local_shipping",
        ),
    )
    EXISTING_OPERATION_MESSAGES: ClassVar[dict[str, str]] = {
        FiscalOperation.RETURN: "Pesquise e selecione a NF-e de compra recebida pela oficina.",
        FiscalOperation.CORRECTION: "Selecione a NF-e que receberá a Carta de Correção.",
        FiscalOperation.COMPLEMENTARY: "Selecione a NF-e que será complementada.",
        FiscalOperation.ADJUSTMENT: "Selecione a NF-e que será vinculada à Nota de Ajuste.",
    }
    OPERATION_PERMISSIONS: ClassVar[dict[str, tuple[tuple[str, str, str], ...]]] = {
        FiscalOperation.RETURN: (("finance", "fiscaldocument", "issue_nfe_return"),),
        FiscalOperation.CORRECTION: (("finance", "fiscaldocumentevent", "issue_nfe_correction"),),
        FiscalOperation.COMPLEMENTARY: (("finance", "fiscaldocument", "issue_nfe_complementary_price_quantity"),),
        FiscalOperation.ADJUSTMENT: (("finance", "fiscaldocument", "issue_nfe_adjustment"),),
    }

    def _has_operation_permission(self, operation: str) -> bool:
        permission_specs = self.OPERATION_PERMISSIONS.get(operation)
        if permission_specs is None:
            return True
        return any(
            has_workshop_perm(
                user=self.request.user,
                workshop=self.workshop,
                app_label=app_label,
                model=model,
                codename=codename,
                request=self.request,
            )
            for app_label, model, codename in permission_specs
        )

    def _available_operation_cards(self) -> tuple[FiscalOperationCard, ...]:
        return tuple(card for card in self.OPERATION_CARDS if self._has_operation_permission(card.value))

    def get_form(self, form_class: type[FiscalOperationGatewayForm] | None = None) -> FiscalOperationGatewayForm:
        form = cast(FiscalOperationGatewayForm, super().get_form(form_class))
        allowed_operations = {card.value for card in self._available_operation_cards()}
        form.fields["operation"].choices = [(value, label) for value, label in FISCAL_OPERATION_CHOICES if value in allowed_operations]
        return form

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
        context["operation_cards"] = self._available_operation_cards()
        return context

    def form_valid(self, form: FiscalOperationGatewayForm) -> HttpResponse:
        operation = str(form.cleaned_data["operation"])
        if not self._has_operation_permission(operation):
            raise PermissionDenied("Usuário sem permissão para iniciar esta operação fiscal.")
        if operation == FiscalOperation.NORMAL:
            return HttpResponseRedirect(reverse("finance:emission_origin"))

        if operation == FiscalOperation.RETURN:
            return HttpResponseRedirect(reverse("finance:purchase_return_create"))

        if operation == FiscalOperation.TRANSPORT:
            messages.info(self.request, "O transporte faz parte da NF-e. Preencha os dados na emissão por Ordem de Serviço.")
            query = urlencode({"tipo": "nfe", "reset": 1, "operacao": operation})
            return HttpResponseRedirect(f"{reverse('finance:emission_normal')}?{query}")

        messages.info(self.request, self.EXISTING_OPERATION_MESSAGES[operation])
        query = urlencode({"tipo": "nfe", "operacao": operation})
        return HttpResponseRedirect(f"{reverse('finance:issued_documents_list')}?{query}")


class NfeEmissionOriginGatewayView(LoginRequiredMixin, WorkshopScopedMixin, FormView):
    template_name = "finance/nfe_emission_origin_gateway.html"
    form_class = NfeEmissionOriginGatewayForm
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nferequest"
    workshop_permission_codename = "view_nferequest"
    workshop_permission_fallbacks = (("finance", "nfserequest", "view_nfserequest"),)

    ORIGIN_CARDS: ClassVar[tuple[FiscalOperationCard, ...]] = (
        FiscalOperationCard(
            value=NfeEmissionOrigin.WORK_ORDER,
            label="Ordem de Serviço",
            description="Utilize os dados de uma Ordem de Serviço para preencher e emitir a Nota Fiscal de Saída.",
            icon="handyman",
        ),
        FiscalOperationCard(
            value=NfeEmissionOrigin.MANUAL,
            label="Emissão Manual",
            description="Abre a emissão manual com destinatário e múltiplos produtos, usando o mesmo motor fiscal da NF-e por OS.",
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
        return context

    def form_valid(self, form: NfeEmissionOriginGatewayForm) -> HttpResponse:
        origin = str(form.cleaned_data["origin"])
        if origin == NfeEmissionOrigin.WORK_ORDER:
            query = urlencode({"reset": 1})
            return HttpResponseRedirect(f"{reverse('finance:emission_normal')}?{query}")

        query = urlencode({"new": 1})
        return HttpResponseRedirect(f"{reverse('finance:emission_manual')}?{query}")
