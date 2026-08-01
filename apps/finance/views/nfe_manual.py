from __future__ import annotations

import json
import logging
from typing import Any, cast

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views.generic import FormView

from apps.budget.forms.item_forms import QuickProductForm
from apps.core.domain.contracts.fiscal import FiscalServiceError
from apps.core.infrastructure.providers import get_fiscal_service
from apps.finance.forms.nfe_manual import NfeManualEmissionForm, NfeManualItemFormSet
from apps.finance.models import NfeEmissionOrigin, NfeRequest, NfeRequestManualItem
from apps.finance.models.finance import NfeFreightMode, NfeRequestStatus
from apps.finance.services.tax_classes import TaxClassServiceError, list_tax_classes
from apps.workshops.mixin import WorkshopScopedMixin


logger = logging.getLogger(__name__)


def _nfe_tax_class_choices(*, workshop: Any) -> list[tuple[str, str]]:
    choices: list[tuple[str, str]] = []
    for tax_class in list_tax_classes(workshop=workshop):
        reference = str(tax_class.get("referencia") or "").strip()
        if not reference or str(tax_class.get("status") or "").strip().lower() == "inativo":
            continue
        tax_type = str(tax_class.get("tipo") or tax_class.get("type") or "").strip().lower()
        if tax_type in {"nfse", "nfs-e", "nsfe"} or (tax_class.get("tipo_emissao") and tax_class.get("codigo_servico")):
            continue
        description = str(tax_class.get("descricao") or "").strip()
        choices.append((reference, f"{reference} - {description}" if description else reference))
    return choices


class NfeManualEmissionCreateView(LoginRequiredMixin, WorkshopScopedMixin, FormView):
    template_name = "finance/nfe_manual_emission_form.html"
    form_class = NfeManualEmissionForm
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nferequest"
    workshop_permission_codename = "view_nfserequest"

    def get_item_formset(self) -> Any:
        if not hasattr(self, "_item_formset"):
            data = self.request.POST if self.request.method == "POST" else None
            self._item_formset = NfeManualItemFormSet(data=data, prefix="items", form_kwargs={"workshop": self.workshop})
        return self._item_formset

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["item_formset"] = self.get_item_formset()
        return context

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        try:
            kwargs["tax_class_choices"] = _nfe_tax_class_choices(workshop=self.workshop)
        except TaxClassServiceError as exc:
            kwargs["tax_class_choices"] = []
            messages.warning(self.request, f"Não foi possível carregar classes de imposto: {exc}")
        return kwargs

    def form_valid(self, form: NfeManualEmissionForm) -> HttpResponse:
        item_formset = self.get_item_formset()
        if not item_formset.is_valid():
            return self.form_invalid(form)

        try:
            with transaction.atomic():
                nfe_request = NfeRequest.objects.create(
                    workshop=self.workshop,
                    workorder=None,
                    manual_recipient=form.cleaned_data["recipient"],
                    emission_origin=NfeEmissionOrigin.MANUAL,
                    current_step=3,
                    status=NfeRequestStatus.CHECKING_PRODUCTS,
                    pricing_slider=0,
                    tax_class=str(form.cleaned_data["tax_class"]),
                    additional_information=str(form.cleaned_data.get("additional_information") or ""),
                    freight_mode=NfeFreightMode.NO_TRANSPORT,
                    transport_snapshot={},
                )
                for item_form in item_formset.forms:
                    if not item_form.cleaned_data or item_form.cleaned_data.get("DELETE"):
                        continue
                    NfeRequestManualItem.objects.create(
                        request=nfe_request,
                        product=item_form.cleaned_data["product"],
                        quantity=item_form.cleaned_data["quantity"],
                        unit_price=item_form.cleaned_data["unit_price"],
                    )
        except ValidationError as exc:
            form.add_error(None, exc)
            return self.form_invalid(form)
        except IntegrityError:
            form.add_error(None, "Não foi possível criar a solicitação manual com os dados informados.")
            return self.form_invalid(form)

        service = get_fiscal_service()
        try:
            response_payload = service.emit_nfe(nfe_request=nfe_request, request=self.request)
            service.sync_nfe_emission_response(nfe_request=nfe_request, response_payload=response_payload)
            if not nfe_request.update_status_based_on_request(response_payload.get("status")):
                nfe_request.set_status(NfeRequestStatus.PROCESSING)
        except FiscalServiceError as exc:
            logger.exception("Falha ao emitir NF-e manual", extra={"nfe_request_id": nfe_request.pk})
            messages.error(self.request, str(exc))
        else:
            messages.success(self.request, "NF-e manual enviada pelo fluxo fiscal existente.")

        return redirect("finance:nfe_detail", pk=nfe_request.pk)


class NfeManualQuickProductCreateView(LoginRequiredMixin, WorkshopScopedMixin, FormView):
    template_name = "finance/partials/nfe_manual_quick_product_modal.html"
    form_class = QuickProductForm
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nferequest"
    workshop_permission_codename = "view_nfserequest"

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        return kwargs

    def get_form(self, form_class: type[QuickProductForm] | None = None) -> QuickProductForm:
        form = cast(QuickProductForm, super().get_form(form_class))
        form.fields["ncm"].required = True
        return form

    def form_valid(self, form: QuickProductForm) -> HttpResponse:
        product = form.save(commit=False)
        product.workshop = self.workshop
        try:
            product.save()
        except IntegrityError:
            form.add_error("code", "Já existe um produto cadastrado com este código.")
            return self.form_invalid(form)

        response = HttpResponse(status=204)
        response["HX-Trigger"] = json.dumps({"manualProductSaved": {"id": str(product.pk), "label": str(product)}})
        return response

    def form_invalid(self, form: QuickProductForm) -> HttpResponse:
        return render(self.request, self.template_name, {"form": form})
