from __future__ import annotations

from copy import deepcopy
import json
import logging
from typing import Any

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import HttpRequest, HttpResponse, JsonResponse
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
from apps.finance.forms import (
    CofinsScenarioForm,
    CofinsScenarioFormSet,
    IcmsScenarioForm,
    IcmsScenarioFormSet,
    IpiScenarioForm,
    IpiScenarioFormSet,
    NfeTaxClassForm,
    NfseRequestStep1Form,
    NfseRequestStep2Form,
    NfseRequestStep3Form,
    NfseTaxClassForm,
    PisScenarioForm,
    PisScenarioFormSet,
)
from apps.finance.models import NfseBatch, NfseItem, NfseRequest, NfseRequestStatus
from apps.finance.services.emission import NfseEmissionError, emit_nfse_request, sync_emission_response
from apps.finance.services.mappers import extract_items_from_batch, map_batch_payload, map_item_payload
from apps.finance.services.tax_classes import TaxClassServiceError, delete_tax_class, list_tax_classes, save_tax_class
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
            tax_classes = list_tax_classes()
        except TaxClassServiceError as exc:
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

        print("[TAX CLASS POST DEBUG] NFS-e choices", {"count": len(choices), "references": [value for value, _ in choices]})
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
        try:
            print(
                "[NFS-E DEBUG] Finalizando emissao",
                {
                    "nfse_request_id": self.object.pk,
                    "workorder_id": self.object.workorder_id,
                    "tax_class": self.object.tax_class,
                },
            )
            response_payload = emit_nfse_request(nfse_request=self.object, request=self.request)
            print("[NFS-E DEBUG] Resposta recebida na finalizacao", response_payload)
            sync_emission_response(nfse_request=self.object, response_payload=response_payload)

            if not self.object.update_status_based_on_request(response_payload.get("status")):
                self.object.set_status(NfseRequestStatus.PROCESSING)

            print("[NFS-E DEBUG] Status final da request", {"nfse_request_id": self.object.pk, "status": self.object.status})

            messages.success(self.request, "Solicitação de NFS-e enviada com sucesso.")
            return True
        except NfseEmissionError as exc:
            logger.exception("Falha ao emitir NFS-e", extra={"nfse_request_id": self.object.pk})
            print("[NFS-E DEBUG] Erro na finalizacao", str(exc))
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


