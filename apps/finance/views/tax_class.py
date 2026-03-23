from __future__ import annotations

from copy import deepcopy
import logging
from typing import Any

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import TemplateView

from apps.core.query_filters import apply_is_active_filter
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
    TaxClassPresetMetaForm,
)
from apps.finance.models.finance import NfseRequest, TaxClassPreset, TaxClassPresetKind
from apps.finance.services.tax_class_presets import normalize_tax_class_preset_payload
from apps.finance.services.tax_classes import TaxClassServiceError, delete_tax_class, list_tax_classes, save_tax_class
from apps.workshops.mixin import WorkshopScopedMixin


logger = logging.getLogger(__name__)


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
    def _preset_kind_from_tab(cls, tab: str) -> str:
        if tab == cls.TAB_NFSE:
            return TaxClassPresetKind.NFSE
        return TaxClassPresetKind.NFE

    def _preset_queryset(self, *, tab: str, active_only: bool = True):
        queryset = TaxClassPreset.objects.filter(workshop=self.workshop, kind=self._preset_kind_from_tab(tab)).order_by("name", "id")
        if active_only:
            queryset = queryset.filter(is_active=True)
        return queryset

    def _preset_options(self, tab: str) -> list[dict[str, str]]:
        options: list[dict[str, str]] = []
        for preset in self._preset_queryset(tab=tab, active_only=True):
            options.append(
                {
                    "key": str(preset.pk),
                    "label": str(preset.name or preset.pk),
                    "description": str(preset.description or ""),
                }
            )
        return options

    def _get_preset_payload(self, *, tab: str, preset_key: str) -> dict[str, object] | None:
        normalized_key = str(preset_key or "").strip()
        if not normalized_key.isdigit():
            return None

        preset = self._preset_queryset(tab=tab, active_only=True).filter(pk=int(normalized_key)).first()
        if preset is None:
            return None

        payload = preset.payload
        if not isinstance(payload, dict):
            return None

        return deepcopy(payload)

    def _load_tax_classes(self) -> list[dict[str, object]]:
        try:
            tax_classes = list_tax_classes(workshop=self.workshop)
        except TaxClassServiceError as exc:
            logger.warning(
                "tax_class_list_load_failed workshop_id=%s user_id=%s error=%s",
                getattr(self.workshop, "pk", None),
                getattr(self.request.user, "id", None),
                str(exc),
            )
            messages.error(self.request, str(exc))
            return []

        logger.info(
            "tax_class_list_loaded workshop_id=%s user_id=%s total=%s",
            getattr(self.workshop, "pk", None),
            getattr(self.request.user, "id", None),
            len(tax_classes),
        )
        return tax_classes

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

        logger.info(
            "tax_class_manager_post workshop_id=%s user_id=%s tab=%s action=%s",
            getattr(self.workshop, "pk", None),
            getattr(request.user, "id", None),
            active_tab,
            form_action,
        )

        tax_classes = self._load_tax_classes()
        edit_reference = str(request.GET.get("edit") or request.POST.get("referencia") or "").strip()
        editing_tax_class = self._find_tax_class_by_reference(tax_classes, edit_reference)

        if form_action == "apply_preset":
            preset_payload = self._get_preset_payload(tab=active_tab, preset_key=selected_preset_key)
            if preset_payload is None:
                logger.warning(
                    "tax_class_preset_invalid workshop_id=%s user_id=%s tab=%s preset=%s",
                    getattr(self.workshop, "pk", None),
                    getattr(request.user, "id", None),
                    active_tab,
                    selected_preset_key,
                )
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
                    logger.warning(
                        "tax_class_save_failed workshop_id=%s user_id=%s tab=%s reference=%s error=%s",
                        getattr(self.workshop, "pk", None),
                        getattr(request.user, "id", None),
                        active_tab,
                        str(payload.get("referencia") or ""),
                        str(exc),
                    )
                    messages.error(request, str(exc))
                else:
                    reference = str(saved_tax_class.get("referencia") or payload.get("referencia") or "").strip()
                    logger.info(
                        "tax_class_save_succeeded workshop_id=%s user_id=%s tab=%s reference=%s",
                        getattr(self.workshop, "pk", None),
                        getattr(request.user, "id", None),
                        active_tab,
                        reference,
                    )
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
                logger.warning(
                    "tax_class_save_failed workshop_id=%s user_id=%s tab=%s reference=%s error=%s",
                    getattr(self.workshop, "pk", None),
                    getattr(request.user, "id", None),
                    active_tab,
                    str(payload.get("referencia") or ""),
                    str(exc),
                )
                messages.error(request, str(exc))
            else:
                reference = str(saved_tax_class.get("referencia") or payload.get("referencia") or "").strip()
                logger.info(
                    "tax_class_save_succeeded workshop_id=%s user_id=%s tab=%s reference=%s",
                    getattr(self.workshop, "pk", None),
                    getattr(request.user, "id", None),
                    active_tab,
                    reference,
                )
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

        logger.info(
            "tax_class_list_post workshop_id=%s user_id=%s tab=%s action=%s",
            getattr(self.workshop, "pk", None),
            getattr(request.user, "id", None),
            active_tab,
            form_action,
        )

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
            logger.warning(
                "tax_class_delete_failed workshop_id=%s user_id=%s reference=%s error=%s",
                getattr(self.workshop, "pk", None),
                getattr(request.user, "id", None),
                reference,
                str(exc),
            )
            messages.error(request, str(exc))
        else:
            logger.info(
                "tax_class_delete_succeeded workshop_id=%s user_id=%s reference=%s",
                getattr(self.workshop, "pk", None),
                getattr(request.user, "id", None),
                reference,
            )
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
        logger.info(
            "tax_class_form_loaded workshop_id=%s user_id=%s is_update=%s reference=%s",
            getattr(self.workshop, "pk", None),
            getattr(request.user, "id", None),
            self.is_update,
            self._resolve_reference(),
        )
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

        logger.info(
            "tax_class_form_post workshop_id=%s user_id=%s is_update=%s tab=%s action=%s",
            getattr(self.workshop, "pk", None),
            getattr(request.user, "id", None),
            self.is_update,
            active_tab,
            form_action,
        )

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
                messages.error(request, "Selecione um preset válido para aplicar.")
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
                    logger.warning(
                        "tax_class_form_save_failed workshop_id=%s user_id=%s tab=%s reference=%s error=%s",
                        getattr(self.workshop, "pk", None),
                        getattr(request.user, "id", None),
                        active_tab,
                        str(payload.get("referencia") or ""),
                        str(exc),
                    )
                    messages.error(request, str(exc))
                else:
                    reference = str(saved_tax_class.get("referencia") or payload.get("referencia") or "").strip()
                    logger.info(
                        "tax_class_form_save_succeeded workshop_id=%s user_id=%s tab=%s reference=%s is_update=%s",
                        getattr(self.workshop, "pk", None),
                        getattr(request.user, "id", None),
                        active_tab,
                        reference,
                        is_update_action,
                    )
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
                logger.warning(
                    "tax_class_form_save_failed workshop_id=%s user_id=%s tab=%s reference=%s error=%s",
                    getattr(self.workshop, "pk", None),
                    getattr(request.user, "id", None),
                    active_tab,
                    str(payload.get("referencia") or ""),
                    str(exc),
                )
                messages.error(request, str(exc))
            else:
                reference = str(saved_tax_class.get("referencia") or payload.get("referencia") or "").strip()
                logger.info(
                    "tax_class_form_save_succeeded workshop_id=%s user_id=%s tab=%s reference=%s is_update=%s",
                    getattr(self.workshop, "pk", None),
                    getattr(request.user, "id", None),
                    active_tab,
                    reference,
                    is_update_action,
                )
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


