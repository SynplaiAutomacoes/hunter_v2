from __future__ import annotations

from django import forms
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse

from crispy_forms.layout import Div, Field, HTML

from apps.budget.models import BudgetStatus
from apps.core.presentation.widgets import CEPInput, SearchableSelectInput, TextInput
from apps.core.text_normalization import name_case, plate_case, sentence_case

NAME_FIELD_NAMES = {
    "name", "fantasy_name", "contact_person", "guest_customer_name",
    "razao_social", "nome_completo", "nome_fantasia",
}

PLATE_FIELD_NAMES = {"plate", "guest_vehicle_plate"}

EXCLUDED_FIELD_NAME_PARTS = {
    "email", "cpf", "cnpj", "rg", "url", "link", "token", "secret",
    "password", "key", "uuid", "external_id", "document_id",
    "content_type", "content_name", "file", "filename", "attachment",
    "xml", "pdf", "nf", "nfe", "nfse", "barcode", "ean", "sku", "code",
    "ncm", "cest", "renavam", "chassi", "cep", "phone", "mobile",
    "whatsapp", "serie", "series", "number", "numero", "protocol",
    "receipt", "agency", "agencia", "account", "conta", "bank_digit",
    "digito",
}


class TextNormalizationFormMixin:
    normalization_name_fields = NAME_FIELD_NAMES
    normalization_plate_fields = PLATE_FIELD_NAMES
    normalization_excluded_name_parts = EXCLUDED_FIELD_NAME_PARTS

    def clean(self) -> dict[str, object]:
        cleaned_data = super().clean()
        if not isinstance(cleaned_data, dict):
            return cleaned_data
        return self._normalize_cleaned_data(cleaned_data)

    def _normalize_cleaned_data(self, cleaned_data: dict[str, object]) -> dict[str, object]:
        normalized_data = cleaned_data.copy()
        for field_name, value in cleaned_data.items():
            if not self._should_normalize_field(field_name, value):
                continue
            normalized_data[field_name] = self._normalize_field_value(field_name, value)
        return normalized_data

    def _should_normalize_field(self, field_name: str, value: object) -> bool:
        if not isinstance(value, str):
            return False
        if not value.strip():
            return False
        field = self.fields.get(field_name)
        if field is None:
            return False
        if getattr(field, "choices", None):
            return False
        if isinstance(field, (forms.FileField, forms.ImageField)):
            return False
        lowered_name = field_name.lower()
        if any(part in lowered_name for part in self.normalization_excluded_name_parts):
            return False
        return True

    def _normalize_field_value(self, field_name: str, value: str) -> str:
        lowered_name = field_name.lower()
        if lowered_name in self.normalization_plate_fields:
            return plate_case(value)
        if lowered_name in self.normalization_name_fields:
            return name_case(value)
        return sentence_case(value)


class CoreForm(TextNormalizationFormMixin, forms.Form):
    pass


class CoreModelForm(TextNormalizationFormMixin, forms.ModelForm):
    pass


class AddressFormMixin:
    def setup_address_fields(self):
        address_widgets = {
            "cep": CEPInput(),
            "logradouro": TextInput(),
            "numero": TextInput(),
            "complemento": TextInput(),
            "bairro": TextInput(),
            "cidade": TextInput(),
            "estado": SearchableSelectInput(),
        }
        for field_name, widget in address_widgets.items():
            if field_name in self.fields:
                self.fields[field_name].widget = widget
                if field_name == "estado":
                    self.fields[field_name].widget = SearchableSelectInput(
                        choices=self.fields[field_name].choices,
                        attrs={"class": "form-control"},
                    )
        for field in ["logradouro", "bairro", "cidade"]:
            if field in self.fields:
                self.fields[field].widget.attrs.update({
                    "readonly": True,
                    "style": "cursor: not-allowed;",
                    "title": "Preencha o campo de CEP",
                })


def address_layout(include_complemento: bool = True) -> Div:
    return Div(
        HTML("""
            <div class="col-span-12" style="display: flex; align-items: center; gap: 25px;">
                <h3 class="text-xl font-bold">Endereço</h3>
                <h5 id="cep-loader" class="htmx-indicator" style="margin:0;">
                    <span class="text-lg font-semibold">(Buscando endereço...)</span>
                </h5>
            </div>
        """),
        Field("cep", wrapper_class="col-span-12 lg:col-span-4",
              hx_get=reverse("core:cep_lookup"), hx_trigger="blur",
              hx_target="this", hx_swap="none", hx_include="[name='cep']",
              hx_indicator="#cep-loader"),
        Field("logradouro", wrapper_class="col-span-12 lg:col-span-4"),
        Field("numero", wrapper_class="col-span-12 lg:col-span-4"),
        *([Field("complemento", wrapper_class="col-span-12 lg:col-span-4")] if include_complemento else []),
        Field("bairro", wrapper_class="col-span-12 lg:col-span-4"),
        Field("cidade", wrapper_class="col-span-12 lg:col-span-4"),
        Field("estado", wrapper_class="col-span-12 lg:col-span-4"),
        css_class="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start col-span-12",
    )


