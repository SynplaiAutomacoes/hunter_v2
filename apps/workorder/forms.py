import json
from decimal import Decimal
from typing import Any, Protocol, cast

from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Field, HTML, Layout, Submit
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from djmoney.forms import MoneyField
from djmoney.money import Money

from django.forms import CheckboxInput, RadioSelect

from apps.budget.pricing import money_from_decimal, resolve_discount_fields
from apps.collaborators.models import WorkshopCollaborator
from apps.collaborators.services import work_assignable_collaborators
from apps.budget.forms.widgets import MultipleFileInput
from apps.core.text_normalization import sentence_case
from apps.core.presentation.widgets import CalendarDateInput, DurationInput, MoneyInput, NumberInput, PercentageInput, RadioButtonGroupInput, SearchableSelectInput, TextInput, TextareaInput
from apps.finance.models.payment_method import PaymentMethod
from apps.workorder.models import WorkOrder, WorkOrderAttachment, WorkOrderCourtesyReasonType, WorkOrderDiscountType, WorkOrderItem, WorkOrderItemBenefitType, WorkOrderPaymentMethod, WorkOrderSignatureStatus, WorkOrderStatus, WorkOrderWarrantyPlan
from apps.terms.models import TermTemplateType, WorkshopTermTemplate
from apps.terms.selectors import get_default_term_template
from apps.workshops.models.review_plans import ReviewPlan
from apps.core.presentation.forms import CoreForm, CoreModelForm


MONEY_ZERO = Decimal("0.00")


class _BoundDataProtocol(Protocol):
    def copy(self) -> Any: ...


def _quantize_money_amount(value: Decimal) -> Decimal:
    return money_from_decimal(value).amount


def _format_brl_amount(value: Decimal) -> str:
    return f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


class WorkOrderCollaboratorForm(CoreModelForm):
    collaborators: forms.ModelMultipleChoiceField = forms.ModelMultipleChoiceField(label="Colaboradores da O.S.", queryset=WorkshopCollaborator.objects.none(), required=False)

    class Meta:
        model = WorkOrder
        fields = ["collaborators"]

    def __init__(self, *args, workorder: WorkOrder | None = None, **kwargs) -> None:
        self.workorder = workorder or kwargs.get("instance")
        super().__init__(*args, **kwargs)
        if self.is_bound and "collaborators_list" in self.data and hasattr(self.data, "copy"):
            bound_data = self.data.copy()
            bound_data.setlist("collaborators", [collaborator_id for collaborator_id in bound_data.getlist("collaborators_list") if collaborator_id.strip()])
            self.data = bound_data

        workshop = getattr(self.workorder, "workshop", None)
        queryset = WorkshopCollaborator.objects.none()
        if workshop is not None:
            include_ids = list(self.workorder.collaborators.values_list("id", flat=True)) if getattr(self.workorder, "pk", None) else []
            queryset = work_assignable_collaborators(workshop=workshop, include_ids=include_ids)
        self.fields["collaborators"].queryset = queryset
        self.fields["collaborators"].help_text = "Selecione os colaboradores responsaveis por esta O.S. A comissao prevista sera calculada a partir desta vinculacao."

    @property
    def initial_collaborators_json(self) -> str:
        initial_collaborators = []
        if self.workorder and self.workorder.pk:
            initial_collaborators = [{"id": str(collaborator.id), "name": collaborator.name, "is_new": False} for collaborator in self.workorder.collaborators.all()]
        if not initial_collaborators:
            initial_collaborators = [{"id": "", "is_new": True}]
        return json.dumps(initial_collaborators)


