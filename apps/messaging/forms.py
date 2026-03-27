from __future__ import annotations

from typing import Any

from crispy_forms.helper import FormHelper  # type: ignore[import-untyped]
from crispy_forms.layout import Div, Field, HTML, Layout, Submit  # type: ignore[import-untyped]
from django import forms
from django.urls import reverse

from apps.core.widgets import CheckboxInput, TextInput, TextareaInput
from apps.messaging.models import MessageTemplate
from apps.workshops.models.workshops import Workshop


MESSAGE_PLACEHOLDER = "Ex: Olá %%nome%%, vimos que seu veículo %%modelo%% (%%placa%%) está próximo da revisão. Seu orçamento %%orcamento_numero%% está com status %%orcamento_status%%."


class MessageTemplateForm(forms.ModelForm):
    class Meta:
        model = MessageTemplate
        fields = ["name", "message", "is_active"]
        widgets = {
            "name": TextInput(attrs={"placeholder": "Ex: Revisão preventiva, Pós-serviço, Cobrança amigável"}),
            "message": TextareaInput(rows=12, attrs={"placeholder": MESSAGE_PLACEHOLDER}),
            "is_active": CheckboxInput(),
        }

    def __init__(self, *args: Any, workshop: Workshop | None = None, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.workshop = workshop

        self.helper = FormHelper()
        self.helper.form_method = "post"
        self.helper.layout = Layout(
            Div(
                Field("name", wrapper_class="col-span-12"),
                Field("message", wrapper_class="col-span-12"),
                Field("is_active", wrapper_class="col-span-12"),
                css_class="grid grid-cols-12 gap-4",
            ),
            HTML('<div class="divider"></div>'),
            Div(
                HTML(f'<a href="{reverse("messaging:message_template_list")}" class="btn-form-cancel">Cancelar</a>'),
                Submit("submit", "Salvar", css_class="btn-form-save"),
                css_class="flex items-center justify-end gap-2",
            ),
        )

    def clean_name(self) -> str:
        name = str(self.cleaned_data.get("name") or "").strip()
        if not name:
            return name

        if self.workshop is None:
            return name

        queryset = MessageTemplate.objects.filter(workshop=self.workshop, name__iexact=name)
        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)

        if queryset.exists():
            raise forms.ValidationError("Já existe uma mensagem com este nome nesta oficina.")

        return name
