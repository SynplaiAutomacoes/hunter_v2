from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Div, Field, HTML
from django import forms

from apps.budget.models import Budget, Defect
from apps.checklist.models import Checklist
from apps.collaborators.models import WorkshopCollaborator
from apps.core.widgets import TextInput, SelectInput, CalendarDateInput
from apps.customer.models import Vehicle
from apps.quote.models.investigative_questions import InvestigativeQuestion, InvestigativeResponse


class BudgetStep1Form(forms.ModelForm):
    workshop = forms.CharField(label="Empresa", widget=TextInput(attrs={"readonly": "readonly"}), required=False)
    cost_estimator = forms.CharField(label="Orçamentista",widget=TextInput(attrs={"readonly": "readonly"}), required=False)
    vehicle = forms.ModelChoiceField(label="Veículo",  queryset=Vehicle.objects.none(), required=False, widget=SelectInput())
    class Meta:
        model = Budget
        fields = [
            "workshop",
            "cost_estimator",
            "entry_date",
            "customer",
            "vehicle",
            "current_km",
            "fuel_level",
        ]
        widgets = {
            "entry_date": CalendarDateInput(),
            "customer": SelectInput(),
            "current_km": TextInput(),
            "fuel_level": TextInput(),
        }

    def __init__(self, *args, **kwargs):
        self.workshop = kwargs.pop("workshop", None)
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)

        # Preenchimento inicial (Campos não editáveis)
        if self.workshop:
            self.fields["workshop"].initial = self.workshop.name
            self.fields["customer"].queryset = self.fields["customer"].queryset.filter(workshop=self.workshop)

        if self.instance and self.instance.customer:
            self.fields["vehicle"].queryset = self.instance.customer.vehicles.all()
        elif self.data.get("customer"):
            try:
                customer_id = self.data.get("customer")
                self.fields["vehicle"].queryset = Vehicle.objects.filter(customer_id=customer_id)
            except (ValueError, TypeError):
                self.fields["vehicle"].queryset = self.fields["vehicle"].queryset.none()
        else:
            self.fields["vehicle"].queryset = self.fields["vehicle"].queryset.none()

        if self.request and self.request.user:
            user = self.request.user
            self.fields["cost_estimator"].initial = user.get_full_name() or user.username

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            HTML("""
                <script>
                    (function() {
                        const updateResume = (name, value, targetId, urlBase) => {
                            const container = document.getElementById(targetId);
                            
                            fetch(`${urlBase}?${name}=${value}`)
                                .then(response => response.text())
                                .then(html => { container.innerHTML = html; })
                                .catch(err => console.error('Erro ao carregar resumo:', err));
                        };

                        document.addEventListener('change', function(e) {
                            if (e.target.name === 'customer') {
                                updateResume('customer', e.target.value, 'resumo-cliente', '/customer/customer-detail/');
                                
                                const vehicleSelect = document.querySelector('[name="vehicle"]');
                                fetch(`/customer/get-vehicles/?customer_id=${e.target.value}`)
                                .then(response => response.json())
                                .then(data => {
                                    let options = '<option value="">Selecione...</option>';
                                    data.forEach(v => {
                                        options += `<option value="${v.id}">${v.label}</option>`;
                                    });
                                    vehicleSelect.innerHTML = options;
                                });
                            }
                            if (e.target.name === 'vehicle') {
                                updateResume('vehicle', e.target.value, 'resumo-veiculo', '/customer/vehicle-detail/');
                            }
                        });
                        
                        const init = () => {
                            const fields = [
                                { name: 'customer', id: 'resumo-cliente', url: '/customer/customer-detail/' },
                                { name: 'vehicle', id: 'resumo-veiculo', url: '/customer/vehicle-detail/' }
                            ];
            
                            fields.forEach(f => {
                                const el = document.querySelector(`[name="${f.name}"]`);
                                if (el) updateResume(f.name, el.value, f.id, f.url);
                            });
            
                            document.addEventListener('change', (e) => {
                                const field = fields.find(f => f.name === e.target.name);
                                if (field) {
                                    updateResume(field.name, e.target.value, field.id, field.url);
                                }
                            });
                        };
            
                        window.addEventListener('load', init);
                    })();
                </script>
            """),
            Div(
                # Coluna Esquerda
                Div(
                    # Orçamento
                    Div(
                        HTML('<h3 class="text-2xl font-bold mb-2">Orçamento</h3>'),
                        Div(
                            Field("workshop", wrapper_class="col-span-12 lg:col-span-12"),
                            Field("cost_estimator", wrapper_class="col-span-12 lg:col-span-12"),
                            Field("entry_date", wrapper_class="col-span-12 lg:col-span-12"),
                            css_class="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start",
                        ),
                        css_class="mb-6 gap-4",
                    ),
                    # Cliente
                    Div(
                        HTML('<h3 class="text-2xl font-bold mb-2">Cliente</h3>'),
                        Div(
                            Field("customer", wrapper_class="col-span-12 lg:col-span-12"),
                            Field("vehicle", wrapper_class="col-span-12 lg:col-span-12"),
                            css_class="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start",
                        ),
                        css_class="mb-6 gap-4",
                    ),
                    # Veículo
                    Div(
                        HTML('<h3 class="text-2xl font-bold mb-2">Veículo</h3>'),
                        Div(
                            Field("current_km", wrapper_class="col-span-12 lg:col-span-6"),
                            Field("fuel_level", wrapper_class="col-span-12 lg:col-span-6"),
                            css_class="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start",
                        ),
                        css_class="mb-6 gap-4",
                    ),
                    css_class="col-span-12 lg:col-span-5",
                ),
                Div(css_class="col-span-12 lg:col-span-2"),
                # Coluna Direita (Resumo)
                Div(
                    Div(
                        HTML('<h2 class="text-2xl font-bold mb-4 pb-2">Resumo</h2>'),
                        # Cliente
                        HTML('<h4 class="text-lg font-bold mb-2">Cliente</h4>'),
                        Div(id="resumo-cliente", css_class="mb-6 overflow-x-auto"),
                        # Veículo
                        HTML('<h4 class="text-lg font-bold mb-2">Veículo</h4>'),
                        Div(id="resumo-veiculo", css_class="overflow-x-auto"),
                    ),
                    css_class="col-span-12 lg:col-span-5",
                ),
                css_class="grid grid-cols-1 lg:grid-cols-12",
            ),
        )

    def clean(self):
        cleaned_data = super().clean()

        cleaned_data["workshop"] = self.workshop
        cleaned_data["cost_estimator"] = self.request.user

        return cleaned_data