class WorkOrderPaymentForm(CoreModelForm):
    entry_amount = MoneyField(label="Valor de entrada", required=False, widget=MoneyInput)
    total_value = forms.CharField(label="Valor Total", required=False, widget=MoneyInput)
    paid_value = forms.CharField(label="Valor Pago", required=False, widget=MoneyInput)
    pending_value = forms.CharField(label="Valor Pendente", required=False, widget=MoneyInput)
    discount_value = MoneyField(label="Desconto em R$", required=False, widget=MoneyInput)
    discount_percentage = forms.DecimalField(
        label="Desconto em %",
        required=False,
        min_value=Decimal("0"),
        max_value=Decimal("1"),
        decimal_places=6,
        max_digits=7,
        widget=PercentageInput(decimal_places=2, behavior="digit_stream"),
    )
    discount_type = forms.ChoiceField(
        label="Selecione o Desconto",
        choices=WorkOrderDiscountType.choices,
        required=False,
        widget=RadioButtonGroupInput,
    )

    class Meta:
        model = WorkOrderPaymentMethod
        fields = ["payment_method", "first_installment_amount", "due_date"]
        widgets = {
            "payment_method": SearchableSelectInput(),
            "first_installment_amount": MoneyInput(),
            "due_date": CalendarDateInput(),
        }

    def __init__(self, *args, **kwargs) -> None:
        self.workorder = kwargs.pop("workorder", None)
        super().__init__(*args, **kwargs)

        payment_methods = PaymentMethod.objects.none()
        if self.workorder:
            payment_methods = PaymentMethod.objects.filter(workshop=self.workorder.workshop, is_active=True).order_by("description")

        payment_method_field = cast(Any, self.fields["payment_method"])
        payment_method_field.queryset = payment_methods
        payment_method_field.required = True
        payment_method_field.label_from_instance = lambda obj: obj.description
        self.is_first_payment = bool(self.workorder and not self.workorder.payments.exists())
        self.fields["entry_amount"].required = self.is_first_payment
        self.fields["first_installment_amount"].label = "Valor a ser pago"
        self.fields["first_installment_amount"].required = not self.is_first_payment
        self.fields["due_date"].required = False

        total_os = _quantize_money_amount(self.workorder.total_budget_value.amount) if self.workorder else MONEY_ZERO
        paid_amount = self._get_paid_amount() if self.workorder else MONEY_ZERO
        pending_amount = _quantize_money_amount(total_os - paid_amount)
        payment_is_fully_paid = pending_amount <= MONEY_ZERO
        pending_amount_display = pending_amount if pending_amount > MONEY_ZERO else MONEY_ZERO
        base_total = self.workorder.total_base_value if self.workorder else Money(MONEY_ZERO, "BRL")
        discount_value = Money(MONEY_ZERO, "BRL")
        discount_percentage = Decimal("0.00")

        blocked_value_attrs = {"readonly": True, "class": "cursor-not-allowed opacity-75"}
        fully_paid_value_attrs = {**blocked_value_attrs, "disabled": True, "title": "OS paga por completo"}

        no_payment_required = bool(self.workorder and self.workorder.budget_type in ("warranty", "courtesy"))

        if no_payment_required:
            for field_name in ["entry_amount", "first_installment_amount", "payment_method", "due_date"]:
                self.fields[field_name].disabled = True
                self.fields[field_name].widget.attrs.update(fully_paid_value_attrs)
        elif payment_is_fully_paid:
            for field_name in ["entry_amount", "first_installment_amount", "payment_method", "due_date"]:
                self.fields[field_name].disabled = True
                self.fields[field_name].widget.attrs.update(fully_paid_value_attrs)
        elif self.is_first_payment:
            self.fields["first_installment_amount"].disabled = True
            self.fields["first_installment_amount"].widget.attrs.update(blocked_value_attrs)
        else:
            self.fields["entry_amount"].disabled = True
            self.fields["entry_amount"].widget.attrs.update(blocked_value_attrs)

        if self.workorder:
            discount_value, discount_percentage = resolve_discount_fields(
                total_base_value=self.workorder.total_base_value,
                discount_value=self.workorder.discount_value,
                discount_percentage=self.workorder.discount_percentage,
            )

        resume_values = {
            "total_value": Money(total_os, "BRL"),
            "paid_value": Money(paid_amount, "BRL"),
            "pending_value": Money(pending_amount_display, "BRL"),
        }

        bound_data = cast(_BoundDataProtocol, self.data).copy() if self.is_bound and hasattr(self.data, "copy") else None

        for field_name, value in resume_values.items():
            self.initial[field_name] = value

            if bound_data is not None:
                bound_data[f"{field_name}_0"] = str(value.amount)
                bound_data[f"{field_name}_1"] = "BRL"

        if bound_data is not None:
            self.data = bound_data

        for field in ["total_value", "paid_value", "pending_value"]:
            self.fields[field].widget.attrs.update({"readonly": True, "class": "cursor-not-allowed opacity-75"})

        self.fields["discount_value"].widget.attrs.update({"class": "font-semibold text-lg"})
        self.fields["discount_percentage"].widget.attrs.update({"class": "font-semibold text-lg"})
        self.fields["discount_type"].widget.attrs.update({"class": "discount-type-radio"})
        self.initial["discount_value"] = discount_value
        self.initial["discount_percentage"] = discount_percentage
        self.initial["discount_type"] = self.workorder.discount_type if self.workorder else WorkOrderDiscountType.BOTH

        if not self.is_bound and not self.initial.get("due_date"):
            self.initial["due_date"] = ""

        pending_amount_js = format(pending_amount, "f")
        today_iso = timezone.localdate().isoformat()
        is_first_payment_js = "true" if self.is_first_payment else "false"
        no_payment_required = bool(self.workorder and self.workorder.budget_type in ("warranty", "courtesy"))
        payment_success_container_class = "col-span-12 mb-4" if (payment_is_fully_paid or no_payment_required) else "hidden col-span-12 mb-4"

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            HTML(f"""
                <div id="payment-success-workorder-js" class="{payment_success_container_class}">
                    <div class="alert alert-success shadow-lg border-2 border-success">
                        <span class="material-icons">check_circle</span>
                        <div>
                            <h3 class="font-bold text-sm">{'Ordem de Serviço não exige pagamento' if no_payment_required else 'Ordem de Serviço completamente paga'}</h3>
                            <div class="text-xs">{'Ordens de serviço do tipo Garantia ou Cortesia não exigem pagamento.' if no_payment_required else 'A ordem de serviço foi paga completamente.'}</div>
                        </div>
                    </div>
                </div>
            """),
            Div(
                HTML(
                    """
                    <div class="grid grid-cols-1 gap-3 mb-5 xl:grid-cols-3">
                    """
                ),
                Div(
                    HTML(
                        """
                        <div id="discount-value-card-body" class="h-full rounded-[1.5rem] border border-base-300 bg-base-100/90 p-4 shadow-sm">
                            <div class="mb-3 flex items-center justify-between gap-3">
                                <div>
                                    <p class="text-sm font-bold text-base-content">Desconto em valor</p>
                                    <p class="text-xs text-base-content/60">Use quando a negociação foi fechada em valor exato.</p>
                                </div>
                                <span class="material-icons text-base-content/40">payments</span>
                            </div>
                        """
                    ),
                    Field("discount_value", wrapper_class="mb-0"),
                    HTML("</div>"),
                    css_class="h-full",
                ),
                Div(
                    HTML(
                        """
                        <div class="h-full rounded-[1.5rem] border border-base-300 bg-base-100/90 p-4 shadow-sm">
                            <div class="mb-3 flex items-center justify-between gap-3">
                                <div>
                                    <p class="text-sm font-bold text-base-content">Tipo de Desconto</p>
                                    <p class="text-xs text-base-content/60">Selecione onde o desconto sera aplicado.</p>
                                </div>
                                <span class="material-icons text-base-content/40">filter_alt</span>
                            </div>
                        """
                    ),
                    Field("discount_type", wrapper_class="mb-0"),
                    HTML("</div>"),
                    css_class="h-full",
                ),
                Div(
                    HTML(
                        """
                        <div id="discount-percentage-card-body" class="h-full rounded-[1.5rem] border border-base-300 bg-base-100/90 p-4 shadow-sm">
                            <div class="mb-3 flex items-center justify-between gap-3">
                                <div>
                                    <p class="text-sm font-bold text-base-content">Desconto em percentual</p>
                                    <p class="text-xs text-base-content/60">Ideal para manter a mesma política comercial em diferentes totais.</p>
                                </div>
                                <span class="material-icons text-base-content/40">percent</span>
                            </div>
                        """
                    ),
                    Field("discount_percentage", wrapper_class="mb-0"),
                    HTML("</div>"),
                    css_class="h-full",
                ),
                HTML("</div>"),
            ),
            HTML('<div class="mb-3 flex justify-end"><span id="workorder-discount-save-status" class="text-xs text-base-content/60" aria-live="polite"></span></div>'),
            Div(
                Field("total_value", wrapper_class="col-span-12 lg:col-span-4"),
                Field("paid_value", wrapper_class="col-span-12 lg:col-span-4"),
                Field("pending_value", wrapper_class="col-span-12 lg:col-span-4"),
                css_class="grid grid-cols-12 gap-4 mb-2 pb-4 border-b-2 border-base-50",
            ),
            Div(
                Field("entry_amount", wrapper_class="col-span-12 lg:col-span-3"),
                Field("first_installment_amount", wrapper_class="col-span-12 lg:col-span-3"),
                Field("payment_method", wrapper_class="col-span-12 lg:col-span-3"),
                Field("due_date", wrapper_class="col-span-12 lg:col-span-3"),
                css_class="grid grid-cols-12 gap-4 mb-2 mt-4",
            ),
            Div(
                HTML("""
                    <div id="payment-warning-workorder-js" class="hidden w-full lg:max-w-2xl lg:mr-auto">
                        <div class="alert alert-error shadow-sm border-2 border-error payment-warning-card">
                            <span class="material-icons payment-warning-icon">error_outline</span>
                            <div>
                                <h3 class="font-bold text-sm payment-warning-title">Valor Não Permitido</h3>
                                <div class="text-xs payment-warning-message">
                                </div>
                            </div>
                        </div>
                    </div>
                """),
                Submit("submit", "Salvar Plano de Pagamento", css_class="btn-form-save btn-primary self-end lg:shrink-0"),
                css_class="mt-4 flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-end",
            ),
            HTML(f"""
            <script>
                (function() {{
                    window.initWorkOrderPaymentForm = function() {{
                        const paymentForm = document.getElementById('payment-form-fields');
                        if (!paymentForm || paymentForm.dataset.paymentInitialized === 'true') {{
                            return;
                        }}

                        const formElement = paymentForm.closest('form');
                        const isFirstPayment = {is_first_payment_js};
                        const paymentMethodInput = document.getElementById('id_payment_method');
                        const entryAmountInput = document.getElementById('id_entry_amount_0');
                        const entryAmountDisplay = document.getElementById('id_entry_amount_0_display');
                        const firstAmountInput = document.getElementById('id_first_installment_amount_0');
                        const firstAmountDisplay = document.getElementById('id_first_installment_amount_0_display');
                        const activeAmountInput = isFirstPayment ? entryAmountInput : firstAmountInput;
                        const activeAmountDisplay = isFirstPayment ? entryAmountDisplay : firstAmountDisplay;
                        const dueDateInput = document.getElementById('id_due_date');
                        const btnSave = formElement ? formElement.querySelector('.btn-form-save') : null;
                        const warningDiv = document.getElementById('payment-warning-workorder-js');
                        const warningMessage = warningDiv ? warningDiv.querySelector('.payment-warning-message') : null;
                        let pendingValue = parseFloat('{pending_amount_js}') || 0;
                        const todayValue = '{today_iso}';
                        const discountMoneyDisplay = document.getElementById('id_discount_value_0_display');
                        const discountMoneyHidden = document.getElementById('id_discount_value_0');
                        const discountPercentageDisplay = document.getElementById('id_discount_percentage_display');
                        const discountPercentageHidden = document.getElementById('id_discount_percentage');
                        const discountDisplay = document.getElementById('workorder-discount-display');
                        const totalDisplay = document.getElementById('workorder-total-final-display');
                        const percentageChip = document.getElementById('workorder-discount-percentage-display');
                        const discountSaveStatus = document.getElementById('workorder-discount-save-status');
                        const totalValueHidden = document.getElementById('id_total_value_0');
                        const totalValueDisplay = document.getElementById('id_total_value_0_display');
                        const paidValueHidden = document.getElementById('id_paid_value_0');
                        const paidValueDisplay = document.getElementById('id_paid_value_0_display');
                        const pendingValueHidden = document.getElementById('id_pending_value_0');
                        const pendingValueDisplay = document.getElementById('id_pending_value_0_display');
                        const discountPersistUrl = '{reverse("workorder:update_discount", args=[self.workorder.pk]) if self.workorder else ""}';
                        const discountValueCardBody = document.getElementById('discount-value-card-body');
                        const discountPercentageCardBody = document.getElementById('discount-percentage-card-body');
                        const discountTypeValue = () => {{
                            const checked = document.querySelector('input[name="discount_type"]:checked');
                            return checked ? checked.value : 'both';
                        }};
                        let discountTimeout = null;
                        let discountRequestController = null;
                        let discountRequestId = 0;

                        if (!paymentMethodInput || !activeAmountInput || !btnSave) {{
                            return;
                        }}

                        paymentForm.dataset.paymentInitialized = 'true';

                        const toggleWarning = (show, message) => {{
                            if (!warningDiv || !warningMessage) {{
                                return;
                            }}
                            warningDiv.classList.toggle('hidden', !show);
                            warningMessage.textContent = message || '';
                        }};
                        const updateDueDate = (force) => {{
                            if (dueDateInput && paymentMethodInput.value && (force || !dueDateInput.value)) {{
                                dueDateInput.value = todayValue;
                            }}
                        }};
                        const parseDotDecimal = (value) => {{
                            const normalized = String(value ?? '').trim().replace(',', '.');
                            if (!normalized) return 0;
                            const parsed = Number.parseFloat(normalized);
                            return Number.isFinite(parsed) ? parsed : 0;
                        }};
                        const baseTotalValue = parseDotDecimal('{base_total.amount}');
                        const clamp = (value, min, max) => Math.min(Math.max(value, min), max);
                        const roundCurrency = (value) => Math.round((value + Number.EPSILON) * 100) / 100;
                        const formatMoney = (value) => value.toLocaleString('pt-BR', {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }});
                        const formatFraction = (fraction) => fraction.toFixed(6).replace(/0+$/, '').replace(/\.$/, '');
                        const formatPercentageDisplay = (fraction) => (fraction * 100).toLocaleString('pt-BR', {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }});
                        const getBaseTotal = () => baseTotalValue;
                        const updateDiscountSummary = (discountAmount, fraction) => {{
                            if (!discountDisplay || !totalDisplay || !percentageChip) {{
                                return;
                            }}
                            const baseTotal = getBaseTotal();
                            const resolvedDiscount = clamp(roundCurrency(discountAmount), 0, baseTotal);
                            const totalValue = roundCurrency(baseTotal - resolvedDiscount);
                            discountDisplay.textContent = `R$ ${{formatMoney(resolvedDiscount)}}`;
                            totalDisplay.textContent = `R$ ${{formatMoney(totalValue)}}`;
                            percentageChip.textContent = `${{formatPercentageDisplay(fraction)}}%`;
                        }};
                        const updateFromMoneyField = () => {{
                            if (!discountMoneyHidden || !discountMoneyDisplay || !discountPercentageHidden || !discountPercentageDisplay) {{
                                return;
                            }}
                            const baseTotal = getBaseTotal();
                            const amount = clamp(roundCurrency(parseDotDecimal(discountMoneyHidden.value)), 0, baseTotal);
                            const hasAmount = amount > 0;
                            discountMoneyHidden.value = amount.toFixed(2);
                            discountMoneyDisplay.value = formatMoney(amount);
                            if (hasAmount) {{
                                discountPercentageHidden.value = '0';
                                discountPercentageDisplay.value = formatPercentageDisplay(0);
                                discountPercentageDisplay.disabled = true;
                            }} else {{
                                discountPercentageHidden.value = '0';
                                discountPercentageDisplay.value = formatPercentageDisplay(0);
                                discountPercentageDisplay.disabled = false;
                            }}
                            updateDiscountSummary(amount, 0);
                        }};
                        const updateFromPercentageField = () => {{
                            if (!discountMoneyHidden || !discountMoneyDisplay || !discountPercentageHidden || !discountPercentageDisplay) {{
                                return;
                            }}
                            const baseTotal = getBaseTotal();
                            const fraction = clamp(parseDotDecimal(discountPercentageHidden.value), 0, 1);
                            const hasFraction = fraction > 0;
                            discountPercentageHidden.value = formatFraction(fraction);
                            discountPercentageDisplay.value = formatPercentageDisplay(fraction);
                            if (hasFraction) {{
                                discountMoneyHidden.value = '0.00';
                                discountMoneyDisplay.value = formatMoney(0);
                                discountMoneyDisplay.disabled = true;
                            }} else {{
                                discountMoneyHidden.value = '0.00';
                                discountMoneyDisplay.value = formatMoney(0);
                                discountMoneyDisplay.disabled = false;
                            }}
                            updateDiscountSummary(0, fraction);
                        }};
                        const setDiscountStatus = (status, message = '') => {{
                            if (!discountSaveStatus) {{
                                return;
                            }}
                            discountSaveStatus.textContent = message;
                            discountSaveStatus.classList.remove('text-base-content/60', 'text-success', 'text-error');
                            if (status === 'saved') {{
                                discountSaveStatus.classList.add('text-success');
                            }} else if (status === 'error') {{
                                discountSaveStatus.classList.add('text-error');
                            }} else {{
                                discountSaveStatus.classList.add('text-base-content/60');
                            }}
                        }};
                        const sendDiscountRequest = () => {{
                            if (!discountPersistUrl || !discountMoneyHidden || !discountPercentageHidden) {{
                                return;
                            }}

                            if (discountRequestController) {{
                                discountRequestController.abort();
                            }}

                            const csrfInput = formElement ? formElement.querySelector('input[name="csrfmiddlewaretoken"]') : null;
                            const csrfToken = csrfInput ? csrfInput.value : '';
                            const requestId = discountRequestId + 1;
                            discountRequestId = requestId;
                            discountRequestController = new AbortController();
                            setDiscountStatus('saving', 'Salvando...');

                            const payload = new URLSearchParams();
                            payload.set('discount_value_0', discountMoneyHidden.value);
                            payload.set('discount_percentage', discountPercentageHidden.value);
                            payload.set('discount_type', discountTypeValue());

                            fetch(discountPersistUrl, {{
                                method: 'POST',
                                headers: {{
                                    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                                    'X-Requested-With': 'XMLHttpRequest',
                                    ...(csrfToken ? {{ 'X-CSRFToken': csrfToken }} : {{}}),
                                }},
                                body: payload.toString(),
                                signal: discountRequestController.signal,
                            }})
                                .then((response) => response.json().then((data) => ({{ response, data }})))
                                .then(({{ response, data }}) => {{
                                    if (requestId !== discountRequestId) {{
                                        return;
                                    }}
                                    if (!response.ok || !data.ok) {{
                                        throw new Error(data.error || 'Falha ao salvar desconto.');
                                    }}
                                    const totalValue = roundCurrency(parseDotDecimal(data.total_budget_value));
                                    const paidValue = roundCurrency(parseDotDecimal(data.paid_value));
                                    pendingValue = roundCurrency(parseDotDecimal(data.pending_value));
                                    if (totalValueHidden) totalValueHidden.value = totalValue.toFixed(2);
                                    if (totalValueDisplay) totalValueDisplay.value = formatMoney(totalValue);
                                    if (paidValueHidden) paidValueHidden.value = paidValue.toFixed(2);
                                    if (paidValueDisplay) paidValueDisplay.value = formatMoney(paidValue);
                                    if (pendingValueHidden) pendingValueHidden.value = pendingValue.toFixed(2);
                                    if (pendingValueDisplay) pendingValueDisplay.value = formatMoney(pendingValue);
                                    if (typeof window.updateWorkorderDeliveryButtonState === 'function') {{
                                        window.updateWorkorderDeliveryButtonState({{
                                            hasCompletionBlockers: Boolean(data.has_completion_blockers),
                                            completionBlockersDisplay: data.completion_blockers_display || '',
                                        }});
                                    }}
                                    setDiscountStatus('saved', 'Salvo');
                                    updatePaymentPlan();
                                    window.setTimeout(() => {{
                                        if (requestId === discountRequestId) {{
                                            setDiscountStatus('idle', '');
                                        }}
                                    }}, 1200);
                                }})
                                .catch((error) => {{
                                    if (error && error.name === 'AbortError') {{
                                        return;
                                    }}
                                    if (requestId !== discountRequestId) {{
                                        return;
                                    }}
                                    setDiscountStatus('error', error?.message || 'Falha ao salvar desconto.');
                                }});
                        }};
                        const persistDiscount = () => {{
                            if (!discountMoneyHidden || !discountPercentageHidden) {{
                                return;
                            }}
                            clearTimeout(discountTimeout);
                            discountTimeout = setTimeout(sendDiscountRequest, 1000);
                        }};
                        const persistDiscountNow = () => {{
                            if (!discountMoneyHidden || !discountPercentageHidden) {{
                                return;
                            }}
                            clearTimeout(discountTimeout);
                            sendDiscountRequest();
                        }};
                        const updatePaymentPlan = () => {{
                            const activeAmount = parseFloat(activeAmountInput.value) || 0;
                            const amountErrorMessage = isFirstPayment
                                ? 'O valor de entrada não pode exceder o saldo disponível da ordem de serviço.'
                                : 'O valor a ser pago não pode exceder o saldo disponível da ordem de serviço.';

                            if (pendingValue <= 0) {{
                                btnSave.disabled = true;
                                btnSave.classList.add('btn-disabled', 'opacity-50');
                                toggleWarning(false, '');
                                return;
                            }}

                            if (activeAmount > (pendingValue + 0.001)) {{
                                btnSave.disabled = true;
                                btnSave.classList.add('btn-disabled', 'opacity-50');
                                toggleWarning(true, amountErrorMessage);
                                return;
                            }}

                            btnSave.disabled = false;
                            btnSave.classList.remove('btn-disabled', 'opacity-50');
                            toggleWarning(false, '');
                        }};

                        paymentMethodInput.addEventListener('change', function() {{
                            updateDueDate(true);
                            updatePaymentPlan();
                        }});
                        paymentMethodInput.addEventListener('input', function() {{
                            updateDueDate(true);
                            updatePaymentPlan();
                        }});

                        if (activeAmountDisplay) {{
                            activeAmountDisplay.addEventListener('input', function() {{
                                requestAnimationFrame(updatePaymentPlan);
                            }});
                            activeAmountDisplay.addEventListener('blur', function() {{
                                setTimeout(updatePaymentPlan, 0);
                            }});
                        }}

                        if (discountMoneyDisplay && discountMoneyDisplay.dataset.discountSyncBound !== 'true') {{
                            const handleMoneyInput = () => {{
                                window.setTimeout(() => {{
                                    updateFromMoneyField();
                                    persistDiscount();
                                }}, 0);
                            }};
                            const handleMoneyBlur = () => {{
                                window.setTimeout(() => {{
                                    updateFromMoneyField();
                                    persistDiscountNow();
                                }}, 0);
                            }};
                            discountMoneyDisplay.addEventListener('input', handleMoneyInput);
                            discountMoneyDisplay.addEventListener('blur', handleMoneyBlur);
                            discountMoneyDisplay.dataset.discountSyncBound = 'true';
                        }}

                        if (discountPercentageDisplay && discountPercentageDisplay.dataset.discountSyncBound !== 'true') {{
                            const handlePercentageInput = () => {{
                                window.setTimeout(() => {{
                                    updateFromPercentageField();
                                    persistDiscount();
                                }}, 0);
                            }};
                            const handlePercentageBlur = () => {{
                                window.setTimeout(() => {{
                                    updateFromPercentageField();
                                    persistDiscountNow();
                                }}, 0);
                            }};
                            discountPercentageDisplay.addEventListener('input', handlePercentageInput);
                            discountPercentageDisplay.addEventListener('blur', handlePercentageBlur);
                            if (discountPercentageHidden) {{
                                discountPercentageHidden.addEventListener('widget:formatted-change', handlePercentageInput);
                            }}
                            discountPercentageDisplay.dataset.discountSyncBound = 'true';
                        }}

                        const pctVal = parseDotDecimal(discountPercentageHidden?.value);
                        const moneyVal = parseDotDecimal(discountMoneyHidden?.value);
                        if (moneyVal > 0) {{
                            discountMoneyDisplay.disabled = false;
                            discountPercentageDisplay.disabled = true;
                            updateDiscountSummary(moneyVal, 0);
                        }} else if (pctVal > 0) {{
                            discountPercentageDisplay.disabled = false;
                            discountMoneyDisplay.disabled = true;
                            updateDiscountSummary(0, pctVal);
                        }} else {{
                            if (discountMoneyDisplay) discountMoneyDisplay.disabled = false;
                            if (discountPercentageDisplay) discountPercentageDisplay.disabled = false;
                            updateDiscountSummary(0, 0);
                        }}
                        document.addEventListener('change', function(e) {{
                            if (e.target && e.target.name === 'discount_type') {{
                                persistDiscountNow();
                            }}
                        }});

                        updateDueDate(false);
                        updatePaymentPlan();
                    }};

                    window.initWorkOrderPaymentForm();
                }})();
            </script>
            """),
        )

    def _get_paid_amount(self) -> Decimal:
        if not self.workorder:
            return MONEY_ZERO
        return _quantize_money_amount(sum((payment.total_paid.amount for payment in self.workorder.payments.all()), start=MONEY_ZERO))

    def clean_discount_value(self) -> Money:
        discount_value = self.cleaned_data.get("discount_value")
        if discount_value is None:
            return Money(MONEY_ZERO, "BRL")
        return discount_value

    def clean_discount_percentage(self) -> Decimal:
        discount_percentage = self.cleaned_data.get("discount_percentage")
        if discount_percentage is None:
            return Decimal("0")
        return discount_percentage

    @staticmethod
    def _resolve_installments_count(payment_method: PaymentMethod | None) -> int:
        if payment_method is None:
            return 1
        return max(int(payment_method.installments_count or 1), 1)

    def clean(self) -> dict[str, Any]:
        cleaned_data = cast(dict[str, Any] | None, super().clean())
        if cleaned_data is None:
            return {}
        if not self.workorder:
            return cleaned_data

        if self.workorder.budget_type in ("warranty", "courtesy"):
            raise ValidationError("Ordens de serviço do tipo Garantia ou Cortesia não aceitam planos de pagamento.")

        payment_method = cleaned_data.get("payment_method")
        entry_amount = cleaned_data.get("entry_amount")
        first_amount = cleaned_data.get("first_installment_amount")
        due_date = cleaned_data.get("due_date")

        if payment_method is None:
            return cleaned_data

        if self.is_first_payment:
            effective_amount = entry_amount
            amount_field_name = "entry_amount"
            amount_label = "valor de entrada"
        else:
            effective_amount = first_amount
            amount_field_name = "first_installment_amount"
            amount_label = "valor a ser pago"

        if effective_amount is None:
            self.add_error(amount_field_name, f"Informe o {amount_label}.")
            return cleaned_data

        if due_date is None:
            due_date = timezone.localdate()
            cleaned_data["due_date"] = due_date

        total_os = _quantize_money_amount(self.workorder.total_budget_value.amount)
        paid_amount = self._get_paid_amount()
        pending_amount = _quantize_money_amount(total_os - paid_amount)

        if pending_amount <= MONEY_ZERO:
            raise ValidationError("A ordem de serviço não possui saldo pendente para um novo plano de pagamento.")

        if effective_amount.amount <= MONEY_ZERO:
            self.add_error(amount_field_name, f"Informe um valor maior que zero para o {amount_label}.")
            return cleaned_data

        if effective_amount.amount > pending_amount:
            self.add_error(amount_field_name, f"O {amount_label} não pode exceder o saldo pendente da O.S. (R$ {_format_brl_amount(pending_amount)}).")
            return cleaned_data

        cleaned_data["effective_payment_amount"] = effective_amount
        installments_count = self._resolve_installments_count(payment_method)

        cleaned_data["installments_count"] = installments_count
        cleaned_data["remaining_installments_amount"] = Money(MONEY_ZERO, "BRL")

        return cleaned_data

    def save(self, commit: bool = True) -> WorkOrderPaymentMethod:
        instance = super().save(commit=False)
        payment_method = self.cleaned_data.get("payment_method")
        effective_payment_amount = self.cleaned_data.get("effective_payment_amount")
        installments_count = self.cleaned_data.get("installments_count", 1)
        remaining_amount = self.cleaned_data.get("remaining_installments_amount", Money(MONEY_ZERO, "BRL"))

        instance.payment_method = payment_method
        if effective_payment_amount is not None:
            instance.first_installment_amount = effective_payment_amount
        instance.installments_count = int(installments_count)
        instance.remaining_installments_amount = remaining_amount

        if commit:
            instance.save()

        return instance


