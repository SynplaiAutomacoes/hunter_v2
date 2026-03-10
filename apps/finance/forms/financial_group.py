from __future__ import annotations

from typing import Any, cast

from crispy_forms.helper import FormHelper  # type: ignore[import-untyped]
from crispy_forms.layout import Div, Field, HTML, Layout, Submit  # type: ignore[import-untyped]
from django import forms
from django.urls import reverse

from apps.core.widgets import CheckboxInput, SelectInput, TextInput
from apps.finance.models.financial_group import FinancialGroup
from apps.workshops.models.workshops import Workshop


class FinancialGroupParentChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj: FinancialGroup) -> str:
        return obj.code_label


class FinancialGroupForm(forms.ModelForm):
    parent = FinancialGroupParentChoiceField(
        queryset=FinancialGroup.objects.none(),
        label="Grupo pai",
        required=False,
        widget=SelectInput(),
        help_text="Deixe em branco para criar um grupo raiz.",
    )

    class Meta:
        model = FinancialGroup
        fields = ["parent", "name", "is_active"]
        widgets = {
            "name": TextInput(attrs={"placeholder": "Ex: Contas Fixas, Água/Luz/Telefone..."}),
            "is_active": CheckboxInput(),
        }

    def __init__(self, *args: Any, workshop: Workshop | None = None, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.workshop = workshop
        parent_field = cast(Any, self.fields["parent"])

        parent_queryset = FinancialGroup.objects.none()
        if workshop is not None:
            parent_queryset = FinancialGroup.objects.filter(workshop=workshop).order_by("sort_key", "id")

        if self.instance.pk:
            parent_queryset = parent_queryset.exclude(pk=self.instance.pk)
            if self.instance.sort_key:
                parent_queryset = parent_queryset.exclude(sort_key__startswith=f"{self.instance.sort_key}.")

            parent_field.disabled = True
            parent_field.help_text = "A troca do grupo pai ainda não está disponível para preservar a hierarquia existente."

        parent_field.queryset = parent_queryset

        self.helper = FormHelper()
        self.helper.form_method = "post"
        self.helper.layout = Layout(
            Div(
                Field("parent", wrapper_class="col-span-12 lg:col-span-6"),
                Field("name", wrapper_class="col-span-12 lg:col-span-4"),
                Field("is_active", wrapper_class="col-span-12 lg:col-span-2"),
                css_class="grid grid-cols-12 gap-4",
            ),
            HTML('<div class="divider"></div>'),
            Div(
                HTML(f'<a href="{reverse("finance:financial_groups_list")}" class="btn-form-cancel">Cancelar</a>'),
                Submit("submit", "Salvar", css_class="btn-form-save"),
                css_class="flex items-center justify-end gap-2",
            ),
        )

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        if cleaned_data is None:
            return {}

        parent = cast(FinancialGroup | None, cleaned_data.get("parent"))
        name = str(cleaned_data.get("name") or "").strip()
        workshop_pk = getattr(self.workshop, "pk", None)

        if parent is not None and workshop_pk is not None and getattr(parent, "workshop_id", None) != workshop_pk:
            self.add_error("parent", "O grupo pai precisa pertencer à mesma oficina.")

        if name and self.workshop is not None:
            existing_groups = FinancialGroup.objects.filter(workshop=self.workshop, parent=parent, name__iexact=name)
            if self.instance.pk:
                existing_groups = existing_groups.exclude(pk=self.instance.pk)
            if existing_groups.exists():
                self.add_error("name", "Já existe um grupo ou subgrupo com este nome neste mesmo nível.")

        if self.instance.pk and parent is not None and getattr(self.instance, "parent_id", None) != getattr(parent, "pk", None):
            self.add_error("parent", "Alterar o grupo pai ainda não está disponível.")

        return cleaned_data