class TaxClassManagerView(LoginRequiredMixin, WorkshopScopedMixin, TemplateView):
    template_name = "finance/tax_class_manager.html"
    model = NfseRequest
    workshop_permission_codename = "view_nfserequest"

    TAB_NFE = "nfe"
    TAB_NFSE = "nfse"

    NFE_FORMSET_CONFIG = {
        "icms": {
            "title": "Cenários de ICMS",
            "description": "Configure os cenários de ICMS por tipo de tributação, pessoa e CFOP.",
            "form_class": IcmsScenarioForm,
            "formset_class": IcmsScenarioFormSet,
        },
        "ipi": {
            "title": "Cenários de IPI",
            "description": "Defina CST, enquadramento e alíquota para IPI.",
            "form_class": IpiScenarioForm,
            "formset_class": IpiScenarioFormSet,
        },
        "pis": {
            "title": "Cenários de PIS",
            "description": "Defina CST e alíquota de PIS.",
            "form_class": PisScenarioForm,
            "formset_class": PisScenarioFormSet,
        },
        "cofins": {
            "title": "Cenários de COFINS",
            "description": "Defina CST e alíquota de COFINS.",
            "form_class": CofinsScenarioForm,
            "formset_class": CofinsScenarioFormSet,
        },
    }

    NFE_PRESETS: dict[str, dict[str, object]] = {
        "simples_nacional_revenda": {
            "label": "Simples Nacional - Revenda padrão",
            "description": "Saída dentro/fora do estado para pessoa física e jurídica com CST 102.",
            "payload": {
                "descricao": "Classe de impostos para Saída de produtos de revenda",
                "icms": [
                    {"tipo_tributacao": "simples_nacional", "cenario": "saida_dentro_estado", "tipo_pessoa": "fisica", "codigo_cfop": "5102", "situacao_tributaria": "102"},
                    {"tipo_tributacao": "simples_nacional", "cenario": "saida_fora_estado", "tipo_pessoa": "fisica", "codigo_cfop": "6102", "situacao_tributaria": "102"},
                    {"tipo_tributacao": "simples_nacional", "cenario": "saida_dentro_estado", "tipo_pessoa": "juridica", "codigo_cfop": "5102", "situacao_tributaria": "102"},
                    {"tipo_tributacao": "simples_nacional", "cenario": "saida_fora_estado", "tipo_pessoa": "juridica", "codigo_cfop": "6102", "situacao_tributaria": "102"},
                ],
                "ipi": [
                    {"cenario": "padrao", "tipo_pessoa": "fisica", "situacao_tributaria": "99", "codigo_enquadramento": "999", "aliquota": "0.00"},
                    {"cenario": "padrao", "tipo_pessoa": "juridica", "situacao_tributaria": "99", "codigo_enquadramento": "999", "aliquota": "0.00"},
                ],
                "pis": [
                    {"cenario": "padrao", "tipo_pessoa": "fisica", "situacao_tributaria": "99", "aliquota": "0.00"},
                    {"cenario": "padrao", "tipo_pessoa": "juridica", "situacao_tributaria": "99", "aliquota": "0.00"},
                ],
                "cofins": [
                    {"cenario": "padrao", "tipo_pessoa": "fisica", "situacao_tributaria": "99", "aliquota": "0.00"},
                    {"cenario": "padrao", "tipo_pessoa": "juridica", "situacao_tributaria": "99", "aliquota": "0.00"},
                ],
            },
        },
        "simples_nacional_credito": {
            "label": "Simples Nacional - Com crédito",
            "description": "Configuração com CST 101 e alíquota de crédito para destinatário jurídico.",
            "payload": {
                "descricao": "Classe de impostos SN com crédito de ICMS",
                "icms": [
                    {"tipo_tributacao": "simples_nacional", "cenario": "saida_dentro_estado", "tipo_pessoa": "juridica", "codigo_cfop": "5102", "situacao_tributaria": "101", "aliquota_credito": "2.00"},
                    {"tipo_tributacao": "simples_nacional", "cenario": "saida_fora_estado", "tipo_pessoa": "juridica", "codigo_cfop": "6102", "situacao_tributaria": "101", "aliquota_credito": "2.00"},
                ],
                "ipi": [{"cenario": "padrao", "tipo_pessoa": "juridica", "situacao_tributaria": "99", "codigo_enquadramento": "999", "aliquota": "0.00"}],
                "pis": [{"cenario": "padrao", "tipo_pessoa": "juridica", "situacao_tributaria": "99", "aliquota": "0.00"}],
                "cofins": [{"cenario": "padrao", "tipo_pessoa": "juridica", "situacao_tributaria": "99", "aliquota": "0.00"}],
            },
        },
    }

    NFSE_PRESETS: dict[str, dict[str, object]] = {
        "nfse_abrasf_basico": {
            "label": "NFS-e Padrão Nacional - Serviço padrão",
            "description": "Preset básico para prestacao de servico no padrao nacional.",
            "payload": {
                "descricao": "Classe de impostos para prestação de serviço",
                "tipo": "nfse",
                "tipo_emissao": "1",
                "codigo_servico": "010101",
                "codigo_tributacao_municipio": "010",
                "tributacao_iss": "1",
                "retencao_iss": "1",
                "cst_pis_cofins": "00",
                "retencao_pis_cofins": "0",
                "iss": "2.00",
                "pis": "0.00",
                "cofins": "0.00",
                "inss": "0.00",
                "ir": "0.00",
                "csll": "0.00",
            },
        },
        "nfse_abrasf_retido": {
            "label": "NFS-e Padrão Nacional - ISS retido",
            "description": "Preset para emissao com retencao de ISS pelo tomador.",
            "payload": {
                "descricao": "Classe de impostos para serviço com ISS retido",
                "tipo": "nfse",
                "tipo_emissao": "1",
                "codigo_servico": "010101",
                "codigo_tributacao_municipio": "010",
                "tributacao_iss": "1",
                "retencao_iss": "2",
                "cst_pis_cofins": "00",
                "retencao_pis_cofins": "0",
                "iss": "2.00",
                "pis": "0.00",
                "cofins": "0.00",
                "inss": "0.00",
                "ir": "0.00",
                "csll": "0.00",
            },
        },
    }

    @classmethod
    def _normalize_tab(cls, value: str | None) -> str:
        normalized = (value or "").strip().lower()
        if normalized == cls.TAB_NFSE:
            return cls.TAB_NFSE
        return cls.TAB_NFE

    @staticmethod
    def _is_nfse_tax_class(tax_class: dict[str, object]) -> bool:
        raw_type = str(tax_class.get("tipo") or tax_class.get("type") or "").strip().lower()
        return raw_type in {"nfse", "nfs-e"}

    def _tab_from_tax_class(self, tax_class: dict[str, object]) -> str:
        return self.TAB_NFSE if self._is_nfse_tax_class(tax_class) else self.TAB_NFE

    @classmethod
    def _preset_registry(cls, tab: str) -> dict[str, dict[str, object]]:
        if tab == cls.TAB_NFSE:
            return cls.NFSE_PRESETS
        return cls.NFE_PRESETS

    @classmethod
    def _preset_options(cls, tab: str) -> list[dict[str, str]]:
        options: list[dict[str, str]] = []
        for key, preset in cls._preset_registry(tab).items():
            options.append(
                {
                    "key": key,
                    "label": str(preset.get("label") or key),
                    "description": str(preset.get("description") or ""),
                }
            )
        return options

    @classmethod
    def _get_preset_payload(cls, *, tab: str, preset_key: str) -> dict[str, object] | None:
        preset = cls._preset_registry(tab).get(preset_key)
        if not isinstance(preset, dict):
            return None

        payload = preset.get("payload")
        if not isinstance(payload, dict):
            return None

        return deepcopy(payload)

    def _load_tax_classes(self) -> list[dict[str, object]]:
        try:
            return list_tax_classes()
        except TaxClassServiceError as exc:
            messages.error(self.request, str(exc))
            return []

    @staticmethod
    def _build_formset_initial(payload_items: object, *, fields: tuple[str, ...]) -> list[dict[str, object]]:
        if not isinstance(payload_items, list):
            return []

        initial: list[dict[str, object]] = []
        for index, item in enumerate(payload_items):
            if not isinstance(item, dict):
                continue

            row: dict[str, object] = {"source_index": index}
            for field_name in fields:
                if field_name in item:
                    row[field_name] = item[field_name]
            initial.append(row)

        return initial

    def _build_nfe_form(self, *, data: Any | None, editing_tax_class: dict[str, object] | None) -> NfeTaxClassForm:
        if data is not None:
            return NfeTaxClassForm(data)
        if editing_tax_class is not None:
            return NfeTaxClassForm(initial=NfeTaxClassForm.initial_from_tax_class(editing_tax_class))
        return NfeTaxClassForm()

    def _build_nfse_form(self, *, data: Any | None, editing_tax_class: dict[str, object] | None) -> NfseTaxClassForm:
        if data is not None:
            return NfseTaxClassForm(data)
        if editing_tax_class is not None:
            return NfseTaxClassForm(initial=NfseTaxClassForm.initial_from_tax_class(editing_tax_class))
        return NfseTaxClassForm()

    def _build_nfe_formsets(self, *, data: Any | None, editing_tax_class: dict[str, object] | None) -> dict[str, Any]:
        formsets: dict[str, Any] = {}
        for section_key, section in self.NFE_FORMSET_CONFIG.items():
            formset_class = section["formset_class"]
            form_class = section["form_class"]

            kwargs: dict[str, Any] = {"prefix": section_key}
            if data is not None:
                kwargs["data"] = data
            elif editing_tax_class is not None:
                kwargs["initial"] = self._build_formset_initial(editing_tax_class.get(section_key), fields=form_class.payload_fields)

            formsets[section_key] = formset_class(**kwargs)

        return formsets

    @staticmethod
    def _build_scenarios_from_formset(formset: Any, original_items: object) -> list[dict[str, object]]:
        original_list = original_items if isinstance(original_items, list) else []
        rows: list[dict[str, object]] = []

        for form in formset.forms:
            cleaned_data = form.cleaned_data
            if not cleaned_data:
                continue
            if cleaned_data.get("DELETE"):
                continue
            if cleaned_data.get("_is_empty"):
                continue

            payload_item, source_index = form.to_payload()
            merged_item: dict[str, object] = {}

            if isinstance(source_index, int) and 0 <= source_index < len(original_list):
                original_item = original_list[source_index]
                if isinstance(original_item, dict):
                    for key, value in original_item.items():
                        if key not in form.payload_fields:
                            merged_item[key] = value

            merged_item.update(payload_item)
            rows.append(merged_item)

        return rows

    def _build_nfe_payload(self, *, form: NfeTaxClassForm, formsets: dict[str, Any]) -> dict[str, object]:
        payload: dict[str, object] = dict(form.get_base_payload())
        payload.pop("tipo", None)

        for field_name in ("referencia", "descricao", "informacoes_fisco", "informacoes_complementares"):
            value = form.cleaned_data.get(field_name)
            if value in (None, ""):
                payload.pop(field_name, None)
                continue
            payload[field_name] = str(value).strip()

        for section_key in self.NFE_FORMSET_CONFIG:
            formset = formsets[section_key]
            scenarios = self._build_scenarios_from_formset(formset, payload.get(section_key))
            if scenarios:
                payload[section_key] = scenarios
            else:
                payload.pop(section_key, None)

        return payload

    @staticmethod
    def _formsets_are_valid(formsets: dict[str, Any]) -> bool:
        return all(formset.is_valid() for formset in formsets.values())

    @staticmethod
    def _sort_tax_classes(tax_classes: list[dict[str, object]]) -> list[dict[str, object]]:
        return sorted(tax_classes, key=lambda item: str(item.get("data") or ""), reverse=True)

    def _split_tax_classes(self, tax_classes: list[dict[str, object]]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        nfe_tax_classes: list[dict[str, object]] = []
        nfse_tax_classes: list[dict[str, object]] = []

        for tax_class in tax_classes:
            if self._is_nfse_tax_class(tax_class):
                nfse_tax_classes.append(tax_class)
                continue
            nfe_tax_classes.append(tax_class)

        return self._sort_tax_classes(nfe_tax_classes), self._sort_tax_classes(nfse_tax_classes)

    @staticmethod
    def _find_tax_class_by_reference(tax_classes: list[dict[str, object]], reference: str) -> dict[str, object] | None:
        normalized_reference = reference.strip()
        if not normalized_reference:
            return None

        for tax_class in tax_classes:
            item_reference = str(tax_class.get("referencia") or "").strip()
            if item_reference == normalized_reference:
                return tax_class

        return None

    def get_context_data(self, **kwargs: object) -> dict[str, object]:
        context = super().get_context_data(**kwargs)

        active_tab_value = kwargs.get("active_tab")
        if isinstance(active_tab_value, str):
            active_tab = self._normalize_tab(active_tab_value)
        else:
            active_tab = self._normalize_tab(self.request.GET.get("tab"))

        tax_classes_value = kwargs.get("tax_classes")
        if isinstance(tax_classes_value, list):
            tax_classes = tax_classes_value
        else:
            tax_classes = self._load_tax_classes()

        edit_reference_value = kwargs.get("edit_reference")
        if isinstance(edit_reference_value, str):
            edit_reference = edit_reference_value.strip()
        else:
            edit_reference = str(self.request.GET.get("edit") or "").strip()

        selected_preset_key_value = kwargs.get("selected_preset_key")
        if isinstance(selected_preset_key_value, str):
            selected_preset_key = selected_preset_key_value.strip()
        else:
            selected_preset_key = ""

        editing_tax_class = self._find_tax_class_by_reference(tax_classes, edit_reference)
        if editing_tax_class is not None:
            active_tab = self._tab_from_tax_class(editing_tax_class)
        else:
            edit_reference = ""

        nfe_form = kwargs.get("nfe_form")
        nfse_form = kwargs.get("nfse_form")
        nfe_formsets = kwargs.get("nfe_formsets")

        if active_tab == self.TAB_NFE:
            if not isinstance(nfe_form, NfeTaxClassForm):
                nfe_form = self._build_nfe_form(data=None, editing_tax_class=editing_tax_class)

            if not isinstance(nfe_formsets, dict):
                nfe_formsets = self._build_nfe_formsets(data=None, editing_tax_class=editing_tax_class)

            if not isinstance(nfse_form, NfseTaxClassForm):
                nfse_form = self._build_nfse_form(data=None, editing_tax_class=None)
        else:
            if not isinstance(nfse_form, NfseTaxClassForm):
                nfse_form = self._build_nfse_form(data=None, editing_tax_class=editing_tax_class)

            if not isinstance(nfe_form, NfeTaxClassForm):
                nfe_form = self._build_nfe_form(data=None, editing_tax_class=None)

            if not isinstance(nfe_formsets, dict):
                nfe_formsets = self._build_nfe_formsets(data=None, editing_tax_class=None)

        nfe_tax_classes, nfse_tax_classes = self._split_tax_classes(tax_classes)

        nfe_formset_sections = [
            {
                "key": section_key,
                "title": section["title"],
                "description": section["description"],
                "formset": nfe_formsets[section_key],
                "required_fields": section["form_class"].required_fields,
            }
            for section_key, section in self.NFE_FORMSET_CONFIG.items()
        ]

        context.update(
            {
                "active_tab": active_tab,
                "nfe_form": nfe_form,
                "nfse_form": nfse_form,
                "nfe_formset_sections": nfe_formset_sections,
                "edit_reference": edit_reference,
                "selected_preset_key": selected_preset_key,
                "nfe_presets": self._preset_options(self.TAB_NFE),
                "nfse_presets": self._preset_options(self.TAB_NFSE),
                "nfe_tax_classes": nfe_tax_classes,
                "nfse_tax_classes": nfse_tax_classes,
            }
        )
        return context

    def post(self, request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        active_tab = self._normalize_tab(request.POST.get("tab"))
        form_action = str(request.POST.get("form_action") or "save").strip().lower()
        selected_preset_key = str(request.POST.get("preset_key") or "").strip()

        tax_classes = self._load_tax_classes()
        edit_reference = str(request.GET.get("edit") or request.POST.get("referencia") or "").strip()
        editing_tax_class = self._find_tax_class_by_reference(tax_classes, edit_reference)

        if form_action == "apply_preset":
            preset_payload = self._get_preset_payload(tab=active_tab, preset_key=selected_preset_key)
            if preset_payload is None:
                messages.error(request, "Selecione um preset válido para aplicar.")
                if active_tab == self.TAB_NFE:
                    return self.render_to_response(
                        self.get_context_data(
                            active_tab=active_tab,
                            tax_classes=tax_classes,
                            nfe_form=self._build_nfe_form(data=request.POST, editing_tax_class=editing_tax_class),
                            nfe_formsets=self._build_nfe_formsets(data=request.POST, editing_tax_class=editing_tax_class),
                            edit_reference=edit_reference,
                            selected_preset_key=selected_preset_key,
                        )
                    )

                return self.render_to_response(
                    self.get_context_data(
                        active_tab=active_tab,
                        tax_classes=tax_classes,
                        nfse_form=self._build_nfse_form(data=request.POST, editing_tax_class=editing_tax_class),
                        edit_reference=edit_reference,
                        selected_preset_key=selected_preset_key,
                    )
                )

            reference_to_keep = str(request.POST.get("referencia") or edit_reference or "").strip()
            if reference_to_keep:
                preset_payload["referencia"] = reference_to_keep

            if active_tab == self.TAB_NFE:
                return self.render_to_response(
                    self.get_context_data(
                        active_tab=active_tab,
                        tax_classes=tax_classes,
                        nfe_form=self._build_nfe_form(data=None, editing_tax_class=preset_payload),
                        nfe_formsets=self._build_nfe_formsets(data=None, editing_tax_class=preset_payload),
                        edit_reference=reference_to_keep,
                        selected_preset_key=selected_preset_key,
                    )
                )

            return self.render_to_response(
                self.get_context_data(
                    active_tab=active_tab,
                    tax_classes=tax_classes,
                    nfse_form=self._build_nfse_form(data=None, editing_tax_class=preset_payload),
                    edit_reference=reference_to_keep,
                    selected_preset_key=selected_preset_key,
                )
            )

        if active_tab == self.TAB_NFE:
            nfe_form = self._build_nfe_form(data=request.POST, editing_tax_class=editing_tax_class)
            nfe_formsets = self._build_nfe_formsets(data=request.POST, editing_tax_class=editing_tax_class)

            if nfe_form.is_valid() and self._formsets_are_valid(nfe_formsets):
                payload = self._build_nfe_payload(form=nfe_form, formsets=nfe_formsets)
                is_update = bool(str(payload.get("referencia") or "").strip())

                try:
                    saved_tax_class = save_tax_class(payload=payload)
                except TaxClassServiceError as exc:
                    messages.error(request, str(exc))
                else:
                    reference = str(saved_tax_class.get("referencia") or payload.get("referencia") or "").strip()
                    if reference:
                        action_label = "atualizada" if is_update else "criada"
                        messages.success(request, f"Classe de imposto {reference} {action_label} com sucesso.")
                    else:
                        messages.success(request, "Classe de imposto salva com sucesso.")

                    redirect_url = f"{reverse('finance:tax_class_manager')}?tab={active_tab}"
                    if reference:
                        redirect_url = f"{redirect_url}&edit={reference}"
                    return redirect(redirect_url)

            return self.render_to_response(
                self.get_context_data(
                    active_tab=active_tab,
                    tax_classes=tax_classes,
                    nfe_form=nfe_form,
                    nfe_formsets=nfe_formsets,
                    edit_reference=edit_reference,
                    selected_preset_key=selected_preset_key,
                )
            )

        nfse_form = self._build_nfse_form(data=request.POST, editing_tax_class=editing_tax_class)

        if nfse_form.is_valid():
            payload = nfse_form.build_payload()
            is_update = bool(str(payload.get("referencia") or "").strip())

            try:
                saved_tax_class = save_tax_class(payload=payload)
            except TaxClassServiceError as exc:
                messages.error(request, str(exc))
            else:
                reference = str(saved_tax_class.get("referencia") or payload.get("referencia") or "").strip()
                if reference:
                    action_label = "atualizada" if is_update else "criada"
                    messages.success(request, f"Classe de imposto {reference} {action_label} com sucesso.")
                else:
                    messages.success(request, "Classe de imposto salva com sucesso.")

                redirect_url = f"{reverse('finance:tax_class_manager')}?tab={active_tab}"
                if reference:
                    redirect_url = f"{redirect_url}&edit={reference}"
                return redirect(redirect_url)

        return self.render_to_response(
            self.get_context_data(
                active_tab=active_tab,
                tax_classes=tax_classes,
                nfse_form=nfse_form,
                edit_reference=edit_reference,
                selected_preset_key=selected_preset_key,
            )
        )


class TaxClassListView(TaxClassManagerView):
    template_name = "finance/tax_class_list.html"

    def get_context_data(self, **kwargs: object) -> dict[str, object]:
        context = TemplateView.get_context_data(self, **kwargs)
        active_tab = self._normalize_tab(self.request.GET.get("tab"))
        tax_classes = self._load_tax_classes()
        nfe_tax_classes, nfse_tax_classes = self._split_tax_classes(tax_classes)
        context.update(
            {
                "active_tab": active_tab,
                "nfe_tax_classes": nfe_tax_classes,
                "nfse_tax_classes": nfse_tax_classes,
            }
        )
        return context

    def post(self, request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        form_action = str(request.POST.get("form_action") or "").strip().lower()
        active_tab = self._normalize_tab(request.POST.get("tab") or request.GET.get("tab"))

        if form_action != "delete":
            messages.error(request, "Acao invalida para a listagem de classe de imposto.")
            return redirect(f"{reverse('finance:tax_class_list')}?tab={active_tab}")

        reference = str(request.POST.get("reference") or "").strip()
        if not reference:
            messages.error(request, "Informe a referencia da classe de imposto para excluir.")
            return redirect(f"{reverse('finance:tax_class_list')}?tab={active_tab}")

        try:
            delete_tax_class(reference=reference)
        except TaxClassServiceError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f"Classe de imposto {reference} excluida com sucesso.")

        return redirect(f"{reverse('finance:tax_class_list')}?tab={active_tab}")


class TaxClassFormBaseView(TaxClassManagerView):
    template_name = "finance/tax_class_form.html"
    is_update = False

    def _resolve_reference(self) -> str:
        if self.is_update:
            return str(self.kwargs.get("reference") or "").strip()
        return str(self.request.GET.get("edit") or self.request.POST.get("referencia") or "").strip()

    def _resolve_target(self, tax_classes: list[dict[str, object]]) -> tuple[str, dict[str, object] | None]:
        reference = self._resolve_reference()
        return reference, self._find_tax_class_by_reference(tax_classes, reference)

    def get(self, request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        tax_classes = self._load_tax_classes()
        edit_reference, editing_tax_class = self._resolve_target(tax_classes)
        if self.is_update and editing_tax_class is None:
            messages.error(request, "Classe de imposto nao encontrada para edicao.")
            return redirect(f"{reverse('finance:tax_class_list')}?tab={self._normalize_tab(request.GET.get('tab'))}")

        active_tab = self._normalize_tab(request.GET.get("tab"))
        if editing_tax_class is not None:
            active_tab = self._tab_from_tax_class(editing_tax_class)

        return self.render_to_response(
            super().get_context_data(
                active_tab=active_tab,
                tax_classes=tax_classes,
                edit_reference=edit_reference,
            )
        )

    def post(self, request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        active_tab = self._normalize_tab(request.POST.get("tab"))
        form_action = str(request.POST.get("form_action") or "save").strip().lower()
        selected_preset_key = str(request.POST.get("preset_key") or "").strip()

        tax_classes = self._load_tax_classes()
        edit_reference, editing_tax_class = self._resolve_target(tax_classes)
        if self.is_update and editing_tax_class is None:
            messages.error(request, "Classe de imposto nao encontrada para edicao.")
            return redirect(f"{reverse('finance:tax_class_list')}?tab={active_tab}")

        if form_action == "apply_preset":
            preset_payload = self._get_preset_payload(tab=active_tab, preset_key=selected_preset_key)
            if preset_payload is None:
                messages.error(request, "Selecione um preset valido para aplicar.")
                return self.render_to_response(
                    super().get_context_data(
                        active_tab=active_tab,
                        tax_classes=tax_classes,
                        nfe_form=self._build_nfe_form(data=request.POST, editing_tax_class=editing_tax_class) if active_tab == self.TAB_NFE else None,
                        nfe_formsets=self._build_nfe_formsets(data=request.POST, editing_tax_class=editing_tax_class) if active_tab == self.TAB_NFE else None,
                        nfse_form=self._build_nfse_form(data=request.POST, editing_tax_class=editing_tax_class) if active_tab == self.TAB_NFSE else None,
                        edit_reference=edit_reference,
                        selected_preset_key=selected_preset_key,
                    )
                )

            reference_to_keep = edit_reference if self.is_update else ""
            if reference_to_keep:
                preset_payload["referencia"] = reference_to_keep

            return self.render_to_response(
                super().get_context_data(
                    active_tab=active_tab,
                    tax_classes=tax_classes,
                    nfe_form=self._build_nfe_form(data=None, editing_tax_class=preset_payload) if active_tab == self.TAB_NFE else None,
                    nfe_formsets=self._build_nfe_formsets(data=None, editing_tax_class=preset_payload) if active_tab == self.TAB_NFE else None,
                    nfse_form=self._build_nfse_form(data=None, editing_tax_class=preset_payload) if active_tab == self.TAB_NFSE else None,
                    edit_reference=reference_to_keep,
                    selected_preset_key=selected_preset_key,
                )
            )

        if active_tab == self.TAB_NFE:
            nfe_form = self._build_nfe_form(data=request.POST, editing_tax_class=editing_tax_class)
            nfe_formsets = self._build_nfe_formsets(data=request.POST, editing_tax_class=editing_tax_class)

            if nfe_form.is_valid() and self._formsets_are_valid(nfe_formsets):
                payload = self._build_nfe_payload(form=nfe_form, formsets=nfe_formsets)
                if self.is_update and edit_reference:
                    payload["referencia"] = edit_reference
                else:
                    payload.pop("referencia", None)

                is_update_action = bool(str(payload.get("referencia") or "").strip())
                try:
                    saved_tax_class = save_tax_class(payload=payload)
                except TaxClassServiceError as exc:
                    messages.error(request, str(exc))
                else:
                    reference = str(saved_tax_class.get("referencia") or payload.get("referencia") or "").strip()
                    action_label = "atualizada" if is_update_action else "criada"
                    if reference:
                        messages.success(request, f"Classe de imposto {reference} {action_label} com sucesso.")
                    else:
                        messages.success(request, "Classe de imposto salva com sucesso.")
                    return redirect(f"{reverse('finance:tax_class_list')}?tab={active_tab}")

            return self.render_to_response(
                super().get_context_data(
                    active_tab=active_tab,
                    tax_classes=tax_classes,
                    nfe_form=nfe_form,
                    nfe_formsets=nfe_formsets,
                    edit_reference=edit_reference,
                    selected_preset_key=selected_preset_key,
                )
            )

        nfse_form = self._build_nfse_form(data=request.POST, editing_tax_class=editing_tax_class)
        if nfse_form.is_valid():
            payload = nfse_form.build_payload()
            if self.is_update and edit_reference:
                payload["referencia"] = edit_reference
            else:
                payload.pop("referencia", None)

            is_update_action = bool(str(payload.get("referencia") or "").strip())
            try:
                saved_tax_class = save_tax_class(payload=payload)
            except TaxClassServiceError as exc:
                messages.error(request, str(exc))
            else:
                reference = str(saved_tax_class.get("referencia") or payload.get("referencia") or "").strip()
                action_label = "atualizada" if is_update_action else "criada"
                if reference:
                    messages.success(request, f"Classe de imposto {reference} {action_label} com sucesso.")
                else:
                    messages.success(request, "Classe de imposto salva com sucesso.")
                return redirect(f"{reverse('finance:tax_class_list')}?tab={active_tab}")

        return self.render_to_response(
            super().get_context_data(
                active_tab=active_tab,
                tax_classes=tax_classes,
                nfse_form=nfse_form,
                edit_reference=edit_reference,
                selected_preset_key=selected_preset_key,
            )
        )


class TaxClassCreateView(TaxClassFormBaseView):
    is_update = False


class TaxClassUpdateView(TaxClassFormBaseView):
    is_update = True


class NfePlaceholderView(LoginRequiredMixin, TemplateView):
    template_name = "finance/nfe_placeholder.html"
