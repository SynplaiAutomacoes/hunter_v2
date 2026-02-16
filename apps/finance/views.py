from __future__ import annotations

import json
import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import CreateView, ListView, TemplateView

from apps.core.forms import MultiStepFormMixin
from apps.core.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.core.views import HtmxTemplateResponseMixin
from apps.finance.forms import NfseRequestStep1Form, NfseRequestStep2Form, NfseRequestStep3Form
from apps.finance.models import NfseBatch, NfseItem, NfseRequest, NfseRequestStatus
from apps.finance.services.emission import NfseEmissionError, emit_nfse_request, sync_emission_response
from apps.finance.services.mappers import extract_items_from_batch, map_batch_payload, map_item_payload
from apps.workshops.mixin import WorkshopScopedMixin
from apps.workshops.util.workshops import get_active_workshop_or_404


logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name="dispatch")
class WebhookView(View):
    def get(self, request):
        return JsonResponse({"ok": True, "message": "Pong"}, status=200)

    def post(self, request):
        try:
            payload = json.loads(request.body)
        except json.JSONDecodeError:
            logger.warning("Erro ao decodificar payload JSON no webhook de NFS-e")
            return JsonResponse({"ok": False, "message": "Invalid JSON"}, status=400)

        model = payload.get("modelo")
        if not model:
            logger.warning("Payload recebido sem campo 'modelo' no webhook de NFS-e")
            return JsonResponse({"ok": False, "message": "Missing 'modelo' field"}, status=400)

        if model == "lote_rps":
            batch_payload = map_batch_payload(payload)
            batch_uuid = batch_payload.get("uuid")
            if not batch_uuid:
                return JsonResponse({"ok": False, "message": "Missing batch uuid"}, status=400)

            batch = NfseBatch.objects.filter(uuid=batch_uuid).select_related("request", "workorder", "workshop").order_by("-id").first()
            if batch is None:
                return JsonResponse({"ok": False, "message": f"Batch não encontrado para UUID: {batch_uuid}"}, status=404)

            items = extract_items_from_batch(payload)

            with transaction.atomic():
                for key, value in batch_payload.items():
                    setattr(batch, key, value)
                batch.raw_payload = payload
                batch.save()

                for item_payload in items:
                    item_uuid = item_payload.get("uuid")
                    if not item_uuid:
                        continue

                    item, created = NfseItem.objects.get_or_create(
                        workorder=batch.workorder,
                        uuid=item_uuid,
                        defaults={
                            "workshop": batch.workshop,
                            "request": batch.request,
                            "batch": batch,
                            **item_payload,
                        },
                    )
                    if not created:
                        for key, value in item_payload.items():
                            setattr(item, key, value)
                        item.batch = batch
                        item.request = batch.request
                        item.raw_payload = payload
                        item.save()
                    else:
                        item.raw_payload = payload
                        item.save(update_fields=["raw_payload"])

                if batch.request:
                    batch.request.update_status_based_on_request(payload.get("status"))

            return JsonResponse({"ok": True, "message": "Payload processed successfully"}, status=200)

        if model == "nfse":
            item_payload = map_item_payload(payload)
            item_uuid = item_payload.get("uuid")
            if not item_uuid:
                return JsonResponse({"ok": False, "message": "Missing item uuid"}, status=400)

            item = NfseItem.objects.filter(uuid=item_uuid).select_related("request").order_by("-id").first()
            if item is None:
                return JsonResponse({"ok": False, "message": f"Item não encontrado para UUID: {item_uuid}"}, status=404)

            with transaction.atomic():
                for key, value in item_payload.items():
                    setattr(item, key, value)
                item.raw_payload = payload
                item.save()

            if item.request:
                item.request.update_status_based_on_request(payload.get("status"))

            return JsonResponse({"ok": True, "message": "Payload processed successfully"}, status=200)

        return JsonResponse({"ok": False, "message": "Invalid payload"}, status=400)


class NfseRequestListView(LoginRequiredMixin, WorkshopScopedMixin, HtmxTemplateResponseMixin, ListView):
    model = NfseRequest
    template_name = "finance/nfse_request_list.html"
    context_object_name = "nfse_requests"
    htmx_template_name = "finance/partials/nfse_request_table.html"

    def get_queryset(self):
        return super().get_queryset().select_related("workorder", "workorder__budget", "workorder__budget__customer", "workorder__budget__vehicle")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["fields"] = [
            TableColumn("ID", attr="id"),
            TableColumn("OS", attr="workorder"),
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
        return kwargs

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
        try:
            response_payload = emit_nfse_request(nfse_request=self.object, request=self.request)
            sync_emission_response(nfse_request=self.object, response_payload=response_payload)

            if not self.object.update_status_based_on_request(response_payload.get("status")):
                self.object.set_status(NfseRequestStatus.PROCESSING)

            messages.success(self.request, "Solicitação de NFS-e enviada com sucesso.")
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

        self._update_request_status_by_step(current_step=current_step)

        next_step_value = min(current_step + 1, total_steps)
        if self.object.current_step < next_step_value:
            self.object.current_step = next_step_value
            self.object.save(update_fields=["current_step"])

        if current_step < total_steps:
            success_url = self._step_url(step=current_step + 1)
            if self.request.htmx:
                response = redirect(success_url)
                response["HX-Push-Url"] = success_url
                return response
            return redirect(success_url)

        if not self._finalize_emission():
            return redirect(self._step_url(step=current_step))

        success_url = reverse("finance:nfse_list")
        if self.request.htmx:
            response = HttpResponse(status=204)
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


class NfePlaceholderView(LoginRequiredMixin, TemplateView):
    template_name = "finance/nfe_placeholder.html"
