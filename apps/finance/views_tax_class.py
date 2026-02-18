from __future__ import annotations

from copy import deepcopy
from typing import Any

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import TemplateView

from apps.finance.forms import (
    CofinsScenarioForm,
    CofinsScenarioFormSet,
    IcmsScenarioForm,
    IcmsScenarioFormSet,
    IpiScenarioForm,
    IpiScenarioFormSet,
    NfeTaxClassForm,
    NfseTaxClassForm,
    PisScenarioForm,
    PisScenarioFormSet,
)
from apps.finance.models import NfseRequest
from apps.finance.services.tax_classes import TaxClassServiceError, delete_tax_class, list_tax_classes, save_tax_class
from apps.workshops.mixin import WorkshopScopedMixin


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
            return list_tax_classes(workshop=self.workshop)
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
                "is_update": getattr(self, "is_update", False),
                "nfe_form": nfe_form,
                "nfse_form": nfse_form,
                "nfe_formset_sections": nfe_formset_sections,
                "edit_reference": edit_reference,
                "editing_tax_class": editing_tax_class,
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
                    saved_tax_class = save_tax_class(workshop=self.workshop, payload=payload)
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
                saved_tax_class = save_tax_class(workshop=self.workshop, payload=payload)
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
            delete_tax_class(workshop=self.workshop, reference=reference)
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

        if self.is_update and editing_tax_class is not None:
            active_tab = self._tab_from_tax_class(editing_tax_class)

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

            reference_to_keep = str(request.POST.get("referencia") or "").strip()
            if self.is_update:
                reference_to_keep = edit_reference
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
                    saved_tax_class = save_tax_class(workshop=self.workshop, payload=payload)
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
                saved_tax_class = save_tax_class(workshop=self.workshop, payload=payload)
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
