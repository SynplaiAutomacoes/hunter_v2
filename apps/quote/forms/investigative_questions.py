from __future__ import annotations

import json
from django import forms
from django.urls import reverse

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Field, HTML, Layout, Submit

from apps.core.presentation.widgets import TextInput, SearchableSelectInput, NumberInput, CheckboxInput
from apps.quote.models.investigative_questions import InvestigativeQuestion
from apps.workshops.models.workshops import Workshop
from apps.core.presentation.forms import CoreModelForm


class InvestigativeQuestionForm(CoreModelForm):
    # Campo auxiliar para receber o JSON do Alpine.js como string
    options_json = forms.CharField(required=False, widget=forms.HiddenInput())

    class Meta:
        model = InvestigativeQuestion
        fields = ["text", "response_type", "order", "is_active"]
        widgets = {
            "text": TextInput(attrs={"placeholder": "Ex: Qual o principal uso do veículo?"}),
            "response_type": SearchableSelectInput(),
            "order": NumberInput(),
            "is_active": CheckboxInput(),
        }

    def __init__(self, *args, workshop: Workshop | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.workshop = workshop

        if self.instance.pk and self.instance.options:
            self.fields["options_json"].initial = json.dumps(self.instance.options)
        else:
            self.fields["options_json"].initial = "[]"

        self.helper = FormHelper()
        self.helper.form_method = "post"
        self.helper.layout = self.get_layout()

    def get_layout(self):
        cancel_url = reverse("quote:investigative_question_list")

        init_type = self.instance.response_type if self.instance.pk else "TEXT"

        init_options = self.fields["options_json"].initial
        if self.is_bound:
            init_options = self.data.get("options_json", "[]")

        return Layout(
            Div(
                Div(
                    Field("text", wrapper_class="col-span-12 lg:col-span-11"),
                    Field("response_type", wrapper_class="col-span-12 lg:col-span-5", **{"x-model": "qType"}),
                    Field("order", wrapper_class="col-span-12 lg:col-span-5"),
                    Field("is_active", wrapper_class="col-span-12 lg:col-span-1"),
                    # --- Área Dinâmica de Opções (Alpine) ---
                    Div(
                        HTML('<label class="label"><span class="label-text font-bold mb-2">Opções de Resposta</span></label>'),
                        HTML("""
                        <div class="flex gap-2 mb-2">
                            <input type="text" class="input-theme w-full" 
                                   placeholder="Digite uma opção e pressione Enter ou +..." 
                                   x-model="newOption" 
                                   @keydown.enter.prevent="addOption()">
                            <button type="button" class="btn btn-primary px-3" @click="addOption()">
                                <span class="material-icons text-base">add</span>
                            </button>
                        </div>
                        """),
                        HTML("""
                        <ul class="flex flex-col gap-2">
                            <template x-for="(opt, index) in options" :key="index">
                                <li class="flex gap-2 items-center">
                                    <div class="p-2 rounded-md w-full flex items-center bg-base-200 text-base-content cursor-default">
                                        <span x-text="opt"></span>
                                    </div>

                                    <button type="button" class="btn-table-delete" @click="removeOption(index)" title="Remover">
                                        <span class="material-icons text-base">delete</span>
                                    </button>
                                </li>
                            </template>
                            <li x-show="options.length === 0" class="text-sm text-gray-500 italic">
                                Nenhuma opção adicionada.
                            </li>
                        </ul>
                        """),
                        Field("options_json", **{"x-ref": "optionsInput"}),
                        css_class="col-span-12 p-4 bg-base-300 rounded-box",
                        **{"x-show": "qType === 'CHOICE'", "x-cloak": True},
                    ),
                    css_class="grid grid-cols-1 lg:grid-cols-11 gap-4 items-start",
                ),
                x_data=f"""{{
                    qType: '{init_type}',
                    options: {init_options},
                    newOption: '',
                    errorMessage: '',

                    addOption() {{
                        const val = this.newOption.trim();
                        if (val !== '') {{
                            // Verificação de Duplicidade (Case Insensitive)
                            const exists = this.options.some(opt => opt.toLowerCase() === val.toLowerCase());

                            if (exists) {{
                                this.errorMessage = 'Esta opção já foi adicionada.';
                                // Limpa a mensagem após 3 segundos
                                setTimeout(() => this.errorMessage = '', 3000);
                                return;
                            }}

                            this.options.push(val);
                            this.newOption = '';
                            this.errorMessage = ''; // Limpa erro se houver
                            this.syncOptions();
                        }}
                    }},

                    removeOption(index) {{
                        this.options.splice(index, 1);
                        this.syncOptions();
                    }},

                    syncOptions() {{
                        $refs.optionsInput.value = JSON.stringify(this.options);
                    }}
                }}""",
            ),
            HTML('<div class="divider"></div>'),
            Div(
                HTML(f'<a href="{cancel_url}" class="btn-form-cancel">Cancelar</a>'),
                Submit("submit", "Salvar", css_class="btn-form-save", **{"@click": "syncOptions()"}),
                css_class="flex items-center justify-end gap-2",
            ),
        )

    def clean(self):
        cleaned_data = super().clean()
        rtype = cleaned_data.get("response_type")
        options_json = cleaned_data.get("options_json")

        options_list = []
        if options_json:
            try:
                options_list = json.loads(options_json)
            except json.JSONDecodeError:
                options_list = []

        if rtype == InvestigativeQuestion.ResponseType.MULTIPLE_CHOICE:
            if not options_list:
                self.add_error("response_type", "Para múltipla escolha, adicione pelo menos uma opção.")
            else:
                normalized_options = [opt.lower().strip() for opt in options_list]
                if len(normalized_options) != len(set(normalized_options)):
                    self.add_error("response_type", "Existem opções duplicadas na lista de múltipla escolha.")
        else:
            options_list = []

        cleaned_data["options"] = options_list
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.workshop = self.workshop
        instance.options = self.cleaned_data.get("options", [])

        if commit:
            instance.save()
        return instance