class TaxClassPresetListView(LoginRequiredMixin, WorkshopScopedMixin, TemplateView):
    template_name = "finance/tax_class_preset_list.html"
    model = NfseRequest
    workshop_permission_codename = "view_nfserequest"

    def _get_queryset_by_tab(self, *, tab: str):
        queryset = TaxClassPreset.objects.filter(workshop=self.workshop, kind=TaxClassManagerView._preset_kind_from_tab(tab))
        queryset = apply_is_active_filter(queryset, params=self.request.GET)
        return queryset.order_by("name", "id")

    def get_context_data(self, **kwargs: object) -> dict[str, object]:
        context = super().get_context_data(**kwargs)
        active_tab = TaxClassManagerView._normalize_tab(self.request.GET.get("tab"))
        context.update(
            {
                "active_tab": active_tab,
                "nfe_presets": self._get_queryset_by_tab(tab=TaxClassManagerView.TAB_NFE),
                "nfse_presets": self._get_queryset_by_tab(tab=TaxClassManagerView.TAB_NFSE),
            }
        )
        return context

    def post(self, request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        form_action = str(request.POST.get("form_action") or "").strip().lower()
        active_tab = TaxClassManagerView._normalize_tab(request.POST.get("tab") or request.GET.get("tab"))
        if form_action != "delete":
            messages.error(request, "Acao invalida para a listagem de presets fiscais.")
            return redirect(f"{reverse('finance:tax_class_preset_list')}?tab={active_tab}")

        preset_id = str(request.POST.get("preset_id") or "").strip()
        if not preset_id.isdigit():
            messages.error(request, "Informe um preset valido para excluir.")
            return redirect(f"{reverse('finance:tax_class_preset_list')}?tab={active_tab}")

        preset = TaxClassPreset.objects.filter(workshop=self.workshop, pk=int(preset_id)).first()
        if preset is None:
            messages.error(request, "Preset fiscal nao encontrado.")
            return redirect(f"{reverse('finance:tax_class_preset_list')}?tab={active_tab}")

        active_tab = TaxClassManagerView._normalize_tab(preset.kind)
        preset_name = preset.name
        preset.delete()
        messages.success(request, f"Preset fiscal {preset_name} excluido com sucesso.")
        return redirect(f"{reverse('finance:tax_class_preset_list')}?tab={active_tab}")


class TaxClassPresetFormBaseView(TaxClassManagerView):
    template_name = "finance/tax_class_preset_form.html"
    is_update = False

    def _resolve_preset(self) -> TaxClassPreset | None:
        if not self.is_update:
            return None

        preset_pk = self.kwargs.get("pk")
        if preset_pk is None:
            return None

        return TaxClassPreset.objects.filter(workshop=self.workshop, pk=preset_pk).first()

    @staticmethod
    def _payload_from_preset(preset: TaxClassPreset | None) -> dict[str, object] | None:
        if preset is None or not isinstance(preset.payload, dict):
            return None
        return deepcopy(preset.payload)

    @staticmethod
    def _build_preset_meta_form(*, data: Any | None, preset: TaxClassPreset | None) -> TaxClassPresetMetaForm:
        if data is not None:
            return TaxClassPresetMetaForm(data, instance=preset)
        return TaxClassPresetMetaForm(instance=preset)

    def _build_preset_form_context(
        self,
        *,
        active_tab: str,
        preset: TaxClassPreset | None,
        meta_form: TaxClassPresetMetaForm | None = None,
        nfe_form: NfeTaxClassForm | None = None,
        nfe_formsets: dict[str, Any] | None = None,
        nfse_form: NfseTaxClassForm | None = None,
    ) -> dict[str, object]:
        payload = self._payload_from_preset(preset)

        if meta_form is None:
            meta_form = self._build_preset_meta_form(data=None, preset=preset)

        if active_tab == self.TAB_NFE:
            if nfe_form is None:
                nfe_form = self._build_nfe_form(data=None, editing_tax_class=payload)
            if nfe_formsets is None:
                nfe_formsets = self._build_nfe_formsets(data=None, editing_tax_class=payload)
            if nfse_form is None:
                nfse_form = self._build_nfse_form(data=None, editing_tax_class=None)
        else:
            if nfse_form is None:
                nfse_form = self._build_nfse_form(data=None, editing_tax_class=payload)
            if nfe_form is None:
                nfe_form = self._build_nfe_form(data=None, editing_tax_class=None)
            if nfe_formsets is None:
                nfe_formsets = self._build_nfe_formsets(data=None, editing_tax_class=None)

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

        return {
            "active_tab": active_tab,
            "is_update": self.is_update,
            "meta_form": meta_form,
            "preset": preset,
            "nfe_form": nfe_form,
            "nfse_form": nfse_form,
            "nfe_formset_sections": nfe_formset_sections,
        }

    def _validate_meta_form_name(self, *, meta_form: TaxClassPresetMetaForm, active_tab: str, preset: TaxClassPreset | None) -> bool:
        if not meta_form.is_valid():
            return False

        name = str(meta_form.cleaned_data.get("name") or "").strip()
        queryset = TaxClassPreset.objects.filter(workshop=self.workshop, kind=self._preset_kind_from_tab(active_tab), name__iexact=name)
        if preset is not None:
            queryset = queryset.exclude(pk=preset.pk)

        if queryset.exists():
            meta_form.add_error("name", "Ja existe um preset com este nome para este tipo de nota nesta oficina.")
            return False

        return True

    def _save_preset(self, *, meta_form: TaxClassPresetMetaForm, active_tab: str, payload: dict[str, object]) -> TaxClassPreset:
        preset = meta_form.save(commit=False)
        preset.workshop = self.workshop
        preset.kind = self._preset_kind_from_tab(active_tab)
        preset.payload = normalize_tax_class_preset_payload(payload=payload, kind=active_tab)
        preset.save()
        return preset

    def get(self, request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        preset = self._resolve_preset()
        if self.is_update and preset is None:
            messages.error(request, "Preset fiscal nao encontrado para edicao.")
            return redirect(f"{reverse('finance:tax_class_preset_list')}?tab={self._normalize_tab(request.GET.get('tab'))}")

        active_tab = self._normalize_tab(request.GET.get("tab") or getattr(preset, "kind", self.TAB_NFE))
        if preset is not None:
            active_tab = self._normalize_tab(preset.kind)

        return self.render_to_response(self._build_preset_form_context(active_tab=active_tab, preset=preset))

    def post(self, request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        preset = self._resolve_preset()
        active_tab = self._normalize_tab(request.POST.get("tab") or getattr(preset, "kind", self.TAB_NFE))
        if self.is_update and preset is None:
            messages.error(request, "Preset fiscal nao encontrado para edicao.")
            return redirect(f"{reverse('finance:tax_class_preset_list')}?tab={active_tab}")

        if preset is not None:
            active_tab = self._normalize_tab(preset.kind)

        meta_form = self._build_preset_meta_form(data=request.POST, preset=preset)
        editing_payload = self._payload_from_preset(preset)

        if active_tab == self.TAB_NFE:
            nfe_form = self._build_nfe_form(data=request.POST, editing_tax_class=editing_payload)
            nfe_formsets = self._build_nfe_formsets(data=request.POST, editing_tax_class=editing_payload)

            if self._validate_meta_form_name(meta_form=meta_form, active_tab=active_tab, preset=preset) and nfe_form.is_valid() and self._formsets_are_valid(nfe_formsets):
                saved_preset = self._save_preset(meta_form=meta_form, active_tab=active_tab, payload=self._build_nfe_payload(form=nfe_form, formsets=nfe_formsets))
                action_label = "atualizado" if preset is not None else "criado"
                messages.success(request, f"Preset fiscal {saved_preset.name} {action_label} com sucesso.")
                return redirect(f"{reverse('finance:tax_class_preset_list')}?tab={active_tab}")

            return self.render_to_response(self._build_preset_form_context(active_tab=active_tab, preset=preset, meta_form=meta_form, nfe_form=nfe_form, nfe_formsets=nfe_formsets))

        nfse_form = self._build_nfse_form(data=request.POST, editing_tax_class=editing_payload)
        if self._validate_meta_form_name(meta_form=meta_form, active_tab=active_tab, preset=preset) and nfse_form.is_valid():
            saved_preset = self._save_preset(meta_form=meta_form, active_tab=active_tab, payload=nfse_form.build_payload())
            action_label = "atualizado" if preset is not None else "criado"
            messages.success(request, f"Preset fiscal {saved_preset.name} {action_label} com sucesso.")
            return redirect(f"{reverse('finance:tax_class_preset_list')}?tab={active_tab}")

        return self.render_to_response(self._build_preset_form_context(active_tab=active_tab, preset=preset, meta_form=meta_form, nfse_form=nfse_form))


class TaxClassPresetCreateView(TaxClassPresetFormBaseView):
    is_update = False


class TaxClassPresetUpdateView(TaxClassPresetFormBaseView):
    is_update = True
