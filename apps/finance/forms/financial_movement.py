import json
import logging
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Field, HTML, Layout
from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.template.loader import render_to_string
from djmoney.forms import MoneyField
from djmoney.money import Money

from apps.collaborators.models import WorkshopCollaborator
from apps.core.presentation.widgets import SearchableSelectInput, TextInput, TextareaInput, CalendarDateInput, DecimalInput, MoneyInput, NumberInput
from apps.finance.models import PaymentMethod, FinancialGroup
from apps.finance.models.bank_account import BankAccount
from apps.finance.models.financial_movement import FinancialMovement, FinancialMovementInstallmentPlan
from apps.finance.services.installments import InstallmentScheduleError, build_installments, parse_installment_schedule
from apps.finance.services.financial_movement import (
    BUDGET_PLAN_REQUIRED,
    apply_payment_reconciliation_rules,
    create_partial_payment_balance,
    generate_card_fee_movement,
)
from apps.suppliers.models import Supplier
from apps.core.text_normalization import sentence_case
from apps.core.presentation.forms import CoreModelForm
from apps.workorder.models import WorkOrderPaymentMethod


logger = logging.getLogger(__name__)


class FinancialMovementBaseForm(CoreModelForm):
    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop("request", None)
        self.workshop = kwargs.pop("workshop", None)
        super().__init__(*args, **kwargs)

    def clean_discount_fields(self, cleaned_data):
        gross_amount = cleaned_data.get("gross_amount")
        discount_mode = cleaned_data.get("discount_mode") or FinancialMovement.DiscountMode.NONE
        discount_value = cleaned_data.get("discount_value")
        discount_percentage = cleaned_data.get("discount_percentage") or getattr(self.instance, "discount_percentage", Decimal("0.00")) or Decimal("0.00")

        if gross_amount is None:
            return cleaned_data

        gross_value = Decimal(str(gross_amount.amount or 0))
        adjustment_amount = Decimal("0.00")
        if discount_mode == FinancialMovement.DiscountMode.AMOUNT:
            adjustment_amount = Decimal(str((discount_value.amount if discount_value else 0) or 0))
            if adjustment_amount <= 0:
                self.add_error("discount_value", "Informe o valor do desconto.")
            if adjustment_amount > gross_value:
                self.add_error("discount_value", "O desconto não pode ser maior que o valor bruto.")
            cleaned_data["discount_percentage"] = Decimal("0.00")
        elif discount_mode == FinancialMovement.DiscountMode.SURCHARGE:
            adjustment_amount = Decimal(str((discount_value.amount if discount_value else 0) or 0))
            if adjustment_amount <= 0:
                self.add_error("discount_value", "Informe o valor do acréscimo.")
            cleaned_data["discount_percentage"] = Decimal("0.00")
        elif discount_mode == FinancialMovement.DiscountMode.PERCENTAGE:
            if discount_percentage <= 0:
                self.add_error("discount_mode", "O desconto percentual legado deve possuir um percentual válido.")
            if discount_percentage > Decimal("100"):
                self.add_error("discount_mode", "O desconto percentual legado não pode ser maior que 100%.")
            adjustment_amount = gross_value * discount_percentage / Decimal("100")
            cleaned_data["discount_value"] = gross_amount.__class__(Decimal("0.00"), gross_amount.currency)
        else:
            cleaned_data["discount_value"] = gross_amount.__class__(Decimal("0.00"), gross_amount.currency)
            cleaned_data["discount_percentage"] = Decimal("0.00")

        if adjustment_amount < 0:
            self.add_error("discount_value" if discount_mode in (FinancialMovement.DiscountMode.AMOUNT, FinancialMovement.DiscountMode.SURCHARGE) else "discount_percentage", "O ajuste não pode ser negativo.")

        if not self.errors:
            net_amount = gross_value + adjustment_amount if discount_mode == FinancialMovement.DiscountMode.SURCHARGE else gross_value - adjustment_amount
            cleaned_data["amount"] = gross_amount.__class__(
                net_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                gross_amount.currency,
            )
        return cleaned_data

    def configure_discount_fields(self):
        is_non_financial_adjustment_context = bool(self.instance.payroll_id or self.instance.movement_group_id)
        self.fields["discount_mode"].label = "Tipo de desconto" if is_non_financial_adjustment_context else "Desconto ou Acréscimo"
        self.fields["discount_mode"].required = True
        self.fields["discount_value"].required = False
        self.fields["discount_value"].label = "Desconto (R$)" if is_non_financial_adjustment_context else "Ajuste (R$)"
        available_choices = (
            [
                (FinancialMovement.DiscountMode.NONE, "Sem desconto"),
                (FinancialMovement.DiscountMode.AMOUNT, "Desconto em reais (R$)"),
                (FinancialMovement.DiscountMode.PERCENTAGE, "Desconto em percentual (%)"),
            ]
            if is_non_financial_adjustment_context
            else [
                (FinancialMovement.DiscountMode.NONE, "Sem desconto ou acréscimo"),
                (FinancialMovement.DiscountMode.AMOUNT, "Desconto"),
                (FinancialMovement.DiscountMode.SURCHARGE, "Acréscimo"),
            ]
        )
        if not is_non_financial_adjustment_context and self.instance.pk and self.instance.discount_mode == FinancialMovement.DiscountMode.PERCENTAGE:
            available_choices.append((FinancialMovement.DiscountMode.PERCENTAGE, "Desconto percentual (legado)"))
        self.fields["discount_mode"].choices = available_choices
        self.fields["discount_mode"].widget.choices = available_choices
        self.fields["amount"].label = "Valor líquido"
        self.fields["amount"].required = False
        if not self.instance.pk:
            self.initial["discount_mode"] = ""


FINANCIAL_DISCOUNT_UI_SCRIPT = """
<script>
(function () {
    function initializeFinancialDiscountFields() {
        const mode = document.getElementById('id_discount_mode');
        const grossHidden = document.getElementById('id_gross_amount_0');
        const grossDisplay = document.getElementById('id_gross_amount_0_display');
        const valueHidden = document.getElementById('id_discount_value_0');
        const valueDisplay = document.getElementById('id_discount_value_0_display');
        const netHidden = document.getElementById('id_amount_0');
        const netDisplay = document.getElementById('id_amount_0_display');
        const valueContainer = document.getElementById('discount-value-field');
        const valueLabel = valueContainer?.querySelector('label');

        if (!mode || mode.dataset.discountUiReady === 'true') return;
        mode.dataset.discountUiReady = 'true';

        const parseNumber = (raw) => {
            const text = String(raw || '').trim();
            const value = text.includes(',') ? text.replace(/\./g, '').replace(',', '.') : text;
            const parsed = Number(value);
            return Number.isFinite(parsed) ? parsed : 0;
        };
        const formatMoney = (value) => Number(value || 0).toLocaleString('pt-BR', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        });
        const hiddenMoneyValue = (hidden, display) => {
            if (hidden && hidden.value !== '') return Number(hidden.value) || 0;
            return parseNumber(display ? display.value : '');
        };

        function updateDiscountUi({ resetInactive = false } = {}) {
            const selectedMode = mode.value;
            if (!['NONE', 'AMOUNT', 'SURCHARGE', 'PERCENTAGE'].includes(selectedMode)) return;

            const usesAmount = ['AMOUNT', 'SURCHARGE'].includes(selectedMode);
            valueContainer?.classList.toggle('hidden', !usesAmount);
            if (valueLabel) {
                valueLabel.textContent = selectedMode === 'SURCHARGE' ? 'Acréscimo (R$)' : 'Desconto (R$)';
            }

            if (resetInactive && !usesAmount) {
                if (valueHidden) valueHidden.value = '0.00';
                if (valueDisplay) valueDisplay.value = formatMoney(0);
            }
            const gross = hiddenMoneyValue(grossHidden, grossDisplay);
            const adjustment = usesAmount ? hiddenMoneyValue(valueHidden, valueDisplay) : 0;
            const net = selectedMode === 'SURCHARGE' ? gross + adjustment : Math.max(gross - adjustment, 0);
            if (netHidden) netHidden.value = net.toFixed(2);
            if (netDisplay) netDisplay.value = formatMoney(net);
        }

        [grossHidden, grossDisplay, valueHidden, valueDisplay].forEach((field) => {
            if (!field) return;
            field.addEventListener('input', updateDiscountUi);
            field.addEventListener('change', updateDiscountUi);
            field.addEventListener('widget:formatted-change', updateDiscountUi);
        });

        ['input', 'change'].forEach((eventName) => {
            mode.addEventListener(eventName, () => updateDiscountUi({ resetInactive: true }));
        });

        updateDiscountUi();
        requestAnimationFrame(() => requestAnimationFrame(() => updateDiscountUi()));
        setTimeout(() => updateDiscountUi(), 50);
    }

    initializeFinancialDiscountFields();
    document.body.addEventListener('htmx:afterSwap', initializeFinancialDiscountFields);
})();
</script>
"""