class BudgetStep2Form(forms.ModelForm):
    class Meta:
        model = Budget
        fields = ["problem_description", "notes"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 4, "cols": 40}),
        }

    def __init__(self, *args, **kwargs):
        self.workshop = kwargs.pop("workshop", None)
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)

        self.investigative_questions = InvestigativeQuestion.objects.filter(workshop=self.workshop, is_active=True).order_by("order")

        self.question_field_names = []
        for q in self.investigative_questions:
            field_name = f"question_{q.id}"
            self.question_field_names.append(field_name)
            # Valor inicial (se estiver editando)
            initial_value = ""
            if self.instance.pk:
                resp = InvestigativeResponse.objects.filter(budget=self.instance, question=q).first()
                initial_value = resp.response if resp else ""
            # Definir o tipo de campo
            if q.response_type == InvestigativeQuestion.ResponseType.BOOLEAN:
                choices = [("", "Selecione..."), ("Sim", "Sim"), ("Não", "Não")]
                self.fields[field_name] = forms.ChoiceField(label=q.text, choices=choices, required=False, initial=initial_value, widget=SelectInput(choices=choices))
            elif q.response_type == InvestigativeQuestion.ResponseType.SCALE:
                display_id = f"display_{field_name}"
                self.fields[field_name] = forms.IntegerField(
                    label=q.text,
                    min_value=1,
                    max_value=10,
                    required=False,
                    initial=initial_value or 5,
                    widget=forms.NumberInput(attrs={ "class": "range range-primary w-full", "type": "range", "step": "1", "min": "1", "max": "10", "oninput": f"document.getElementById('{display_id}').innerText = this.value" }
                    ),
                )
                self.fields[field_name].help_text = f'Valor selecionado: <span id="{display_id}" class="font-bold text-primary">{initial_value or 5}</span>'
            elif q.response_type == InvestigativeQuestion.ResponseType.MULTIPLE_CHOICE:
                choices = [(opt, opt) for opt in q.options]
                choices1 = [("", "Selecione...")] + choices
                self.fields[field_name] = forms.ChoiceField(label=q.text, choices=choices1, required=False, initial=initial_value, widget=SelectInput(choices=choices1))
            else:  # FREE_TEXT
                self.fields[field_name] = forms.CharField(label=q.text, required=False, initial=initial_value, widget=forms.TextInput(attrs={"class": "input input-bordered w-full"}))

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
                    Div(*question_layout_fields, css_class="border px-4 py-2 rounded-lg pr-4 overflow-y-auto max-h-[40vh] scrollbar-thin scrollbar-thumb-gray-400"),
                    css_class="col-span-12 lg:col-span-6",
                ),
                # Observações
                Div(Field("notes", wrapper_class="w-full"), css_class="col-span-12"),
                css_class="grid grid-cols-12 gap-6",
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


