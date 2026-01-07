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
        label="Permissões",
        queryset=Permission.objects.select_related("content_type").order_by("content_type__app_label", "codename"),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = WorkshopRole
        fields = ("name", "permissions")
        widgets = {
            "name": TextInput(attrs={"placeholder": "Ex: Mecânico"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        cancel_url = reverse("iam:role_list")

        self.helper = FormHelper()
        self.helper.form_method = "post"
        self.helper.layout = Layout(
            Div(
                Field("name", wrapper_class="w-full"),
                css_class="grid grid-cols-1 gap-4",
            ),
            HTML('<div class="divider"></div>'),
            Div(
                Field("permissions", wrapper_class="w-full"),
                css_class="grid grid-cols-1 gap-2",
            ),
            HTML('<div class="divider"></div>'),
            Div(
                HTML(f'<a href="{cancel_url}" class="btn-form-cancel">Cancelar</a>'),
                Submit("submit", "Salvar", css_class="btn-form-save"),
                css_class="flex items-center justify-end gap-2",
            ),
        )
