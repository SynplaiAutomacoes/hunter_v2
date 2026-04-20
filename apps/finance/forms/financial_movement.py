from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Field, HTML, Layout
from django import forms
from django.template.loader import render_to_string
from django.urls import reverse_lazy

from apps.collaborators.models import WorkshopCollaborator
from apps.core.widgets import SearchableSelectInput, TextInput, TextareaInput, CalendarDateInput, SelectInput, MoneyInput, NumberInput
from apps.finance.models import PaymentMethod, FinancialGroup
from apps.finance.models.bank_account import BankAccount
from apps.finance.models.financial_movement import FinancialMovement
from apps.sources.models import Source
from apps.suppliers.models import Supplier


class FinancialMovementBaseForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop("request", None)
        self.workshop = kwargs.pop("workshop", None)
        super().__init__(*args, **kwargs)


class MovementStep1Form(FinancialMovementBaseForm):
    person_type = forms.ChoiceField(label="", choices=[("supplier", "Fornecedor"), ("collaborator", "Colaborador")],
                                    widget=SelectInput(), required=True)

    entity = forms.ChoiceField(label="", widget=SearchableSelectInput(), required=True)

    class Meta:
        model = FinancialMovement
        fields = ["direction"]

        widgets = {
            "direction": SelectInput()
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Defaults
        self.fields["entity"].choices = []

        if self.workshop:
            suppliers = Supplier.objects.filter(workshop=self.workshop)
            collaborators = WorkshopCollaborator.objects.filter(workshop=self.workshop)

            self.suppliers_choices = [(s.id, s.name) for s in suppliers]
            self.collaborators_choices = [(c.id, str(c)) for c in collaborators]

        # Bind dinâmico (POST ou edição)
        person_type = self.data.get("person_type")

        self.fields["direction"].label = ""

        if person_type == "supplier":
            self.fields["entity"].choices = getattr(self, "suppliers_choices", [])
        elif person_type == "collaborator":
            self.fields["entity"].choices = getattr(self, "collaborators_choices", [])

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            HTML("""
            <script>
                document.addEventListener('DOMContentLoaded', function() {
                    const personType = document.querySelector('[name="person_type"]');
                    const entityField = document.querySelector('[name="entity"]');
                    const directionField = document.querySelector('[name="direction"]');

                    const step2 = document.getElementById('step-2');
                    const step3 = document.getElementById('step-3');
                    const step4 = document.getElementById('step-4');

                    const personTitle = document.getElementById('person-title');
                    const resumeContainer = document.getElementById('entity-details');

                    function updateTitles() {
                        const direction = directionField.value;

                        if (direction === "DEBIT") {
                            personTitle.innerText = "Escolha o credor";
                        } else if (direction === "CREDIT") {
                            personTitle.innerText = "Escolha o devedor";
                        }
                    }

                    function handleDirection() {
                        updateTitles();

                        if (directionField.value) {
                            step2.classList.remove('hidden');
                        } else {
                            step2.classList.add('hidden');
                            step3.classList.add('hidden');
                            step4.classList.add('hidden');

                            personType.value = "";
                            entityField.innerHTML = "";
                            resumeContainer.innerHTML = "";
                        }
                    }

                    function loadEntities() {
                        const type = personType.value;
                        const entityTitle = document.getElementById('entity-title');

                        if (!type) {
                            step3.classList.add('hidden');
                            step4.classList.add('hidden');
                    
                            entityTitle.innerText = "Fornecedor/Colaborador";
                            return;
                        }

                        // Atualiza o título dinamicamente
                        if (type === "supplier") {
                            entityTitle.innerText = "Fornecedor";
                        } else if (type === "collaborator") {
                            entityTitle.innerText = "Colaborador";
                        }
                    
                        step3.classList.remove('hidden');

                        fetch(`/finance/entities?type=${type}`, {
                            headers: { 'X-Requested-With': 'XMLHttpRequest' }
                        })
                        .then(r => r.json())
                        .then(data => {
                            // Encontra o container do SearchableSelectInput (tem x-data)
                            const container = entityField.closest('[x-data]');
                            if (!container) return;

                            // Acessa os dados do Alpine se possível, ou apenas manipula o DOM
                            const optionsList = container.querySelector('[x-ref="options"]');
                            if (!optionsList) return;

                            // Limpa o valor atual no componente Alpine
                            if (window.Alpine) {
                                const alpineData = Alpine.$data(container);
                                if (alpineData && typeof alpineData.clear === 'function') {
                                    alpineData.clear();
                                }
                            }

                            optionsList.innerHTML = "";

                            data.forEach(item => {
                                const li = document.createElement("li");
                                li.setAttribute("x-show", "!search || $el.dataset.searchText.includes(search.toLowerCase())");
                                li.setAttribute("@click", "select($el)");
                                li.dataset.value = item.id;
                                li.dataset.label = item.name;
                                li.dataset.searchText = item.name.toLowerCase();
                                li.className = "relative cursor-pointer select-none py-2 pl-3 pr-9 hover:bg-primary hover:text-white transition-colors group";
                                
                                const span = document.createElement("span");
                                span.className = "block truncate";
                                span.setAttribute(":class", `{'font-bold': value == '${item.id}'}`);
                                span.textContent = item.name;
                                
                                li.appendChild(span);
                                optionsList.appendChild(li);
                            });

                            // Adiciona a mensagem de "Nenhum resultado"
                            const noResults = document.createElement("li");
                            noResults.setAttribute("x-show", "search && $refs.options.querySelectorAll('li[data-value]:not([style*=\\'display: none\\'])').length === 0");
                            noResults.className = "py-2 pl-3 text-gray-500 italic";
                            noResults.textContent = "Nenhum resultado encontrado...";
                            optionsList.appendChild(noResults);
                        });
                    }

                    function loadDetails() {
                        const id = entityField.value;
                        const type = personType.value;

                        if (!id) {
                            step4.classList.add('hidden');
                            return;
                        }

                        step4.classList.remove('hidden');

                        fetch(`/finance/entity_details?type=${type}&id=${id}`, {
                            headers: { 'X-Requested-With': 'XMLHttpRequest' }
                        })
                        .then(r => r.text())
                        .then(html => {
                            resumeContainer.innerHTML = html;
                        });
                    }

                    directionField.addEventListener('change', handleDirection);
                    personType.addEventListener('change', loadEntities);
                    entityField.addEventListener('change', loadDetails);

                    // Estado inicial
                    handleDirection();
                    loadEntities();
                    loadDetails();
                });
            </script>"""),
            Div(
                Div(
                    # Opção 1
                    Div(
                        HTML('<h2 class="text-xl font-bold mb-4">Defina se é contas a pagar ou a receber</h2>'),
                        Field("direction"),
                    ),
                    # Opção 2
                    Div(
                        HTML('<h2 id="person-title" class="text-xl font-bold mt-15 mb-4">Escolha o credor ou devedor</h2>'),
                        Field("person_type"),
                        css_class="hidden",
                        css_id="step-2"
                    ),
                    css_class="col-span-12 lg:col-span-6",
                ),
                Div(
                    # Opção 3
                    Div(
                        HTML('<h2 id="entity-title" class="text-xl font-bold mb-4">Fornecedor/Colaborador</h2>'),
                        Field("entity"),
                        css_id="step-3"
                    ),
                    # Opção 4
                    Div(
                        HTML('<h2 class="text-xl font-bold mt-15 mb-4">Confirme os dados</h2>'),
                        Div(id="entity-details"),
                        css_class="hidden",
                        css_id="step-4"
                    ),
                    css_class="col-span-12 lg:col-span-6",
                ),
                css_class="grid grid-cols-12 gap-6",
            )
        )

    def save(self, commit=True):
        instance = super().save(commit=False)

        person_type = self.cleaned_data.get("person_type")
        entity_id = self.cleaned_data.get("entity")

        instance.supplier = None
        instance.collaborator = None

        if person_type == "supplier":
            instance.supplier_id = entity_id
        elif person_type == "collaborator":
            instance.collaborator_id = entity_id

        if commit:
            instance.save()

        return instance


