from django import forms
from crispy_forms.helper import FormHelper
from django.urls import reverse
from .models import Checklist
from apps.core.widgets import TextInput
from ..workshops.models.workshops import Workshop


class ChecklistForm(forms.ModelForm):
    class Meta:
        model = Checklist
        exclude = ["workshop", "criado_em", "atualizado_em"]
        fields = [
            "name"
        ]
        widgets = {
            "name": TextInput()
        }

    def __init__(self, *args, workshop: Workshop | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.workshop = workshop
        self.helper = FormHelper()
        self.helper.form_method = "post"

        cancel_url = reverse("checklist:checklist_list")