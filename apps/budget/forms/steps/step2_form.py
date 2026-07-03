# ruff: noqa: F403,F405
from .base import BudgetStepBaseForm
from .common import *


class BudgetStep2Form(BudgetStepBaseForm):
    class Meta:
        model = Budget
        fields = ["problem_description", "notes"]
        widgets = {
            "problem_description": TextareaInput(
                attrs={
                    "rows": 4,
                    "cols": 40,
                    "class": "bg-base-200",
                    "style": "background-color: var(--color-base-200); resize: none; height: 40vh; min-height: 40vh; max-height: 40vh; overflow-y: auto;",
                }
            ),
            "notes": TextareaInput(
                attrs={
                    "rows": 4,
                    "cols": 40,
                    "class": "bg-base-200",
                    "style": "background-color: var(--color-base-200); resize: none;",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.investigative_questions = InvestigativeQuestion.objects.filter(workshop=self.workshop, is_active=True).order_by("order")

        responses_by_question_id: dict[int, str] = {}
        if self.instance.pk:
            responses_by_question_id = {response.question_id: response.response for response in InvestigativeResponse.objects.filter(budget=self.instance).only("question_id", "response")}

        self.question_field_names = []
        for q in self.investigative_questions:
            field_name = f"question_{q.id}"
            self.question_field_names.append(field_name)
            # Valor inicial (se estiver editando)
            initial_value = responses_by_question_id.get(q.id, "")
            # Definir o tipo de campo
            if q.response_type == InvestigativeQuestion.ResponseType.BOOLEAN:
                choices = [("", "Selecione..."), ("Sim", "Sim"), ("Não", "Não")]
                self.fields[field_name] = forms.ChoiceField(label=q.text, choices=choices, required=False, initial=initial_value, widget=SearchableSelectInput(choices=choices))
            elif q.response_type == InvestigativeQuestion.ResponseType.SCALE:
                display_id = f"display_{field_name}"
                self.fields[field_name] = forms.IntegerField(
                    label=q.text,
                    min_value=1,
                    max_value=10,
                    required=False,
                    initial=initial_value or 5,
                    widget=forms.NumberInput(attrs={"class": "range range-primary w-full", "type": "range", "step": "1", "min": "1", "max": "10", "oninput": f"document.getElementById('{display_id}').innerText = this.value"}),
                )
                self.fields[field_name].help_text = f'Valor selecionado: <span id="{display_id}" class="font-bold text-xs">{initial_value or 5}</span>'
            elif q.response_type == InvestigativeQuestion.ResponseType.MULTIPLE_CHOICE:
                choices = [(opt, opt) for opt in q.options]
                choices1 = [("", "Selecione...")] + choices
                self.fields[field_name] = forms.ChoiceField(label=q.text, choices=choices1, required=False, initial=initial_value, widget=SearchableSelectInput(choices=choices1))
            else:  # FREE_TEXT
                self.fields[field_name] = forms.CharField(label=q.text, required=False, initial=initial_value, widget=TextInput())

        # 3. Configurar Layout dinâmico do Crispy
        question_layout_fields = [Field(name, wrapper_class="mb-4") for name in self.question_field_names]

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                HTML('<h3 class="text-2xl font-bold col-span-12">Relato do Cliente</h3>'),
                # Descrição do Problema
                Div(Field("problem_description", wrapper_class="flex flex-col h-full", css_class="flex-1"), css_class="col-span-12 lg:col-span-6 flex flex-col"),
                # Perguntas Investigativas
                Div(
                    HTML('<h5 class="font-bold mb-2">Perguntas Investigativas</h5>'),
                    Div(*question_layout_fields, css_class="border bg-base-200 px-4 py-2 rounded-lg pr-4 overflow-y-auto scrollbar-thin scrollbar-thumb-gray-400", style="border-color: var(--color-input-ring); height: 40vh; min-height: 40vh; max-height: 40vh;"),
                    css_class="col-span-12 lg:col-span-6",
                ),
                # Observações
                Div(Field("notes", wrapper_class="w-full", css_class="bg-base-200"), css_class="col-span-12"),
                css_class="budget-step2-client-report grid grid-cols-12 gap-6",
            ),
        )

    def save(self, commit=True):
        budget = super().save(commit=commit)

        # Salvar as respostas vinculadas
        for field_name in self.question_field_names:
            question_id = field_name.split("_")[1]
            response_text = self.cleaned_data.get(field_name)

            if response_text:
                InvestigativeResponse.objects.update_or_create(budget=budget, question_id=question_id, defaults={"workshop": self.workshop, "response": str(response_text)})
        return budget

    def clean_problem_description(self):
        value = self.cleaned_data.get("problem_description")
        return sentence_case(value) if value else value

    def clean_notes(self):
        value = self.cleaned_data.get("notes")
        return sentence_case(value) if value else value
