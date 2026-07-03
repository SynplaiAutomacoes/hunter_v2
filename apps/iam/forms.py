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
from apps.iam.permissions_registry import get_perm_info, is_auto_grant

RESERVED_ROLE_NAMES = {"diretor", "gerente"}


class WorkshopRoleForm(CoreModelForm):
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

    def clean_name(self) -> str:
        name = self.cleaned_data.get("name", "")
        normalized_name = str(name).strip().lower()
        current_name = str(getattr(self.instance, "name", "")).strip().lower()

        if normalized_name in RESERVED_ROLE_NAMES and normalized_name != current_name:
            raise forms.ValidationError("Este nome de cargo é reservado pelo sistema e não pode ser usado.")
        return name

    def save(self, commit: bool = True):
        instance = super().save(commit)
        if commit:
            auto_grant_ids = [
                p.id
                for p in Permission.objects.select_related("content_type").only(
                    "id", "content_type__app_label", "content_type__model"
                )
                if is_auto_grant(p.content_type.app_label, p.content_type.model)
            ]
            instance.permissions.add(*auto_grant_ids)
        return instance

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        perms = Permission.objects.select_related("content_type").order_by("content_type__app_label", "content_type__model", "codename")

        grouped = {}
        seen_classes = set()
        last_ct_id = None
        skip_ct = False
        perm_info = None

        for p in perms:
            if p.content_type_id != last_ct_id:
                last_ct_id = p.content_type_id
                perm_info = get_perm_info(p.content_type.app_label, p.content_type.model)
                if not perm_info.visible:
                    skip_ct = True
                    continue
                model_class = p.content_type.model_class()
                if model_class is not None:
                    ct_key = (p.content_type.app_label, model_class)
                else:
                    ct_key = (p.content_type.app_label, p.content_type.model.lower())
                if ct_key in seen_classes:
                    skip_ct = True
                    continue
                seen_classes.add(ct_key)
                skip_ct = False

            if skip_ct or perm_info is None:
                continue

            app_label = p.content_type.app_label

            try:
                app_name = apps.get_app_config(app_label).verbose_name
            except LookupError:
                app_name = app_label.capitalize()

            model_class = p.content_type.model_class()
            if model_class:
                model_name = model_class._meta.verbose_name.capitalize()
            else:
                model_name = p.content_type.model.capitalize()

            if app_name not in grouped:
                grouped[app_name] = {"models": {}, "total_count": 0}
            if model_name not in grouped[app_name]["models"]:
                grouped[app_name]["models"][model_name] = {
                    "perms": [],
                    "description": perm_info.description,
                    "total_count": 0,
                }

            grouped[app_name]["models"][model_name]["perms"].append(p)
            grouped[app_name]["models"][model_name]["total_count"] += 1
            grouped[app_name]["total_count"] += 1

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