class WorkOrderAttachmentForm(CoreModelForm):
    file_upload = forms.FileField(
        required=False,
        widget=MultipleFileInput(
            attrs={
                "id": "file-upload-input",
                "accept": "*/*",
                "data-max-file-size-bytes": str(200 * 1024 * 1024),
                "data-max-files": "1000",
                "data-auto-upload": "true",
            }
        ),
    )

    class Meta:
        model = WorkOrderAttachment
        fields = []

    def __init__(self, *args, **kwargs):
        self.workorder = kwargs.pop("workorder", None)
        self.require_unsigned_delivery_reason = kwargs.pop("require_unsigned_delivery_reason", True)
        super().__init__(*args, **kwargs)

        self.fields["file_upload"].label = None

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(Field("file_upload"))


class WorkOrderCustomerApprovalForm(CoreForm):
    km_initial = forms.IntegerField(label="KM inicial", required=False, widget=NumberInput(attrs={"readonly": "readonly"}))
    km_final = forms.IntegerField(label="KM final", required=True, min_value=0, widget=NumberInput())
    warranty_plan = forms.ChoiceField(
        label="Plano de garantia",
        choices=[("", "Selecione o plano de garantia")] + list(WorkOrderWarrantyPlan.choices),
        required=True,
        widget=SearchableSelectInput(),
    )
    last_oil_change_date = forms.DateField(label="Data da última troca de óleo", required=False, widget=CalendarDateInput())
    last_oil_change_km = forms.IntegerField(label="KM da última troca de óleo", required=False, min_value=0, widget=NumberInput())
    review_plan = forms.ModelChoiceField(label="Plano de revisão", queryset=ReviewPlan.objects.none(), required=False, widget=SearchableSelectInput())
    warranty_origin = forms.ModelChoiceField(label="O.S. de venda de origem", queryset=WorkOrder.objects.none(), required=False, widget=SearchableSelectInput())
    warranty_term_template = forms.ModelChoiceField(
        label="Termo de garantia",
        queryset=WorkshopTermTemplate.objects.none(),
        required=False,
        widget=SearchableSelectInput(),
    )
    unsigned_delivery_reason = forms.CharField(
        label="Justificativa da entrega sem assinatura",
        required=False,
        widget=TextareaInput(
            rows=6,
            attrs={
                "placeholder": "Explique por que o veículo está sendo entregue sem a assinatura da O.S.",
                "class": "min-h-[10.5rem] h-full resize-y",
            },
        ),
    )
    courtesy_reason_type = forms.ChoiceField(
        label="Motivo da cortesia/garantia",
        choices=[("", "Selecione o motivo")] + list(WorkOrderCourtesyReasonType.choices),
        required=False,
        widget=SearchableSelectInput(),
    )
    courtesy_reason_description = forms.CharField(
        label="Descrição do motivo da cortesia/garantia",
        required=False,
        widget=TextareaInput(
            rows=4,
            attrs={
                "placeholder": "Descreva a falha encontrada ou o motivo pelo qual está sendo cedida a cortesia/garantia.",
            },
        ),
    )

    DRAFT_FIELD_NAMES = frozenset(
        {
            "km_final",
            "warranty_plan",
            "last_oil_change_date",
            "last_oil_change_km",
            "review_plan",
            "unsigned_delivery_reason",
            "courtesy_reason_type",
            "courtesy_reason_description",
            "warranty_origin",
            "warranty_term_template",
        }
    )

    def __init__(self, *args, **kwargs):
        self.workorder = kwargs.pop("workorder", None)
        self.require_unsigned_delivery_reason = kwargs.pop("require_unsigned_delivery_reason", True)
        self.require_warranty_plan = kwargs.pop("require_warranty_plan", True)
        self.require_km_final = kwargs.pop("require_km_final", True)
        super().__init__(*args, **kwargs)

        km_initial_value = 0
        if self.workorder and self.workorder.budget_id:
            km_initial_value = int(getattr(self.workorder.budget, "current_km", 0) or 0)

        self.fields["km_initial"].initial = km_initial_value
        self.fields["km_initial"].disabled = True
        self.fields["km_final"].widget.attrs["min"] = km_initial_value

        self.fields["km_final"].error_messages["required"] = "Preencha o KM final para concluir a entrega do veículo."
        self.fields["warranty_plan"].error_messages["required"] = "Selecione o plano de garantia para concluir a entrega do veículo."
        self.fields["unsigned_delivery_reason"].error_messages["required"] = "Informe a justificativa para entregar o veículo sem a assinatura da O.S."
        self.fields["km_final"].required = self.require_km_final
        self.fields["warranty_plan"].required = self.require_warranty_plan

        vehicle = getattr(getattr(self.workorder, "budget", None), "vehicle", None)
        review_plan_field = cast(forms.ModelChoiceField, self.fields["review_plan"])
        workshop = getattr(self.workorder, "workshop", None)
        review_plan_field.queryset = ReviewPlan.objects.filter(workshop=workshop, is_active=True).order_by("name") if workshop else ReviewPlan.objects.none()
        warranty_term_field = cast(forms.ModelChoiceField, self.fields["warranty_term_template"])
        warranty_term_field.queryset = (
            WorkshopTermTemplate.objects.filter(
                workshop=workshop,
                template_type=TermTemplateType.WARRANTY,
                is_active=True,
            ).order_by("-is_default", "name")
            if workshop
            else WorkshopTermTemplate.objects.none()
        )
        if self.workorder and not self.is_bound:
            from apps.terms.models import WorkOrderTermSigning

            existing_signing = WorkOrderTermSigning.objects.filter(workorder=self.workorder).select_related("term_template").first()
            if existing_signing is not None:
                self.fields["warranty_term_template"].initial = existing_signing.term_template_id
            else:
                default_template = get_default_term_template(workshop=workshop, template_type=TermTemplateType.WARRANTY) if workshop else None
                if default_template is not None:
                    self.fields["warranty_term_template"].initial = default_template.pk

        if self.workorder and self.workorder.km_final is not None and not self.is_bound:
            self.fields["km_final"].initial = self.workorder.km_final
        if self.workorder and self.workorder.warranty_plan and not self.is_bound:
            self.fields["warranty_plan"].initial = self.workorder.warranty_plan
        if self.workorder and self.workorder.unsigned_delivery_reason and not self.is_bound:
            self.fields["unsigned_delivery_reason"].initial = self.workorder.unsigned_delivery_reason

        self.is_courtesy_or_warranty = bool(self.workorder and self.workorder.budget_type in ("courtesy", "warranty"))
        if self.is_courtesy_or_warranty:
            self.fields["courtesy_reason_type"].required = True
            self.fields["courtesy_reason_type"].error_messages["required"] = "Selecione o motivo da cortesia/garantia para concluir a entrega."
            if self.workorder and self.workorder.courtesy_reason_type and not self.is_bound:
                self.fields["courtesy_reason_type"].initial = self.workorder.courtesy_reason_type
            if self.workorder and self.workorder.courtesy_reason_description and not self.is_bound:
                self.fields["courtesy_reason_description"].initial = self.workorder.courtesy_reason_description
        else:
            for field_name in ("courtesy_reason_type", "courtesy_reason_description"):
                self.fields[field_name].disabled = True

        if self.workorder and self.workorder.budget_type in ("warranty", "courtesy"):
            warranty_origin_field = cast(forms.ModelChoiceField, self.fields["warranty_origin"])
            warranty_origin_qs = WorkOrder.objects.none()
            if workshop and vehicle:
                warranty_origin_qs = WorkOrder.objects.filter(
                    workshop=workshop, budget_type="sale", status=WorkOrderStatus.APPROVED, budget__vehicle_id=vehicle.id
                ).select_related("budget__customer", "budget__vehicle").order_by("-criado_em")
            warranty_origin_field.queryset = warranty_origin_qs
            warranty_origin_field.label_from_instance = lambda obj: f"#{obj.get_id} - {obj.budget.customer.name if obj.budget.customer else ''} - {obj.budget.vehicle.plate if obj.budget.vehicle else ''} - {obj.get_status_display()}"
            if self.workorder.warranty_origin_id and not self.is_bound:
                self.fields["warranty_origin"].initial = self.workorder.warranty_origin_id
        else:
            self.fields["warranty_origin"].disabled = True

        if self.workorder and not self.is_bound:
            has_workorder_oil_data = bool(self.workorder.last_oil_change_date or self.workorder.last_oil_change_km is not None or self.workorder.review_plan_id)
            if has_workorder_oil_data:
                self.fields["last_oil_change_date"].initial = self.workorder.last_oil_change_date
                self.fields["last_oil_change_km"].initial = self.workorder.last_oil_change_km
                self.fields["review_plan"].initial = self.workorder.review_plan_id
            elif vehicle is not None:
                if vehicle.last_oil_change_date:
                    self.fields["last_oil_change_date"].initial = vehicle.last_oil_change_date
                if vehicle.last_oil_change_km is not None:
                    self.fields["last_oil_change_km"].initial = vehicle.last_oil_change_km
                if vehicle.review_plan_id:
                    self.fields["review_plan"].initial = vehicle.review_plan_id

        unsigned_delivery_is_required = bool(self.require_unsigned_delivery_reason and self.workorder and self.workorder.signature_request_status != WorkOrderSignatureStatus.APPROVED)
        self.fields["unsigned_delivery_reason"].required = unsigned_delivery_is_required

        reason_value = ""
        if self.is_bound:
            reason_value = str(self.data.get("unsigned_delivery_reason") or "").strip()
        else:
            reason_value = str(self.fields["unsigned_delivery_reason"].initial or "").strip()
        reason_starts_visible = bool(unsigned_delivery_is_required and reason_value)
        reason_wrapper_class = "col-span-12 lg:col-span-6 flex flex-col"
        if unsigned_delivery_is_required and not reason_starts_visible:
            reason_wrapper_class = f"{reason_wrapper_class} hidden"
        oil_panel_class = "col-span-12 rounded-box border border-success/25 bg-success/10 p-4 text-base-content [&_label]:text-base-content [&_.label-text]:text-base-content"
        if reason_starts_visible:
            oil_panel_class = f"{oil_panel_class} lg:col-span-6"
            oil_half_class = "col-span-12 sm:col-span-6 oil-field-half"
            oil_plan_class = "col-span-12 sm:col-span-12 oil-field-plan"
        else:
            oil_half_class = "col-span-12 sm:col-span-4 oil-field-half"
            oil_plan_class = "col-span-12 sm:col-span-4 oil-field-plan"

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                Div(
                    Field("km_initial", wrapper_class="mb-0"),
                    css_class="col-span-12 lg:col-span-6",
                ),
                Div(
                    Field("km_final", wrapper_class="mb-0"),
                    Field("warranty_plan", wrapper_class="mt-4 mb-0"),
                    Field("warranty_term_template", wrapper_class="mt-4 mb-0"),
                    css_class="col-span-12 lg:col-span-6",
                ),
                css_class="grid grid-cols-12 gap-4",
            ),
            Div(
                Div(
                    Field(
                        "unsigned_delivery_reason",
                        wrapper_class="flex h-full min-h-[10.5rem] flex-col [&>div]:flex [&>div]:h-full [&>div]:flex-col [&_textarea]:flex-1",
                    ),
                    css_id="unsigned-delivery-reason-wrapper",
                    css_class=reason_wrapper_class,
                ),
                Div(
                    Div(
                        Field("last_oil_change_date", wrapper_class=oil_half_class),
                        Field("last_oil_change_km", wrapper_class=oil_half_class),
                        Field("review_plan", wrapper_class=oil_plan_class),
                        css_class="grid grid-cols-12 gap-4",
                        css_id="oil-fields-grid",
                    ),
                    css_id="oil-fields-panel",
                    css_class=oil_panel_class,
                ),
                css_id="delivery-oil-reason-row",
                css_class="mt-4 grid grid-cols-12 gap-4 items-stretch",
            ),
            *( 
                [
                    Div(
                        Div(
                            Field(
                                "warranty_origin", 
                                wrapper_class="mb-0",
                            ),
                            HTML(f'<div id="warranty-origin-detail" hx-get="{reverse("workorder:warranty_origin_detail", args=[self.workorder.pk]) if self.workorder and self.workorder.pk else ""}" hx-include="#id_warranty_origin" hx-trigger="change from:#id_warranty_origin, load" hx-target="#warranty-origin-detail"></div>'),
                            css_class="col-span-12",
                        ),
                        css_id="warranty-origin-section",
                        css_class="mt-4 grid grid-cols-12 gap-4 rounded-box border border-info/25 bg-info/10 p-4 text-base-content [&_label]:text-base-content [&_.label-text]:text-base-content",
                    )
                ]
                if self.workorder and self.workorder.budget_type in ("warranty", "courtesy")
                else []
            ),
            *(
                [
                    Div(
                        Div(
                            Field("courtesy_reason_type", wrapper_class="mb-0"),
                            css_class="col-span-12",
                        ),
                        Div(
                            Field("courtesy_reason_description", wrapper_class="mb-0"),
                            css_class="col-span-12",
                        ),
                        css_id="courtesy-reason-section",
                        css_class="mt-4 grid grid-cols-12 gap-4 rounded-box border border-warning/25 bg-warning/10 p-4 text-base-content [&_label]:text-base-content [&_.label-text]:text-base-content",
                    )
                ]
                if getattr(self, "is_courtesy_or_warranty", False)
                else []
            ),
        )

    def clean_km_final(self) -> int | None:
        km_final = self.cleaned_data.get("km_final")
        if km_final is None:
            return None

        km_final_value = int(km_final)
        km_initial = int(getattr(self.workorder.budget, "current_km", 0) or 0) if self.workorder else 0
        if km_final_value < km_initial:
            raise ValidationError(f"O KM final não pode ser menor que o KM inicial ({km_initial:,}).".replace(",", "."))

        return km_final_value

    def clean_unsigned_delivery_reason(self) -> str:
        reason = str(self.cleaned_data.get("unsigned_delivery_reason") or "").strip()
        if self.require_unsigned_delivery_reason and self.workorder and self.workorder.signature_request_status != WorkOrderSignatureStatus.APPROVED and not reason:
            raise ValidationError("Informe a justificativa para entregar o veículo sem a assinatura da O.S.")
        return reason

    def clean_courtesy_reason_type(self) -> str:
        reason_type = str(self.cleaned_data.get("courtesy_reason_type") or "").strip()
        if getattr(self, "is_courtesy_or_warranty", False) and not reason_type:
            raise ValidationError("Selecione o motivo da cortesia/garantia para concluir a entrega.")
        return reason_type


