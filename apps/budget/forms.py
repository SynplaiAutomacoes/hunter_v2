from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Div, Field, Layout
from django import forms
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from djmoney.money import Money

from decimal import Decimal

from apps.budget.models import Budget, BudgetImage, BudgetItem, Defect
from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.checklist.models import Checklist
from apps.collaborators.models import WorkshopCollaborator
from apps.core.utils import alert_confirm_layout
from apps.core.widgets import CalendarDateInput, DurationInput, MoneyInput, NumberInput, SelectInput, TextInput
from apps.customer.models import Vehicle
from apps.quote.models.investigative_questions import InvestigativeQuestion, InvestigativeResponse


class MultipleFileInput(forms.FileInput):
    """Custom widget to support multiple file uploads with preview"""
    allow_multiple_selected = True
    template_name = "widgets/multiple_image_input.html"

    def __init__(self, attrs=None):
        if attrs is None:
            attrs = {}
        attrs['multiple'] = True
        super().__init__(attrs)

    def value_from_datadict(self, data, files, name):
        if hasattr(files, 'getlist'):
            return files.getlist(name)
        return files.get(name)


class BudgetStep1Form(forms.ModelForm):
    workshop = forms.CharField(label="Empresa", widget=TextInput(attrs={"readonly": "readonly"}), required=False)
    cost_estimator = forms.CharField(label="Orçamentista", widget=TextInput(attrs={"readonly": "readonly"}), required=False)
    vehicle = forms.ModelChoiceField(label="Veículo", queryset=Vehicle.objects.none(), required=False, widget=SelectInput())

    class Meta:
        model = Budget
        fields = ["workshop", "cost_estimator", "entry_date", "customer", "vehicle", "current_km", "fuel_level"]
        widgets = {
            "entry_date": CalendarDateInput(),
            "customer": SelectInput(attrs={"x-model": "customerId", "@change": "customerId = $el.value; vehicleId = '';"}),
            "current_km": NumberInput(),
            "fuel_level": SelectInput(),
        }

    def __init__(self, *args, **kwargs):
        self.workshop = kwargs.pop("workshop", None)
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)

        self.fields["customer"].widget.attrs.update(
            {
                "x-model": "customerId",
                "hx-get": reverse_lazy("budget:customer-detail"),
                "hx-trigger": "change",
                "hx-target": "#resumo-cliente",
                "@change": "customerId = $el.value; vehicleId = ''; updateVehicleList($el.value);",
            }
        )

        self.fields["vehicle"].widget.attrs.update(
            {
                "x-model": "vehicleId",
                ":disabled": "!customerId",
                ":class": "{ 'cursor-not-allowed': !customerId }",
                "hx-get": reverse_lazy("budget:vehicle-detail"),
                "hx-trigger": "change",
                "hx-target": "#resumo-veiculo",
                "hx-include": "[name='customer']",
            }
        )

        self.fields["vehicle"].widget.attrs.update({"id": "id_vehicle"})

        # Preenchimento inicial
        if self.workshop:
            workshop_name = self.workshop.name
            self.fields["workshop"].initial = workshop_name
            self.initial["workshop"] = workshop_name
            self.fields["customer"].queryset = self.fields["customer"].queryset.filter(workshop=self.workshop)

        if self.instance:
            user = self.instance.cost_estimator
            if user:
                display_name = user.get_full_name() or user.username
                self.fields["cost_estimator"].initial = display_name
                self.initial["cost_estimator"] = display_name

            customer_id = self.data.get("customer") or (self.instance.customer_id if self.instance.customer else None)
            if customer_id:
                self.fields["vehicle"].queryset = Vehicle.objects.filter(customer_id=customer_id)
            else:
                self.fields["vehicle"].queryset = Vehicle.objects.none()

        if not self.instance.pk:
            self.fields["entry_date"].initial = timezone.now().date()
            self.fields["current_km"].initial = None
            self.fields["fuel_level"].initial = None

        if self.request and self.request.user:
            user = self.request.user
            self.fields["cost_estimator"].initial = user.get_full_name() or user.username

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            HTML(r"""
            <script>
                document.addEventListener('input', function (e) {
                    if (e.target && e.target.name === 'current_km') {
                        let value = e.target.value.replace(/\D/g, '');
                        e.target.value = value.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
                    }
                });
                
                async function updateVehicleList(customerId) {
                    // 1. Busca os dados da sua VehicleListView (JSON)
                    const response = await fetch(`/budget/get-vehicles/?customer=${customerId}`);
                    const vehicles = await response.json();
                    
                    // 2. Localiza o Alpine Data do widget de veículo
                    // 'id_vehicle' deve ser o ID do input hidden dentro do widget
                    const vehicleEl = document.querySelector('[name="vehicle"]').closest('[x-data]');
                    const vehicleData = Alpine.$data(vehicleEl);
            
                    // 3. Limpa o valor atual e as opções no DOM
                    vehicleData.clear();
                    const optionsUl = vehicleEl.querySelector('ul[role="listbox"]');
                    
                    // Remove todos os <li> que não sejam o "Limpar seleção"
                    optionsUl.querySelectorAll('li[data-value]').forEach(li => li.remove());
            
                    // 4. Adiciona as novas opções dinamicamente
                    vehicles.forEach(v => {
                        const li = document.createElement('li');
                        li.className = 'relative cursor-pointer select-none py-2 pl-3 pr-9 hover:bg-primary hover:text-white group transition-colors';
                        li.setAttribute('data-value', v.id);
                        li.setAttribute('data-label', v.label);
                        li.innerHTML = `<span class="block truncate">${v.label}</span>`;
                        
                        // Adiciona o evento de clique que o seu widget espera
                        li.addEventListener('click', () => vehicleData.select(li));
                        
                        optionsUl.appendChild(li);
                    });
                }
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
                                HTML("""<button type="button" class="btn btn-circle mb-2" :class="customerId ? 'btn-warning' : 'btn-primary'"
                                                                @click="const url = customerId ? `/customer/quick-update/${customerId}/` : '/customer/quick-create/';
                                                                        htmx.ajax('GET', url, {target: '#modal-container', swap: 'innerHTML'});
                                                                        document.getElementById('form_modal').showModal();">
                                                                <span class="material-icons" x-text="customerId ? 'edit' : 'person_add'"></span>
                                                            </button>"""),
                                css_class="flex items-end gap-2 w-full",
                            ),
                            Div(
                                Field("vehicle", wrapper_class="flex-1 mb-0"),
                                HTML("""<button type="button" class="btn btn-circle mb-2" 
                                                                :class="!customerId ? 'btn-disabled opacity-50' : (vehicleId ? 'btn-warning' : 'btn-primary')" 
                                                                :disabled="!customerId"
                                                                @click="const url = vehicleId ? `/customer/vehicle/quick-update/${vehicleId}/` : `/customer/vehicle/quick-create/?customer_id=${customerId}`;
                                                                        htmx.ajax('GET', url, {target: '#modal-container', swap: 'innerHTML'});
                                                                        document.getElementById('form_modal').showModal();">
                                                                <span class="material-icons" x-text="vehicleId ? 'edit' : 'directions_car_filled'"></span>
                                                            </button>"""),
                                css_class="flex items-end gap-2 w-full",
                                **{":class": "{ 'pointer-events-none': !customerId }"},
                            ),
                            x_data=f"{{ customerId: '{self.instance.customer.id if self.instance and self.instance.customer else ''}', vehicleId: '{self.instance.vehicle.id if self.instance and self.instance.vehicle else ''}' }}",
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
                        Div(HTML(render_to_string("budget/partials/components/customer_resume.html", {"customer": self.instance.customer})), id="resumo-cliente", css_class="mb-6 overflow-x-auto"),
                        # Veículo
                        HTML('<h4 class="text-lg font-bold mb-2">Veículo</h4>'),
                        Div(HTML(render_to_string("budget/partials/components/vehicle_resume.html", {"vehicle": self.instance.vehicle})), id="resumo-veiculo", css_class="overflow-x-auto"),
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
                    widget=forms.NumberInput(attrs={"class": "range range-primary w-full", "type": "range", "step": "1", "min": "1", "max": "10", "oninput": f"document.getElementById('{display_id}').innerText = this.value"}),
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
                Div(Field("problem_description", wrapper_class="flex flex-col h-full", css_class="flex-1 !bg-transparent"), css_class="col-span-12 lg:col-span-6 flex flex-col"),
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
    images = forms.FileField(label=False, required=False, widget=MultipleFileInput(attrs={'accept': 'image/*', 'class': 'file-input file-input-bordered w-full'}))

    class Meta:
        model = Budget
        fields = ["collaborator", "technical_diagnosis"]
        widgets = {
            "technical_diagnosis": forms.Textarea(attrs={"rows": 10, "placeholder": "Descreva detalhadamente as observações técnicas, diagnósticos preliminares, testes realizados...", "class": "textarea textarea-bordered w-full !bg-transparent"}),
        }

    def __init__(self, *args, **kwargs):
        self.workshop = kwargs.pop("workshop", None)
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)

        if self.workshop:
            self.fields["collaborator"].queryset = WorkshopCollaborator.objects.filter(workshop=self.workshop, is_active=True)
            self.fields["checklist"].queryset = Checklist.objects.filter(workshop=self.workshop)

        if self.instance.pk:
            img_obj = self.instance.budget_image.first()
            if img_obj:
                img_obj.url = reverse("budget:image_view", kwargs={"pk": img_obj.pk})
                self.fields["image"].initial = img_obj

        initial_collab_id = ""
        if self.instance.pk and self.instance.collaborator:
            initial_collab_id = self.instance.collaborator.id

        self.fields["collaborator"].widget.attrs.update(
            {
                "x-model": "collaboratorId",
            }
        )

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            HTML(f"""<script>
                    function addDefectRow() {{
                        const input = document.getElementById('id_new_defect');
                        const container = document.getElementById('defect-list-container');
                        const text = input.value.trim();
                        if (text === "") return;
                        const id = 'new-' + Date.now();
                        const html = `<div class="badge badge-lg badge-ghost gap-2 py-5 mb-2 mr-2 pr-1" id="defect-${{id}}">
                                <input type="hidden" name="defects_list" value="${{text}}">
                                <span class="font-medium">${{text}}</span>
                                <button type="button" onclick="this.parentElement.remove()" class="btn btn-ghost btn-xs btn-circle text-error">
                                    X
                                </button>
                            </div>`;
                        container.insertAdjacentHTML('beforeend', html);
                        input.value = "";
                        input.focus();
                    }}
                    
                    document.body.addEventListener('collaboratorSaved', function(evt) {{
                        const modal = document.getElementById('form_modal');
                        if (modal) modal.close();
                        
                        // Get current collaborator selection
                        const selectElement = document.querySelector('#id_collaborator');
                        const currentValue = selectElement ? selectElement.value : '';
                        
                        // Save to localStorage before refresh
                        if (currentValue) {{
                            localStorage.setItem('budget_step3_collaborator', currentValue);
                        }}
                        
                        // Refresh the collaborator dropdown via HTMX
                        const budgetId = {self.instance.pk if self.instance.pk else 'null'};
                        if (budgetId) {{
                            const savedId = localStorage.getItem('budget_step3_collaborator');
                            const url = `/budget/${{budgetId}}/collaborator-field/` + (savedId ? `?selected=${{savedId}}` : '');
                            
                            htmx.ajax('GET', url, {{
                                target: '#collaborator-field-container',
                                swap: 'outerHTML'
                            }}).then(() => {{
                                // After refresh, update Alpine.js model with the saved value
                                if (savedId) {{
                                    setTimeout(() => {{
                                        const alpineContainer = document.querySelector('[x-data*="collaboratorId"]');
                                        if (alpineContainer && typeof Alpine !== 'undefined') {{
                                            const alpineData = Alpine.$data(alpineContainer);
                                            if (alpineData) {{
                                                alpineData.collaboratorId = savedId;
                                            }}
                                        }}
                                    }}, 100);
                                }}
                                
                                // Clear localStorage after use
                                localStorage.removeItem('budget_step3_collaborator');
                            }});
                        }}
                    }});
                </script>"""),
            Div(
                # Coluna Esquerda
                Div(
                    # Diagnóstico Técnico
                    Div(
                        HTML('<h3 class="text-2xl font-bold mb-4">Diagnóstico Técnico</h3>'),
                        HTML(f'''
                            {{% include "budget/partials/components/collaborator_field.html" with field=form.collaborator initial_collab_id="{initial_collab_id}" %}}
                        '''),
                        #
                        HTML('<label class="block text-gray-700 font-bold mb-2">Adicione os defeitos encontrados durante a inspeção</label>'),
                        Div(id="defect-list-container", css_class="mb-4 p-4 border-2 border-dashed border-gray-200 rounded-lg min-h-[120px] flex flex-wrap content-start"),
                        Div(
                            Div(Field("new_defect", wrapper_class="mb-0"), css_class="flex-1"),
                            HTML("""<button type="button" class="btn btn-primary ml-2" onclick="addDefectRow()">
                                    Adicionar</button>"""),
                            css_class="flex items-end mb-8",
                        ),
                        css_class="mb-8",
                    ),
                    # Checklist para Impressão
                    Div(
                        HTML('<h3 class="text-2xl font-bold mb-4">Checklist para Impressão</h3>'),
                        Div(
                            Div(Field("checklist", wrapper_class="mb-0"), css_class="flex-1"),
                            HTML("""<button type="button" class="btn btn-primary ml-2">
                                            Imprimir</button>"""),
                            css_class="flex items-end mb-8",
                        ),
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
                        HTML('<div id="existing-images-container" class="grid grid-cols-2 gap-4 mb-4"></div>'),
                        Field("images", label=False, wrapper_class="mb-0"),
                        HTML('<p class="text-sm text-gray-500 mt-2">Você pode selecionar múltiplas imagens. Máximo de 10 imagens por orçamento.</p>'),
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

            # Inject existing images with delete buttons
            existing_images = self.instance.ordered_images
            if existing_images.exists():
                import base64
                images_html = []
                for img in existing_images:
                    if img.content:
                        img_data = base64.b64encode(img.content).decode('utf-8')
                        img_src = f"data:{img.content_type or 'image/jpeg'};base64,{img_data}"
                        img_name = img.content_name or f"Imagem {img.id}"
                        images_html.append(f"""
                        <div class="relative border-2 border-gray-200 rounded-lg p-2 hover:border-primary transition-colors" id="image-{img.id}">
                            <img src="{img_src}" alt="{img_name}" class="w-full h-32 object-cover rounded mb-2">
                            <input type="hidden" name="images_to_delete" value="" id="delete-flag-{img.id}">
                            <button type="button" 
                                    onclick="document.getElementById('delete-flag-{img.id}').value='{img.id}'; document.getElementById('image-{img.id}').classList.add('opacity-50', 'line-through'); this.disabled=true; this.textContent='Será excluída';"
                                    class="btn btn-xs btn-error w-full gap-1"
                                    title="Marcar para exclusão">
                                <span class="material-icons text-xs">delete</span>
                                Remover
                            </button>
                        </div>
                        """)

                images_json = "".join(images_html)
                self.helper.layout.append(
                    HTML(f"""
                    <script>
                        document.getElementById('existing-images-container').innerHTML = `{images_json}`;
                    </script>
                    """)
                )

    def clean(self):
        cleaned_data = super().clean()

        # Validate images if uploaded
        if self.files:
            new_images = self.files.getlist("images")
            if new_images:
                # Check file extensions
                allowed_extensions = ['jpg', 'jpeg', 'png', 'gif']
                for img in new_images:
                    ext = img.name.split('.')[-1].lower() if '.' in img.name else ''
                    if ext not in allowed_extensions:
                        raise forms.ValidationError(f"Formato de arquivo '{img.name}' não permitido. Use: {', '.join(allowed_extensions)}")

                    # Check file size (10MB max)
                    if img.size > 10 * 1024 * 1024:
                        raise forms.ValidationError(f"Imagem '{img.name}' excede o tamanho máximo de 10MB ({(img.size / 1024 / 1024):.2f}MB).")

                # Check total count if instance exists
                if self.instance and self.instance.pk:
                    existing_count = self.instance.budget_image.count()
                    images_to_delete = self.data.getlist("images_to_delete")
                    delete_count = len([img_id for img_id in images_to_delete if img_id.strip()])
                    final_count = existing_count - delete_count + len(new_images)

                    if final_count > 10:
                        raise forms.ValidationError(f"Máximo de 10 imagens permitido. Você terá {final_count} imagens após esta operação.")

        return cleaned_data

    def save(self, commit=True):
        budget = super().save(commit=commit)

        # Processamento dos Defeitos (Somente no Save final)
        if "defects_list" in self.request.POST:
            defect_names = self.request.POST.getlist("defects_list")

            # Sincronização: remove antigos e adiciona novos
            budget.defects.all().delete()
            for name in defect_names:
                if name.strip():
                    Defect.objects.create(workshop=self.workshop, budget=budget, name=name.strip())

        # Handle image deletion - delete specific images marked for deletion
        images_to_delete = self.request.POST.getlist("images_to_delete")
        if images_to_delete:
            # Filter out empty strings
            image_ids = [img_id for img_id in images_to_delete if img_id.strip()]
            if image_ids:
                BudgetImage.objects.filter(id__in=image_ids, budget=budget).delete()

        # Handle new images upload - append to existing images
        new_images = self.request.FILES.getlist("images")
        if new_images:
            # Check total images limit (existing + new)
            existing_count = budget.budget_image.count()
            total_count = existing_count + len(new_images)

            if total_count > 10:
                from django.core.exceptions import ValidationError
                raise ValidationError(f"Máximo de 10 imagens permitido. Você tem {existing_count} imagens e está tentando adicionar {len(new_images)}.")

            for new_image in new_images:
                if new_image and hasattr(new_image, "read"):
                    # Validate file size (10MB max)
                    if new_image.size > 10 * 1024 * 1024:
                        from django.core.exceptions import ValidationError
                        raise ValidationError(f"Imagem '{new_image.name}' excede o tamanho máximo de 10MB.")

                    BudgetImage.objects.create(
                        workshop=self.workshop,
                        budget=budget,
                        content=new_image.read(),
                        content_name=new_image.name,
                        content_type=getattr(new_image, "content_type", "image/jpeg")
                    )

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
                # Produto: item.product existe OU é local com custo/venda de produto preenchido
                if item.product or (item.is_local and (item.product_cost_price.amount > 0 or item.product_selling_price.amount > 0 or item.shipping.amount > 0)):
                    products_html += render_to_string("budget/partials/items/item_product_row.html", context)
                # Serviço: item.service existe OU é local com custo/venda de serviço preenchido ou duração
                elif item.service or (item.is_local and (item.service_cost_price.amount > 0 or item.service_selling_price.amount > 0 or item.duration)):
                    services_html += render_to_string("budget/partials/items/item_service_row.html", context)
                # Kit
                elif item.kit:
                    kits_html += render_to_string("budget/partials/items/item_kit_row.html", context)

        if not products_html:
            products_html = '<tr><td colspan="6" class="text-center text-gray-400 py-4">Nenhum produto adicionado</td></tr>'
        if not services_html:
            services_html = '<tr><td colspan="6" class="text-center text-gray-400 py-4">Nenhum serviço adicionado</td></tr>'
        if not kits_html:
            kits_html = '<tr><td colspan="5" class="text-center text-gray-400 py-4">Nenhum kit adicionado</td></tr>'

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            alert_confirm_layout(),
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
                                            <th class="w-full">DESCRIÇÃO</th>
                                            <th class="text-center">QTD.</th>
                                            <th>CUSTO</th>
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
                                            <th class="w-full">DESCRIÇÃO</th>
                                            <th class="text-center">QTD.</th>
                                            <th>CUSTO</th>
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
                                            <th class="w-full">NOME</th>
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
                            HTML(render_to_string("budget/partials/components/budget_summary.html", {"budget": budget})),
                            css_class="sticky top-4",
                            css_id="budget-summary",
                        ),
                        css_class="p-6 h-fit text-lg",
                    ),
                    css_class="col-span-12 lg:col-span-5 mt-10 lg:mt-0",
                ),
                css_class="grid grid-cols-1 lg:grid-cols-12 gap-4",
            ),
        )

        # Adicionar listener para atualizar resumo dinamicamente
        self.helper.layout.append(
            HTML(f"""
            <script>
            document.body.addEventListener('update-summary', function() {{
                // Recarrega apenas a coluna de resumo via HTMX
                htmx.ajax('GET', '{reverse("budget:budget_summary", kwargs={"budget_id": budget.pk})}', {{
                    target: '#budget-summary',
                    swap: 'innerHTML'
                }});
            }});
            </script>
            """)
        )

    def save(self, commit=True):
        # Como este form é estrutural, o save lida com persistência de estado da etapa
        return super().save(commit=commit)


class BudgetStep5Form(forms.ModelForm):
    slider = forms.IntegerField(
        required=False,
        widget=forms.NumberInput(
            attrs={
                "class": "w-full centered-range",
                "type": "range",
                "min": "-100",
                "max": "100",
                "step": "5"}))

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
        self.fields["slider"].widget.attrs.update(
            {"hx-post": reverse("budget:update_slider", args=[self.instance.pk]), "hx-trigger": "change",
             "hx-swap": "none"})

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

        duracao_total = dados.get('duracao_total') or "00h 00m"

        def parse_duracao_em_horas(duracao):
            try:
                h, m = duracao.replace("h", "").replace("m", "").split()
                return Decimal(h) + (Decimal(m) / Decimal(60))
            except Exception:
                return Decimal("0")

        duracao_em_horas = parse_duracao_em_horas(duracao_total)
        custo_total_mao_obra = custo_hora_mecanico * duracao_em_horas

        # Valores Venda
        venda_pecas = dados.get('venda_pecas') or zerado
        venda_servico_terceiros = dados.get('venda_servico_terceiro') or zerado
        venda_mao_obra = dados.get('venda_mao_obra') or zerado

        # Extra
        metodo_precificacao = dados.get('method_name') or ""
        duracao_total = dados.get('duracao_total') or "00h 00m"
        lucro_operacional = dados.get('lucro_operacional') or zerado
        rentabilidade = dados.get('rentabilidade') or 0

        status_cor = "text-error" if rentabilidade < 60 else "text-warning" if (
                    60 <= rentabilidade < 70) else "text-success"
        status_texto = "Ruim" if rentabilidade < 60 else "Médio" if (60 <= rentabilidade < 70) else "Bom"

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            HTML(f"""
            <style>
                input[type="range"].centered-range {{
                  -webkit-appearance: none;
                  -moz-appearance: none;
                  width: 100%;
                  height: 8px;
                  background: transparent;
                }}

                input[type="range"].centered-range::-webkit-slider-runnable-track {{
                  height: 8px;
                  border-radius: 999px;
                  background: linear-gradient(
                    to right,
                    #e5e7eb var(--left),
                    #2563eb var(--left),
                    #2563eb var(--right),
                    #e5e7eb var(--right)
                  );
                }}

                input[type="range"].centered-range::-webkit-slider-thumb {{
                  -webkit-appearance: none;
                  width: 18px;
                  height: 18px;
                  background: #007bff;
                  border-radius: 50%;
                  margin-top: -5px;
                  cursor: pointer;
                }}

                input[type="range"].centered-range::-moz-range-track {{
                  height: 8px;
                  border-radius: 999px;
                  background: linear-gradient(
                    to right,
                    #e5e7eb var(--left),
                    #2563eb var(--left),
                    #2563eb var(--right),
                    #e5e7eb var(--right)
                  );
                }}

                input[type="range"].centered-range::-moz-range-thumb {{
                  width: 18px;
                  height: 18px;
                  background: #007bff;
                  border-radius: 50%;
                  border: none;
                }}
            </style>
            <script>
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
                        function initSlider() {{
                            const slider = document.querySelector('input[name="slider"]');
                            const labelPecaPct = document.getElementById('val-peca');
                            const labelMOPct = document.getElementById('val-mo');
                            const vendaPecaEl = document.getElementById('display-venda-pecas');
                            const vendaMOEl = document.getElementById('display-venda-mo');
                    
                            if (!slider || !vendaPecaEl || !vendaMOEl) return;
                    
                            const basePeca = parseFloat(vendaPecaEl.dataset.baseVal);
                            const baseMO = parseFloat(vendaMOEl.dataset.baseVal);
                            const costPeca = parseFloat(vendaPecaEl.dataset.costVal);
                            const fretePeca = parseFloat(vendaPecaEl.dataset.freteVal || 0);
                            const minVendaPeca = costPeca + fretePeca;
                            const costMO = parseFloat(vendaMOEl.dataset.costVal);
                    
                            const totalLucro = Math.max(
                                (basePeca + baseMO) - (minVendaPeca + costMO),
                                0
                            );
                    
                            const format = (v) =>
                                "R$ " + v.toLocaleString("pt-BR", {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }}
                            );
                    
                            function updateFill(val) {{
                                const min = -100;
                                const max = 100;
                                const center = 50;
                                const percent = ((val - min) / (max - min)) * 100;
                    
                                if (val === 0) {{
                                    slider.style.setProperty('--left', `${{center}}%`);
                                    slider.style.setProperty('--right', `${{center}}%`);
                                }} else if (val < 0) {{
                                    slider.style.setProperty('--left', `${{percent}}%`);
                                    slider.style.setProperty('--right', `${{center}}%`);
                                }} else {{
                                    slider.style.setProperty('--left', `${{center}}%`);
                                    slider.style.setProperty('--right', `${{percent}}%`);
                                }}
                            }}
                    
                            function update(val) {{
                                val = parseInt(val || 0);
                    
                                let lucroPeca = 0;
                                let lucroMO = 0;
                    
                                if (val < 0) {{
                                    lucroPeca = totalLucro * Math.abs(val) / 100;
                                    lucroMO = totalLucro - lucroPeca;
                                }} else if (val > 0) {{
                                    lucroMO = totalLucro * val / 100;
                                    lucroPeca = totalLucro - lucroMO;
                                }} else {{
                                    lucroPeca = basePeca - costPeca;
                                    lucroMO = baseMO - costMO;
                                }}
                    
                                vendaPecaEl.textContent = format(minVendaPeca + lucroPeca);
                                vendaMOEl.textContent = format(costMO + lucroMO);
                    
                                labelPecaPct.textContent = val < 0 ? Math.abs(val) : 0;
                                labelMOPct.textContent = val > 0 ? val : 0;
                    
                                updateFill(val);
                            }}
                    
                            slider.addEventListener('input', e => update(e.target.value));
                            update(slider.value || 0);
                        }}
                    
                        document.addEventListener('DOMContentLoaded', initSlider);
                        document.body.addEventListener('htmx:afterSettle', initSlider);
                    }})();
                </script>"""),
            Div(
                HTML('<h3 class="text-2xl font-bold col-span-12">Método de Precificação</h3>'),
                # Coluna Esquerda
                Div(
                    Div(
                        HTML(
                            f'<h3 class="text-3xl font-bold mb-2 border-b-3 border-[#007bff] text-[#222a2c] text-center">Método {metodo_precificacao}</h3>'),
                        Div(
                            # Grid de Custos vs Vendas
                            Div(
                                HTML(f"""
                                <div class="grid grid-cols-1 md:grid-cols-2 mt-7 gap-x-8 gap-y-3 text-base text-[#222a2c] font-semibold">

                                    <!-- COLUNA ESQUERDA — CUSTOS -->
                                    <div class="grid grid-cols-12 border bg-white">
                                        <span class="col-span-8 p-2 bg-gray-50">Custo de Peças</span>
                                        <span class="col-span-4 p-2 border-l">{custo_pecas}</span>
                                    </div>

                                    <div class="grid grid-cols-12 border bg-white">
                                        <span class="col-span-8 p-2 bg-gray-50">Valor de Venda de Peças</span>
                                        <span id="display-venda-pecas"
                                                class="col-span-4 p-2 border-l whitespace-nowrap"
                                                data-base-val="{venda_pecas.amount}"
                                                data-cost-val="{custo_pecas.amount}"
                                                data-frete-val="{custo_frete_pecas.amount}">
                                            {venda_pecas}
                                        </span>
                                    </div>

                                    <div class="grid grid-cols-12 border bg-white">
                                        <span class="col-span-8 p-2 bg-gray-50">Custo de Frete de Peças</span>
                                        <span class="col-span-4 p-2 border-l">{custo_frete_pecas}</span>
                                    </div>

                                    <div class="grid grid-cols-12 border bg-white">
                                        <span class="col-span-8 p-2 bg-gray-50">Valor de Venda de Serviço de Terceiros</span>
                                        <span class="col-span-4 p-2 border-l">{venda_servico_terceiros}</span>
                                    </div>

                                    <div class="grid grid-cols-12 border bg-white">
                                        <span class="col-span-8 p-2 bg-gray-50">Custo de Serviço de Terceiros</span>
                                        <span class="col-span-4 p-2 border-l">{custo_servico_terceiros}</span>
                                    </div>

                                    <div class="grid grid-cols-12"></div>

                                    <div class="grid grid-cols-12 border bg-white">
                                        <span class="col-span-8 p-2 bg-gray-50">Custo da Hora do Mecânico</span>
                                        <span class="col-span-4 p-2 border-l">{custo_hora_mecanico}</span>
                                    </div>

                                    <div class="grid grid-cols-12 border bg-white">
                                        <span class="col-span-8 p-2 bg-gray-50">Valor de Venda de Mão de Obra</span>
                                        <span id="display-venda-mo"
                                              class="col-span-4 p-2 border-l"
                                              data-base-val="{venda_mao_obra.amount}"
                                              data-cost-val="{custo_total_mao_obra.amount}">
                                            {venda_mao_obra}
                                        </span>
                                    </div>

                                    <div class="grid grid-cols-12 border bg-white font-semibold">
                                        <span class="col-span-8 p-2 bg-gray-50">Custo Total da Mão de Obra</span>
                                        <span class="col-span-4 p-2 border-l">{custo_total_mao_obra}</span>
                                    </div>

                                    <div class="grid grid-cols-12 border bg-white">
                                        <span class="col-span-8 p-2 bg-gray-50">Duração Total</span>
                                        <span class="col-span-4 p-2 border-l">{duracao_total}</span>
                                    </div>

                                    <!-- RESULTADO (respiro visual) -->
                                    <div class="md:col-span-2 h-2"></div>

                                    <div class="grid grid-cols-12 border bg-white font-bold">
                                        <span class="col-span-8 p-2 bg-gray-50">Lucro Operacional</span>
                                        <span class="col-span-4 p-2 border-l">{lucro_operacional}</span>
                                    </div>

                                    <div class="grid grid-cols-12 border border-warning bg-white">
                                        <span class="col-span-8 p-2 bg-gray-50">Rentabilidade</span>
                                        <span class="col-span-4 p-2 border-l text-warning">
                                            {rentabilidade:.2f}% ({status_texto})
                                        </span>
                                    </div>

                                    <div class="grid grid-cols-12 border bg-white">
                                        <span class="col-span-8 p-2 bg-gray-50">MLO</span>
                                        <span class="col-span-4 p-2 border-l">0.00</span>
                                    </div>

                                    <div class="grid grid-cols-12 border bg-white">
                                        <span class="col-span-8 p-2 bg-gray-50">MLR</span>
                                        <span class="col-span-4 p-2 border-l">0.00</span>
                                    </div>

                                </div>
                                """)
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
                            HTML("""
                                <div class="flex justify-between mb-1">
                                    <span class="text-sm font-bold">Peça: <span id="val-peca">0</span>%</span>
                                    <span class="text-sm font-bold">Mão de Obra: <span id="val-mo">0</span>%</span>
                                </div>
                            """),
                            Field(
                                "slider",
                                label=False,
                                help_text=False,
                                wrapper_class="w-full"
                            ),
                            HTML(
                                '<p class="text-sm text-gray-500 font-semibold italic">Deslize para a esquerda para aumentar Peça, ou para direita para aumentar Mão de obra</p>'),
                            css_class="mb-8 p-4 bg-base-200/50 rounded-lg",
                        ),
                        # Desconto
                        Div(HTML('<h4 class="font-bold text-lg mb-2">Desconto</h4>'),
                            Field("discount_value", wrapper_class="col-span-12 lg:col-span-4"),
                            css_class="mb-8 p-4 bg-base-200/50 rounded-lg"),
                        # Valor Final
                        Div(
                            HTML(
                                '<h4 class="font-bold text-lg mb-2 text-center border-b-1 border-gray-300">Valor Final</h4>'),
                            HTML(
                                '<h5 class="font-semibold text-lg mb-2 text-center">Valor do Orçamento com desconto aplicado:</h5>'),
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
        has_local_items = budget.items.filter(is_local=True).exists() if budget.pk else False

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
                # Produto: item.product existe OU é local com custo/venda de produto preenchido
                if item.product or (item.is_local and (item.product_cost_price.amount > 0 or item.product_selling_price.amount > 0 or item.shipping.amount > 0)):
                    products_html += render_to_string("budget/partials/items/item_product_row.html", context)
                # Serviço: item.service existe OU é local com custo/venda de serviço preenchido ou duração
                elif item.service or (item.is_local and (item.service_cost_price.amount > 0 or item.service_selling_price.amount > 0 or item.duration)):
                    services_html += render_to_string("budget/partials/items/item_service_row.html", context)
                # Kit
                elif item.kit:
                    kits_html += render_to_string("budget/partials/items/item_kit_row.html", context)

        if not products_html:
            products_html = '<tr><td colspan="5" class="text-center text-gray-400 py-4">Nenhum produto adicionado</td></tr>'
        if not services_html:
            services_html = '<tr><td colspan="5" class="text-center text-gray-400 py-4">Nenhum serviço adicionado</td></tr>'
        if not kits_html:
            kits_html = """
                <tr>
                    <td colspan="5" class="text-center text-gray-400 py-4">
                        Nenhum kit adicionado
                    </td>
                </tr>
            """

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            alert_confirm_layout(),
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
                    
                    async function updateBudgetStatus(budgetId, status) {
                        const confirmed = await customConfirm("Você tem certeza que deseja alterar o status deste orçamento?");
                        if (!confirmed) return;
                    
                        fetch(`/budget/update-status/${budgetId}/${status}`, {
                            method: 'POST',
                            headers: { 'X-CSRFToken': '{{ csrf_token }}' }
                        }).then(() => {
                            window.location.href = "{% url 'budget:budget_list' %}";
                        });
                    }
                    
                    function openKitModal(button) {
                        const modal = document.getElementById('kitModal');
                    
                        const title = document.getElementById('kit-modal-title');
                        const productsList = document.getElementById('kit-modal-products');
                        const servicesList = document.getElementById('kit-modal-services');
                    
                        const productsCount = document.getElementById('kit-products-count');
                        const servicesCount = document.getElementById('kit-services-count');
                    
                        const productsCountSide = document.getElementById('kit-products-count-side');
                        const servicesCountSide = document.getElementById('kit-services-count-side');
                    
                        title.textContent = button.dataset.kitName;
                    
                        productsList.innerHTML = '';
                        servicesList.innerHTML = '';
                    
                        const products = button.dataset.kitProductsList
                            .split('|').map(i => i.trim()).filter(Boolean);
                    
                        const services = button.dataset.kitServicesList
                            .split('|').map(i => i.trim()).filter(Boolean);
                    
                        productsCount.textContent = products.length;
                        servicesCount.textContent = services.length;
                    
                        productsCountSide.textContent = products.length;
                        servicesCountSide.textContent = services.length;
                    
                        products.forEach(s => {
                            const li = document.createElement('li');
                            li.className = "flex items-start gap-3";
                            li.innerHTML = `
                              <span class="material-icons text-info text-sm mt-0.5 flex-shrink-0">circle</span>
                              <span class="break-words break-all whitespace-normal">
                                ${s}
                              </span>
                            `;
                            productsList.appendChild(li);
                        });
                    
                        services.forEach(s => {
                            const li = document.createElement('li');
                            li.className = "flex items-start gap-3";
                            li.innerHTML = `
                              <span class="material-icons text-info text-sm mt-0.5 flex-shrink-0">circle</span>
                              <span class="break-words break-all whitespace-normal">
                                ${s}
                              </span>
                            `;
                            servicesList.appendChild(li);
                        });
                    
                        modal.showModal();
                    }
                    
                    function closeKitModal() {
                        const modal = document.getElementById('kitModal');
                        if (modal) {
                            modal.close();
                        }
                    }
            </script>"""),
            Div(
                HTML('<h3 class="text-2xl font-bold col-span-12">Revisão e Confirmação</h3>'),
                # Coluna Esquerda
                Div(
                    HTML('<div class="border-t-2 mb-4 mt-0"></div>'),
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
                                                            <th>CUSTO</th>
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
                                                            <th>CUSTO</th>
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
                                                            <th class="text-center">AÇÕES</th>
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
                            HTML(f"""
                            <div class="flex flex-col gap-3 text-center grid grid-cols-12">
                                <button type="button" class="btn btn-success gap-2 col-span-4" onclick="window.dispatchEvent(new CustomEvent('open-pdf-modal', {{ detail: {{ url: '{reverse('budget:visualizar_pdf', args=[budget.pk])}' }} }}))">
                                    <span class="material-icons">description</span>
                                    Visualizar PDF
                                </button>

                                <button type="button" class="btn btn-success gap-2 col-span-4" onclick="window.dispatchEvent(new CustomEvent('open-pdf-modal', {{ detail: {{ url: '{reverse('budget:visualizar_pdf_gestor', args=[budget.pk])}' }} }}))">
                                    <span class="material-icons">supervisor_account</span>
                                    Visualizar PDF Gestor
                                </button>

                                <button type="button" class="btn btn-success gap-2 col-span-4" onclick="window.dispatchEvent(new CustomEvent('open-pdf-modal', {{ detail: {{ url: '{reverse('budget:visualizar_pdf_mecanico', args=[budget.pk])}' }} }}))">
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

                                <button
                                    type="button"
                                    class="btn gap-2 col-span-4
                                           {{% if form.instance.has_local_items %}}
                                               btn-disabled cursor-not-allowed
                                           {{% else %}}
                                               btn-success
                                           {{% endif %}}"
                                    {{% if not form.instance.has_local_items %}}
                                        onclick="updateBudgetStatus({{{{ form.instance.pk }}}}, 'approve')"
                                    {{% endif %}}
                                    {{% if form.instance.has_local_items %}}
                                        disabled
                                        title="Existem itens não cadastrados no sistema"
                                    {{% endif %}}
                                >
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
            HTML("""
            <dialog id="pdfModal" class="modal" x-data="{ pdfUrl: '' }" @open-pdf-modal.window="pdfUrl = $event.detail.url; $el.showModal()">
              <div class="modal-box max-w-5xl w-full h-[90vh] p-0 flex flex-col">
                <div class="flex items-center justify-between px-6 py-4 border-b bg-base-200">
                    <h3 class="text-xl font-bold flex items-center gap-2">
                        <span class="material-icons">description</span> Visualização do PDF
                    </h3>
                    <div class="flex gap-2">
                        <button type="button" 
                                class="btn btn-sm btn-success gap-2"
                                onclick="const frame = document.querySelector('#pdfModal iframe'); frame.contentWindow.focus(); frame.contentWindow.print();">
                            <span class="material-icons text-sm">download</span> Baixar PDF
                        </button>
                        <button type="button" class="btn btn-sm" onclick="document.getElementById('pdfModal').close()">
                            <span class="material-icons text-sm">close</span>
                        </button>
                    </div>
                </div>
                
                <div class="flex-1 bg-gray-100">
                    <template x-if="pdfUrl">
                        <iframe :src="pdfUrl" class="w-full h-full" frameborder="0"></iframe>
                    </template>
                </div>
              </div>
              <form method="dialog" class="modal-backdrop">
                <button>close</button>
              </form>
            </dialog>"""),
            HTML("""
                <dialog
                    id="kitModal"
                    class="modal"
                    onclick="if(event.target === this) closeKitModal()"
                >
                  <div class="modal-box max-w-5xl w-full max-h-[75vh] p-0 flex flex-col">
                
                    <!-- HEADER -->
                    <div class="flex items-center justify-between px-8 py-5 border-b bg-base-200">
                        <div class="flex items-center gap-4">
                            <div class="p-3 rounded-lg bg-primary/10">
                                <span class="material-icons text-primary text-3xl">inventory_2</span>
                            </div>
                
                            <div>
                                <h3 class="text-2xl font-bold leading-tight" id="kit-modal-title"></h3>
                                <span class="badge badge-primary badge-outline mt-1">
                                    Kit de Serviços
                                </span>
                            </div>
                        </div>
                    </div>
                
                    <!-- BODY -->
                    <div class="p-8 grid grid-cols-1 lg:grid-cols-3 gap-6 flex-1 overflow-y-auto">
                
                        <!-- PRODUTOS (CARD VERTICAL) -->
                        <div class="card bg-base-100 shadow-md border lg:col-span-1">
                            <div class="card-body gap-4">
                                <div class="flex items-center justify-between">
                                    <h4 class="font-semibold text-base flex items-center gap-2">
                                        <span class="material-icons text-info">build</span>
                                        Produtos
                                    </h4>
                                    <span id="kit-products-count" class="badge badge-info"></span>
                                </div>
                
                                <div class="divider my-1"></div>
                
                                <ul
                                    id="kit-modal-products"
                                    class="flex flex-col gap-3 text-sm
                                         max-h-64 overflow-y-auto pr-2
                                         overflow-x-hidden"
                                ></ul>
                            </div>
                        </div>
                
                        <!-- SERVIÇOS (CARD VERTICAL) -->
                        <div class="card bg-base-100 shadow-md border lg:col-span-1">
                            <div class="card-body gap-4">
                                <div class="flex items-center justify-between">
                                    <h4 class="font-semibold text-base flex items-center gap-2">
                                        <span class="material-icons text-success">engineering</span>
                                        Serviços
                                    </h4>
                                    <span id="kit-services-count" class="badge badge-success"></span>
                                </div>
                
                                <div class="divider my-1"></div>
                
                                <ul
                                    id="kit-modal-services"
                                    class="flex flex-col gap-3 text-sm
                                         max-h-64 overflow-y-auto pr-2
                                         overflow-x-hidden"
                                ></ul>
                            </div>
                        </div>
                
                        <!-- COLUNA DE CONTEXTO (PROFISSIONAL) -->
                        <div class="card bg-base-200/60 border lg:col-span-1">
                            <div class="card-body gap-4">
                                <h4 class="font-semibold text-base">
                                    Informações do Kit
                                </h4>
                
                                <div class="flex flex-col gap-3 text-sm text-base-content/80">
                                    <div class="flex justify-between">
                                        <span>Total de Produtos</span>
                                        <strong id="kit-products-count-side"></strong>
                                    </div>
                
                                    <div class="flex justify-between">
                                        <span>Total de Serviços</span>
                                        <strong id="kit-services-count-side"></strong>
                                    </div>
                                </div>
                
                                <div class="divider"></div>
                
                                <p class="text-xs text-base-content/60 leading-relaxed">
                                    Este kit agrupa produtos e serviços vinculados ao orçamento,
                                    facilitando a visualização e conferência antes da aprovação.
                                </p>
                            </div>
                        </div>
                
                    </div>
                
                    <!-- FOOTER -->
                    <div class="flex justify-end px-8 py-5 border-t bg-base-200">
                        <button
                            type="button"
                            class="btn btn-primary"
                            onclick="closeKitModal()"
                        >
                            <span class="material-icons text-sm">close</span>
                            Fechar
                        </button>
                    </div>
                
                  </div>
                </dialog>
            """),
        )


class BudgetItemEditForm(forms.ModelForm):
    class Meta:
        model = BudgetItem
        fields = ["description", "quantity", "product_selling_price", "product_cost_price", "shipping", "service_selling_price", "service_cost_price", "duration"]

        widgets = {
            "description": TextInput(),
            "quantity": NumberInput(),
            "product_selling_price": MoneyInput(),
            "product_cost_price": MoneyInput(),
            "shipping": MoneyInput(),
            "service_selling_price": MoneyInput(),
            "service_cost_price": MoneyInput(),
            "duration": DurationInput(),
        }

    def __init__(self, *args, budget_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        item = self.instance

        # Se for kit, remover todos os campos de edição (kits usam modal próprio)
        if item.kit:
            fields_to_remove = ["service_selling_price", "service_cost_price", "duration",
                              "product_selling_price", "product_cost_price", "shipping"]
            for field in fields_to_remove:
                if field in self.fields:
                    self.fields.pop(field)
            return

        # Identificar tipo de item local pelos valores preenchidos
        # Verificar se campos Money existem antes de acessar .amount
        is_local_product = item.is_local and (
            (item.product_cost_price and item.product_cost_price.amount > 0) or
            (item.product_selling_price and item.product_selling_price.amount > 0) or
            (item.shipping and item.shipping.amount > 0)
        )
        is_local_service = item.is_local and (
            (item.service_cost_price and item.service_cost_price.amount > 0) or
            (item.service_selling_price and item.service_selling_price.amount > 0) or
            item.duration
        )

        if item.product or is_local_product:
            self.fields.pop("service_selling_price")
            self.fields.pop("service_cost_price")
            self.fields.pop("duration")
        elif item.service or is_local_service:
            self.fields.pop("product_selling_price")
            self.fields.pop("product_cost_price")
            self.fields.pop("shipping")

            if budget_id:
                self.fields["duration"].widget.attrs.update({
                    "hx-post": reverse("budget:calculate_item", kwargs={"budget_id": budget_id, "item_id": item.id}),
                    "hx-trigger": "keyup changed delay:200ms",
                    "hx-target": "#div_id_service_cost_price",
                    "hx-swap": "outerHTML",
                    "hx-include": "closest form",
                    "hx-indicator": "#calculation-indicator",
                })


class LocalProductForm(forms.ModelForm):
    class Meta:
        model = BudgetItem
        fields = ["description", "quantity", "product_cost_price", "product_selling_price", "shipping"]
        widgets = {
            "description": TextInput(attrs={"placeholder": "Ex: Parafuso XPTO"}),
            "quantity": NumberInput(),
            "product_cost_price": MoneyInput(),
            "product_selling_price": MoneyInput(),
            "shipping": MoneyInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["description"].label = "Descrição"
        self.fields["quantity"].label = "Quantidade"
        self.fields["product_cost_price"].label = "Custo"
        self.fields["product_selling_price"].label = "Valor de Venda"
        self.fields["shipping"].label = "Frete"


class LocalServiceForm(forms.ModelForm):
    class Meta:
        model = BudgetItem
        fields = ["description", "quantity", "service_cost_price", "service_selling_price", "duration"]
        widgets = {
            "description": TextInput(attrs={"placeholder": "Ex: Serviço Especial Ferrari"}),
            "quantity": NumberInput(),
            "service_cost_price": MoneyInput(),
            "service_selling_price": MoneyInput(),
            "duration": DurationInput(),
        }

    def __init__(self, *args, budget_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["description"].label = "Descrição"
        self.fields["quantity"].label = "Quantidade"
        self.fields["service_cost_price"].label = "Custo"
        self.fields["service_selling_price"].label = "Valor de Venda"
        self.fields["duration"].label = "Duração"

        # Adicionar cálculo automático
        if budget_id and not self.instance.pk:
            self.fields["duration"].widget.attrs.update({
                "hx-post": reverse("budget:calculate_local_service", kwargs={"budget_id": budget_id}),
                "hx-trigger": "keyup changed delay:200ms",
                "hx-target": "#div_id_service_cost_price",
                "hx-swap": "outerHTML",
                "hx-include": "closest form",
                "hx-indicator": "#calculation-indicator",
            })


class QuickProductForm(forms.ModelForm):
    """Formulário simplificado para cadastro rápido de produtos (apenas campos obrigatórios)"""
    class Meta:
        model = Product
        fields = ["code", "unit", "name", "group", "cost_price", "selling_price"]
        widgets = {
            "code": TextInput(attrs={"placeholder": "Ex: P001"}),
            "name": TextInput(attrs={"placeholder": "Ex: Filtro de Óleo"}),
            "unit": SelectInput(),
            "group": SelectInput(),
            "cost_price": MoneyInput(),
            "selling_price": MoneyInput(),
        }

    def __init__(self, *args, workshop=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.workshop = workshop

        if workshop:
            self.fields["group"].queryset = CatalogGroup.objects.filter(workshop=workshop)

        # Labels
        self.fields["code"].label = "Código"
        self.fields["name"].label = "Nome do Produto"
        self.fields["unit"].label = "Unidade"
        self.fields["group"].label = "Grupo"
        self.fields["cost_price"].label = "Custo"
        self.fields["selling_price"].label = "Valor de Venda"


class QuickServiceForm(forms.ModelForm):
    """Formulário simplificado para cadastro rápido de serviços (apenas campos obrigatórios)"""
    class Meta:
        model = Service
        fields = ["name", "duration", "selling_price"]
        widgets = {
            "name": TextInput(attrs={"placeholder": "Ex: Troca de Óleo"}),
            "duration": DurationInput(),
            "selling_price": MoneyInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Labels
        self.fields["name"].label = "Nome do Serviço"
        self.fields["duration"].label = "Duração"
        self.fields["selling_price"].label = "Valor de Venda"



