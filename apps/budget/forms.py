from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Div, Field, HTML
from django import forms

from apps.budget.models import Budget
from apps.collaborators.models import WorkshopCollaborator
from apps.core.widgets import TextInput, SelectInput, CalendarDateInput
from apps.customer.models import Vehicle
from apps.quote.models.investigative_questions import InvestigativeQuestion


class BudgetStep1Form(forms.ModelForm):
    workshop = forms.CharField(widget=TextInput(attrs={"readonly": "readonly"}), required=False)
    collaborator = forms.CharField(widget=TextInput(attrs={"readonly": "readonly"}), required=False)
    class Meta:
        model = Budget
        fields = [
            "workshop",
            "collaborator",
            "entry_date",
            "customer",
            "vehicle",
            "current_km",
            "fuel_level",
        ]
        widgets = {
            "entry_date": CalendarDateInput(),
            "customer": SelectInput(),
            "vehicle": forms.Select(),
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
            self.fields["collaborator"].initial = user.get_full_name() or user.username

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
                            Field("collaborator", wrapper_class="col-span-12 lg:col-span-12"),
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
        cleaned_data["collaborator"] = WorkshopCollaborator.objects.filter(user=self.request.user, workshop=self.workshop).first()

        return cleaned_data


class BudgetStep2Form(forms.ModelForm):
    class Meta:
        model = Budget
        fields = ["problem_description", "notes"]
        widgets = {
            "problem_description": forms.Textarea(attrs={
                "class": "textarea textarea-bordered w-full",
                "rows": "17",
                "placeholder": "Descreva detalhadamente o relato do cliente..."
            }),
            "notes": forms.Textarea(attrs={
                "class": "textarea textarea-bordered w-full",
                "rows": "4",
                "placeholder": "Observações gerais sobre este orçamento..."
            }),
        }

    def __init__(self, *args, **kwargs):
        self.workshop = kwargs.pop("workshop", None)
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)

        questions = []
        if self.workshop:
            questions = InvestigativeQuestion.objects.filter(workshop=self.workshop, is_active=True).order_by("order")

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                HTML('<h3 class="text-2xl font-bold col-span-12">Relato do Cliente</h3>'),
                # Descrição do Problema
                Div(Field("problem_description", wrapper_class="w-full"), css_class="col-span-12 lg:col-span-6"),

                # Perguntas Investigativas
                Div(
                    HTML('<h5 class="font-semibold mb-1.5">Perguntas Investigativas</h5>'),
                    Div(
                        Div(*[self._render_question(q) for q in questions], css_class="space-y-4 p-4"),
                        css_class="border rounded-lg bg-base-200 overflow-y-auto",
                        style="height: 375px;",
                    ),
                    css_class="col-span-12 lg:col-span-6",
                ),

                # Observações
                Div(Field("notes", wrapper_class="w-full"), css_class="col-span-12"),
                css_class="grid grid-cols-12 gap-6",
            ),
        )

    def _render_question(self, question):
        """Helper para renderizar o HTML de cada pergunta dentro do scroll"""
        # Aqui você pode adaptar o input baseado no question.response_type
        input_html = f'<input type="text" name="question_{question.id}" class="input input-bordered w-full mt-1" placeholder="Resposta...">'

        if question.response_type == "BOOL":
            input_html = f"""
                <div class="flex gap-4 mt-1">
                    <label class="flex items-center gap-2 cursor-pointer"><input type="radio" name="q_{question.id}" class="radio radio-primary"> Sim</label>
                    <label class="flex items-center gap-2 cursor-pointer"><input type="radio" name="q_{question.id}" class="radio radio-primary"> Não</label>
                </div>
            """

        return HTML(f"""
            <div class="form-control w-full border-b border-base-300 pb-3 last:border-0">
                <span class="text-sm font-medium text-base-content">{question.text}</span>
                {input_html}
            </div>
        """)