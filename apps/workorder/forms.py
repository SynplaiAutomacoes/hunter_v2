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

from apps.budget.pricing import resolve_discount_fields
from apps.collaborators.models import WorkshopCollaborator
from apps.budget.forms.widgets import MultipleFileInput
from apps.core.utils import alert_confirm_layout
from apps.core.text_normalization import sentence_case
from apps.core.widgets import CalendarDateInput, DurationInput, MoneyInput, NumberInput, PercentageInput, SearchableSelectInput, TextInput
from apps.finance.models.payment_method import PaymentMethod
from apps.workorder.models import WorkOrder, WorkOrderAttachment, WorkOrderItem, WorkOrderPaymentMethod, WorkOrderSignatureStatus
from apps.core.forms import CoreForm, CoreModelForm


MONEY_ZERO = Decimal("0.00")


class _BoundDataProtocol(Protocol):
    def copy(self) -> Any: ...


def _format_brl_amount(value: Decimal) -> str:
    return f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


class WorkOrderCollaboratorForm(CoreModelForm):
    collaborators = forms.ModelMultipleChoiceField(label="Colaboradores da O.S.", queryset=WorkshopCollaborator.objects.none(), required=False, widget=forms.SelectMultiple(attrs={"class": "select select-bordered min-h-40 w-full"}))

    class Meta:
        model = WorkOrder
        fields = ["collaborators"]

    def __init__(self, *args, workorder: WorkOrder | None = None, **kwargs) -> None:
        self.workorder = workorder or kwargs.get("instance")
        super().__init__(*args, **kwargs)
        workshop = getattr(self.workorder, "workshop", None)
        queryset = WorkshopCollaborator.objects.none()
        if workshop is not None:
            queryset = WorkshopCollaborator.objects.filter(workshop=workshop, is_active=True).order_by("name")
        self.fields["collaborators"].queryset = queryset
        self.fields["collaborators"].help_text = "Selecione os colaboradores responsaveis por esta O.S. A comissao prevista sera calculada a partir desta vinculacao."


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
        widget=PercentageInput(decimal_places=2, behavior="free_decimal"),
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

        total_os = self.workorder.total_budget_value.amount if self.workorder else MONEY_ZERO
        paid_amount = self._get_paid_amount() if self.workorder else MONEY_ZERO
        pending_amount = total_os - paid_amount
        payment_has_paid_value = paid_amount > MONEY_ZERO
        payment_is_fully_paid = pending_amount <= MONEY_ZERO
        pending_amount_display = pending_amount if pending_amount > MONEY_ZERO else MONEY_ZERO
        base_total = self.workorder.total_base_value if self.workorder else Money(MONEY_ZERO, "BRL")
        discount_value = Money(MONEY_ZERO, "BRL")
        discount_percentage = Decimal("0.00")

        blocked_value_attrs = {"readonly": True, "class": "cursor-not-allowed opacity-75"}
        fully_paid_value_attrs = {**blocked_value_attrs, "disabled": True, "title": "OS paga por completo"}
        discount_locked_attrs = {"readonly": True, "disabled": True, "title": "OS já tem valor pago", "class": "font-semibold text-lg cursor-not-allowed bg-base-200/70 text-base-content/60 border-base-300"}

        if payment_is_fully_paid:
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

        if payment_has_paid_value:
            for field_name in ["discount_value", "discount_percentage"]:
                self.fields[field_name].disabled = True
                self.fields[field_name].widget.attrs.update(discount_locked_attrs)

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

        if not payment_has_paid_value:
            self.fields["discount_value"].widget.attrs.update({"class": "font-semibold text-lg"})
            self.fields["discount_percentage"].widget.attrs.update({"class": "font-semibold text-lg"})
        self.initial["discount_value"] = discount_value
        self.initial["discount_percentage"] = discount_percentage

        if not self.is_bound and not self.initial.get("due_date"):
            self.initial["due_date"] = ""

        pending_amount_js = format(pending_amount, "f")
        today_iso = timezone.localdate().isoformat()
        is_first_payment_js = "true" if self.is_first_payment else "false"
        payment_success_container_class = "col-span-12 mb-4" if payment_is_fully_paid else "hidden col-span-12 mb-4"
        discount_locked_js = "true" if payment_has_paid_value else "false"
        discount_lock_notice = """
                    <div class="mb-4 rounded-2xl border border-base-300 bg-base-200/60 p-4 text-sm text-base-content/80" title="OS já tem valor pago">
                        <div class="flex items-start gap-3">
                            <span class="material-icons mt-0.5 text-base-content/50">lock</span>
                            <div class="space-y-1">
                                <p class="font-semibold text-base-content">Descontos indisponíveis</p>
                                <p>Esta OS já possui valor pago. Para desbloquear os cards de desconto, nenhum pagamento deve ocorrer ou ter ocorrido nesta OS.</p>
                            </div>
                        </div>
                    </div>
        """ if payment_has_paid_value else ""
        discount_card_class = "border-base-300 bg-base-100 shadow-sm" if payment_has_paid_value else "border-base-300 bg-base-100/90 shadow-sm"
        discount_title_attr = ' title="OS já tem valor pago"' if payment_has_paid_value else ""
        discount_badge = '<span class="badge badge-neutral badge-sm badge-outline">Indisponível</span>' if payment_has_paid_value else ""
        discount_value_icon = "lock" if payment_has_paid_value else "payments"
        discount_percentage_icon = "lock" if payment_has_paid_value else "percent"
        discount_icon_class = "text-base-content/40" if payment_has_paid_value else "text-base-content/40"
        discount_value_hint = "Indisponível porque a OS já tem valor pago." if payment_has_paid_value else "O percentual acompanha automaticamente."
        discount_percentage_hint = "Indisponível porque a OS já tem valor pago." if payment_has_paid_value else "O valor em reais acompanha instantaneamente."

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            alert_confirm_layout(title="Deseja remover este registro?"),
            HTML(f"""
                <div id="payment-success-workorder-js" class="{payment_success_container_class}">
                    <div class="alert alert-success shadow-lg border-2 border-success">
                        <span class="material-icons">check_circle</span>
                        <div>
                            <h3 class="font-bold text-sm">Ordem de Serviço completamente paga</h3>
                            <div class="text-xs">A ordem de serviço foi paga completamente.</div>
                        </div>
                    </div>
                </div>
            """),
            Div(
                HTML(
                    f"""
                    {discount_lock_notice}
                    <div class="grid grid-cols-1 gap-3 mb-5 xl:grid-cols-2">
                    """
                ),
                Div(
                    HTML(
                        f"""
                        <div class="h-full rounded-[1.5rem] border p-4 {discount_card_class}"{discount_title_attr}>
                            <div class="mb-3 flex items-center justify-between gap-3">
                                <div>
                                    <div class="flex flex-wrap items-center gap-2">
                                        <p class="text-sm font-bold text-base-content">Desconto em valor</p>
                                        {discount_badge}
                                    </div>
                                    <p class="text-xs text-base-content/60">Use quando a negociação foi fechada em valor exato.</p>
                                </div>
                                <span class="material-icons {discount_icon_class}">{discount_value_icon}</span>
                            </div>
                        """
                    ),
                    Field("discount_value", wrapper_class="mb-0"),
                    HTML(f'<p class="mt-2 text-xs text-base-content/55">{discount_value_hint}</p></div>'),
                    css_class="h-full",
                ),
                Div(
                    HTML(
                        f"""
                        <div class="h-full rounded-[1.5rem] border p-4 {discount_card_class}"{discount_title_attr}>
                            <div class="mb-3 flex items-center justify-between gap-3">
                                <div>
                                    <div class="flex flex-wrap items-center gap-2">
                                        <p class="text-sm font-bold text-base-content">Desconto em percentual</p>
                                        {discount_badge}
                                    </div>
                                    <p class="text-xs text-base-content/60">Ideal para manter a mesma política comercial em diferentes totais.</p>
                                </div>
                                <span class="material-icons {discount_icon_class}">{discount_percentage_icon}</span>
                            </div>
                        """
                    ),
                    Field("discount_percentage", wrapper_class="mb-0"),
                    HTML(f'<p class="mt-2 text-xs text-base-content/55">{discount_percentage_hint}</p></div>'),
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
                        const discountLocked = {discount_locked_js};
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
                        const syncFromPercentage = () => {{
                            if (!discountMoneyDisplay || !discountMoneyHidden || !discountPercentageHidden) {{
                                return;
                            }}
                            const baseTotal = getBaseTotal();
                            const fraction = clamp(parseDotDecimal(discountPercentageHidden.value), 0, 1);
                            const amount = baseTotal > 0 ? clamp(roundCurrency(baseTotal * fraction), 0, baseTotal) : 0;
                            discountMoneyHidden.value = amount.toFixed(2);
                            discountMoneyDisplay.value = formatMoney(amount);
                            discountPercentageHidden.value = formatFraction(fraction);
                            updateDiscountSummary(amount, fraction);
                        }};
                        const syncFromValue = (updateSourceDisplay = true) => {{
                            if (!discountMoneyHidden || !discountPercentageHidden || !discountPercentageDisplay) {{
                                return;
                            }}
                            const baseTotal = getBaseTotal();
                            const amount = clamp(roundCurrency(parseDotDecimal(discountMoneyHidden.value)), 0, baseTotal);
                            const fraction = baseTotal > 0 ? clamp(amount / baseTotal, 0, 1) : 0;
                            discountMoneyHidden.value = amount.toFixed(2);
                            if (discountMoneyDisplay && updateSourceDisplay) {{
                                discountMoneyDisplay.value = formatMoney(amount);
                            }}
                            discountPercentageHidden.value = formatFraction(fraction);
                            discountPercentageDisplay.value = formatPercentageDisplay(fraction);
                            updateDiscountSummary(amount, fraction);
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
                            if (discountLocked || !discountPersistUrl || !discountMoneyHidden || !discountPercentageHidden) {{
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

                        if (!discountLocked && discountMoneyDisplay && discountMoneyDisplay.dataset.discountSyncBound !== 'true') {{
                            const handleMoneyInput = () => {{
                                window.setTimeout(() => {{
                                    syncFromValue(false);
                                    persistDiscount();
                                }}, 0);
                            }};
                            const handleMoneyBlur = () => {{
                                window.setTimeout(() => {{
                                    syncFromValue(false);
                                    persistDiscountNow();
                                }}, 0);
                            }};
                            discountMoneyDisplay.addEventListener('input', handleMoneyInput);
                            discountMoneyDisplay.addEventListener('blur', handleMoneyBlur);
                            discountMoneyDisplay.dataset.discountSyncBound = 'true';
                        }}

                        if (!discountLocked && discountPercentageDisplay && discountPercentageDisplay.dataset.discountSyncBound !== 'true') {{
                            const handlePercentageInput = () => {{
                                window.setTimeout(() => {{
                                    syncFromPercentage();
                                    persistDiscount();
                                }}, 0);
                            }};
                            const handlePercentageBlur = () => {{
                                window.setTimeout(() => {{
                                    syncFromPercentage();
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

                        if (discountPercentageHidden && parseDotDecimal(discountPercentageHidden.value) > 0) {{
                            syncFromPercentage();
                        }} else {{
                            syncFromValue();
                        }}

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
        return sum((payment.total_paid.amount for payment in self.workorder.payments.all()), start=MONEY_ZERO)

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

        total_os = self.workorder.total_budget_value.amount
        paid_amount = self._get_paid_amount()
        pending_amount = total_os - paid_amount

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
    unsigned_delivery_reason = forms.CharField(
        label="Justificativa da entrega sem assinatura",
        required=False,
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "Explique por que o veículo está sendo entregue sem a assinatura da O.S."}),
    )

    def __init__(self, *args, **kwargs):
        self.workorder = kwargs.pop("workorder", None)
        self.require_unsigned_delivery_reason = kwargs.pop("require_unsigned_delivery_reason", True)
        super().__init__(*args, **kwargs)

        km_initial_value = 0
        if self.workorder and self.workorder.budget_id:
            km_initial_value = int(getattr(self.workorder.budget, "current_km", 0) or 0)

        self.fields["km_initial"].initial = km_initial_value
        self.fields["km_initial"].disabled = True

        self.fields["km_final"].error_messages["required"] = "Preencha o KM final para concluir a entrega do veículo."
        self.fields["unsigned_delivery_reason"].error_messages["required"] = "Informe a justificativa para entregar o veículo sem a assinatura da O.S."

        if self.workorder and self.workorder.km_final is not None and not self.is_bound:
            self.fields["km_final"].initial = self.workorder.km_final
        if self.workorder and self.workorder.unsigned_delivery_reason and not self.is_bound:
            self.fields["unsigned_delivery_reason"].initial = self.workorder.unsigned_delivery_reason

        unsigned_delivery_is_required = bool(self.require_unsigned_delivery_reason and self.workorder and self.workorder.signature_request_status != WorkOrderSignatureStatus.APPROVED)
        self.fields["unsigned_delivery_reason"].required = unsigned_delivery_is_required

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            alert_confirm_layout(),
            Div(
                Field("km_initial", wrapper_class="col-span-12 lg:col-span-6"),
                Field("km_final", wrapper_class="col-span-12 lg:col-span-6"),
                css_class="grid grid-cols-12 gap-4",
            ),
            Div(
                Field("unsigned_delivery_reason"),
                css_id="unsigned-delivery-reason-wrapper",
                css_class="mt-4",
            ),
        )

    def clean_km_final(self) -> int:
        km_final = self.cleaned_data.get("km_final")
        if km_final is None:
            return 0

        km_initial = int(getattr(self.workorder.budget, "current_km", 0) or 0) if self.workorder else 0
        if km_final < km_initial:
            raise ValidationError(f"O KM final não pode ser menor que o KM inicial ({km_initial:,}).".replace(",", "."))

        return km_final

    def clean_unsigned_delivery_reason(self) -> str:
        reason = str(self.cleaned_data.get("unsigned_delivery_reason") or "").strip()
        if self.require_unsigned_delivery_reason and self.workorder and self.workorder.signature_request_status != WorkOrderSignatureStatus.APPROVED and not reason:
            raise ValidationError("Informe a justificativa para entregar o veículo sem a assinatura da O.S.")
        return reason


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
                "label": "Justificativa da rejeição",
                "placeholder": "Explique por que esta O.S. está sendo rejeitada.",
                "required_message": "Informe a justificativa para rejeitar a O.S.",
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        item = self.instance

        if item.kit:
            fields_to_remove = ["service_selling_price", "service_cost_price", "duration", "product_selling_price", "product_cost_price", "shipping"]
            for field in fields_to_remove:
                if field in self.fields:
                    self.fields.pop(field)
            return

        if item.product:
            self.fields.pop("service_selling_price")
            self.fields.pop("service_cost_price")
            self.fields.pop("duration")
        elif item.service:
            self.fields.pop("product_selling_price")
            self.fields.pop("product_cost_price")
            self.fields.pop("shipping")

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
