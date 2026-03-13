from __future__ import annotations

import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import CreateView, ListView

from apps.core.forms import MultiStepFormMixin
from apps.core.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.core.views import HtmxTemplateResponseMixin
from apps.finance.forms import NfseRequestStep1Form, NfseRequestStep2Form, NfseRequestStep3Form
from apps.finance.models.finance import NfseRequest, NfseRequestStatus
from apps.finance.services.emission import NfseEmissionError, emit_nfse_request, sync_emission_response
from apps.finance.services.tax_classes import TaxClassServiceError, list_tax_classes
from apps.workshops.mixin import WorkshopScopedMixin
from apps.workshops.util.workshops import get_active_workshop_or_404


logger = logging.getLogger(__name__)


class NfseRequestListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = NfseRequest
    template_name = "finance/nfse_request_list.html"
    context_object_name = "nfse_requests"
    htmx_template_name = "finance/partials/nfse_request_table.html"

    def get_queryset(self):
        return super().get_queryset().select_related("workorder", "workorder__budget", "workorder__budget__customer", "workorder__budget__vehicle")

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
            TableColumn("Ordem de Serviço", attr="workorder"),
            TableColumn("Cliente", attr="customer_name"),
            TableColumn(NfseRequest.criado_em.field.verbose_name, attr=NfseRequest.criado_em.field.name),
            TableColumn("Status", attr="nfse_request_status_badge", format="status_badge"),
        ]
        context["actions"] = [
            TableActionDefaults.edit("finance:nfse_update"),
        ]
        return context


