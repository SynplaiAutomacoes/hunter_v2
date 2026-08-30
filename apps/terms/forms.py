from __future__ import annotations

import json
from typing import Any

from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Div, Field, Layout
from django import forms

from apps.core.presentation.forms import CoreModelForm
from apps.core.presentation.widgets import TextareaInput, TextInput
from apps.terms.defaults import default_vehicle_receipt_content, default_warranty_content
from apps.terms.models import TermTemplateType, WorkshopTermTemplate
from apps.terms.services.color_contrast import resolve_term_colors, validate_term_colors


class WorkshopTermTemplateForm(CoreModelForm):
    content_json = forms.CharField(
        label="Conteúdo do termo",
        required=False,
        widget=forms.HiddenInput(),
    )

    class Meta:
        model = WorkshopTermTemplate
        fields = [
            "template_type",
            "name",
            "document_title",
            "subtitle",
            "intro_text",
            "primary_color",
            "accent_color",
            "text_color",
            "muted_color",
            "is_active",
            "content_json",
        ]
        widgets = {
            "name": TextInput(),
            "document_title": TextInput(),
            "subtitle": TextInput(),
            "intro_text": TextareaInput(attrs={"rows": 3}),
            "primary_color": forms.TextInput(attrs={"type": "color", "class": "h-10 w-16 p-1"}),
            "accent_color": forms.TextInput(attrs={"type": "color", "class": "h-10 w-16 p-1"}),
            "text_color": forms.TextInput(attrs={"type": "color", "class": "h-10 w-16 p-1"}),
            "muted_color": forms.TextInput(attrs={"type": "color", "class": "h-10 w-16 p-1"}),
            "template_type": forms.Select(attrs={"class": "select select-bordered w-full"}),
            "is_active": forms.CheckboxInput(attrs={"class": "toggle toggle-primary"}),
        }

    def __init__(self, *args, **kwargs):
        self.workshop = kwargs.pop("workshop", None)
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.content:
            self.fields["content_json"].initial = json.dumps(self.instance.content, ensure_ascii=False)
        elif not self.is_bound:
            default_content = (
                default_warranty_content()
                if self.initial.get("template_type") == TermTemplateType.WARRANTY
                else default_vehicle_receipt_content()
            )
            self.fields["content_json"].initial = json.dumps(default_content, ensure_ascii=False)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                Field("template_type", wrapper_class="col-span-12 md:col-span-4"),
                Field("name", wrapper_class="col-span-12 md:col-span-8"),
                Field("document_title", wrapper_class="col-span-12"),
                Field("subtitle", wrapper_class="col-span-12"),
                Field("intro_text", wrapper_class="col-span-12"),
                css_class="grid grid-cols-12 gap-4",
            ),
            Div(
                Field("primary_color", wrapper_class="col-span-6 md:col-span-3"),
                Field("accent_color", wrapper_class="col-span-6 md:col-span-3"),
                Field("text_color", wrapper_class="col-span-6 md:col-span-3"),
                Field("muted_color", wrapper_class="col-span-6 md:col-span-3"),
                css_class="grid grid-cols-12 gap-4 mt-4",
            ),
            Div(
                Field("is_active", wrapper_class="col-span-12"),
                css_class="grid grid-cols-12 gap-4 mt-4",
            ),
            Field("content_json"),
            HTML('<div id="term-content-editor" class="mt-6"></div>'),
        )

    def clean_content_json(self) -> dict[str, Any]:
        raw = self.cleaned_data.get("content_json") or "{}"
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise forms.ValidationError("Conteúdo do termo inválido.") from exc
        if not isinstance(parsed, dict):
            raise forms.ValidationError("Conteúdo do termo deve ser um objeto JSON.")
        sections = parsed.get("sections")
        if not isinstance(sections, list) or not sections:
            raise forms.ValidationError("Adicione pelo menos uma página ao termo.")
        return parsed

    def clean(self):
        cleaned_data = super().clean()
        colors = resolve_term_colors(
            primary=str(cleaned_data.get("primary_color") or "#000000"),
            accent=str(cleaned_data.get("accent_color") or "#E30613"),
            text=str(cleaned_data.get("text_color") or "#111827"),
            muted=str(cleaned_data.get("muted_color") or "#6B7280"),
        )
        for error in validate_term_colors(colors):
            raise forms.ValidationError(error)
        return cleaned_data

    def save(self, commit: bool = True):
        instance = super().save(commit=False)
        instance.content = self.cleaned_data["content_json"]
        if self.workshop is not None:
            instance.workshop = self.workshop
        if commit:
            instance.save()
        return instance
