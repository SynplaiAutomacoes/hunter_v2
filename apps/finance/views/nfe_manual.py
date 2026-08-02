from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Any, cast

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import FormView

from apps.core.domain.contracts.fiscal import FiscalServiceError
from apps.core.infrastructure.providers import get_fiscal_service
from apps.finance.forms.nfe_manual import NfeManualEmissionForm, NfeManualItemFormSet, NfeManualQuickProductForm
from apps.finance.models import FiscalEmissionAttempt, NfeEmissionOrigin, NfeRequest, NfeRequestManualItem
from apps.finance.models.finance import NfeFreightMode, NfeRequestStatus
from apps.finance.services.tax_classes import TaxClassServiceError, list_tax_classes
from apps.finance.views.request_workflow import render_emission_preview_modal
from apps.workshops.mixin import WorkshopScopedMixin
from apps.workshops.util.workshops import has_workshop_perm


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
    _preview_draft: NfeRequest | None
    template_name = "finance/nfe_manual_emission_form.html"
    form_class = NfeManualEmissionForm
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nferequest"
    workshop_permission_codename = "view_nferequest"
    workshop_permission_fallbacks = (("finance", "nfserequest", "view_nfserequest"),)

    def _preview_draft_session_key(self) -> str:
        return f"finance.manual_nfe_preview:{self.workshop.pk}:{self.request.user.pk}"

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if request.GET.get("new") == "1":
            request.session.pop(self._preview_draft_session_key(), None)
            return redirect("finance:emission_manual")
        return super().get(request, *args, **kwargs)

    def _get_reusable_preview_draft(self) -> NfeRequest | None:
        if hasattr(self, "_preview_draft"):
            return self._preview_draft

        session_key = self._preview_draft_session_key()
        draft_id = self.request.session.get(session_key)
        if not draft_id:
            self._preview_draft = None
            return None

        draft = (
            NfeRequest.objects.filter(
                pk=draft_id,
                workshop=self.workshop,
                emission_origin=NfeEmissionOrigin.MANUAL,
                status__in=(NfeRequestStatus.CHECKING_CLIENT, NfeRequestStatus.CHECKING_PRODUCTS),
                reserved_number__isnull=True,
                items__isnull=True,
            )
            .distinct()
            .first()
        )
        has_attempt = draft is not None and FiscalEmissionAttempt.objects.filter(request_model="NfeRequest", request_id=draft.pk).exists()
        if draft is not None and not has_attempt:
            self._preview_draft = draft
            return draft

        self.request.session.pop(session_key, None)
        self._preview_draft = None
        return None

    def _persist_manual_items(self, *, nfe_request: NfeRequest, item_formset: Any) -> None:
        nfe_request.manual_items.all().delete()
        for item_form in item_formset.forms:
            if not item_form.cleaned_data or item_form.cleaned_data.get("DELETE"):
                continue
            NfeRequestManualItem.objects.create(
                request=nfe_request,
                product=item_form.cleaned_data["product"],
                item_origin=item_form.cleaned_data["item_origin"],
                fiscal_snapshot=item_form.cleaned_data["fiscal_snapshot"],
                quantity=item_form.cleaned_data["quantity"],
                unit_price=item_form.cleaned_data["unit_price"],
            )

    def _save_progress(self, *, form: NfeManualEmissionForm, next_step: int, item_formset: Any | None = None) -> NfeRequest:
        nfe_request = self._get_reusable_preview_draft() or NfeRequest(workshop=self.workshop)
        nfe_request.workorder = None
        nfe_request.manual_recipient = form.cleaned_data["recipient"]
        nfe_request.emission_origin = NfeEmissionOrigin.MANUAL
        nfe_request.current_step = next_step
        nfe_request.status = NfeRequestStatus.CHECKING_CLIENT if next_step == 2 else NfeRequestStatus.CHECKING_PRODUCTS
        nfe_request.pricing_slider = 0
        nfe_request.freight_mode = NfeFreightMode.NO_TRANSPORT
        nfe_request.transport_snapshot = {}
        nfe_request.save()

        if item_formset is not None:
            self._persist_manual_items(nfe_request=nfe_request, item_formset=item_formset)

        self.request.session[self._preview_draft_session_key()] = nfe_request.pk
        self._preview_draft = nfe_request
        return nfe_request

    def _save_preview_draft(self, *, form: NfeManualEmissionForm, item_formset: Any) -> NfeRequest:
        nfe_request = self._get_reusable_preview_draft() or NfeRequest(workshop=self.workshop)
        nfe_request.workorder = None
        nfe_request.manual_recipient = form.cleaned_data["recipient"]
        nfe_request.emission_origin = NfeEmissionOrigin.MANUAL
        nfe_request.current_step = 3
        nfe_request.status = NfeRequestStatus.CHECKING_PRODUCTS
        nfe_request.pricing_slider = 0
        nfe_request.tax_class = str(form.cleaned_data["tax_class"])
        nfe_request.additional_information = str(form.cleaned_data.get("additional_information") or "")
        nfe_request.freight_mode = NfeFreightMode.NO_TRANSPORT
        nfe_request.transport_snapshot = {}
        nfe_request.save()
        self._persist_manual_items(nfe_request=nfe_request, item_formset=item_formset)

        self.request.session[self._preview_draft_session_key()] = nfe_request.pk
        self._preview_draft = nfe_request
        return nfe_request

    def get_item_formset(self) -> Any:
        if not hasattr(self, "_item_formset"):
            data = self.request.POST if self.request.method == "POST" else None
            initial = None
            if data is None:
                draft = self._get_reusable_preview_draft()
                if draft is not None:
                    initial = [
                        {
                            "item_origin": item.item_origin,
                            "product": item.product_id,
                            "fiscal_snapshot": item.fiscal_snapshot,
                            "quantity": item.quantity,
                            "unit_price": item.unit_price,
                        }
                        for item in draft.manual_items.order_by("pk")
                    ]
            self._item_formset = NfeManualItemFormSet(data=data, initial=initial, prefix="items", form_kwargs={"workshop": self.workshop})
        return self._item_formset

    def get_initial(self) -> dict[str, Any]:
        initial = super().get_initial()
        draft = self._get_reusable_preview_draft()
        if draft is not None:
            initial.update({"recipient": draft.manual_recipient_id, "additional_information": draft.additional_information})
            tax_class_default = NfeRequest._meta.get_field("tax_class").get_default()
            if draft.tax_class != tax_class_default:
                initial["tax_class"] = draft.tax_class
        return initial

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["item_formset"] = self.get_item_formset()
        draft = self._get_reusable_preview_draft()
        context["manual_current_step"] = draft.current_step if draft is not None else 1
        context["manual_max_reached_step"] = draft.current_step if draft is not None else 1
        context["can_add_customer"] = has_workshop_perm(
            user=self.request.user,
            workshop=self.workshop,
            app_label="customer",
            model="customer",
            codename="add_customer",
            request=self.request,
        )
        context["can_add_product"] = has_workshop_perm(
            user=self.request.user,
            workshop=self.workshop,
            app_label="catalog",
            model="product",
            codename="add_product",
            request=self.request,
        )
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

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if request.POST.get("_save_progress") != "1":
            return super().post(request, *args, **kwargs)

        try:
            next_step = int(request.POST.get("next_step", "0"))
        except ValueError:
            next_step = 0
        if next_step not in {2, 3}:
            return JsonResponse({"error": "Etapa inválida."}, status=400)

        form = self.get_form()
        form.fields["tax_class"].required = False
        if not form.is_valid():
            return JsonResponse({"errors": form.errors.get_json_data()}, status=400)

        item_formset = self.get_item_formset() if next_step == 3 else None
        if item_formset is not None and not item_formset.is_valid():
            return JsonResponse({"errors": item_formset.errors, "non_form_errors": list(item_formset.non_form_errors())}, status=400)

        with transaction.atomic():
            nfe_request = self._save_progress(form=form, next_step=next_step, item_formset=item_formset)
        return JsonResponse({"current_step": nfe_request.current_step, "nfe_request_id": nfe_request.pk})

    def form_valid(self, form: NfeManualEmissionForm) -> HttpResponse:
        item_formset = self.get_item_formset()
        if not item_formset.is_valid():
            return self.form_invalid(form)

        try:
            with transaction.atomic():
                nfe_request = self._save_preview_draft(form=form, item_formset=item_formset)
        except ValidationError as exc:
            form.add_error(None, exc)
            return self.form_invalid(form)
        except IntegrityError:
            form.add_error(None, "Não foi possível criar a solicitação manual com os dados informados.")
            return self.form_invalid(form)

        return render_emission_preview_modal(
            request=self.request,
            title="Prévia da emissão manual de NF-e",
            description="Confira a DANFE e, se os dados estiverem corretos, confirme a transmissão.",
            previews=[{"label": "DANFE", "embed_url": reverse("finance:nfe_preview_pdf", kwargs={"pk": nfe_request.pk})}],
            transmit_url=reverse("finance:emission_manual_transmit", kwargs={"pk": nfe_request.pk}),
            hidden_fields=[],
            transmit_target="#modal-container",
            transmit_label="Transmitir nota",
        )

    def form_invalid(self, form: NfeManualEmissionForm) -> HttpResponse:
        response = super().form_invalid(form)
        if getattr(self.request, "htmx", False):
            response["HX-Retarget"] = "#manual-nfe-page"
            response["HX-Reswap"] = "outerHTML"
            response["HX-Reselect"] = "#manual-nfe-page"
        return response