FINANCIAL_INSTALLMENTS_UI_SCRIPT = """
<script>
(function () {
    function initializeFinancialInstallments() {
        const countField = document.getElementById('id_installments_count');
        const scheduleContainer = document.getElementById('installment-schedule');
        const dueDate = document.getElementById('id_due_date');
        const gross = document.getElementById('id_gross_amount_0');
        const grossDisplay = document.getElementById('id_gross_amount_0_display');
        const adjustment = document.getElementById('id_discount_value_0');
        const adjustmentDisplay = document.getElementById('id_discount_value_0_display');
        const mode = document.getElementById('id_discount_mode');
        const initialScheduleElement = document.getElementById('financial-installment-schedule-initial');
        const initialSchedule = initialScheduleElement ? JSON.parse(initialScheduleElement.textContent || '[]') : [];
        if (!countField || !scheduleContainer || countField.dataset.installmentUiReady === 'true') return;
        countField.dataset.installmentUiReady = 'true';

        const number = (value) => {
            const text = String(value || '').trim();
            const normalized = text.includes(',') ? text.replace(/\\./g, '').replace(',', '.') : text;
            return Number.isFinite(Number(normalized)) ? Number(normalized) : 0;
        };
        const moneyValue = (hidden, display) => hidden?.value !== '' ? number(hidden.value) : number(display?.value);
        const addMonths = (value, months) => {
            const [year, month, day] = String(value).split('-').map(Number);
            const result = new Date(year, month - 1 + months, 1);
            result.setDate(Math.min(day, new Date(result.getFullYear(), result.getMonth() + 1, 0).getDate()));
            return `${result.getFullYear()}-${String(result.getMonth() + 1).padStart(2, '0')}-${String(result.getDate()).padStart(2, '0')}`;
        };
        const netAmount = () => {
            const base = moneyValue(gross, grossDisplay);
            const value = moneyValue(adjustment, adjustmentDisplay);
            return mode?.value === 'SURCHARGE' ? base + value : Math.max(base - value, 0);
        };
        function generate({ preserve = false } = {}) {
            const count = Math.max(Number(countField.value || 1), 1);
            const firstDate = dueDate?.value;
            if (count === 1 || !firstDate) {
                scheduleContainer.classList.add('hidden');
                scheduleContainer.innerHTML = '';
                return;
            }
            const renderedAmounts = [...scheduleContainer.querySelectorAll('[name="installment_amount"]')].map((input) => input.value);
            const renderedDates = [...scheduleContainer.querySelectorAll('[name="installment_due_date"]')].map((input) => input.value);
            const previous = preserve ? (renderedAmounts.length ? renderedAmounts : initialSchedule.map((item) => item.amount)) : [];
            const dates = preserve ? (renderedDates.length ? renderedDates : initialSchedule.map((item) => item.due_date)) : [];
            const cents = Math.round(netAmount() * 100);
            const each = Math.floor(cents / count);
            const remainder = cents % count;
            const rows = Array.from({ length: count }, (_, index) => {
                const amount = previous[index] || ((each + (index === count - 1 ? remainder : 0)) / 100).toFixed(2);
                const date = dates[index] || addMonths(firstDate, index);
                return `<tr><td class="font-medium">${index + 1}/${count}</td><td><input type="date" class="input input-bordered input-sm w-full" name="installment_due_date" value="${date}" required></td><td><input type="number" step="0.01" min="0.01" class="input input-bordered input-sm w-full text-right" name="installment_amount" value="${amount}" required></td></tr>`;
            }).join('');
            scheduleContainer.innerHTML = `<div class="flex items-center justify-between gap-3"><div><h4 class="font-semibold">Parcelas</h4><p class="mt-1 text-xs text-base-content/60">Esta operação será dividida nas parcelas abaixo. Repetir lançamento continua sendo uma função separada.</p></div><button type="button" class="btn btn-outline btn-sm" id="regenerate-installments">Gerar novamente</button></div><div class="mt-3 overflow-x-auto"><table class="table table-sm"><thead><tr><th>Parcela</th><th>Vencimento</th><th class="text-right">Valor</th></tr></thead><tbody>${rows}</tbody></table></div>`;
            scheduleContainer.classList.remove('hidden');
            scheduleContainer.querySelector('#regenerate-installments')?.addEventListener('click', () => generate());
        }
        countField.addEventListener('input', () => generate());
        dueDate?.addEventListener('change', () => generate());
        [gross, grossDisplay, adjustment, adjustmentDisplay, mode].forEach((field) => {
            field?.addEventListener('input', () => generate());
            field?.addEventListener('change', () => generate());
            field?.addEventListener('widget:formatted-change', () => generate());
        });
        generate({ preserve: true });
    }
    initializeFinancialInstallments();
    document.body.addEventListener('htmx:afterSwap', initializeFinancialInstallments);
})();
</script>
"""


