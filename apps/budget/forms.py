from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Div, Field, HTML
from django import forms
from django.db.models import Sum, F
from django.template.loader import render_to_string
from django.urls import reverse_lazy, reverse
from djmoney.money import Money

from apps.budget.models import Budget, Defect, BudgetImage
from apps.checklist.models import Checklist
from apps.collaborators.models import WorkshopCollaborator
from apps.core.widgets import TextInput, SelectInput, CalendarDateInput, MoneyInput
from apps.customer.models import Vehicle
from apps.quote.models.investigative_questions import InvestigativeQuestion, InvestigativeResponse


class BudgetStep1Form(forms.ModelForm):
    workshop = forms.CharField(label="Empresa", widget=TextInput(attrs={"readonly": "readonly"}), required=False)
    cost_estimator = forms.CharField(label="Orçamentista",widget=TextInput(attrs={"readonly": "readonly"}), required=False)
    vehicle = forms.ModelChoiceField(label="Veículo",  queryset=Vehicle.objects.none(), required=False, widget=SelectInput())
    class Meta:
        model = Budget
        fields = ["workshop", "cost_estimator", "entry_date", "customer", "vehicle", "current_km", "fuel_level"]
        widgets = {
            "entry_date": CalendarDateInput(),
            "customer": SelectInput(attrs={"x-model": "customerId", "@change": "customerId = $el.value"}),
            "current_km": TextInput(),
            "fuel_level": TextInput(),
        }

    def __init__(self, *args, **kwargs):
        self.workshop = kwargs.pop("workshop", None)
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)
        # No __init__ do BudgetStep1Form, adicione esta linha:
        self.fields["customer"].widget.attrs.update({"data-vehicle-url": reverse_lazy("budget:get-vehicles")})

        # Preenchimento inicial (Campos não editáveis)
        if self.workshop:
            self.fields["workshop"].initial = self.workshop.name
            self.fields["customer"].queryset = self.fields["customer"].queryset.filter(workshop=self.workshop)
            self.initial["workshop"] = self.workshop.name

        if self.instance and self.instance.cost_estimator:
            user = self.instance.cost_estimator
            self.fields["cost_estimator"].initial = user.get_full_name() or user.username
            self.initial["cost_estimator"] = user.get_full_name() or user.username

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
                    const lastValues = {};
                
                    const updateVehicleSelect = (customerId) => {
                        const vehicleContainer = document.querySelector('[name="vehicle"]').closest('div'); // container do SelectInput
                        if (!vehicleContainer) return;
                    
                        const optionsList = vehicleContainer.querySelector('[x-ref="options"]');
                        if (!optionsList) return;
                    
                        // Limpa opções existentes (exceto o "Limpar seleção")
                        optionsList.querySelectorAll('li[data-value]').forEach(li => li.remove());
                    
                        if (!customerId) return;
                    
                        const url = `/budget/get-vehicles/?customer=${customerId}`;
                        fetch(url)
                            .then(response => response.json())
                            .then(data => {
                                data.forEach(v => {
                                    const li = document.createElement('li');
                                    li.setAttribute('data-value', v.id);
                                    li.setAttribute('data-label', v.label);
                                    li.className = 'relative cursor-pointer select-none py-2 pl-3 pr-9 hover:bg-primary hover:text-white group transition-colors';
                                    li.textContent = v.label;
                    
                                    li.addEventListener('click', () => {
                                        const input = vehicleContainer.querySelector('input[name="vehicle"]');
                                        input.value = v.id;
                                    
                                        // --- ADICIONE ESTA LINHA ---
                                        // Isso garante que o Alpine.js atualize a variável interna vehicleId
                                        if (window.Alpine) {
                                            const alpineData = Alpine.$data(input.closest('[x-data]'));
                                            if (alpineData) alpineData.vehicleId = v.id;
                                        }
                                        // ---------------------------
                                    
                                        const spanLabel = vehicleContainer.querySelector('button span:first-child');
                                        if (spanLabel) spanLabel.textContent = v.label;
                                    
                                        input.dispatchEvent(new Event('input', { bubbles: true }));
                                        input.dispatchEvent(new Event('change', { bubbles: true }));
                                        
                                        document.body.click();
                                    });
                    
                                    optionsList.appendChild(li);
                                });
                            })
                            .catch(err => console.error('Erro ao buscar veículos:', err));
                    };
            
                    const updateResume = (name, value, targetId, urlBase) => {
                        if (!value || lastValues[name] === value) return;
                        lastValues[name] = value;
                
                        const container = document.getElementById(targetId);
                        if (!container) return;

                        fetch(`${urlBase}?${name}=${value}`)
                            .then(r => r.text())
                            .then(html => container.innerHTML = html)
                            .catch(err => console.error('Erro ao carregar resumo:', err));
                    };

                    const bindField = (field) => {
                        const el = document.querySelector(`[name="${field.name}"]`);
                        if (!el) return;
                    
                        el.addEventListener('change', (e) => {
                            const val = e.target.value;
                            
                            // Sincroniza com o Alpine.js SEMPRE, mesmo se for vazio
                            if (window.Alpine) {
                                const alpineData = Alpine.$data(el.closest('[x-data]'));
                                if (alpineData) {
                                    if (field.name === 'customer') alpineData.customerId = val;
                                    if (field.name === 'vehicle') alpineData.vehicleId = val;
                                }
                            }
                    
                            if (lastValues[field.name] === val) return;
                            lastValues[field.name] = val;
                    
                            // Se o valor for vazio, limpa o resumo e para por aqui
                            if (!val) {
                                const container = document.getElementById(field.id);
                                if (container) container.innerHTML = '';
                                return; 
                            }
                    
                            updateResume(field.name, val, field.id, field.url);
                            
                            if (field.name === 'customer') {
                                updateVehicleSelect(val);
                                const vResumo = document.getElementById('resumo-veiculo');
                                if (vResumo) vResumo.innerHTML = '';
                                
                                const vehicleInput = document.querySelector('[name="vehicle"]');
                                if (vehicleInput) {
                                    vehicleInput.value = '';
                                    vehicleInput.dispatchEvent(new Event('change', { bubbles: true }));
                                }
                            }
                        });
                    };
                
                    const initFormLogic = () => {
                        [
                            { name: 'customer', id: 'resumo-cliente', url: '/budget/customer-detail/' },
                            { name: 'vehicle', id: 'resumo-veiculo', url: '/budget/vehicle-detail/' }
                        ].forEach(bindField);
                    };

                    // Tenta rodar imediatamente (para carregamento inicial da página)
                    if (document.readyState === 'complete') {
                        initFormLogic();
                    } else {
                        window.addEventListener('load', initFormLogic);
                    }

                    document.body.addEventListener('htmx:afterSettle', initFormLogic);
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
                            Div(
                                Field("customer", wrapper_class="flex-1 mb-0"),
                                HTML("""<button type="button" class="btn btn-circle mb-2 p-4" :class="customerId ? 'btn-warning' : 'btn-primary'"
                                    @click="
                                        const url = customerId ? `/customer/quick-update/${customerId}/` : '/customer/quick-create/';
                                        htmx.ajax('GET', url, {target: '#modal-container', swap: 'innerHTML'});
                                        document.getElementById('form_modal').showModal();
                                    ">
                                    <span class="material-icons" x-text="customerId ? 'edit' : 'person_add'"></span>
                                </button>"""),
                                css_class="flex items-end gap-2 w-full",
                            ),
                            Div(
                                Field("vehicle", wrapper_class="flex-1 mb-0"),
                                HTML("""<button type="button" class="btn btn-circle mb-2 p-4" :class="!customerId ? 'btn-disabled opacity-50' : (vehicleId && vehicleId !== '' ? 'btn-warning' : 'btn-primary')" :disabled="!customerId"
                                    @click="
                                        const url = vehicleId ? `/customer/vehicle/quick-update/${vehicleId}/` : `/customer/vehicle/quick-create/?customer_id=${customerId}`;
                                        htmx.ajax('GET', url, {target: '#modal-container', swap: 'innerHTML'});
                                        document.getElementById('form_modal').showModal();
                                    ">
                                    <span class="material-icons" x-text="(vehicleId && vehicleId !== '') ? 'edit' : 'directions_car_filled'"></span>
                                </button>"""),
                                css_class="flex items-end gap-2 w-full",
                            ),
                            x_data=f"""{{customerId: '{self.instance.customer.id if self.instance and self.instance.customer else ""}',
                                       vehicleId: '{self.instance.vehicle.id if self.instance and self.instance.vehicle else ""}'}}""",
                            css_class="grid grid-cols-1 gap-2",
                        ),
                        css_class="mb-6",
                    ),
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
            "notes": forms.Textarea(attrs={"rows": 4, "cols": 40, "class": "!bg-transparent"}),
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
                self.fields[field_name].help_text = f'Valor selecionado: <span id="{display_id}" class="font-bold text-xs">{initial_value or 5}</span>'
            elif q.response_type == InvestigativeQuestion.ResponseType.MULTIPLE_CHOICE:
                choices = [(opt, opt) for opt in q.options]
                choices1 = [("", "Selecione...")] + choices
                self.fields[field_name] = forms.ChoiceField(label=q.text, choices=choices1, required=False, initial=initial_value, widget=SelectInput(choices=choices1))
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
                Div(
                    Field("problem_description", wrapper_class="flex flex-col h-full", css_class="flex-1 !bg-transparent"),
                    css_class="col-span-12 lg:col-span-6 flex flex-col"
                ),
                # Perguntas Investigativas
                Div(
                    HTML('<h5 class="font-bold mb-2">Perguntas Investigativas</h5>'),
                    Div(*question_layout_fields, css_class="border px-4 py-2 rounded-lg pr-4 overflow-y-auto min-h-[40vh] max-h-[40vh] scrollbar-thin scrollbar-thumb-gray-400"),
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
            "technical_diagnosis": forms.Textarea(attrs={
                "rows": 10,
                "placeholder": "Descreva detalhadamente as observações técnicas, diagnósticos preliminares, testes realizados...",
                "class": "textarea textarea-bordered w-full !bg-transparent"
            }),
        }

    def __init__(self, *args, **kwargs):
        self.workshop = kwargs.pop("workshop", None)
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)

        if self.workshop:
            self.fields["collaborator"].queryset = WorkshopCollaborator.objects.filter(workshop=self.workshop, is_active=True)
            self.fields["checklist"].queryset = Checklist.objects.filter(workshop=self.workshop)

        existing_file_html = ""
        if self.instance.pk:
            img = self.instance.budget_image.first()
            if img:
                existing_file_html = f"""<div class="mb-4">
                            <p class="text-sm font-medium text-gray-500 mb-2">Imagem atual:</p>
                            <div class="badge badge-success gap-2 py-3">
                                <span class="material-icons text-xs">attachment</span>
                                {img.content_name}
                            </div>
                        </div>"""

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
                        HTML(existing_file_html),
                        HTML("""
                                        <div class="flex flex-col w-full gap-4">
                                            <label class="flex flex-col items-center justify-center w-full h-32 border-2 border-dashed rounded-lg cursor-pointer hover:bg-base-200 transition-colors">
                                                <div class="flex flex-col items-center justify-center pt-5 pb-6">
                                                    <p class="mb-1 text-lg font-semibold text-gray-700">Clique para selecionar novas imagens</p>
                                                    <p class="text-sm text-gray-400">JPG, PNG, GIF (máx. 5MB)</p>
                                                    <div id="image-preview-container" class="flex flex-wrap gap-2 mt-2"></div>
                                                </div>
                                                <input type="file" id="image-input" name="budget_images" class="hidden" multiple accept="image/*" onchange="previewImages(this)" />
                                            </label>
                                        </div>
                                        <script>
                                            function previewImages(input) {
                                                const container = document.getElementById('image-preview-container');
                                                container.innerHTML = '';
                                                if (input.files) {
                                                    Array.from(input.files).forEach(file => {
                                                        const html = `
                                                            <div class="mt-2 badge badge-info gap-2 py-2">
                                                                <span class="max-w-[150px] truncate">${file.name}</span>
                                                            </div>`;
                                                        container.insertAdjacentHTML('beforeend', html);
                                                    });
                                                }
                                            }
                                        </script>
                                    """),
                        css_class="mb-6",
                    ),
                    css_class="col-span-12 lg:col-span-6",
                ),
                css_class="grid grid-cols-1 lg:grid-cols-12 gap-4",
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
                # Injeta os defeitos existentes após a renderização do container
                self.helper.layout.append(
                    HTML(f"""
                    <script>
                        document.getElementById('defect-list-container').innerHTML = `{defects_json}`;
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

        new_image = self.request.FILES.get("budget_images")
        if new_image:
            budget.budget_image.all().delete()
            BudgetImage.objects.create(workshop=self.workshop, budget=budget, content=new_image.read(), content_name=new_image.name, content_type=new_image.content_type)

        return budget


class BudgetStep4Form(forms.ModelForm):
    class Meta:
        model = Budget
        fields = []
        widgets = {}

    def __init__(self, *args, **kwargs):
        self.workshop = kwargs.pop("workshop", None)
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)

        budget = self.instance

        products_html = ""
        services_html = ""
        kits_html = ""

        if budget.pk:
            items = budget.items.all()
            for item in items:
                context = {"item": item, "budget": budget, "is_full_render": True}
                if item.product:
                    products_html += render_to_string("budget/partials/item_product_row.html", context)
                if item.service:
                    services_html += render_to_string("budget/partials/item_service_row.html", context)
                if item.kit:
                    kits_html += render_to_string("budget/partials/item_kit_row.html", context)

        if not products_html: products_html = '<tr><td colspan="6" class="text-center text-gray-400 py-4">Nenhum produto adicionado</td></tr>'
        if not services_html: services_html = '<tr><td colspan="6" class="text-center text-gray-400 py-4">Nenhum serviço adicionado</td></tr>'
        if not kits_html: kits_html = '<tr><td colspan="5" class="text-center text-gray-400 py-4">Nenhum kit adicionado</td></tr>'

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                # Coluna Esquerda: Seleção
                Div(
                    HTML('<h2 class="text-2xl font-bold mb-6">Seleção de Produtos e Serviços</h2>'),
                    # Seção de Produtos
                    Div(
                        Div(
                            HTML('<h3 class="text-xl font-semibold text-gray-700">Produtos</h3>'),
                            HTML(f'<button type="button" class="btn btn-primary" hx-get="{reverse("budget:item_selection", kwargs={"budget_id": budget.pk, "item_type": "product"})}" hx-target="#modal-container" onclick="form_modal.showModal()">Inserir Produto</button>'),
                            css_class="flex justify-between items-center mb-4",
                        ),
                        Div(
                            HTML(f"""
                                <table class="table table-zebra w-full">
                                    <thead>
                                        <tr>
                                            <th>NOME</th>
                                            <th class="text-center">QTD.</th>
                                            <th>VALOR VENDA</th>
                                            <th>FRETE</th>
                                            <th>TOTAL</th>
                                            <th class="text-center">AÇÕES</th>
                                        </tr>
                                    </thead>
                                    <tbody id="product-list-body">
                                        {products_html}
                                    </tbody>
                                </table>
                            """),
                            css_class="overflow-x-auto mb-8 rounded-lg shadow-md shadow-gray-300/50",
                        ),
                        css_class="mb-10",
                    ),
                    # Seção de Serviços
                    Div(
                        Div(
                            HTML('<h3 class="text-xl font-semibold text-gray-700">Serviços</h3>'),
                            HTML(f'<button type="button" class="btn btn-primary" hx-get="{reverse("budget:item_selection", kwargs={"budget_id": budget.pk, "item_type": "service"})}" hx-target="#modal-container" onclick="form_modal.showModal()">Inserir Serviço</button>'),
                            css_class="flex justify-between items-center mb-4",
                        ),
                        Div(
                            HTML(f"""
                                <table class="table table-zebra w-full">
                                    <thead>
                                        <tr>
                                            <th>NOME</th>
                                            <th class="text-center">QTD.</th>
                                            <th>VALOR VENDA</th>
                                            <th>TEMPO</th>
                                            <th>TOTAL</th>
                                            <th class="text-center">AÇÕES</th>
                                        </tr>
                                    </thead>
                                    <tbody id="service-list-body">
                                        {services_html}
                                    </tbody>
                                </table>
                            """),
                            css_class="overflow-x-auto mb-8 rounded-lg shadow-md shadow-gray-300/50",
                        ),
                        css_class="mb-10",
                    ),
                    # Seção de Kits
                    Div(
                        Div(
                            HTML('<h3 class="text-xl font-semibold text-gray-700">Kits</h3>'),
                            HTML(f'<button type="button" class="btn btn-primary px-8" hx-get="{reverse("budget:item_selection", kwargs={"budget_id": budget.pk, "item_type": "kit"})}" hx-target="#modal-container" onclick="form_modal.showModal()">Inserir Kit</button>'),
                            css_class="flex justify-between items-center mb-4",
                        ),
                        Div(
                            HTML(f"""
                                <table class="table table-compact w-full">
                                    <thead>
                                        <tr>
                                            <th>NOME</th>
                                            <th class="text-center">QTD.</th>
                                            <th class="text-center">PRODUTOS</th>
                                            <th class="text-center">SERVIÇOS</th>
                                            <th class="text-center">AÇÕES</th>
                                        </tr>
                                    </thead>
                                    <tbody id="kit-list-body">
                                        {kits_html}
                                    </tbody>
                                </table>
                            """),
                            css_class="overflow-x-auto mb-4 rounded-lg shadow-md shadow-gray-300/50",
                        ),
                        css_class="mb-6",
                    ),
                    css_class="col-span-12 lg:col-span-6",
                ),
                #
                Div(css_class="hidden lg:block lg:col-span-1"),
                #
                # Coluna Direita
                Div(
                    Div(
                        HTML('<h2 class="text-2xl font-bold mb-4 mt-8">Resumo</h2>'),
                        Div(
                            Div(HTML(f"<span>Total Produtos</span><span>{budget.total_products_value}</span>"), css_class="border rounded-xl flex justify-between items-center p-3 rounded mb-2"),
                            Div(HTML(f"<span>Total Serviços</span><span>{budget.total_services_value}</span>"), css_class="border rounded-xl flex justify-between items-center p-3 rounded mb-2"),
                            Div(HTML(f"<span>Total Frete</span><span>R$ 0,00</span>"), css_class="border rounded-xl flex justify-between items-center p-3 rounded mb-2"),
                            Div(HTML(f"<span>Tempo Total</span><span>{budget.total_duration_display}</span>"), css_class="border rounded-xl flex justify-between items-center p-3 rounded mb-2"),
                            Div(HTML(f'<span class="font-bold">Total Geral</span><span class="font-bold">{budget.total_base_value}</span>'), css_class="border rounded-xl flex justify-between items-center p-3 rounded mb-2"),
                            css_class="sticky top-4",
                        ),
                        css_class="p-6 h-fit text-lg",
                    ),
                    css_class="col-span-12 lg:col-span-5 mt-10 lg:mt-0",
                ),
                css_class="grid grid-cols-1 lg:grid-cols-12 gap-4",
            ),
        )

    def save(self, commit=True):
        # Como este form é estrutural, o save lida com persistência de estado da etapa
        return super().save(commit=commit)


class BudgetStep5Form(forms.ModelForm):
    slider = forms.IntegerField(required=False, widget=forms.NumberInput(attrs={"class": "range range-primary w-full", "type": "range", "min": "-100", "max": "100", "step": "5"}))

    class Meta:
        model = Budget
        fields = ["discount_value", "slider"]
        widgets = {
            "discount_value": MoneyInput(),
        }

    def __init__(self, *args, **kwargs):
        self.workshop = kwargs.pop("workshop", None)
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)

        self.fields["slider"].label = ""
        self.fields["slider"].help_text = ""
        self.fields["discount_value"].required = False
        self.fields["slider"].widget.attrs.update({"hx-post": reverse("budget:update_slider", args=[self.instance.pk]), "hx-trigger": "change", "hx-swap": "none"})

        budget = self.instance

        dados = {}
        if budget.pk:
            self.fields["slider"].initial = budget.slider
            dados = budget.calculate_pricing_methods()

        mlr = dados.get("mlr", None)
        mlo = dados.get("mlo", None)
        mlr_html = ""
        if mlr is not None:
            mlr_html = f"""
            <div class="grid grid-cols-12 border bg-white overflow-hidden">
                <span class="col-span-8 p-2 bg-gray-50">MLR</span>
                <span class="col-span-4 p-2 border-l text-left">{float(mlr):.2f}</span>
            </div>
            """
        mlo_html = ""
        if mlo is not None:
            mlo_html = f"""
            <div class="grid grid-cols-12 border bg-white overflow-hidden">
                <span class="col-span-8 p-2 bg-gray-50">MLO</span>
                <span class="col-span-4 p-2 border-l text-left">{float(mlo):.2f}</span>
            </div>
            """

        zerado = Money(0, 'BRL')

        # Custos
        custo_pecas = dados.get('custo_pecas') or zerado
        custo_frete_pecas = dados.get('custo_frete_pecas') or zerado
        custo_servico_terceiros = dados.get('custo_servico_terceiro') or zerado
        custo_hora_mecanico = dados.get('custo_hora_mecanico') or zerado

        # Valores Venda
        venda_pecas = dados.get('venda_pecas') or zerado
        venda_servico_terceiros = dados.get('venda_servico_terceiro') or zerado
        venda_mao_obra = dados.get('venda_mao_obra') or zerado

        # Extra
        metodo_precificacao = dados.get('method_name') or ""
        duracao_total = dados.get('duracao_total') or "00h 00m"
        lucro_operacional = dados.get('lucro_operacional') or zerado
        rentabilidade = dados.get('rentabilidade') or 0

        status_cor = "text-error" if rentabilidade < 60 else "text-warning" if (60 <= rentabilidade < 70) else "text-success"
        status_texto = "Ruim" if rentabilidade < 60 else "Médio" if (60 <= rentabilidade < 70) else "Bom"

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            HTML(f"""<script>
                    (function() {{
                        let timeout = null;
                    
                        const performUpdate = (value) => {{
                            htmx.ajax('POST', '{{% url "budget:update_budget_discount" {self.instance.pk} %}}', {{
                                values: {{ "discount_value_0": value }},
                                swap: 'none'
                            }});
                        }};
                    
                        const initDiscountObserver = () => {{
                            const hiddenInput = document.getElementById('id_discount_value_0');
                            if (!hiddenInput) return;
                    
                            let lastValue = hiddenInput.value;
                    
                            const handleChange = (newValue) => {{
                                if (newValue === lastValue) return;
                                lastValue = newValue;
                    
                                clearTimeout(timeout);
                                timeout = setTimeout(() => {{
                                    performUpdate(newValue);
                                }}, 800);
                            }};
                    
                            const observer = new MutationObserver((mutations) => {{
                                mutations.forEach((mutation) => {{
                                    if (mutation.attributeName === 'value') {{
                                        handleChange(hiddenInput.value);
                                    }}
                                }});
                            }});
                    
                            observer.observe(hiddenInput, {{ attributes: true }});
                    
                            hiddenInput.addEventListener('input', (e) => handleChange(e.target.value));
                            hiddenInput.addEventListener('change', (e) => handleChange(e.target.value));
                        }};
                    
                        document.addEventListener('DOMContentLoaded', initDiscountObserver);
                        document.body.addEventListener('htmx:afterSettle', initDiscountObserver);
                    }})();
                    
                    (function () {{
                        function initSlider(root=document) {{
                            const slider = root.querySelector('input[name="slider"]');
                            const labelPecaPct = root.querySelector('#val-peca');
                            const labelMOPct = root.querySelector('#val-mo');
                    
                            const displayVendaPecas = root.querySelector('#display-venda-pecas');
                            const displayVendaMO = root.querySelector('#display-venda-mo');
                    
                            if (!slider || !labelPecaPct || !labelMOPct || !displayVendaPecas || !displayVendaMO) return;
                    
                            const basePeca = parseFloat(displayVendaPecas.dataset.baseVal.replace(',', '.'));
                            const baseMO = parseFloat(displayVendaMO.dataset.baseVal.replace(',', '.'));
                            const totalOriginal = basePeca + baseMO;
                    
                            const formatCurrency = (val) => {{
                                return "R$ " + val.toLocaleString('pt-BR', {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }});
                            }};
                    
                            const updateValues = (val) => {{
                                const sliderVal = parseInt(val || 0);
                    
                                let pecaPctUI = 0;
                                let moPctUI = 0;
                    
                                if (sliderVal < 0) {{
                                    pecaPctUI = Math.abs(sliderVal);
                                    moPctUI = 100 - Math.abs(sliderVal);
                                }} else if (sliderVal > 0) {{
                                    moPctUI = Math.abs(sliderVal);
                                    pecaPctUI = 100 - Math.abs(sliderVal);
                                }}
                                
                                labelPecaPct.textContent = pecaPctUI;
                                labelMOPct.textContent = moPctUI;
                    
                                const _pecaPct = sliderVal < 0 ? Math.abs(sliderVal) / 100 : (sliderVal > 0 ? (100 - sliderVal) / 100 : 0);
                                const _maoPct = sliderVal > 0 ? sliderVal / 100 : (sliderVal < 0 ? (100 - Math.abs(sliderVal)) / 100 : 0);
                    
                                let novoVendaPeca, novoVendaMO;
                    
                                if (sliderVal === 0) {{
                                    novoVendaPeca = basePeca;
                                    novoVendaMO = baseMO;
                                }} else {{
                                    novoVendaPeca = totalOriginal * _pecaPct;
                                    novoVendaMO = totalOriginal * _maoPct;
                                }}
                                displayVendaPecas.textContent = formatCurrency(novoVendaPeca);
                                displayVendaMO.textContent = formatCurrency(novoVendaMO);
                            }};
                            updateValues(slider.value);
                            if (!slider.dataset.bound) {{
                                slider.addEventListener('input', e => updateValues(e.target.value));
                                slider.dataset.bound = "1";
                            }}
                        }}
                    
                        document.addEventListener('DOMContentLoaded', () => initSlider());
                        document.body.addEventListener('htmx:afterSettle', (e) => initSlider(e.target));
                    }})();
                </script>"""),
            Div(
                HTML('<h3 class="text-2xl font-bold col-span-12">Método de Precificação</h3>'),
                # Coluna Esquerda
                Div(
                    Div(
                        HTML(f'<h3 class="text-3xl font-bold mb-2 border-b-3 border-[#007bff] text-[#222a2c] text-center">Método {metodo_precificacao}</h3>'),
                        Div(
                            # Grid de Custos vs Vendas
                            Div(
                                HTML(f"""
                                    <div class="grid grid-cols-1 md:grid-cols-2 mt-7 gap-x-6 gap-y-2 text-base text-[#222a2c] font-semibold">
                                        <div class="grid grid-cols-12 border bg-white overflow-hidden">
                                            <span class="col-span-8 p-2 bg-gray-50">Custo de Peças</span>
                                            <span class="col-span-4 p-2 border-l text-left">{custo_pecas}</span>
                                        </div>
                                        <div class="grid grid-cols-12 border bg-white overflow-hidden">
                                            <span class="col-span-8 p-2 bg-gray-50">Valor de Venda de Peças</span>
                                            <span id="display-venda-pecas" class="col-span-4 p-2 border-l text-left" data-base-val="{venda_pecas.amount}">{venda_pecas}</span>
                                        </div>

                                        <div class="grid grid-cols-12 border bg-white overflow-hidden">
                                            <span class="col-span-8 p-2 bg-gray-50">Custo de Frete de Peças</span>
                                            <span class="col-span-4 p-2 border-l text-left">{custo_frete_pecas}</span>
                                        </div>
                                        <div class="invisible md:visible"></div>
                                        <div class="grid grid-cols-12 border bg-white overflow-hidden">
                                            <span class="col-span-8 p-2 bg-gray-50">Custo de Serviço de Terceiros</span>
                                            <span class="col-span-4 p-2 border-l text-left">{custo_servico_terceiros}</span>
                                        </div>
                                        <div class="grid grid-cols-12 border bg-white overflow-hidden">
                                            <span class="col-span-8 p-2 bg-gray-50">Valor de Venda de Serviço de Terceiros</span>
                                            <span class="col-span-4 p-2 border-l text-left">{venda_servico_terceiros}</span>
                                        </div>

                                        <div class="grid grid-cols-12 border bg-white overflow-hidden">
                                            <span class="col-span-8 p-2 bg-gray-50">Custo da Hora do Mecânico</span>
                                            <span class="col-span-4 p-2 border-l text-left">{custo_hora_mecanico}</span>
                                        </div>
                                        <div class="grid grid-cols-12 border bg-white overflow-hidden">
                                            <span class="col-span-8 p-2 bg-gray-50">Valor de Venda de Mão de Obra</span>
                                            <span id="display-venda-mo" class="col-span-4 p-2 border-l text-left" data-base-val="{venda_mao_obra.amount}">{venda_mao_obra}</span>
                                        </div>
                                        
                                        <div class="grid grid-cols-12 border bg-white overflow-hidden">
                                            <span class="col-span-8 p-2 bg-gray-50">Duração Total</span>
                                            <span class="col-span-4 p-2 border-l text-left">{duracao_total}</span>
                                        </div>
                                        <div class="invisible md:visible"></div>

                                        <div class="grid grid-cols-12 border bg-white overflow-hidden">
                                            <span class="col-span-8 p-2 bg-gray-50">Lucro Operacional</span>
                                            <span class="col-span-4 p-2 border-l text-left">{lucro_operacional}</span>
                                        </div>
                                        <div class="grid grid-cols-12 border bg-white overflow-hidden {status_cor.replace("text-", "border-")}">
                                            <span class="col-span-8 p-2 bg-gray-50">Rentabilidade</span>
                                            <span class="col-span-4 p-2 border-l text-left {status_cor}">{rentabilidade:.2f}% ({status_texto})</span>
                                        </div>
                                        
                                        {mlr_html}
                                        {mlo_html}
                                    </div>
                                """),
                            ),
                            css_class="h-full",
                        ),
                        Div(
                            HTML(f"""<div class="text-center text-[#222a2c] mt-6">
                                    <p class="text-2xl font-bold">Valor do Orçamento</p>
                                    <p class="text-3xl font-black">{budget.total_base_value}</p>
                                </div>""")
                        ),
                        css_class="bg-[#d4e6ff] p-6 rounded-2xl border-2 border-[#007bff] h-full flex flex-col",
                    ),
                    css_class="col-span-12 lg:col-span-6 h-full",
                ),
                # Coluna Direita
                Div(
                    Div(
                        # Slider
                        Div(
                            HTML('<h4 class="font-bold text-lg mb-2">Margem de Lucro</h4>'),
                            Div(HTML('<span class="text-sm font-bold">Peça: <span id="val-peca">0</span>%</span>'), HTML('<span class="text-sm font-bold">Mão de Obra: <span id="val-mo">0</span>%</span>'), css_class="flex justify-between mb-1"),
                            Field("slider", label=False, help_text=False, wrapper_class="mb-0"),
                            HTML('<p class="text-sm text-gray-500 font-semibold italic">Deslize para a esquerda para aumentar Peça, ou para direita para aumentar Mão de obra</p>'),
                            css_class="mb-8 p-4 bg-base-200/50 rounded-lg",
                        ),
                        # Desconto
                        Div(HTML('<h4 class="font-bold text-lg mb-2">Desconto</h4>'), Field("discount_value", wrapper_class="col-span-12 lg:col-span-4"), css_class="mb-8 p-4 bg-base-200/50 rounded-lg"),
                        # Valor Final
                        Div(
                            HTML('<h4 class="font-bold text-lg mb-2 text-center border-b-1 border-gray-300">Valor Final</h4>'),
                            HTML('<h5 class="font-semibold text-lg mb-2 text-center">Valor do Orçamento com desconto aplicado:</h5>'),
                            HTML(f"""<div class="space-y-3">
                                        <div class="flex justify-between text-xl font-semibold">
                                            <span>Subtotal:</span>
                                            <span class="line-through">{budget.total_base_value}</span>
                                        </div>
                                        <div class="flex justify-between text-xl font-black">
                                            <span>Valor Final:</span>
                                            <span id="valor-final-display">{budget.total_budget_value}</span>
                                        </div>
                                    </div>"""),
                            css_class="mb-8 p-4 bg-base-200/50 rounded-lg",
                        ),
                        css_class="sticky top-4",
                    ),
                    css_class="col-span-12 lg:col-span-6",
                ),
                css_class="grid grid-cols-1 lg:grid-cols-12 gap-8 items-stretch",
            ),
        )


class BudgetStep6Form(forms.ModelForm):
    class Meta:
        model = Budget
        fields = []
        widgets = {}

    def __init__(self, *args, **kwargs):
        self.workshop = kwargs.pop("workshop", None)
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)

        budget = self.instance

        saved_observation = ""
        if self.workshop:
            saved_observation = self.workshop.pdf_observation or ""

        products_html = ""
        services_html = ""
        kits_html = ""

        if budget.pk:
            items = budget.items.all()
            for item in items:
                context = {"item": item, "budget": budget, "is_full_render": True, "step6": True}
                if item.product:
                    products_html += render_to_string("budget/partials/item_product_row.html", context)
                if item.service:
                    services_html += render_to_string("budget/partials/item_service_row.html", context)
                if item.kit:
                    kits_html += render_to_string("budget/partials/item_kit_row.html", context)

        if not products_html: products_html = '<tr><td colspan="5" class="text-center text-gray-400 py-4">Nenhum produto adicionado</td></tr>'
        if not services_html: services_html = '<tr><td colspan="5" class="text-center text-gray-400 py-4">Nenhum serviço adicionado</td></tr>'
        if not kits_html: kits_html = '<tr><td colspan="4" class="text-center text-gray-400 py-4">Nenhum kit adicionado</td></tr>'

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            HTML("""<script>
                    function saveObservation(budgetId) {
                        const observation = document.getElementById('budget-observation').value;
                    
                        fetch('/budget/save-observation/', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                'X-CSRFToken': '{{ csrf_token }}'
                            },
                            body: JSON.stringify({
                                budget_id: budgetId,
                                observation: observation,
                            })
                        });
                    }
                    
                    function updateBudgetStatus(budgetId, status) {
                        if (!confirm('Deseja realmente posseguir?')) return;
                    
                        fetch(`/budget/update-status/${budgetId}/${status}`, {
                            method: 'POST',
                            headers: { 'X-CSRFToken': '{{ csrf_token }}' }
                        }).then(() => {
                            window.location.href = "{% url 'budget:budget_list' %}";
                        });
                    }
            </script>"""),
            Div(
                HTML('<h3 class="text-2xl font-bold col-span-12">Revisão e Confirmação</h3>'),
                # Coluna Esquerda
                Div(
                    HTML('<div class="border-t-2 mb-4 mt-0"></div>'),
                    HTML('<h2 class="text-lg font-semibold mb-6">Revise os dados e confirme o orçamento</h2>'),
                    # Seção de Produtos
                    Div(
                        Div(
                            HTML('<h3 class="text-xl font-semibold text-gray-700">Peças Selecionadas</h3>'),
                            css_class="flex justify-between items-center mb-4",
                        ),
                        Div(
                            HTML(f"""<table class="table table-zebra w-full">
                                                    <thead class="text-white bg-primary">
                                                        <tr>
                                                            <th>NOME</th>
                                                            <th class="text-center">QTD.</th>
                                                            <th>VALOR VENDA</th>
                                                            <th>FRETE</th>
                                                            <th>TOTAL</th>
                                                        </tr>
                                                    </thead>
                                                    <tbody id="product-list-body">
                                                        {products_html}
                                                    </tbody>
                                                </table>"""),
                            css_class="overflow-x-auto mb-8 rounded-lg shadow-md shadow-gray-300/50",
                        ),
                        css_class="mb-10",
                    ),
                    # Seção de Serviços
                    Div(
                        Div(
                            HTML('<h3 class="text-xl font-semibold text-gray-700">Serviços Selecionados</h3>'),
                            css_class="flex justify-between items-center mb-4",
                        ),
                        Div(
                            HTML(f"""<table class="table table-zebra w-full">
                                                    <thead class="text-white bg-primary">
                                                        <tr>
                                                            <th>NOME</th>
                                                            <th class="text-center">QTD.</th>
                                                            <th>VALOR VENDA</th>
                                                            <th>TEMPO</th>
                                                            <th>TOTAL</th>
                                                        </tr>
                                                    </thead>
                                                    <tbody id="service-list-body">
                                                        {services_html}
                                                    </tbody>
                                                </table>"""),
                            css_class="overflow-x-auto mb-8 rounded-lg shadow-md shadow-gray-300/50",
                        ),
                        css_class="mb-10",
                    ),
                    # Seção de Kits
                    Div(
                        Div(
                            HTML('<h3 class="text-xl font-semibold text-gray-700">Kits Selecionados</h3>'),
                            css_class="flex justify-between items-center mb-4",
                        ),
                        Div(
                            HTML(f"""<table class="table table-compact w-full">
                                                    <thead class="text-white bg-primary">
                                                        <tr>
                                                            <th>NOME</th>
                                                            <th class="text-center">QTD.</th>
                                                            <th class="text-center">PRODUTOS</th>
                                                            <th class="text-center">SERVIÇOS</th>
                                                        </tr>
                                                    </thead>
                                                    <tbody id="kit-list-body">
                                                        {kits_html}
                                                    </tbody>
                                                </table>"""),
                            css_class="overflow-x-auto mb-4 rounded-lg shadow-md shadow-gray-300/50",
                        ),
                        css_class="mb-6",
                    ),
                    css_class="col-span-12 lg:col-span-5",
                ),
                #
                Div(css_class="hidden lg:block lg:col-span-1"),
                #
                # Coluna Direita
                Div(
                    Div(
                        # PDF
                        Div(
                            HTML('<h4 class="font-bold text-lg mb-2 border-b-1 border-gray-300">PDF</h4>'),
                            HTML("""
                            <div class="flex flex-col gap-3 text-center grid grid-cols-12">
                            
                                <button type="button" class="btn btn-success gap-2 col-span-4">
                                    <span class="material-icons">description</span>
                                    Visualizar PDF
                                </button>

                                <button type="button" class="btn btn-success gap-2 col-span-4">
                                    <span class="material-icons">supervisor_account</span>
                                    Visualizar PDF Gestor
                                </button>

                                <button type="button" class="btn btn-success gap-2 col-span-4">
                                    <span class="material-icons">engineering</span>
                                    Visualizar PDF Mecânico
                                </button>
                                
                            </div>
                            """),
                            css_class="mb-8 p-4 bg-base-200/50 rounded-lg",
                        ),
                        # Observação
                        Div(
                            HTML('<h4 class="font-bold text-lg mb-2 border-b-1 border-gray-300">Observação</h4>'),
                            HTML(f"""
                            <div class="flex flex-col gap-3">

                                <textarea 
                                    class="textarea textarea-bordered w-full"
                                    maxlength="250"
                                    rows="4"
                                    placeholder="Digite uma observação para o PDF (máx. 250 caracteres)..."
                                    id="budget-observation"
                                >{saved_observation}</textarea>

                                <div class="flex justify-between items-center text-sm text-gray-500">
                                    <span id="obs-counter">0 / 250</span>

                                    <button type="button" class="btn btn-sm btn-primary gap-2" onclick="saveObservation({budget.pk})">
                                        <span class="material-icons">save</span>
                                        Salvar observação
                                    </button>
                                </div>

                            </div>

                            <script>
                                const textarea = document.getElementById('budget-observation');
                                const counter = document.getElementById('obs-counter');

                                if (textarea && counter) {{
                                    textarea.addEventListener('input', () => {{
                                        counter.textContent = `${{textarea.value.length}} / 250`;
                                    }});
                                }}
                            </script>
                            """),
                            css_class="mb-8 p-4 bg-base-200/50 rounded-lg",
                        ),
                        # Aprovação
                        Div(
                            HTML('<h4 class="font-bold text-lg mb-2 border-b-1 border-gray-300">Aprovação</h4>'),
                            HTML(f"""
                            <div class="flex flex-col text-center gap-3 grid grid-cols-12">

                                <button type="button" class="btn btn-error gap-2 col-span-4" onclick="updateBudgetStatus({budget.pk}, 'cancel')">
                                    <span class="material-icons">close</span>
                                    Cancelar Orçamento
                                </button>

                                <button type="button" class="btn btn-success gap-2 col-span-4" onclick="updateBudgetStatus({budget.pk}, 'approve')">
                                    <span class="material-icons">check_circle</span>
                                    Aprovar Orçamento
                                </button>

                                <button type="button" class="btn btn-warning gap-2 col-span-4" onclick="updateBudgetStatus({budget.pk}, 'reject')">
                                    <span class="material-icons">lock</span>
                                    Reprovar Orçamento
                                </button>

                            </div>
                            """),
                            css_class="mb-8 p-4 bg-base-200/50 rounded-lg",
                        ),
                        css_class="sticky",
                    ),
                    css_class="col-span-12 lg:col-span-6",
                ),
                css_class="grid grid-cols-1 lg:grid-cols-12 gap-8 items-stretch",
            ),
        )