class BudgetStep3Form(forms.ModelForm):
    new_defect = forms.CharField(label=False, required=False, widget=TextInput(attrs={"id": "id_new_defect", "placeholder": "Digite um defeito e clique em Adicionar", "onkeypress": "if(event.keyCode==13){ event.preventDefault(); addDefectRow(); }"}))
    checklist = forms.ModelChoiceField(label="Selecione o Checklist", queryset=Checklist.objects.none(), required=False, widget=SelectInput())
    collaborator = forms.ModelChoiceField(label="Selecione o colaborador que realizará o serviço", required=True, queryset=WorkshopCollaborator.objects.none(), widget=SelectInput())

    class Meta:
        model = Budget
        fields = ["collaborator","technical_diagnosis"]
        widgets = {
            "technical_diagnosis": forms.Textarea(attrs={"rows": 10, "placeholder": "Descreva detalhadamente as observações técnicas, diagnósticos preliminares, testes realizados...", "class": "textarea textarea-bordered w-full"}),
        }

    def __init__(self, *args, **kwargs):
        self.workshop = kwargs.pop("workshop", None)
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)

        if self.workshop:
            self.fields["collaborator"].queryset = WorkshopCollaborator.objects.filter(workshop=self.workshop, is_active=True)
            self.fields["checklist"].queryset = Checklist.objects.filter(workshop=self.workshop)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            HTML("""<script>
                    function addDefectRow() {
                        const input = document.getElementById('id_new_defect');
                        const container = document.getElementById('defect-list-container');
                        const text = input.value.trim();
                        if (text === "") return;
                        const id = 'new-' + Date.now();
                        const html = `<div class="badge badge-lg badge-ghost gap-2 py-5 mb-2 mr-2 pr-1" id="defect-${id}">
                                <input type="hidden" name="defects_list" value="${text}">
                                <span class="font-medium">${text}</span>
                                <button type="button" onclick="this.parentElement.remove()" class="btn btn-ghost btn-xs btn-circle text-error">
                                    X
                                </button>
                            </div>`;
                        container.insertAdjacentHTML('beforeend', html);
                        input.value = "";
                        input.focus();
                    }
                </script>"""),
            Div(
                # Coluna Esquerda
                Div(
                    # Diagnóstico Técnico
                    Div(
                        HTML('<h3 class="text-2xl font-bold mb-4">Diagnóstico Técnico</h3>'),
                        Field("collaborator", label="Selecione o colaborador que realizará o serviço", wrapper_class="mb-6"),
                        #
                        HTML('<label class="block text-gray-700 font-bold mb-2">Adicione os defeitos encontrados durante a inspeção</label>'),
                        Div(id="defect-list-container", css_class="mb-4 p-4 border-2 border-dashed border-gray-200 rounded-lg min-h-[120px] flex flex-wrap content-start"),
                        Div(Div(Field("new_defect", wrapper_class="mb-0"), css_class="flex-1"),
                            HTML("""<button type="button" class="btn btn-primary ml-2" onclick="addDefectRow()">
                                    Adicionar</button>"""), css_class="flex items-end mb-8"),
                        css_class="mb-8",
                    ),
                    # Checklist para Impressão
                    Div(
                        HTML('<h3 class="text-2xl font-bold mb-4">Checklist para Impressão</h3>'),
                        Div(Div(Field("checklist", wrapper_class="mb-0"), css_class="flex-1"),
                        HTML("""<button type="button" class="btn btn-primary ml-2">
                                            Imprimir</button>"""), css_class="flex items-end mb-8"),
                        css_class="mb-8",
                    ),
                    css_class="col-span-12 lg:col-span-5",
                ),
                #
                Div(css_class="hidden lg:block lg:col-span-1"),
                #
                # Coluna Direita
                Div(
                    # Observações Técnicas
                    Div(
                        HTML('<h3 class="text-2xl font-bold mb-4">Observações Técnicas</h3>'),
                        Field("technical_diagnosis", label=False, wrapper_class="mb-0"),
                        css_class="mb-8",
                    ),
                    # Imagens
                    Div(
                        HTML('<h3 class="text-2xl font-bold mb-4">Anexar Imagens</h3>'),
                        HTML("""<div class="flex items-center justify-center w-full">
                                <label class="flex flex-col items-center justify-center w-full h-32 border-2 border-gray-300 border-dashed rounded-lg cursor-pointer">
                                    <div class="flex flex-col items-center justify-center pt-5 pb-6">
                                        <p class="mb-1 text-lg font-semibold text-gray-700">Arraste e solte imagens aqui ou clique para selecionar</p>
                                        <p class="text-sm text-gray-400">Formatos aceitos: JPG, PNG, GIF (máx. 5MB cada)</p>
                                    </div>
                                    <input type="file" name="budget_images" class="hidden" multiple accept="image/*" />
                                </label>
                            </div>"""), css_class="mb-6",
                    ), css_class="col-span-12 lg:col-span-6",
                ), css_class="grid grid-cols-1 lg:grid-cols-12 gap-4",
            ),
        )

        if self.instance.pk:
            existing_defects = self.instance.defects.all()
            if existing_defects.exists():
                defects_json = "".join(
                    [
                        f"""<div class="badge badge-lg badge-ghost gap-2 py-5 mb-2 mr-2 pr-1" id="defect-old-{d.id}">
                            <input type="hidden" name="defects_list" value="{d.name}">
                            <span class="font-medium">{d.name}</span>
                            <button type="button" onclick="this.parentElement.remove()" class="btn btn-ghost btn-xs btn-circle text-error">
                                X
                            </button>
                        </div>"""
                        for d in existing_defects
                    ]
                )
                # Injeta os defeitos existentes via JS após a renderização do container
                self.helper.layout.append(
                    HTML(f"""
                    <script>
                        document.addEventListener("DOMContentLoaded", function() {{
                            document.getElementById('defect-list-container').innerHTML = `{defects_json}`;
                        }});
                    </script>
                """)
                )

    def save(self, commit=True):
        budget = super().save(commit=commit)

        # Processamento dos Defeitos (Somente no Save final)
        if "defects_list" in self.request.POST:
            defect_names = self.request.POST.getlist("defects_list")

            # Sincronização: remove antigos e adiciona novos
            budget.defects.all().delete()
            for name in defect_names:
                if name.strip():
                    Defect.objects.create(
                        workshop=self.workshop,
                        budget=budget,
                        name=name.strip()
                    )

        return budget