class NfseRequestCreateView(LoginRequiredMixin, WorkshopScopedMixin, MultiStepFormMixin, CreateView):
    model = NfseRequest
    template_name = "finance/nfse_request_form.html"

    steps_definition = [
        {"title": "Selecionar OS", "form_class": NfseRequestStep1Form},
        {"title": "Conferir Cliente", "form_class": NfseRequestStep2Form},
        {"title": "Conferir Serviços", "form_class": NfseRequestStep3Form},
    ]

    def get_template_names(self):
        if self.request.htmx:
            return ["finance/partials/nfse_step_content.html"]
        return [self.template_name]

    def get_object(self, queryset=None):
        pk = self.kwargs.get("pk") or self.request.GET.get("pk")
        if not pk:
            return None
        return NfseRequest.objects.select_related("workorder", "workorder__budget", "workorder__budget__customer", "workorder__budget__vehicle").filter(pk=pk, workshop=self.workshop).first()

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request
        kwargs["workshop"] = self.workshop
        kwargs["instance"] = self.get_object()

        form_class = self.get_form_class()
        if isinstance(form_class, type) and issubclass(form_class, NfseRequestStep3Form):
            kwargs["tax_class_choices"] = self._get_nfse_tax_class_choices()

        return kwargs

    def _get_nfse_tax_class_choices(self) -> list[tuple[str, str]]:
        try:
            tax_classes = list_tax_classes(workshop=self.workshop, force_refresh=True)
        except TaxClassServiceError as exc:
            logger.warning(
                "nfse_tax_class_choices_load_failed workshop_id=%s user_id=%s error=%s",
                getattr(self.workshop, "pk", None),
                getattr(self.request.user, "id", None),
                str(exc),
            )
            messages.warning(self.request, f"Nao foi possivel carregar classes de imposto de NFS-e: {exc}")
            return []

        choices: list[tuple[str, str]] = []
        for tax_class in tax_classes:
            reference = str(tax_class.get("referencia") or "").strip()
            if not reference:
                continue

            tax_type = str(tax_class.get("tipo") or tax_class.get("type") or "").strip().lower()
            is_nfse_tax_class = tax_type in {"nfse", "nfs-e", "nsfe"}

            if not is_nfse_tax_class:
                has_nfse_shape = bool(tax_class.get("tipo_emissao")) and bool(tax_class.get("codigo_servico"))
                if not has_nfse_shape:
                    continue

            if str(tax_class.get("status") or "").strip().lower() == "inativo":
                continue

            description = str(tax_class.get("descricao") or "").strip()
            if description:
                label = f"{reference} - {description}"
            else:
                label = reference
            choices.append((reference, label))

        logger.info(
            "nfse_tax_class_choices_loaded workshop_id=%s user_id=%s total_choices=%s",
            getattr(self.workshop, "pk", None),
            getattr(self.request.user, "id", None),
            len(choices),
        )
        return choices

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault("is_update", False)
        return context

    def _step_url(self, step: int) -> str:
        return f"{self.request.path}?step={step}&pk={self.object.pk}"

    def _update_request_status_by_step(self, *, current_step: int) -> None:
        if current_step == 1:
            self.object.set_status(NfseRequestStatus.CHECKING_CLIENT)
        elif current_step == 2:
            self.object.set_status(NfseRequestStatus.CHECKING_SERVICES)

    def _finalize_emission(self) -> bool:
        logger.info(
            "nfse_finalize_started nfse_request_id=%s workshop_id=%s user_id=%s",
            getattr(self.object, "pk", None),
            getattr(self.workshop, "pk", None),
            getattr(self.request.user, "id", None),
        )
        try:
            response_payload = emit_nfse_request(nfse_request=self.object, request=self.request)
            sync_emission_response(nfse_request=self.object, response_payload=response_payload)

            if not self.object.update_status_based_on_request(response_payload.get("status")):
                self.object.set_status(NfseRequestStatus.PROCESSING)

            messages.success(self.request, "Solicitação de NFS-e enviada com sucesso.")
            logger.info(
                "nfse_finalize_succeeded nfse_request_id=%s workshop_id=%s user_id=%s status=%s",
                getattr(self.object, "pk", None),
                getattr(self.workshop, "pk", None),
                getattr(self.request.user, "id", None),
                str(getattr(self.object, "status", "")),
            )
            return True
        except NfseEmissionError as exc:
            logger.exception("Falha ao emitir NFS-e", extra={"nfse_request_id": self.object.pk})
            messages.error(self.request, str(exc))
            return False

    def form_valid(self, form):
        form.instance.workshop = self.workshop
        self.object = form.save()

        current_step = self.get_current_step()
        total_steps = len(self.get_steps_config())

        logger.info(
            "nfse_form_step_saved nfse_request_id=%s workshop_id=%s user_id=%s step=%s total_steps=%s",
            getattr(self.object, "pk", None),
            getattr(self.workshop, "pk", None),
            getattr(self.request.user, "id", None),
            current_step,
            total_steps,
        )

        self._update_request_status_by_step(current_step=current_step)

        next_step_value = min(current_step + 1, total_steps)
        if self.object.current_step < next_step_value:
            self.object.current_step = next_step_value
            self.object.save(update_fields=["current_step"])

        if current_step < total_steps:
            success_url = self._step_url(step=current_step + 1)
            logger.info(
                "nfse_form_next_step_redirect nfse_request_id=%s next_step=%s user_id=%s",
                getattr(self.object, "pk", None),
                current_step + 1,
                getattr(self.request.user, "id", None),
            )
            if self.request.htmx:
                response = redirect(success_url)
                response["HX-Push-Url"] = success_url
                return response
            return redirect(success_url)

        if not self._finalize_emission():
            step_url = self._step_url(step=current_step)
            logger.warning(
                "nfse_finalize_failed_redirect nfse_request_id=%s step=%s user_id=%s",
                getattr(self.object, "pk", None),
                current_step,
                getattr(self.request.user, "id", None),
            )
            if self.request.htmx:
                response = HttpResponse()
                response["HX-Redirect"] = step_url
                return response
            return redirect(step_url)

        success_url = reverse("finance:nfse_list")
        logger.info(
            "nfse_flow_completed nfse_request_id=%s user_id=%s",
            getattr(self.object, "pk", None),
            getattr(self.request.user, "id", None),
        )
        if self.request.htmx:
            response = HttpResponse()
            response["HX-Redirect"] = success_url
            return response
        return redirect(success_url)


class NfseRequestUpdateView(NfseRequestCreateView):
    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        step_in_url = int(request.GET.get("step", 0))

        if not step_in_url and self.object:
            target_step = self.object.current_step
            return redirect(f"{reverse('finance:nfse_update', kwargs={'pk': self.object.pk})}?step={target_step}")

        return super().get(request, *args, **kwargs)

    def dispatch(self, request, *args, **kwargs):
        self.workshop = get_active_workshop_or_404(request)
        if not self.model_instance:
            logger.warning(
                "nfse_update_missing_instance workshop_id=%s user_id=%s pk=%s",
                getattr(self.workshop, "pk", None),
                getattr(request.user, "id", None),
                kwargs.get("pk"),
            )
            return redirect("finance:nfse_list")
        return super().dispatch(request, *args, **kwargs)

    def get_object(self, queryset=None):
        pk = self.kwargs.get("pk")
        if pk:
            return NfseRequest.objects.select_related("workorder", "workorder__budget", "workorder__budget__customer", "workorder__budget__vehicle").filter(pk=pk, workshop=self.workshop).first()
        return super().get_object(queryset=queryset)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["is_update"] = True
        return context

    def _step_url(self, step: int) -> str:
        return f"{reverse('finance:nfse_update', kwargs={'pk': self.object.pk})}?step={step}"