class WorkOrderDeliveryDateForm(CoreForm):
    delivered_at = forms.DateTimeField(
        label="Data e hora da entrega",
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(
            format="%Y-%m-%dT%H:%M",
            attrs={"type": "datetime-local", "class": "input-theme"},
        ),
    )

    def __init__(self, *args, workorder: WorkOrder, **kwargs) -> None:
        self.workorder = workorder
        super().__init__(*args, **kwargs)
        if not self.is_bound and workorder.delivered_at is not None:
            self.fields["delivered_at"].initial = timezone.localtime(workorder.delivered_at)

    def clean_delivered_at(self):
        delivered_at = self.cleaned_data["delivered_at"]
        if timezone.is_naive(delivered_at):
            delivered_at = timezone.make_aware(delivered_at, timezone.get_current_timezone())
        return delivered_at


class WorkOrderReopenForm(CoreForm):
    reopen_reason = forms.CharField(
        label="Justificativa da reabertura",
        required=True,
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "Explique por que esta O.S. precisa ser reaberta e quais estornos foram autorizados."}),
    )

    def __init__(self, *args, **kwargs):
        self.workorder = kwargs.pop("workorder", None)
        super().__init__(*args, **kwargs)
        self.fields["reopen_reason"].error_messages["required"] = "Informe a justificativa para reabrir a O.S."

        if self.workorder and self.workorder.reopen_reason and not self.is_bound:
            self.fields["reopen_reason"].initial = self.workorder.reopen_reason

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(Field("reopen_reason"))

    def clean_reopen_reason(self) -> str:
        reason = str(self.cleaned_data.get("reopen_reason") or "").strip()
        if not reason:
            raise ValidationError("Informe a justificativa para reabrir a O.S.")
        return reason