class NfeManualTransmissionView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nferequest"
    workshop_permission_codename = "view_nferequest"
    workshop_permission_fallbacks = (("finance", "nfserequest", "view_nfserequest"),)

    def _redirect_to_detail(self, *, nfe_request: NfeRequest) -> HttpResponse:
        detail_url = reverse("finance:nfe_detail", kwargs={"pk": nfe_request.pk})
        if getattr(self.request, "htmx", False):
            response = HttpResponse(status=204)
            response["HX-Redirect"] = detail_url
            return response
        return redirect(detail_url)

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        nfe_request = get_object_or_404(
            NfeRequest.objects.select_related("manual_recipient"),
            pk=kwargs["pk"],
            workshop=self.workshop,
            emission_origin=NfeEmissionOrigin.MANUAL,
        )
        attempt_exists = FiscalEmissionAttempt.objects.filter(request_model="NfeRequest", request_id=nfe_request.pk).exists()
        if attempt_exists or nfe_request.status != NfeRequestStatus.CHECKING_PRODUCTS:
            messages.warning(request, "Esta NF-e manual já foi enviada ou possui uma tentativa de transmissão registrada.")
            return self._redirect_to_detail(nfe_request=nfe_request)

        if nfe_request.manual_recipient_id is None or not nfe_request.manual_items.exists():
            messages.error(request, "A NF-e manual não possui destinatário e itens válidos para transmissão.")
            return self._redirect_to_detail(nfe_request=nfe_request)

        service = get_fiscal_service()
        try:
            response_payload = service.emit_nfe(nfe_request=nfe_request, request=request)
            service.sync_nfe_emission_response(nfe_request=nfe_request, response_payload=response_payload)
            if not nfe_request.update_status_based_on_request(response_payload.get("status")):
                nfe_request.set_status(NfeRequestStatus.PROCESSING)
        except FiscalServiceError as exc:
            logger.exception("Falha ao transmitir NF-e manual", extra={"nfe_request_id": nfe_request.pk})
            messages.error(request, str(exc))
        else:
            session_key = f"finance.manual_nfe_preview:{self.workshop.pk}:{request.user.pk}"
            if request.session.get(session_key) == nfe_request.pk:
                request.session.pop(session_key, None)
            messages.success(request, "NF-e manual enviada pelo fluxo fiscal existente.")

        return self._redirect_to_detail(nfe_request=nfe_request)


