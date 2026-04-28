from __future__ import annotations

from typing import Any, cast

from django import forms
from django.db.models import Q

from apps.core.widgets import CheckboxInput, TextInput, TextareaInput
from apps.core.text_normalization import sentence_case
from apps.messaging.models import CustomerMessageGroup, MessageTemplate
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

        name = sentence_case(name)

        if self.workshop is None:
            return name

        queryset = MessageTemplate.objects.filter(workshop=self.workshop, name__iexact=name)
        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)

        if queryset.exists():
            raise forms.ValidationError("Já existe uma mensagem com este nome nesta oficina.")

        return name


class QuickMessageTemplateForm(MessageTemplateForm):
    pass


class CustomerMessageGroupForm(forms.ModelForm):
    class Meta:
        model = CustomerMessageGroup
        fields = ["name", "description", "message_template", "message", "is_active"]
        widgets = {
            "name": TextInput(attrs={"placeholder": "Ex: Promoções, Aniversariantes, Revisão preventiva"}),
            "description": TextareaInput(rows=4, attrs={"placeholder": "Descreva quando este grupo deve ser usado e quem faz parte dele."}),
            "message_template": forms.Select(attrs={"class": "select select-bordered w-full"}),
            "message": TextareaInput(rows=12, attrs={"placeholder": MESSAGE_PLACEHOLDER}),
            "is_active": CheckboxInput(),
        }

    def __init__(self, *args: Any, workshop: Workshop | None = None, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.workshop = workshop
        message_template_field = cast(forms.ModelChoiceField, self.fields["message_template"])
        message_template_field.required = False
        message_template_field.queryset = MessageTemplate.objects.none()
        message_template_field.widget.attrs.update({"x-ref": "messageTemplateSelect", "@change": "syncTemplateSelection(false)"})
        self.fields["message"].widget.attrs.update({"x-ref": "messageField"})

        if self.workshop is not None:
            current_message_template_id = self.instance.message_template_id if self.instance.pk else None
            template_queryset = MessageTemplate.objects.filter(workshop=self.workshop)
            if current_message_template_id is None:
                template_queryset = template_queryset.filter(is_active=True)
            else:
                template_queryset = template_queryset.filter(Q(is_active=True) | Q(pk=current_message_template_id))
            message_template_field.queryset = template_queryset.order_by("name")

    def clean_name(self) -> str:
        name = str(self.cleaned_data.get("name") or "").strip()
        if not name:
            return name

        name = sentence_case(name)

        if self.workshop is None:
            return name

        queryset = CustomerMessageGroup.objects.filter(workshop=self.workshop, name__iexact=name)
        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)

        if queryset.exists():
            raise forms.ValidationError("Já existe um grupo com este nome nesta oficina.")

        return name

    def clean_message(self) -> str:
        message = str(self.cleaned_data.get("message") or "").strip()
        if not message:
            raise forms.ValidationError("Informe a mensagem que será usada neste grupo.")
        return sentence_case(message)

    def clean_description(self) -> str:
        description = str(self.cleaned_data.get("description") or "").strip()
        return sentence_case(description) if description else description
