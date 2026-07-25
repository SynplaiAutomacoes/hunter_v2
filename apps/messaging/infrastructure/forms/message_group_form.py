from __future__ import annotations

import json
from typing import Any, cast

from django import forms
from django.db import transaction
from django.db.models import Q

from apps.core.presentation.forms import CoreModelForm
from apps.core.presentation.widgets import CheckboxInput, TextInput, TextareaInput
from apps.core.text_normalization import sentence_case
from apps.messaging.application.services.typed_templates import deactivate_other_active_typed_templates
from apps.messaging.domain.value_objects import FilterCriteria
from apps.messaging.models import CustomerMessageGroup, MessageTemplate
from apps.workshops.models.workshops import Workshop


MESSAGE_PLACEHOLDER = "Ex: Olá %%nome%%, vimos que seu veículo %%modelo%% (%%placa%%) está próximo da revisão. Seu orçamento %%orcamento_numero%% está com status %%orcamento_status%%."


class MessageTemplateForm(CoreModelForm):
    class Meta:
        model = MessageTemplate
        fields = ["name", "template_type", "message", "is_active"]
        widgets = {
            "name": TextInput(attrs={"placeholder": "Ex: Revisão preventiva, Pós-serviço, Cobrança amigável"}),
            "template_type": forms.Select(attrs={"class": "select select-bordered w-full"}),
            "message": TextareaInput(rows=12, attrs={"placeholder": MESSAGE_PLACEHOLDER}),
            "is_active": CheckboxInput(),
        }

    def __init__(self, *args: Any, workshop: Workshop | None = None, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.workshop = workshop
        template_type_field = cast(forms.ChoiceField, self.fields["template_type"])
        template_type_field.choices = MessageTemplate.TemplateType.choices

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

    def clean_message(self) -> str:
        message = str(self.cleaned_data.get("message") or "").strip()
        if not message:
            raise forms.ValidationError("Informe o texto da mensagem.")
        return message

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean()
        if not isinstance(cleaned, dict):
            return cleaned

        template_type = str(cleaned.get("template_type") or MessageTemplate.TemplateType.GENERIC)
        is_active = bool(cleaned.get("is_active"))
        if self.workshop is not None and is_active and template_type in MessageTemplate.SPECIAL_TYPES:
            existing = MessageTemplate.objects.filter(
                workshop=self.workshop,
                template_type=template_type,
                is_active=True,
            )
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                cleaned["_deactivate_previous_typed"] = True

        return cleaned

    def save(self, commit: bool = True) -> MessageTemplate:
        instance = cast(MessageTemplate, super().save(commit=False))
        if self.workshop is not None and getattr(instance, "workshop_id", None) is None:
            instance.workshop = self.workshop

        if not commit:
            return instance

        with transaction.atomic():
            if bool(self.cleaned_data.get("_deactivate_previous_typed")) and instance.is_active:
                deactivate_other_active_typed_templates(
                    workshop_id=instance.workshop_id,
                    template_type=instance.template_type,
                    keep_pk=instance.pk,
                )
            instance.save()
            self.save_m2m()
        return instance


class QuickMessageTemplateForm(MessageTemplateForm):
    def __init__(self, *args: Any, workshop: Workshop | None = None, **kwargs: Any):
        super().__init__(*args, workshop=workshop, **kwargs)
        self.fields["template_type"].initial = MessageTemplate.TemplateType.GENERIC
        self.fields["template_type"].widget = forms.HiddenInput()

    def clean_template_type(self) -> str:
        return MessageTemplate.TemplateType.GENERIC


class CustomerMessageGroupForm(CoreModelForm):
    class Meta:
        model = CustomerMessageGroup
        fields = ["name", "description", "message_template", "message", "is_active", "filter_criteria"]
        widgets = {
            "name": TextInput(attrs={"placeholder": "Ex: Promoções, Aniversariantes, Revisão preventiva"}),
            "description": TextareaInput(rows=4, attrs={"placeholder": "Descreva quando este grupo deve ser usado e quem faz parte dele."}),
            "message_template": forms.Select(attrs={"class": "select select-bordered w-full"}),
            "message": TextareaInput(rows=12, attrs={"placeholder": MESSAGE_PLACEHOLDER}),
            "is_active": CheckboxInput(),
            "filter_criteria": forms.HiddenInput(),
        }

    def __init__(self, *args: Any, workshop: Workshop | None = None, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.workshop = workshop
        message_template_field = cast(forms.ModelChoiceField, self.fields["message_template"])
        message_template_field.required = False
        message_template_field.queryset = MessageTemplate.objects.none()
        message_template_field.widget.attrs.update({"x-ref": "messageTemplateSelect", "@change": "syncTemplateSelection(false)"})
        self.fields["message"].widget.attrs.update({"x-ref": "messageField"})
        self.fields["filter_criteria"].required = False

        if self.workshop is not None:
            current_message_template_id = self.instance.message_template_id if self.instance.pk else None
            template_queryset = MessageTemplate.objects.filter(
                workshop=self.workshop,
                template_type=MessageTemplate.TemplateType.GENERIC,
            )
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

    def clean_filter_criteria(self) -> dict[str, Any] | None:
        value = self.cleaned_data.get("filter_criteria")
        if value in (None, "", {}):
            return None

        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
            try:
                value = json.loads(value)
            except json.JSONDecodeError as exc:
                raise forms.ValidationError("Critérios de segmentação inválidos.") from exc

        if not isinstance(value, dict):
            raise forms.ValidationError("Critérios de segmentação inválidos.")

        rules = value.get("rules") or []
        if not rules:
            return None

        try:
            criteria = FilterCriteria.from_dict(value)
        except ValueError as exc:
            raise forms.ValidationError("Critérios de segmentação inválidos.") from exc

        return criteria.to_dict()