class MovementStep1Form(FinancialMovementBaseForm):
    person_type = forms.ChoiceField(label="", choices=[("supplier", "Fornecedor"), ("collaborator", "Colaborador")], widget=SearchableSelectInput(), required=True)

    entity = forms.ChoiceField(label="", widget=SearchableSelectInput(), required=True)

    class Meta:
        model = FinancialMovement
        fields = ["direction"]

        widgets = {"direction": SearchableSelectInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Defaults
        self.fields["entity"].choices = []

        if self.workshop:
            suppliers = Supplier.objects.filter(workshop=self.workshop)
            collaborators = WorkshopCollaborator.objects.filter(workshop=self.workshop)

            self.suppliers_choices = [(s.id, s.name) for s in suppliers]
            self.collaborators_choices = [(c.id, str(c)) for c in collaborators]

        # Em um POST, os valores enviados têm precedência. Em um retorno ao
        # passo 1, estes campos auxiliares precisam ser reconstruídos a partir
        # da origem que já foi persistida no lançamento.
        person_type = self.data.get("person_type") if self.is_bound else None
        entity_id = self.data.get("entity") if self.is_bound else None
        if not person_type:
            if self.instance.supplier_id:
                person_type = "supplier"
                entity_id = str(self.instance.supplier_id)
            elif self.instance.collaborator_id:
                person_type = "collaborator"
                entity_id = str(self.instance.collaborator_id)

        if person_type:
            self.initial.setdefault("person_type", person_type)
        if entity_id:
            self.initial.setdefault("entity", str(entity_id))

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
                (function initMovementStep1() {
                    function bindMovementStep1() {
                    const personType = document.querySelector('[name="person_type"]');
                    const entityField = document.querySelector('[name="entity"]');
                    const directionField = document.querySelector('[name="direction"]');
                    const supplierQuickBtn = document.getElementById('supplier-quick-btn');

                    const step2 = document.getElementById('step-2');
                    const step3 = document.getElementById('step-3');
                    const step4 = document.getElementById('step-4');

                    const personTitle = document.getElementById('person-title');
                    const resumeContainer = document.getElementById('entity-details');

                    function getSearchableData(input) {
                        const container = input && input.closest('[x-data]');
                        if (!container || !window.Alpine) return null;
                        try {
                            return Alpine.$data(container);
                        } catch (error) {
                            return null;
                        }
                    }

                    function clearSearchable(input, { clearOptions = false } = {}) {
                        const alpineData = getSearchableData(input);
                        if (alpineData && typeof alpineData.clear === 'function') {
                            alpineData.clear();
                            if (clearOptions && typeof alpineData.setOptions === 'function') {
                                alpineData.setOptions([]);
                            }
                            return;
                        }
                        if (input) input.value = '';
                    }

                    function setSearchableOptions(input, options) {
                        const alpineData = getSearchableData(input);
                        if (alpineData && typeof alpineData.setOptions === 'function') {
                            alpineData.setOptions(options);
                            return;
                        }
                        const container = input && input.closest('[x-data]');
                        if (container) {
                            container.dispatchEvent(new CustomEvent('searchable-set-options', {
                                detail: { options }, bubbles: true,
                            }));
                        }
                    }

                    function updateTitles() {
                        const direction = directionField.value;

                        if (direction === "DEBIT") {
                            personTitle.innerText = "Escolha o credor";
                        } else if (direction === "CREDIT") {
                            personTitle.innerText = "Escolha o devedor";
                        }
                    }

                    function syncSupplierQuickButton() {
                        if (!supplierQuickBtn) return;

                        if (personType.value === 'supplier') {
                            supplierQuickBtn.classList.remove('hidden');
                            const hasSupplier = Boolean(entityField.value);
                            supplierQuickBtn.classList.toggle('btn-warning', hasSupplier);
                            supplierQuickBtn.classList.toggle('btn-primary', !hasSupplier);
                            supplierQuickBtn.title = hasSupplier ? 'Editar Fornecedor' : 'Cadastrar Fornecedor';
                            const icon = supplierQuickBtn.querySelector('.material-icons');
                            if (icon) {
                                icon.textContent = hasSupplier ? 'edit' : 'note_add';
                            }
                        } else {
                            supplierQuickBtn.classList.add('hidden');
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

                            clearSearchable(personType);
                            clearSearchable(entityField, { clearOptions: true });
                            resumeContainer.innerHTML = "";
                            syncSupplierQuickButton();
                        }
                    }

                    function selectEntityOption(entityId) {
                        if (!entityId) return;

                        const alpineData = getSearchableData(entityField);
                        if (alpineData && typeof alpineData.setValue === 'function') {
                            alpineData.setValue(entityId);
                        }
                        syncSupplierQuickButton();
                    }

                    function loadEntities(selectedEntity) {
                        const type = personType.value;
                        const entityTitle = document.getElementById('entity-title');

                        if (!type) {
                            step3.classList.add('hidden');
                            step4.classList.add('hidden');
                    
                            entityTitle.innerText = "Fornecedor/Colaborador";
                            syncSupplierQuickButton();
                            return Promise.resolve();
                        }

                        // Atualiza o título dinamicamente
                        if (type === "supplier") {
                            entityTitle.innerText = "Fornecedor";
                        } else if (type === "collaborator") {
                            entityTitle.innerText = "Colaborador";
                        }
                    
                        step3.classList.remove('hidden');
                        syncSupplierQuickButton();

                        return fetch(`/finance/entities?type=${type}`, {
                            headers: { 'X-Requested-With': 'XMLHttpRequest' }
                        })
                        .then(r => r.json())
                        .then(data => {
                            const options = (Array.isArray(data) ? data : []).map((item) => ({
                                value: item.id,
                                label: item.name,
                            }));
                            setSearchableOptions(entityField, options);

                            if (selectedEntity && selectedEntity.id) {
                                selectEntityOption(selectedEntity.id);
                            } else {
                                clearSearchable(entityField);
                                syncSupplierQuickButton();
                            }
                        });
                    }

                    function loadDetails() {
                        const id = entityField.value;
                        const type = personType.value;

                        if (!id) {
                            step4.classList.add('hidden');
                            syncSupplierQuickButton();
                            return;
                        }

                        step4.classList.remove('hidden');
                        syncSupplierQuickButton();

                        fetch(`/finance/entity_details?type=${type}&id=${id}`, {
                            headers: { 'X-Requested-With': 'XMLHttpRequest' }
                        })
                        .then(r => r.text())
                        .then(html => {
                            resumeContainer.innerHTML = html;
                        });
                    }

                    function openSupplierQuickForm() {
                        const supplierId = entityField.value;
                        const url = supplierId
                            ? `/stock/supplier/quick-update/${supplierId}/`
                            : '/stock/supplier/quick-create/';
                        htmx.ajax('GET', url, {target: '#modal-container', swap: 'innerHTML'});
                    }

                    function selectPersonType(value) {
                        const container = personType.closest('[x-data]');
                        if (!container || !window.Alpine) {
                            personType.value = value;
                            personType.dispatchEvent(new Event('change', { bubbles: true }));
                            return;
                        }

                        const alpineData = Alpine.$data(container);
                        const optionsList = container.querySelector('[x-ref="options"]');
                        const option = optionsList ? optionsList.querySelector(`li[data-value='${value}']`) : null;
                        if (option && typeof alpineData.select === 'function') {
                            alpineData.select(option);
                        } else {
                            personType.value = value;
                            personType.dispatchEvent(new Event('change', { bubbles: true }));
                        }
                    }

                    directionField.addEventListener('change', handleDirection);
                    personType.addEventListener('change', function() {
                        if (window.__financeSelectingSupplier) return;
                        loadEntities();
                        syncSupplierQuickButton();
                    });
                    entityField.addEventListener('change', loadDetails);
                    if (supplierQuickBtn) {
                        supplierQuickBtn.addEventListener('click', openSupplierQuickForm);
                    }

                    if (!window.__financeSupplierSavedBound) {
                        window.__financeSupplierSavedBound = true;
                        document.body.addEventListener('supplierSaved', function (evt) {
                            const modalContainer = document.getElementById('modal-container');
                            if (modalContainer) {
                                modalContainer.innerHTML = '';
                            }

                            const supplier = evt && evt.detail ? evt.detail : null;
                            if (!supplier || !supplier.id) return;

                            if (personType.value !== 'supplier') {
                                window.__financeSelectingSupplier = true;
                                try {
                                    selectPersonType('supplier');
                                } finally {
                                    window.__financeSelectingSupplier = false;
                                }
                            }
                            loadEntities(supplier);
                        });
                    }

                    // Estado inicial
                    handleDirection();
                    loadEntities(entityField.value ? { id: entityField.value } : null);
                    loadDetails();
                    syncSupplierQuickButton();
                    }

                    if (document.readyState === 'loading') {
                        document.addEventListener('DOMContentLoaded', bindMovementStep1);
                    } else {
                        bindMovementStep1();
                    }
                })();
            </script>"""),
            Div(
                Div(
                    # Opção 1
                    Div(
                        HTML('<h2 class="text-xl font-bold mb-4">Defina se é contas a pagar ou a receber</h2>'),
                        Field("direction"),
                    ),
                    # Opção 2
                    Div(HTML('<h2 id="person-title" class="text-xl font-bold mt-15 mb-4">Escolha o credor ou devedor</h2>'), Field("person_type"), css_class="hidden", css_id="step-2"),
                    css_class="col-span-12 lg:col-span-6",
                ),
                Div(
                    # Opção 3
                    Div(
                        HTML('<h2 id="entity-title" class="text-xl font-bold mb-4">Fornecedor/Colaborador</h2>'),
                        Div(
                            Div(Field("entity"), css_class="flex-grow"),
                            HTML(
                                """
                                <button
                                    id="supplier-quick-btn"
                                    type="button"
                                    class="btn btn-circle btn-primary mb-2 ml-2 hidden"
                                    title="Cadastrar Fornecedor"
                                >
                                    <span class="material-icons">note_add</span>
                                </button>
                                """
                            ),
                            css_class="flex items-end mb-2",
                        ),
                        css_id="step-3",
                    ),
                    # Opção 4
                    Div(HTML('<h2 class="text-xl font-bold mt-15 mb-4">Confirme os dados</h2>'), Div(id="entity-details"), css_class="hidden", css_id="step-4"),
                    css_class="col-span-12 lg:col-span-6",
                ),
                css_class="grid grid-cols-12 gap-6",
            ),
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

    def clean_description(self):
        value = self.cleaned_data.get("description")
        return sentence_case(value) if value else value

    def clean_items_observation(self):
        value = self.cleaned_data.get("items_observation")
        return sentence_case(value) if value else value


class MovementStep3Form(FinancialMovementBaseForm):
    is_paid = forms.TypedChoiceField(label="Pago", required=True, initial=False, coerce=lambda value: str(value).lower() == "true", choices=((False, "Não"), (True, "Sim")), widget=SearchableSelectInput(choices=[(False, "Não"), (True, "Sim")]))
    is_reconciled = forms.TypedChoiceField(
        label="Conciliado",
        required=True,
        initial=False,
        coerce=lambda value: str(value).lower() == "true",
        choices=((False, "Aguardando Conciliação"), (True, "Conciliado")),
        widget=SearchableSelectInput(choices=[(False, "Aguardando Conciliação"), (True, "Conciliado")]),
    )

    class Meta:
        model = FinancialMovement
        fields = ["entry_date", "payment_method", "is_paid", "is_reconciled", "gross_amount", "discount_mode", "discount_value", "amount", "due_date", "nf_number", "budget_plan", "bank_account", "attachment", "financial_observation"]
        widgets = {
            "entry_date": CalendarDateInput(),
            "payment_method": SearchableSelectInput(),
            "gross_amount": MoneyInput(),
            "discount_mode": SearchableSelectInput(),
            "discount_value": MoneyInput(),
            "amount": MoneyInput(attrs={"readonly": "readonly"}),
            "due_date": CalendarDateInput(),
            "nf_number": NumberInput(),
            "budget_plan": SearchableSelectInput(),
            "bank_account": SearchableSelectInput(),
            "financial_observation": TextareaInput(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["due_date"].required = True
        self.fields["gross_amount"].required = True
        self.configure_discount_fields()
        self.fields["payment_method"].required = True
        self.fields["budget_plan"].required = True
        self.fields["budget_plan"].error_messages["required"] = BUDGET_PLAN_REQUIRED
        self.fields["is_paid"].initial = bool(self.instance.is_paid) if self.instance.pk else False
        self.fields["is_reconciled"].initial = bool(self.instance.is_reconciled) if self.instance.pk else False

        self.fields["repeat_count"] = forms.IntegerField(required=False, min_value=1, max_value=120, widget=NumberInput(attrs={"class": "w-8 text-center", "placeholder": "1"}))

        self.fields["repeat_count"].label = "Repetir este lançamento"
        self.fields["installments_count"] = forms.IntegerField(
            label="Número de parcelas",
            required=False,
            min_value=1,
            max_value=60,
            initial=1,
            widget=NumberInput(attrs={"id": "id_installments_count", "placeholder": "1"}),
            help_text="Divide esta operação em parcelas. Não é uma repetição de lançamento.",
        )
        if self.instance.installment_plan_id:
            self.initial["installments_count"] = self.instance.installments_count

        self.initial_installment_schedule = []
        if getattr(self, "request", None) and self.instance.pk:
            self.initial_installment_schedule = self.request.session.get(f"installment_schedule_{self.instance.pk}", [])
        if not self.initial_installment_schedule and self.instance.installment_plan_id:
            self.initial_installment_schedule = [
                {
                    "number": movement.installment_number,
                    "total": movement.installments_count,
                    "due_date": movement.due_date.isoformat(),
                    "amount": str(movement.amount.amount),
                }
                for movement in self.instance.installment_plan.financial_movements.order_by("installment_number", "pk")
            ]
        if self.initial_installment_schedule:
            self.initial["installments_count"] = len(self.initial_installment_schedule)

        repeat_choices = [
            ("mensal", "Mensal"),
            ("quinzenal", "Quinzenal"),
            ("semanal", "Semanal"),
            ("diario", "Diário"),
        ]
        has_collab = getattr(self.instance, "collaborator_id", None)
        if has_collab:
            repeat_choices.append(("5_dia_util", "5º dia útil"))

        self.fields["repeat_type"] = forms.ChoiceField(choices=repeat_choices, initial="mensal", required=False)

        if self.workshop:
            self.fields["budget_plan"].widget.choices = [("", "---------")] + [(bp.id, str(bp)) for bp in FinancialGroup.objects.filter(workshop=self.workshop)]
            bank_accounts = BankAccount.objects.filter(workshop=self.workshop, is_active=True).order_by("bank_name", "account_number", "id")
            self.fields["bank_account"].queryset = bank_accounts
            self.fields["bank_account"].widget.choices = [(ba.id, str(ba)) for ba in bank_accounts]

            payment_methods = PaymentMethod.objects.filter(workshop=self.workshop, is_active=True)
            direction = self.instance.direction

            if direction == FinancialMovement.MovementDirection.CREDIT:
                payment_methods = payment_methods.filter(payment_type__in=[PaymentMethod.PaymentType.CREDIT, PaymentMethod.PaymentType.BOTH])

            elif direction == FinancialMovement.MovementDirection.DEBIT:
                payment_methods = payment_methods.filter(payment_type__in=[PaymentMethod.PaymentType.DEBIT, PaymentMethod.PaymentType.BOTH])

            self.fields["payment_method"].widget.choices = [(pm.id, str(pm)) for pm in payment_methods]

        btn_class = "join-item btn bg-base-200 border-base-300 font-normal shadow-none px-6 checked:bg-primary checked:text-primary-content checked:border-primary"
        btn_mensal = f'<input class="{btn_class}" type="radio" name="repeat_type" value="mensal" aria-label="Mensal" checked />'
        btn_quinzenal = f'<input class="{btn_class}" type="radio" name="repeat_type" value="quinzenal" aria-label="Quinzenal" />'
        btn_semanal = f'<input class="{btn_class}" type="radio" name="repeat_type" value="semanal" aria-label="Semanal" />'
        btn_diario = f'<input class="{btn_class}" type="radio" name="repeat_type" value="diario" aria-label="Diário" />'
        btn_5_dia_util = f'<input class="{btn_class}" type="radio" name="repeat_type" value="5_dia_util" aria-label="5º dia útil" />'
        repeat_html = f'<div class="join">{btn_mensal}{btn_quinzenal}{btn_semanal}{btn_diario}{btn_5_dia_util if has_collab else ""}</div>'

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                Div("entry_date", css_class="col-span-4"),
                Div("due_date", css_class="col-span-4"),
                Div("is_paid", css_class="col-span-4"),
                Div("is_reconciled", css_class="col-span-4"),
                Div("payment_method", css_class="col-span-4"),
                Div("budget_plan", css_class="col-span-4"),
                Div("bank_account", css_class="col-span-4"),
                #
                Div("nf_number", css_class="col-span-6"),
                Div(
                    Div(Field("repeat_count", wrapper_class="mb-0"), HTML('<span class="text-sm font-semibold">vezes</span>'), HTML(repeat_html), css_class="flex items-center gap-4 mb-4 col-span-6"),
                    css_class="col-span-6",
                ),
                HTML('<div class="col-span-12 mt-2 border-t border-base-300 pt-5"><h3 class="text-base font-semibold">Valores e ajuste</h3><p class="text-sm text-base-content/60">Informe se este lançamento possui desconto ou acréscimo. O valor líquido será calculado automaticamente.</p></div>'),
                Div("gross_amount", css_class="col-span-4"),
                Div("discount_mode", css_class="col-span-4"),
                Div("discount_value", css_class="col-span-4", css_id="discount-value-field"),
                Div("amount", css_class="col-span-4", css_id="net-amount-field"),
                Div("installments_count", css_class="col-span-12 md:col-span-3 max-w-xs", css_id="installments-count-field"),
                HTML('<div id="installment-schedule" class="col-span-12 hidden rounded-xl border border-primary/25 bg-primary/5 p-4"></div>'),
                #
                Div("attachment", css_class="col-span-12"),
                Div("financial_observation", css_class="col-span-12"),
                css_class="grid grid-cols-12 gap-4",
            ),
            HTML(FINANCIAL_DISCOUNT_UI_SCRIPT),
            HTML(f'<script id="financial-installment-schedule-initial" type="application/json">{json.dumps(self.initial_installment_schedule)}</script>'),
            HTML(FINANCIAL_INSTALLMENTS_UI_SCRIPT),
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
                schedule = self.cleaned_data.get("installment_schedule") or []
                if len(schedule) > 1:
                    self.request.session[f"installment_schedule_{instance.pk}"] = [
                        {"number": item.number, "total": item.total, "due_date": item.due_date.isoformat(), "amount": str(item.amount)}
                        for item in schedule
                    ]
                else:
                    self.request.session.pop(f"installment_schedule_{instance.pk}", None)
        return instance

    def clean_financial_observation(self):
        value = self.cleaned_data.get("financial_observation")
        return sentence_case(value) if value else value

    def clean(self):
        cleaned_data = super().clean()
        cleaned_data = self.clean_discount_fields(cleaned_data)
        for field, message in apply_payment_reconciliation_rules(cleaned_data):
            self.add_error(field, message)
        installments_count = int(cleaned_data.get("installments_count") or 1)
        repeat_count = int(cleaned_data.get("repeat_count") or 1)
        if installments_count > 1 and repeat_count > 1:
            self.add_error("installments_count", "Parcelamento e repetição são processos diferentes e não podem ser usados juntos.")
            return cleaned_data

        if self.instance.installment_plan_id:
            return cleaned_data

        if installments_count > 1 and cleaned_data.get("due_date") and cleaned_data.get("amount"):
            getlist = getattr(self.data, "getlist", None)
            due_dates = getlist("installment_due_date") if callable(getlist) else []
            amounts = getlist("installment_amount") if callable(getlist) else []
            try:
                if due_dates or amounts:
                    schedule = parse_installment_schedule(
                        due_dates=due_dates,
                        amounts=amounts,
                        expected_count=installments_count,
                        expected_total=cleaned_data["amount"].amount,
                    )
                else:
                    schedule = build_installments(
                        total_amount=cleaned_data["amount"].amount,
                        first_due_date=cleaned_data["due_date"],
                        installments_count=installments_count,
                    )
            except InstallmentScheduleError as exc:
                self.add_error(None, str(exc))
            else:
                cleaned_data["installment_schedule"] = schedule
                cleaned_data["due_date"] = schedule[0].due_date
        return cleaned_data


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

        installment_schedule = []
        if getattr(self, "request", None) and inst.pk:
            installment_schedule = self.request.session.get(f"installment_schedule_{inst.pk}", [])
        if not installment_schedule and inst.installment_plan_id:
            installment_schedule = [
                {"number": movement.installment_number, "total": movement.installments_count, "due_date": movement.due_date.isoformat(), "amount": str(movement.amount.amount)}
                for movement in inst.installment_plan.financial_movements.order_by("installment_number", "pk")
            ]
        installments_summary_html = ""
        if installment_schedule:
            rows = "".join(
                f'<tr><td>{item["number"]}/{item["total"]}</td><td>{date.fromisoformat(item["due_date"]).strftime("%d/%m/%Y")}</td><td class="text-right">R$ {Decimal(item["amount"]):.2f}</td></tr>'
                for item in installment_schedule
            )
            installments_summary_html = f'''<div class="mt-4 rounded-lg border border-base-300 bg-base-100 p-3"><p class="text-xs font-bold uppercase opacity-50">Parcelamento</p><table class="table table-xs mt-2"><thead><tr><th>Parcela</th><th>Vencimento</th><th class="text-right">Valor</th></tr></thead><tbody>{rows}</tbody></table></div>'''

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
                                        {installments_summary_html}
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
            installment_flag_key = f"generated_installments_{instance.pk}"
            if getattr(self, "request", None) and not self.request.session.get(installment_flag_key):
                schedule = self.request.session.pop(f"installment_schedule_{instance.pk}", None)
                if schedule:
                    self._generate_installments(instance, schedule)
                    self.request.session[installment_flag_key] = True
            flag_key = f"generated_reps_{instance.pk}"
            if getattr(self, "request", None) and not self.request.session.get(flag_key):
                repeat_count = self.request.session.pop(f"repeat_count_{instance.pk}", None)
                repeat_type = self.request.session.pop(f"repeat_type_{instance.pk}", None)
                if repeat_count and repeat_count > 0:
                    repeat_count = int(repeat_count) - 1 if repeat_count > 0 else int(repeat_count)
                    self._generate_repetitions(instance, repeat_count, repeat_type)
                    self.request.session[flag_key] = True
            generate_card_fee_movement(instance)
        return instance

    def _generate_repetitions(self, instance, count, r_type):
        import calendar
        import datetime

        def add_months(sourcedate, months):
            month = sourcedate.month - 1 + months
            year = sourcedate.year + month // 12
            month = month % 12 + 1
            day = min(sourcedate.day, calendar.monthrange(year, month)[1])
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

    def _generate_installments(self, instance, schedule):
        if instance.installment_plan_id or len(schedule) < 2:
            return

        original_gross_amount = instance.gross_amount
        original_discount_value = instance.discount_value
        original_amount = instance.amount
        plan = FinancialMovementInstallmentPlan.objects.create(
            workshop=instance.workshop,
            user=instance.user,
            gross_amount=original_gross_amount,
            adjustment_mode=instance.discount_mode,
            adjustment_value=original_discount_value,
            net_amount=original_amount,
            installments_count=len(schedule),
        )
        first_installment = schedule[0]
        instance.installment_plan = plan
        instance.installment_number = first_installment["number"]
        instance.installments_count = first_installment["total"]
        instance.description = f"{instance.description} - Parcela {first_installment['number']}/{first_installment['total']}"
        instance.due_date = date.fromisoformat(first_installment["due_date"])
        instance.gross_amount = Money(Decimal(first_installment["amount"]), original_amount.currency)
        instance.discount_mode = FinancialMovement.DiscountMode.NONE
        instance.discount_value = Money(Decimal("0.00"), original_amount.currency)
        instance.discount_percentage = Decimal("0.00")
        instance.save()

        for installment in schedule[1:]:
            new_instance = FinancialMovement.objects.get(pk=instance.pk)
            new_instance.pk = None
            new_instance.attachment = None
            new_instance.is_paid = False
            new_instance.installment_number = installment["number"]
            new_instance.installments_count = installment["total"]
            new_instance.description = new_instance.description.rsplit(" - Parcela ", 1)[0] + f" - Parcela {installment['number']}/{installment['total']}"
            new_instance.due_date = date.fromisoformat(installment["due_date"])
            new_instance.gross_amount = Money(Decimal(installment["amount"]), original_amount.currency)
            new_instance.amount = new_instance.gross_amount
            new_instance.save()


class ReportMovementEditForm(FinancialMovementBaseForm):
    """Formulário unificado para edição de movimentação financeira via modal no relatório."""

    ENTITY_REQUIRED_ERROR = "Selecione um fornecedor ou colaborador."
    ENTITY_EXCLUSIVE_ERROR = "Selecione apenas um fornecedor ou um colaborador."
    PAYMENT_METHOD_DIRECTION_ERROR = "Selecione uma forma de pagamento compatível com o tipo da movimentação."

    is_paid = forms.TypedChoiceField(
        label="Pago",
        required=True,
        coerce=lambda value: str(value).lower() == "true",
        choices=((False, "Não"), (True, "Sim")),
        widget=SearchableSelectInput(choices=[(False, "Não"), (True, "Sim")]),
        initial=False,
    )
    is_reconciled = forms.TypedChoiceField(
        label="Conciliado",
        required=True,
        coerce=lambda value: str(value).lower() == "true",
        choices=((False, "Aguardando Conciliação"), (True, "Conciliado")),
        widget=SearchableSelectInput(choices=[(False, "Aguardando Conciliação"), (True, "Conciliado")]),
        initial=False,
    )
    is_partial_payment = forms.TypedChoiceField(
        label="Pagamento parcial",
        required=False,
        coerce=lambda value: str(value).lower() == "true",
        empty_value=False,
        choices=((False, "Não"), (True, "Sim")),
        widget=SearchableSelectInput(choices=[(False, "Não"), (True, "Sim")]),
        initial=False,
    )
    partial_payment_amount = MoneyField(label="Valor pago", required=False, widget=MoneyInput())

    class Meta:
        model = FinancialMovement
        fields = [
            # Agente
            "supplier",
            "collaborator",
            # Itens
            "description",
            "items_observation",
            # Pagamento
            "entry_date",
            "due_date",
            "direction",
            "gross_amount",
            "discount_mode",
            "discount_value",
            "amount",
            "budget_plan",
            "bank_account",
            "payment_method",
            "is_paid",
            "is_reconciled",
            "nf_number",
            "financial_observation",
            "attachment",
        ]
        widgets = {
            "supplier": SearchableSelectInput(),
            "collaborator": SearchableSelectInput(),
            "description": TextInput(),
            "items_observation": TextareaInput(attrs={"rows": 3}),
            "entry_date": CalendarDateInput(),
            "due_date": CalendarDateInput(),
            "direction": SearchableSelectInput(),
            "gross_amount": MoneyInput(),
            "discount_mode": SearchableSelectInput(),
            "discount_value": MoneyInput(),
            "amount": MoneyInput(attrs={"readonly": "readonly"}),
            "budget_plan": SearchableSelectInput(),
            "bank_account": SearchableSelectInput(),
            "payment_method": SearchableSelectInput(),
            "nf_number": NumberInput(),
            "financial_observation": TextareaInput(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._was_paid = bool(self.instance.pk and self.instance.is_paid)
        self.payment_method_filter_data = {"CREDIT": [], "DEBIT": []}
        self.selected_workorder_payment: WorkOrderPaymentMethod | None = None

        self.fields["supplier"].required = False
        self.fields["collaborator"].required = False
        self.fields["description"].required = getattr(self.instance, "workorder_id", None) is None
        self.fields["due_date"].required = True
        self.fields["direction"].required = True
        self.fields["gross_amount"].required = True
        self.configure_discount_fields()
        self.fields["payment_method"].required = True
        self.fields["budget_plan"].required = True
        self.fields["budget_plan"].error_messages["required"] = BUDGET_PLAN_REQUIRED
        self.fields["bank_account"].required = False
        self.fields["is_paid"].initial = bool(self.instance.is_paid) if self.instance.pk else False
        self.fields["is_reconciled"].initial = bool(getattr(self.instance, "is_reconciled", False)) if self.instance.pk else False
        self.fields["partial_payment_amount"].widget.attrs["data-partial-payment-amount"] = "true"

        if getattr(self.instance, "workorder_id", None):
            raw_payment_id = ""
            if getattr(self, "request", None):
                raw_payment_id = self.request.GET.get("payment_id") if not self.is_bound else self.data.get("selected_workorder_payment_id")

            if raw_payment_id:
                self.selected_workorder_payment = WorkOrderPaymentMethod.objects.filter(pk=raw_payment_id, workorder=self.instance.workorder).select_related("payment_method").first()

            if self.selected_workorder_payment is None and getattr(self.instance, "workorder_payment_id", None):
                self.selected_workorder_payment = WorkOrderPaymentMethod.objects.filter(pk=self.instance.workorder_payment_id, workorder=self.instance.workorder).select_related("payment_method").first()

            if self.selected_workorder_payment is None and getattr(self.instance, "workorder", None) is not None:
                self.selected_workorder_payment = WorkOrderPaymentMethod.objects.filter(workorder=self.instance.workorder).select_related("payment_method").order_by("-pk").first()

            logger.warning(
                "[ReportMovementEditForm] workorder movement resolve payment | movement_id=%s kind=%s workorder_id=%s raw_payment_id=%s instance_workorder_payment_id=%s selected_workorder_payment_id=%s selected_workorder_payment_method_id=%s instance_payment_method_id=%s direction=%s",
                getattr(self.instance, "pk", None),
                getattr(self.instance, "movement_kind", None),
                getattr(self.instance, "workorder_id", None),
                raw_payment_id,
                getattr(self.instance, "workorder_payment_id", None),
                getattr(self.selected_workorder_payment, "pk", None),
                getattr(self.selected_workorder_payment, "payment_method_id", None),
                getattr(self.instance, "payment_method_id", None),
                getattr(self.instance, "direction", None),
            )

        if self.workshop:
            supplier_qs = Supplier.objects.filter(workshop=self.workshop)
            collaborator_qs = WorkshopCollaborator.objects.filter(workshop=self.workshop)
            payment_method_qs = self._get_payment_method_queryset()
            self.fields["supplier"].queryset = supplier_qs
            self.fields["supplier"].widget.choices = [(supplier.id, supplier.name) for supplier in supplier_qs]
            self.fields["collaborator"].queryset = collaborator_qs
            self.fields["collaborator"].widget.choices = [(collaborator.id, str(collaborator)) for collaborator in collaborator_qs]
            self.fields["payment_method"].queryset = payment_method_qs

            self.fields["payment_method"].widget.choices = [(pm.id, str(pm)) for pm in payment_method_qs]
            self.fields["budget_plan"].widget.choices = [("", "---------")] + [(bp.id, str(bp)) for bp in FinancialGroup.objects.filter(workshop=self.workshop)]
            bank_account_qs = self._get_bank_account_queryset()
            self.fields["bank_account"].queryset = bank_account_qs
            self.fields["bank_account"].widget.choices = [(ba.id, str(ba)) for ba in bank_account_qs]
            self.payment_method_filter_data = {
                "CREDIT": [str(payment_method.pk) for payment_method in payment_method_qs if payment_method.payment_type in [PaymentMethod.PaymentType.CREDIT, PaymentMethod.PaymentType.BOTH]],
                "DEBIT": [str(payment_method.pk) for payment_method in payment_method_qs if payment_method.payment_type in [PaymentMethod.PaymentType.DEBIT, PaymentMethod.PaymentType.BOTH]],
            }

            if self.selected_workorder_payment and self.selected_workorder_payment.payment_method_id:
                self.fields["payment_method"].initial = self.selected_workorder_payment.payment_method_id
            elif self.instance.payment_method_id:
                self.fields["payment_method"].initial = self.instance.payment_method_id

            logger.warning(
                "[ReportMovementEditForm] payment_method initial applied | movement_id=%s initial=%s queryset_size=%s",
                getattr(self.instance, "pk", None),
                self.fields["payment_method"].initial,
                self.fields["payment_method"].queryset.count() if hasattr(self.fields["payment_method"], "queryset") else -1,
            )

        selected_supplier = self.instance.supplier_id if self.instance.pk else None
        selected_collaborator = self.instance.collaborator_id if self.instance.pk else None

        if self.is_bound:
            selected_supplier = self.data.get("supplier") or None
            selected_collaborator = self.data.get("collaborator") or None

        if selected_supplier and not selected_collaborator:
            self.fields["collaborator"].widget.attrs["disabled"] = True
        elif selected_collaborator and not selected_supplier:
            self.fields["supplier"].widget.attrs["disabled"] = True

        details_context = self._build_entity_details_context()

        installment_indicator_html = ""
        if self.instance.installment_plan_id and self.instance.installment_number and self.instance.installments_count:
            installment_indicator_html = (
                '<span class="badge badge-warning gap-1 font-semibold text-warning-content shadow-sm">'
                '<span class="material-icons text-sm">calendar_month</span>'
                f"Parcela {self.instance.installment_number} de {self.instance.installments_count}"
                "</span>"
            )

        source_info_html = ""
        if self.instance.pk and self.instance.source_id and not self.instance.supplier_id and not self.instance.collaborator_id:
            source_name = str(getattr(self.instance.source, "name", "") or "")
            source_info_html = f'<div class="alert bg-base-200 border border-base-300 shadow-sm mb-10"><span class="material-icons text-sm text-base-content/50">info</span><div class="flex flex-col"><span class="text-xs font-bold uppercase opacity-50">Origem automática</span><span class="text-sm font-semibold">{source_name}</span><span class="text-xs opacity-60">Esta movimentação foi gerada automaticamente. Selecione um fornecedor ou colaborador acima para substituir a origem.</span></div></div>'

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            HTML('<section x-show="activeTab === \'initial\'" x-cloak class="space-y-4">') if self.instance.workorder_id is None else HTML(""),
            HTML('<h3 class="text-base font-semibold text-base-content flex items-center gap-2 mb-3"><span class="material-icons text-sm">groups</span> Dados Iniciais</h3>') if self.instance.workorder_id is None else HTML(""),
            HTML(source_info_html) if self.instance.workorder_id is None else HTML(""),
            Div(
                Div("supplier", css_class="col-span-12 lg:col-span-6"),
                Div("collaborator", css_class="col-span-12 lg:col-span-6"),
                Div(
                    HTML(render_to_string(details_context["template"], details_context["context"])),
                    id="report-edit-entity-details",
                    css_class="col-span-12",
                ),
                css_class="grid grid-cols-12 gap-4",
            )
            if self.instance.workorder_id is None
            else HTML(""),
            HTML("</section>") if self.instance.workorder_id is None else HTML(""),
            HTML('<section x-show="activeTab === \'item\'" x-cloak class="space-y-4">') if self.instance.workorder_id is None else HTML(""),
            HTML('<h3 class="text-base font-semibold text-base-content flex items-center gap-2 mb-3"><span class="material-icons text-sm">inventory_2</span> Sobre o Item</h3>') if self.instance.workorder_id is None else HTML(""),
            Div(
                Div("description", css_class="col-span-12"),
                Div("items_observation", css_class="col-span-12"),
                css_class="grid grid-cols-12 gap-4",
            )
            if self.instance.workorder_id is None
            else HTML(""),
            HTML("</section>") if self.instance.workorder_id is None else HTML(""),
            HTML('<section x-show="activeTab === \'payment\'" x-cloak class="space-y-4">'),
            HTML(
                '<div class="flex items-center justify-between gap-4 mb-3">'
                '<h3 class="text-base font-semibold text-base-content flex items-center gap-2">'
                '<span class="material-icons text-sm">payments</span> Sobre o Pagamento</h3>'
                f"{installment_indicator_html}"
                "</div>"
            ),
            Div(
                Div("entry_date", css_class="col-span-12 lg:col-span-4"),
                Div("due_date", css_class="col-span-12 lg:col-span-4"),
                Div("direction", css_class="col-span-12 lg:col-span-4"),
                #
                Div("budget_plan", css_class="col-span-12 lg:col-span-6"),
                Div("bank_account", css_class="col-span-12 lg:col-span-6"),
                #
                Div("payment_method", css_class="col-span-12 lg:col-span-4"),
                Div("is_paid", css_class="col-span-12 lg:col-span-4"),
                Div("is_reconciled", css_class="col-span-12 lg:col-span-4"),
                Div("is_partial_payment", css_class="col-span-12 lg:col-span-4 partial-payment-option"),
                Div("partial_payment_amount", css_class="col-span-12 lg:col-span-4 partial-payment-amount"),
                Div("nf_number", css_class="col-span-12 lg:col-span-4"),
                HTML('<div class="col-span-12 mt-2 border-t border-base-300 pt-5"><h3 class="text-base font-semibold">Valores e ajuste</h3><p class="text-sm text-base-content/60">Informe se este lançamento possui desconto ou acréscimo. O valor líquido será calculado automaticamente.</p></div>'),
                Div("gross_amount", css_class="col-span-12 lg:col-span-4"),
                Div("discount_mode", css_class="col-span-12 lg:col-span-4"),
                Div("discount_value", css_class="col-span-12 lg:col-span-4", css_id="discount-value-field"),
                Div("amount", css_class="col-span-12 lg:col-span-4", css_id="net-amount-field"),
                Div("financial_observation", css_class="col-span-12"),
                css_class="grid grid-cols-12 gap-4",
            ),
            HTML(FINANCIAL_DISCOUNT_UI_SCRIPT),
            HTML("</section>"),
            HTML('<section x-show="activeTab === \'attachment\'" x-cloak class="space-y-4">'),
            HTML('<h3 class="text-base font-semibold text-base-content flex items-center gap-2 mb-3"><span class="material-icons text-sm">attach_file</span> Anexo</h3>'),
            Div(
                Div("attachment", css_class="col-span-12"),
                css_class="grid grid-cols-12 gap-4",
            ),
            HTML("</section>"),
        )

    @property
    def was_initially_paid(self) -> bool:
        """Status persistido antes de o ModelForm aplicar os dados do POST na instância."""
        return self._was_paid

    def clean_description(self):
        value = self.cleaned_data.get("description")
        return sentence_case(value) if value else value

    def clean_items_observation(self):
        value = self.cleaned_data.get("items_observation")
        return sentence_case(value) if value else value

    def clean_financial_observation(self):
        value = self.cleaned_data.get("financial_observation")
        return sentence_case(value) if value else value

    def _build_entity_details_context(self) -> dict[str, object]:
        supplier_id = self.data.get("supplier") or (self.instance.supplier_id if self.instance.pk else None)
        collaborator_id = self.data.get("collaborator") or (self.instance.collaborator_id if self.instance.pk else None)

        if supplier_id and self.workshop:
            supplier = Supplier.objects.filter(id=supplier_id, workshop=self.workshop).first()
            return {"template": "finance/partials/supplier_resume.html", "context": {"entity": supplier, "type": "supplier"}}

        if collaborator_id and self.workshop:
            collaborator = WorkshopCollaborator.objects.filter(id=collaborator_id, workshop=self.workshop).first()
            return {"template": "finance/partials/collaborator_resume.html", "context": {"entity": collaborator, "type": "collaborator"}}

        if self.instance.pk and self.instance.source_id:
            return {"template": "finance/partials/source_resume.html", "context": {"entity": self.instance.source, "type": "source"}}

        return {
            "template": "finance/partials/financial_movement/report_edit_entity_placeholder.html",
            "context": {},
        }

    def _get_payment_method_queryset(self):
        payment_methods = PaymentMethod.objects.filter(workshop=self.workshop, is_active=True)

        pinned_payment_method_ids: set[int] = set()
        if self.instance.pk and self.instance.payment_method_id:
            pinned_payment_method_ids.add(int(self.instance.payment_method_id))
        if self.selected_workorder_payment and self.selected_workorder_payment.payment_method_id:
            pinned_payment_method_ids.add(int(self.selected_workorder_payment.payment_method_id))

        if pinned_payment_method_ids:
            payment_methods = PaymentMethod.objects.filter(workshop=self.workshop).filter(Q(is_active=True) | Q(pk__in=pinned_payment_method_ids))

        return payment_methods.order_by("description").distinct()

    def _get_bank_account_queryset(self):
        bank_accounts = BankAccount.objects.filter(workshop=self.workshop, is_active=True)

        pinned_bank_account_ids: set[int] = set()
        if self.instance.pk and self.instance.bank_account_id:
            pinned_bank_account_ids.add(int(self.instance.bank_account_id))

        if pinned_bank_account_ids:
            bank_accounts = BankAccount.objects.filter(workshop=self.workshop).filter(
                Q(is_active=True) | Q(pk__in=pinned_bank_account_ids)
            )

        return bank_accounts.order_by("bank_name", "account_number", "id").distinct()

    @staticmethod
    def _payment_method_matches_direction(payment_method, direction):
        if direction == FinancialMovement.MovementDirection.CREDIT:
            return payment_method.payment_type in [PaymentMethod.PaymentType.CREDIT, PaymentMethod.PaymentType.BOTH]

        if direction == FinancialMovement.MovementDirection.DEBIT:
            return payment_method.payment_type in [PaymentMethod.PaymentType.DEBIT, PaymentMethod.PaymentType.BOTH]

        return True

    def clean(self):
        cleaned_data = super().clean()
        cleaned_data = self.clean_discount_fields(cleaned_data)
        supplier = cleaned_data.get("supplier")
        collaborator = cleaned_data.get("collaborator")
        direction = cleaned_data.get("direction")
        payment_method = cleaned_data.get("payment_method")

        if getattr(self.instance, "workorder_id", None) and payment_method is None:
            if self.selected_workorder_payment and self.selected_workorder_payment.payment_method is not None:
                payment_method = self.selected_workorder_payment.payment_method
                cleaned_data["payment_method"] = payment_method
            elif self.instance.payment_method is not None:
                payment_method = self.instance.payment_method
                cleaned_data["payment_method"] = payment_method

        if not getattr(self.instance, "workorder_id", None):
            if supplier and collaborator:
                self.add_error("supplier", self.ENTITY_EXCLUSIVE_ERROR)
                self.add_error("collaborator", self.ENTITY_EXCLUSIVE_ERROR)
            elif not supplier and not collaborator:
                self.add_error("supplier", self.ENTITY_REQUIRED_ERROR)
                self.add_error("collaborator", self.ENTITY_REQUIRED_ERROR)

        if getattr(self.instance, "movement_kind", None) != FinancialMovement.MovementKind.WORKORDER_CARD_FEE and payment_method and direction and not self._payment_method_matches_direction(payment_method, direction):
            self.add_error("payment_method", self.PAYMENT_METHOD_DIRECTION_ERROR)

        if cleaned_data.get("is_partial_payment"):
            # A partial settlement always settles the paid portion. The user
            # should not need to mark the same payment as paid a second time.
            cleaned_data["is_paid"] = True
            paid_amount = cleaned_data.get("partial_payment_amount")
            total_amount = cleaned_data.get("amount")
            if direction != FinancialMovement.MovementDirection.DEBIT:
                self.add_error("is_partial_payment", "Pagamento parcial está disponível apenas para contas a pagar.")
            if paid_amount is None:
                self.add_error("partial_payment_amount", "Informe o valor efetivamente pago.")
            elif total_amount is not None and (paid_amount <= Money(0, paid_amount.currency) or paid_amount >= total_amount):
                self.add_error("partial_payment_amount", "O valor pago deve ser maior que zero e menor que o valor total da conta.")
            if self._was_paid:
                self.add_error("is_partial_payment", "Não é possível dividir uma conta que já foi paga.")

        for field, message in apply_payment_reconciliation_rules(cleaned_data):
            self.add_error(field, message)

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        supplier = self.cleaned_data.get("supplier")
        collaborator = self.cleaned_data.get("collaborator")

        if getattr(self.instance, "workorder_id", None) and self.instance.movement_kind == FinancialMovement.MovementKind.WORKORDER_PARENT and self.selected_workorder_payment is not None and getattr(self.instance, "workorder_payment_id", None) != self.selected_workorder_payment.pk:
            target_instance = (
                FinancialMovement.objects.filter(
                    workorder=self.instance.workorder,
                    workorder_payment=self.selected_workorder_payment,
                    movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
                )
                .exclude(pk=self.instance.pk)
                .order_by("-pk")
                .first()
            )
            if target_instance is None:
                target_instance = FinancialMovement(
                    workshop=self.instance.workshop,
                    user=self.instance.user,
                    workorder=self.instance.workorder,
                    workorder_payment=self.selected_workorder_payment,
                    movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
                    source=self.instance.source,
                )

            for field_name in self._meta.fields:
                setattr(target_instance, field_name, getattr(instance, field_name))

            target_instance.workorder = self.instance.workorder
            target_instance.workorder_payment = self.selected_workorder_payment
            target_instance.movement_kind = FinancialMovement.MovementKind.WORKORDER_PARENT
            target_instance.source = self.instance.source
            instance = target_instance

        instance.source = None
        instance.supplier = supplier if supplier else None
        instance.collaborator = collaborator if collaborator else None

        if supplier:
            instance.collaborator = None
        if collaborator:
            instance.supplier = None

        if commit:
            instance.save()
            self.save_m2m()
            if self.cleaned_data.get("is_partial_payment"):
                try:
                    create_partial_payment_balance(
                        paid_movement=instance,
                        paid_amount=self.cleaned_data["partial_payment_amount"],
                    )
                except ValidationError as exc:
                    raise ValueError(str(exc)) from exc

        return instance