class NfeManualQuickProductCreateView(LoginRequiredMixin, WorkshopScopedMixin, FormView):
    template_name = "finance/partials/nfe_manual_quick_product_modal.html"
    form_class = NfeManualQuickProductForm
    workshop_permission_app_label = "finance"
    workshop_permission_model = "nferequest"
    workshop_permission_codename = "view_nferequest"
    workshop_permission_fallbacks = (("finance", "nfserequest", "view_nfserequest"),)

    def can_save_to_catalog(self) -> bool:
        return has_workshop_perm(
            user=self.request.user,
            workshop=self.workshop,
            app_label="catalog",
            model="product",
            codename="add_product",
            request=self.request,
        )

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["workshop"] = self.workshop
        kwargs["can_save_to_catalog"] = self.can_save_to_catalog()
        return kwargs

    def get_form(self, form_class: type[NfeManualQuickProductForm] | None = None) -> NfeManualQuickProductForm:
        return cast(NfeManualQuickProductForm, super().get_form(form_class))

    def form_valid(self, form: NfeManualQuickProductForm) -> HttpResponse:
        if not form.should_save_to_catalog:
            snapshot = form.build_fiscal_snapshot()
            unit_price = Decimal(form.cleaned_data["selling_price"].amount)
            response = HttpResponse(status=204)
            response["HX-Trigger"] = json.dumps(
                {
                    "manualTemporaryProductCreated": {
                        "label": snapshot["description"],
                        "snapshot": snapshot,
                        "unit_price": str(unit_price),
                    }
                }
            )
            return response

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

    def form_invalid(self, form: NfeManualQuickProductForm) -> HttpResponse:
        return render(self.request, self.template_name, {"form": form})
