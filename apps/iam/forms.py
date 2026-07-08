from __future__ import annotations

from django import forms
from django.apps import apps
from django.contrib.auth.models import Permission
from django.urls import reverse

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Field, HTML, Layout, Submit

from apps.core.presentation.widgets import TextInput
from apps.iam.models import WorkshopRole
from apps.core.presentation.forms import CoreModelForm

RESERVED_ROLE_NAMES = {"diretor", "gerente"}


def _iter_live_permissions():
    for permission in Permission.objects.select_related("content_type").order_by("content_type__app_label", "content_type__model", "codename"):
        if permission.content_type.model_class() is None:
            continue
        yield permission


class WorkshopRoleForm(CoreModelForm):
    permissions = forms.ModelMultipleChoiceField(
        queryset=Permission.objects.none(),
        required=False,
    )

    class Meta:
        model = WorkshopRole
        fields = ("name", "permissions")
        widgets = {
            "name": TextInput(attrs={"placeholder": "Ex: Mecânico"}),
        }

    def clean_name(self) -> str:
        name = self.cleaned_data.get("name", "")
        normalized_name = str(name).strip().lower()
        current_name = str(getattr(self.instance, "name", "")).strip().lower()

        if normalized_name in RESERVED_ROLE_NAMES and normalized_name != current_name:
            raise forms.ValidationError("Este nome de cargo é reservado pelo sistema e não pode ser usado.")
        return name

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        perms = list(_iter_live_permissions())
        self.fields["permissions"].queryset = Permission.objects.filter(pk__in=[permission.pk for permission in perms]).select_related("content_type")

        grouped = {}
        for p in perms:
            app_label = p.content_type.app_label

            try:
                # Tenta pegar o verbose_name definido no apps.py
                app_name = apps.get_app_config(app_label).verbose_name
            except LookupError:
                app_name = app_label.capitalize()

            # Pega o nome amigável do Modelo
            model_class = p.content_type.model_class()
            model_name = model_class._meta.verbose_name.capitalize()

            if app_name not in grouped:
                grouped[app_name] = {}
            if model_name not in grouped[app_name]:
                grouped[app_name][model_name] = []

            grouped[app_name][model_name].append(p)

        self.grouped_permissions = grouped

        cancel_url = reverse("iam:role_list")

        self.helper = FormHelper()

        self.helper.layout = Layout(
            Div(Field("name", wrapper_class="w-full"), css_class="mb-6"),
            HTML('{% include "iam/partials/permissions_grid.html" %}'),
            Div(
                HTML(f'<a href="{cancel_url}" class="btn-form-cancel">Cancelar</a>'),
                Submit("submit", "Salvar", css_class="btn-form-save"),
                css_class="flex items-center justify-end gap-2 mt-8",
            ),
        )
