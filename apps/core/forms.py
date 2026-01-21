from django.urls import reverse
from crispy_forms.layout import Div, Field, HTML
from apps.core.widgets import CEPInput, TextInput, SelectInput


class AddressFormMixin:
    """Mixin para centralizar widgets e lógica de readonly do endereço."""

    def setup_address_fields(self):
        # Configura os widgets de endereço
        address_widgets = {
            "cep": CEPInput(),
            "logradouro": TextInput(),
            "numero": TextInput(),
            "complemento": TextInput(),
            "bairro": TextInput(),
            "cidade": TextInput(),
            "estado": SelectInput(),
        }

        for field_name, widget in address_widgets.items():
            if field_name in self.fields:
                self.fields[field_name].widget = widget
                if field_name == "estado":
                    self.fields[field_name].widget = SelectInput(
                        choices=self.fields[field_name].choices,
                        attrs={"class": "form-control"},
                    )

        # Bloqueio dos campos antes do usuário preencher o campo CEP
        for field in ["logradouro", "bairro", "cidade"]:
            if field in self.fields:
                self.fields[field].widget.attrs.update({"readonly": True, "style": "cursor: not-allowed;", "title": "Preencha o campo de CEP"})


def address_layout() -> Div:
    return Div(
        HTML("""
            <div class="col-span-12" style="display: flex; align-items: center; gap: 25px;">
                <h3 class="text-xl font-bold">Endereço</h3>
                <h5 id="cep-loader" class="htmx-indicator" style="margin:0;">
                    <span class="text-lg font-semibold">(Buscando endereço...)</span>
                </h5>
            </div>
        """),
        Field("cep", wrapper_class="col-span-12 lg:col-span-4", hx_get=reverse("core:cep_lookup"), hx_trigger="blur", hx_target="this", hx_swap="none", hx_include="[name='cep']", hx_indicator="#cep-loader"),
        Field("logradouro", wrapper_class="col-span-12 lg:col-span-4"),
        Field("numero", wrapper_class="col-span-12 lg:col-span-4"),
        #
        Field("complemento", wrapper_class="col-span-12 lg:col-span-4"),
        Field("bairro", wrapper_class="col-span-12 lg:col-span-4"),
        Field("cidade", wrapper_class="col-span-12 lg:col-span-4"),
        #
        Field("estado", wrapper_class="col-span-12 lg:col-span-4"),
        css_class="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start col-span-12",
    )