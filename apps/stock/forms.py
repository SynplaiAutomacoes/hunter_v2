import re

from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Div, Field, HTML

from apps.core.widgets import TextInput


class ImportStep1Form(forms.Form):
    METHOD_CHOICES = [
        ('SEFAZ', 'SEFAZ'),
        ('XML', 'Arquivo XML'),
        ('KEY', 'Chave de Acesso'),
        ('OS', 'Abrir Ordem de Serviço'),
    ]
    method = forms.ChoiceField(choices=METHOD_CHOICES, label="Selecione o método de Importação de Itens", widget=forms.Select(attrs={'x-model': 'method'}))
    xml_file = forms.FileField(label="Selecione o arquivo XML", required=False)
    access_key = forms.CharField(label="Insira a chave de acesso", max_length=47, required=False, widget=TextInput(attrs={'oninput': "this.value = this.value.replace(/[^0-9]/g, '')"}))

    def __init__(self, *args, **kwargs):
        self.workshop = kwargs.pop("workshop", None)
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = (Layout(
                Div(
                    # Coluna Esquerda: Seleção
                    Div(
                        HTML('<h2 class="text-2xl font-bold mb-6">Método de Importação</h2>'),
                        Field("method", css_class="select select-bordered w-full"),
                        css_class="col-span-12 lg:col-span-5",
                    ),
                    #
                    Div(css_class="hidden lg:block lg:col-span-2"),
                    #
                    # Coluna Direita
                    Div(
                        # Cabeçalhos Dinâmicos
                        HTML('<h2 class="text-2xl font-bold mb-6" x-show="method == \'XML\'">Importação do Arquivo</h2>'),
                        HTML('<h2 class="text-2xl font-bold mb-6" x-show="method == \'KEY\'">Chave de Acesso</h2>'),
                        # Campos Dinâmicos
                        Div(Field("xml_file", css_class="file-input file-input-bordered w-full"), x_show="method == 'XML'"),
                        Div(Field("access_key", css_class="input input-bordered w-full"), x_show="method == 'KEY'"),
                        css_class="col-span-12 lg:col-span-5",
                    ),
                    css_class="grid grid-cols-1 lg:grid-cols-12 gap-4",
                )
            )
        )

    def clean(self):
        cleaned_data = super().clean()
        method = cleaned_data.get("method")

        if method == 'XML' and not self.files.get('xml_file'):
            self.add_error("xml_file", "O arquivo XML é obrigatório para este método.")

        if method == "KEY":
            key = cleaned_data.get("access_key")
            if not key or len(re.sub(r"\D", "", key)) != 44:
                self.add_error("access_key", "Insira uma chave válida de 44 dígitos.")

        return cleaned_data
