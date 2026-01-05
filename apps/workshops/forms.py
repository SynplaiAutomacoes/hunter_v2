from crispy_forms.layout import Submit, Layout, Div, HTML, Field
from django.forms import ModelForm

from crispy_forms.helper import FormHelper
from django.urls import reverse

from apps.workshops.models import Workshop
from apps.core.widgets import TextInput, CPForCNPJInput, CheckboxInput


class WorkshopForm(ModelForm):
    class Meta:
        model = Workshop
        fields = ["name", "cnpj", "is_active"]
        widgets = {
            "name": TextInput(attrs={"placeholder": "Oficina Hunter"}),
            "cnpj": CPForCNPJInput(mode="cnpj"),
            "is_active": CheckboxInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        cancel_url = reverse("workshops:list")

        self.helper = FormHelper()
        self.helper.layout = Layout(
            Div(
                Field("name", wrapper_class="w-full"),
                Field("cnpj", wrapper_class="w-full"),
                Field("is_active", wrapper_class="w-fit"),
                css_class="grid grid-cols-1 lg:grid-cols-[1fr_1fr_auto] gap-4 items-start",
            ),
            HTML('<div class="divider"></div>'),
            Div(
                HTML(f'<a href="{cancel_url}" class="btn btn-ghost text-base-content/70">Cancelar</a>'),
                Submit("submit", "Salvar", css_class="btn btn-primary px-8"),
                css_class="flex items-center justify-end gap-2",
            ),
        )
