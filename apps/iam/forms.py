from __future__ import annotations

from django import forms
from django.contrib.auth.models import Permission
from django.urls import reverse

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Field, HTML, Layout, Submit

from apps.core.widgets import TextInput
from apps.iam.models import WorkshopRole


class WorkshopRoleForm(forms.ModelForm):
    permissions = forms.ModelMultipleChoiceField(
        queryset=Permission.objects.select_related("content_type").all(),
        required=False,
    )

    class Meta:
        model = WorkshopRole
        fields = ("name", "permissions")
        widgets = {
            "name": TextInput(attrs={"placeholder": "Ex: Mecânico"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        perms = Permission.objects.select_related("content_type").order_by("content_type__app_label", "content_type__model", "codename")

        grouped = {}
        for p in perms:
            app = p.content_type.app_label.capitalize()
            model = p.content_type.model_class()._meta.verbose_name.capitalize() if p.content_type.model_class() else p.content_type.model.capitalize()

            if app not in grouped:
                grouped[app] = {}
            if model not in grouped[app]:
                grouped[app][model] = []

            grouped[app][model].append(p)

        self.grouped_permissions = grouped

        cancel_url = reverse("iam:role_list")

        self.helper = FormHelper()

        self.helper.layout = Layout(
            Div(Field("name", wrapper_class="w-full"), css_class="mb-6"),
            HTML('<h3 class="text-xl font-bold mb-4 border-b pb-2">Configurações de Acesso</h3>'),
            HTML('{% include "iam/partials/permissions_grid.html" %}'),
            Div(
                HTML(f'<a href="{cancel_url}" class="btn-form-cancel">Cancelar</a>'),
                Submit("submit", "Salvar", css_class="btn-form-save"),
                css_class="flex items-center justify-end gap-2 mt-8",
            ),
        )