class WorkOrderStatusReasonForm(CoreForm):
    status_reason = forms.CharField(label="Justificativa", required=True, widget=forms.Textarea(attrs={"rows": 4}))

    def __init__(self, *args, **kwargs):
        self.workorder = kwargs.pop("workorder", None)
        self.action = str(kwargs.pop("action", "")).strip().lower()
        super().__init__(*args, **kwargs)

        config = self._get_action_config()
        self.fields["status_reason"].label = config["label"]
        self.fields["status_reason"].widget.attrs["placeholder"] = config["placeholder"]
        self.fields["status_reason"].error_messages["required"] = config["required_message"]

        initial_value = ""
        if self.workorder and not self.is_bound:
            initial_value = str(getattr(self.workorder, config["field_name"] or "", "") or "")
        if initial_value:
            self.fields["status_reason"].initial = initial_value

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(Field("status_reason"))

    def _get_action_config(self) -> dict[str, str]:
        config_map = {
            "cancel": {
                "field_name": "cancellation_reason",
                "label": "Justificativa do cancelamento",
                "placeholder": "Explique por que esta O.S. está sendo cancelada.",
                "required_message": "Informe a justificativa para cancelar a O.S.",
            },
            "reject": {
                "field_name": "rejection_reason",
                "label": "Justificativa da reprovação",
                "placeholder": "Explique por que esta O.S. está sendo reprovada.",
                "required_message": "Informe a justificativa para reprovar a O.S.",
            },
        }
        return config_map.get(self.action, config_map["reject"])

    def clean_status_reason(self) -> str:
        reason = str(self.cleaned_data.get("status_reason") or "").strip()
        if not reason:
            raise ValidationError(self._get_action_config()["required_message"])
        return reason