class MovementStep2Form(FinancialMovementBaseForm):
    class Meta:
        model = FinancialMovement
        fields = ["description", "items_observation"]
        widgets = {"description": TextInput(), "items_observation": TextareaInput(attrs={"rows": 4, "placeholder": "Ex: Compra de 50 cápsulas de café expresso..."})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["description"].required = True
        self.helper = FormHelper()
        self.helper.form_tag = False


class MovementStep3Form(FinancialMovementBaseForm):
    is_paid = forms.TypedChoiceField(label="Pago", required=True, initial=False,
        coerce=lambda value: str(value).lower() == "true",
        choices=((False, "Não"), (True, "Sim")),
        widget=SelectInput(choices=[(False, "Não"), (True, "Sim")]))

    class Meta:
        model = FinancialMovement
        fields = ["payment_method", "is_paid", "amount", "due_date", "nf_number", "budget_plan", "bank_account", "attachment", "financial_observation"]
        widgets = {
            "payment_method": SearchableSelectInput(),
            "amount": MoneyInput(),
            "due_date": CalendarDateInput(),
            "nf_number": NumberInput(),
            "budget_plan": SearchableSelectInput(),
            "bank_account": SearchableSelectInput(),
            "financial_observation": TextareaInput(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["due_date"].required = True
        self.fields["amount"].required = True
        self.fields["payment_method"].required = True
        self.fields["is_paid"].initial = bool(self.instance.is_paid) if self.instance.pk else False

        self.fields["repeat_count"] = forms.IntegerField(required=False, min_value=1, max_value=120,
            widget=NumberInput(attrs={"class": "w-8 text-center", "placeholder": "1"}))

        self.fields["repeat_count"].label = ""
        self.fields["repeat_count"].required = True
        
        repeat_choices = [("mensal", "Mensal")]
        has_collab = getattr(self.instance, "collaborator_id", None)
        if has_collab:
            repeat_choices.append(("5_dia_util", "5º dia útil"))
        
        self.fields["repeat_type"] = forms.ChoiceField(choices=repeat_choices, initial="mensal", required=False)

        if self.workshop:
            self.fields["budget_plan"].widget.choices = [(bp.id, str(bp)) for bp in FinancialGroup.objects.filter(workshop=self.workshop)]
            self.fields["bank_account"].widget.choices = [(ba.id, str(ba)) for ba in BankAccount.objects.filter(workshop=self.workshop)]

            payment_methods = PaymentMethod.objects.filter(workshop=self.workshop, is_active=True)
            direction = self.instance.direction

            if direction == FinancialMovement.MovementDirection.CREDIT:
                payment_methods = payment_methods.filter(payment_type__in=[
                        PaymentMethod.PaymentType.CREDIT, PaymentMethod.PaymentType.BOTH])

            elif direction == FinancialMovement.MovementDirection.DEBIT:
                payment_methods = payment_methods.filter(payment_type__in=[
                        PaymentMethod.PaymentType.DEBIT, PaymentMethod.PaymentType.BOTH])

            self.fields["payment_method"].widget.choices = [(pm.id, str(pm)) for pm in payment_methods]

        top_btn = '<input class="join-item btn bg-base-200 border-base-300 font-normal shadow-none px-6 checked:bg-primary checked:text-primary-content checked:border-primary" type="radio" name="repeat_type" value="mensal" aria-label="Mensal" checked />'
        bot_btn = '<input class="join-item btn bg-base-200 border-base-300 font-normal shadow-none px-6 checked:bg-primary checked:text-primary-content checked:border-primary" type="radio" name="repeat_type" value="5_dia_util" aria-label="5º dia útil" />'
        
        repeat_html = f'<div class="join">{top_btn}{bot_btn if has_collab else ""}</div>'

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                Div("due_date", css_class="col-span-4"),
                Div("is_paid", css_class="col-span-4"),
                Div("amount", css_class="col-span-4"),
                #
                Div("payment_method", css_class="col-span-4"),
                Div("budget_plan", css_class="col-span-4"),
                Div("bank_account", css_class="col-span-4"),
                #
                Div("nf_number", css_class="col-span-6"),
                Div(
                    Div(
                        HTML('<span class="text-base font-semibold mb-4 mr-2">Repetir este lançamento</span>'),
                        Field("repeat_count", wrapper_class="mb-0"),
                        HTML('<span class="text-base font-semibold mb-4 ml-2">vezes</span>'),
                        css_class="flex items-center gap-2 mb-4"
                    ),
                    Div(
                        HTML(repeat_html),
                        css_class="flex items-center gap-4"
                    ),
                    css_class="col-span-6"
                ),
                #
                Div("attachment", css_class="col-span-12"),
                Div("financial_observation", css_class="col-span-12"),
                css_class="grid grid-cols-12 gap-4",
            )
        )

    def save(self, commit=True):
        instance = super().save(commit=commit)
        if commit:
            repeat_count = self.cleaned_data.get("repeat_count")
            repeat_type = self.cleaned_data.get("repeat_type")
            
            if getattr(self, "request", None):
                if repeat_count and repeat_count > 0:
                    self.request.session[f"repeat_count_{instance.pk}"] = repeat_count
                    self.request.session[f"repeat_type_{instance.pk}"] = repeat_type
                else:
                    self.request.session.pop(f"repeat_count_{instance.pk}", None)
                    self.request.session.pop(f"repeat_type_{instance.pk}", None)
        return instance


class MovementStep4Form(FinancialMovementBaseForm):
    class Meta:
        model = FinancialMovement
        fields = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        inst = self.instance
        self.helper = FormHelper()
        self.helper.form_tag = False

        is_entry = inst.direction == FinancialMovement.MovementDirection.CREDIT
        status_color = "text-success" if is_entry else "text-error"
        direction_label = inst.get_direction_display()

        # Origem exibida: Supplier, Collaborator ou fallback
        origin_name = "Não informado"
        origin_label = "Origem"

        if inst.supplier:
            origin_name = str(inst.supplier.name) if inst.supplier.name else ""
            origin_label = "Fornecedor"
        elif inst.collaborator:
            origin_name = str(inst.collaborator.name) if inst.collaborator.name else ""
            origin_label = "Colaborador"

        self.helper.layout = Layout(
            HTML(f"""
                    <div class="grid grid-cols-1 lg:grid-cols-12 gap-8 items-stretch">

                        <div class="col-span-12 lg:col-span-6 space-y-6">
                            <div>
                                <h3 class="text-2xl font-bold mb-6 flex items-center gap-2 text-base-content">
                                    <span class="material-icons">description</span>
                                    Revisão da Movimentação
                                </h3>

                                <div class="card bg-base-200 shadow-sm border border-base-300">
                                    <div class="card-body p-6">
                                        <h4 class="text-base uppercase font-black opacity-50 mb-4 flex items-center gap-1">
                                            <span class="material-icons text-sm">inventory_2</span> {origin_label} e Identificação
                                        </h4>

                                        <div class="space-y-4">
                                            <div>
                                                <p class="text-sm opacity-60">{origin_label}</p>
                                                <p class="text-lg font-semibold">{origin_name}</p>
                                            </div>

                                            <div>
                                                <p class="text-sm opacity-60">Descrição</p>
                                                <p class="text-md italic">"{inst.description or "Sem descrição"}"</p>
                                            </div>

                                            <div class="alert bg-base-100 border-none shadow-inner py-3 mt-4">
                                                <span class="material-icons text-info">notes</span>
                                                <div class="flex flex-col">
                                                    <span class="text-xs font-bold uppercase opacity-50">Observações</span>
                                                    <span class="text-sm">{inst.items_observation or "Nenhuma observação adicional registrada."}</span>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <div class="hidden lg:block lg:col-span-1"></div>

                        <div class="col-span-12 lg:col-span-5 flex flex-col gap-6">
                            <div class="card bg-base-300 shadow-md h-full">
                                <div class="card-body p-6 flex flex-col">
                                    <h2 class="text-xl font-bold mb-6 uppercase text-base-content opacity-70 flex items-center gap-2">
                                        <span class="material-icons text-sm">payments</span> 
                                        Resumo Financeiro
                                    </h2>

                                    <div class="space-y-4 flex-grow">
                                        <div class="flex justify-between items-center bg-base-100 p-3 rounded-lg">
                                            <span class="text-sm font-medium">Operação:</span>
                                            <span class="badge badge-lg font-bold {status_color} bg-opacity-10 border-none">
                                                {direction_label}
                                            </span>
                                        </div>

                                        <div class="flex justify-between items-center px-2">
                                            <span class="text-sm opacity-70 italic">Data de Vencimento:</span>
                                            <span class="font-mono font-bold tracking-wider italic text-base-content">
                                                {inst.due_date.strftime("%d/%m/%Y") if inst.due_date else "---"}
                                            </span>
                                        </div>

                                        <div class="divider my-2"></div>

                                        <div class="bg-base-100 p-4 rounded-xl border border-base-300">
                                            <div class="flex justify-between items-end">
                                                <span class="text-sm uppercase font-black opacity-40 mb-1">Valor Total</span>
                                                <span class="text-3xl font-black {status_color}">
                                                    {inst.amount}
                                                </span>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    """)
        )

    def save(self, commit=True):
        instance = super().save(commit=commit)
        if commit:
            flag_key = f"generated_reps_{instance.pk}"
            if getattr(self, "request", None) and not self.request.session.get(flag_key):
                repeat_count = self.request.session.pop(f"repeat_count_{instance.pk}", None)
                repeat_type = self.request.session.pop(f"repeat_type_{instance.pk}", None)
                if repeat_count and repeat_count > 0:
                    repeat_count = int(repeat_count) - 1 if repeat_count > 0 else int(repeat_count)
                    self._generate_repetitions(instance, repeat_count, repeat_type)
                    self.request.session[flag_key] = True
        return instance

    def _generate_repetitions(self, instance, count, r_type):
        import calendar
        import datetime
        
        def add_months(sourcedate, months):
            month = sourcedate.month - 1 + months
            year = sourcedate.year + month // 12
            month = month % 12 + 1
            day = min(sourcedate.day, calendar.monthrange(year,month)[1])
            return datetime.date(year, month, day)
            
        def get_5th_business_day(year, month):
            business_days = 0
            day = 1
            while True:
                d = datetime.date(year, month, day)
                if d.weekday() < 5:
                    business_days += 1
                    if business_days == 5:
                        return d
                day += 1

        for i in range(1, count + 1):
            new_instance = FinancialMovement.objects.get(pk=instance.pk)
            new_instance.pk = None
            new_instance.is_paid = False
            new_instance.attachment = None
            
            if r_type == "mensal":
                new_instance.due_date = add_months(instance.due_date, i)
            elif r_type == "5_dia_util":
                target_date = add_months(instance.due_date, i)
                new_instance.due_date = get_5th_business_day(target_date.year, target_date.month)
                
            new_instance.save()


class ReportMovementEditForm(FinancialMovementBaseForm):
    """Formulário unificado para edição de movimentação financeira via modal no relatório."""

    is_paid = forms.TypedChoiceField(
        label="Pago",
        required=True,
        coerce=lambda value: str(value).lower() == "true",
        choices=((False, "Não"), (True, "Sim")),
        widget=SelectInput(choices=[(False, "Não"), (True, "Sim")]),
        initial=False,
    )

    class Meta:
        model = FinancialMovement
        fields = [
            # Origem
            "source",
            # Itens
            "description",
            "items_observation",
            # Pagamento
            "due_date",
            "direction",
            "amount",
            "budget_plan",
            "bank_account",
            "payment_method",
            "is_paid",
            "nf_number",
            "financial_observation",
            "attachment",
        ]
        widgets = {
            "source": SearchableSelectInput(),
            "description": TextInput(),
            "items_observation": TextareaInput(attrs={"rows": 3}),
            "due_date": CalendarDateInput(),
            "direction": SelectInput(),
            "amount": MoneyInput(),
            "budget_plan": SearchableSelectInput(),
            "bank_account": SearchableSelectInput(),
            "payment_method": SearchableSelectInput(),
            "nf_number": NumberInput(),
            "financial_observation": TextareaInput(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["source"].required = True
        self.fields["description"].required = True
        self.fields["due_date"].required = True
        self.fields["direction"].required = True
        self.fields["amount"].required = True
        self.fields["payment_method"].required = True
        self.fields["is_paid"].initial = bool(self.instance.is_paid) if self.instance.pk else False

        if self.workshop:
            source_qs = Source.objects.filter(workshop=self.workshop)
            self.fields["source"].queryset = source_qs
            self.fields["source"].widget.choices = [(s.id, s.name) for s in source_qs]

            self.fields["payment_method"].widget.choices = [
                (pm.id, str(pm)) for pm in PaymentMethod.objects.filter(workshop=self.workshop)
            ]
            self.fields["budget_plan"].widget.choices = [
                (bp.id, str(bp)) for bp in FinancialGroup.objects.filter(workshop=self.workshop)
            ]
            self.fields["bank_account"].widget.choices = [
                (ba.id, str(ba)) for ba in BankAccount.objects.filter(workshop=self.workshop)
            ]

        # Resolve source object for inline display
        source_id = self.data.get("source") or (self.instance.source_id if self.instance.pk else None)
        source_obj = None
        if source_id:
            source_obj = Source.objects.filter(id=source_id, workshop=self.workshop).first() if self.workshop else None

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            # ── Seção 1: Fornecedor (Origem) ──
            HTML('<h3 class="text-base font-semibold text-base-content flex items-center gap-2 mb-3">'
                 '<span class="material-icons text-sm">store</span> Sobre o Fornecedor</h3>'),
            Div(
                Div("source", css_class="col-span-12"),
                Div(
                    HTML(render_to_string("finance/partials/source_resume.html", {"source_obj": source_obj})),
                    id="report-edit-source-details",
                    css_class="col-span-12",
                ),
                css_class="grid grid-cols-12 gap-4",
            ),
            HTML('<div class="divider my-4"></div>'),

            # ── Seção 2: Item ──
            HTML('<h3 class="text-base font-semibold text-base-content flex items-center gap-2 mb-3">'
                 '<span class="material-icons text-sm">inventory_2</span> Sobre o Item</h3>'),
            Div(
                Div("description", css_class="col-span-12"),
                Div("items_observation", css_class="col-span-12"),
                css_class="grid grid-cols-12 gap-4",
            ),
            HTML('<div class="divider my-4"></div>'),

            # ── Seção 3: Pagamento ──
            HTML('<h3 class="text-base font-semibold text-base-content flex items-center gap-2 mb-3">'
                 '<span class="material-icons text-sm">payments</span> Sobre o Pagamento</h3>'),
            Div(
                Div("due_date", css_class="col-span-12 lg:col-span-4"),
                Div("direction", css_class="col-span-12 lg:col-span-4"),
                Div("amount", css_class="col-span-12 lg:col-span-4"),
                #
                Div("budget_plan", css_class="col-span-12 lg:col-span-6"),
                Div("bank_account", css_class="col-span-12 lg:col-span-6"),
                #
                Div("payment_method", css_class="col-span-12 lg:col-span-4"),
                Div("is_paid", css_class="col-span-12 lg:col-span-4"),
                Div("nf_number", css_class="col-span-12 lg:col-span-4"),
                #
                Div("financial_observation", css_class="col-span-12"),
                Div("attachment", css_class="col-span-12"),
                css_class="grid grid-cols-12 gap-4",
            ),
        )