class MultiStepFormMixin:
    steps_definition = []
    step_template_name = None

    def get_step_template_name(self):
        return self.step_template_name or "stock/partials/import_step_content.html"

    @property
    def model_instance(self):
        if not hasattr(self, "_model_instance"):
            self._model_instance = self.get_object() if hasattr(self, "get_object") else None
        return self._model_instance

    def get_steps_config(self):
        if hasattr(self, "get_steps_definition"):
            return self.get_steps_definition()
        return self.steps_definition

    def get_current_step(self):
        step_url = self.request.GET.get("step")
        try:
            step = int(step_url) if step_url else None
        except (ValueError, TypeError):
            step = None
        if not step:
            obj = self.model_instance
            if obj and hasattr(obj, "current_step"):
                return obj.current_step
            return 1
        total_steps = len(self.get_steps_config())
        if step > total_steps:
            return total_steps
        return max(1, step)

    def get_form_class(self):
        current_step = self.get_current_step()
        steps = self.get_steps_config()
        if not steps:
            return None
        idx = max(0, min(current_step - 1, len(steps) - 1))
        return steps[idx].get("form_class")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        obj = getattr(self, "object", None) or self.get_object()
        if obj:
            kwargs["instance"] = obj
        elif "instance" in kwargs:
            kwargs.pop("instance")
        if hasattr(self, "workshop"):
            kwargs.update({"workshop": self.workshop})
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        forced_current_step = kwargs.get("current_step")
        current_step = forced_current_step if forced_current_step is not None else self.get_current_step()
        steps = self.get_steps_config()
        context["steps_config"] = [{"number": i + 1, "title": step["title"]} for i, step in enumerate(steps)]
        context["current_step"] = current_step
        context["object"] = self.model_instance
        context["max_reached_step"] = self.model_instance.current_step if self.model_instance else 1
        if steps and current_step <= len(steps):
            step_config = steps[current_step - 1]
            if "formset_class" in step_config:
                obj = getattr(self, "object", self.model_instance)
                context["step_formset"] = step_config["formset_class"](
                    instance=obj,
                    data=self.request.POST if self.request.method == "POST" else None,
                )
        return context

    def render_next_step(self, form):
        current_step = self.get_current_step()
        steps = self.get_steps_config()
        if current_step < len(steps):
            next_step = current_step + 1
        else:
            return redirect(self.get_success_url())
        next_url = f"{self.request.path}?step={next_step}"
        if self.request.htmx:
            self.request.GET = self.request.GET.copy()
            self.request.GET["step"] = str(next_step)
            form_class = self.get_form_class()
            next_form = form_class(**self.get_form_kwargs())
            context = self.get_context_data(form=next_form)
            context["current_step"] = next_step
            return render(self.request, self.get_step_template_name(), context)
        return redirect(next_url)

    def apply_step_status(self, budget=None, current_step=None, actor=None, isUpdate=False, *, save: bool = True):
        """Apply auto status for the current step.

        When ``save=False``, only mutates ``budget.status`` in memory so the
        caller can coalesce with other metadata fields (e.g. ``current_step``).
        """
        steps = self.get_steps_config()
        if budget is None:
            budget = getattr(self, "object", None) or getattr(self, "budget_object", None)
        if budget is None:
            return False
        if current_step is None:
            current_step = self.get_current_step()
        if not (1 <= current_step <= len(steps)):
            return False
        step_config = steps[current_step - 1]
        auto_apply = step_config.get("auto_apply", False)
        desired = step_config.get("status", None)
        if not auto_apply or not desired:
            return False
        if isUpdate and current_step < 4:
            return False
        try:
            new_status = desired.value if hasattr(desired, "value") else str(desired)
        except Exception:
            new_status = str(desired)
        try:
            BudgetStatus(new_status)
        except Exception:
            return False
        terminal = {BudgetStatus.APPROVED, BudgetStatus.REJECTED, BudgetStatus.CANCELLED}
        if budget.status in terminal:
            return False
        if budget.status == new_status:
            return False
        actor = actor or getattr(self, "request", None) and getattr(self.request, "user", None)
        if not save:
            budget.status = new_status
            return True
        with transaction.atomic():
            try:
                locked = budget.__class__.objects.select_for_update().get(pk=budget.pk)
            except Exception:
                locked = budget
            locked.status = new_status
            locked.save(update_fields=["status"])
            budget.status = new_status
        return True
