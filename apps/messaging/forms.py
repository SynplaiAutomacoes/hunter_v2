from __future__ import annotations

from typing import Any

from django import forms

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