class WorkOrderItemEditForm(CoreModelForm):
    class Meta:
        model = WorkOrderItem
        fields = ["description", "quantity", "is_customer_supplied", "product_selling_price", "product_cost_price", "shipping", "service_selling_price", "service_cost_price", "duration", "item_benefit_type"]
        widgets = {
            "description": TextInput(),
            "quantity": NumberInput(),
            "is_customer_supplied": CheckboxInput(),
            "product_selling_price": MoneyInput(),
            "product_cost_price": MoneyInput(),
            "shipping": MoneyInput(),
            "service_selling_price": MoneyInput(),
            "service_cost_price": MoneyInput(),
            "duration": DurationInput(),
            "item_benefit_type": RadioSelect(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        item = self.instance

        if item.kit:
            fields_to_remove = ["service_selling_price", "service_cost_price", "duration", "product_selling_price", "product_cost_price", "shipping", "is_customer_supplied"]
            for field in fields_to_remove:
                if field in self.fields:
                    self.fields.pop(field)

        if item.product:
            self.fields.pop("service_selling_price")
            self.fields.pop("service_cost_price")
            self.fields.pop("duration")
        elif item.service:
            self.fields.pop("product_selling_price")
            self.fields.pop("product_cost_price")
            self.fields.pop("shipping")
            self.fields.pop("is_customer_supplied")

        budget_type = getattr(getattr(item, "workorder", None), "budget_type", "sale")
        if budget_type in ("warranty", "courtesy"):
            self.fields["item_benefit_type"].disabled = True

    def clean_item_benefit_type(self):
        value = self.cleaned_data.get("item_benefit_type")
        item = self.instance
        budget_type = getattr(getattr(item, "workorder", None), "budget_type", "sale")
        if budget_type == "warranty" and value != WorkOrderItemBenefitType.WARRANTY:
            raise forms.ValidationError("Itens em O.S. de garantia devem ser do tipo 'Garantia'.")
        if budget_type == "courtesy" and value != WorkOrderItemBenefitType.COURTESY:
            raise forms.ValidationError("Itens em O.S. de cortesia devem ser do tipo 'Cortesia'.")
        return value

    def clean_description(self):
        value = self.cleaned_data.get("description")
        return sentence_case(value) if value else value


class WorkOrderKitProductEditRowForm(CoreForm):
    quantity = forms.IntegerField(min_value=0, widget=NumberInput(attrs={"data-field": "quantity", "min": "0"}))
    cost = MoneyField(required=False, widget=MoneyInput(attrs={"data-field": "cost"}))
    price = MoneyField(required=False, widget=MoneyInput(attrs={"data-field": "price"}))
    shipping = MoneyField(required=False, widget=MoneyInput(attrs={"data-field": "shipping"}))


class WorkOrderKitServiceEditRowForm(CoreForm):
    quantity = forms.IntegerField(min_value=0, widget=NumberInput(attrs={"data-field": "quantity", "min": "0"}))
    cost = MoneyField(required=False, widget=MoneyInput(attrs={"data-field": "cost"}))
    price = MoneyField(required=False, widget=MoneyInput(attrs={"data-field": "price"}))
    duration = forms.CharField(required=False, widget=DurationInput(attrs={"data-field": "duration"}))
