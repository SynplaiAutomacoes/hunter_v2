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
from apps.core.widgets import CalendarDateInput, DurationInput, MoneyInput, NumberInput, PercentageInput, SelectInput, TextInput
from apps.finance.models.payment_method import PaymentMethod
from apps.workorder.models import WorkOrderAttachment, WorkOrderItem, WorkOrderPaymentMethod


MONEY_ZERO = Decimal("0.00")


class _BoundDataProtocol(Protocol):
    def copy(self) -> Any: ...


def _format_brl_amount(value: Decimal) -> str:
    return f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


class WorkOrderPaymentForm(forms.ModelForm):
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
            "payment_method": SelectInput(),
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
        self.fields["first_installment_amount"].label = "Valor a ser pago"
        self.fields["due_date"].required = False

        total_os = self.workorder.total_budget_value.amount if self.workorder else MONEY_ZERO
        paid_amount = self._get_paid_amount() if self.workorder else MONEY_ZERO
        pending_amount = total_os - paid_amount
        pending_amount_display = pending_amount if pending_amount > MONEY_ZERO else MONEY_ZERO
        base_total = self.workorder.total_base_value if self.workorder else Money(MONEY_ZERO, "BRL")
        discount_value = Money(MONEY_ZERO, "BRL")
        discount_percentage = Decimal("0.00")

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
        self.initial["discount_value"] = discount_value
        self.initial["discount_percentage"] = discount_percentage

        if not self.is_bound and not self.initial.get("due_date"):
            self.initial["due_date"] = ""

        pending_amount_js = format(pending_amount, "f")
        pending_amount_display_text = _format_brl_amount(pending_amount_display)
        today_iso = timezone.localdate().isoformat()

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            HTML(f"""
                <div id="payment-warning-workorder-js" class="hidden col-span-12 mb-4">
                    <div class="alert alert-error shadow-lg border-2 border-error">
                        <span class="material-icons">error_outline</span>
                        <div>
                            <h3 class="font-bold text-sm">Valor Não Permitido</h3>
                            <div class="text-xs payment-warning-message">
                                O valor a ser pago não pode exceder o saldo disponível de <strong>R$ {pending_amount_display_text}</strong>.
                            </div>
                        </div>
                    </div>
                </div>
            """),
            Div(
                HTML(
                    """
                    <div class="grid grid-cols-1 gap-3 mb-5 xl:grid-cols-2">
                    """
                ),
                Div(
                    HTML(
                        """
                        <div class="h-full rounded-[1.5rem] border border-base-300 bg-base-100/90 p-4 shadow-sm">
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
                    HTML('<p class="mt-2 text-xs text-base-content/55">O percentual acompanha automaticamente.</p></div>'),
                    css_class="h-full",
                ),
                Div(
                    HTML(
                        """
                        <div class="h-full rounded-[1.5rem] border border-base-300 bg-base-100/90 p-4 shadow-sm">
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
                    HTML('<p class="mt-2 text-xs text-base-content/55">O valor em reais acompanha instantaneamente.</p></div>'),
                    css_class="h-full",
                ),
                HTML("</div>"),
            ),
            Div(
                Field("total_value", wrapper_class="col-span-12 lg:col-span-4"),
                Field("paid_value", wrapper_class="col-span-12 lg:col-span-4"),
                Field("pending_value", wrapper_class="col-span-12 lg:col-span-4"),
                css_class="grid grid-cols-12 gap-4 mb-2 pb-4 border-b-2 border-base-50",
            ),
            Div(
                Field("payment_method", wrapper_class="col-span-12 lg:col-span-4"),
                Field("first_installment_amount", wrapper_class="col-span-12 lg:col-span-4"),
                Field("due_date", wrapper_class="col-span-12 lg:col-span-4"),
                css_class="grid grid-cols-12 gap-4 mb-2 mt-4",
            ),
            Div(Submit("submit", "Salvar Plano de Pagamento", css_class="btn-form-save btn-primary"), css_class="flex justify-end mt-4"),
            HTML(f"""
            <script>
                (function() {{
                    window.initWorkOrderPaymentForm = function() {{
                        const paymentForm = document.getElementById('payment-form-fields');
                        if (!paymentForm || paymentForm.dataset.paymentInitialized === 'true') {{
                            return;
                        }}

                        const formElement = paymentForm.closest('form');
                        const paymentMethodInput = document.getElementById('id_payment_method');
                        const firstAmountInput = document.getElementById('id_first_installment_amount_0');
                        const firstAmountDisplay = document.getElementById('id_first_installment_amount_0_display');
                        const dueDateInput = document.getElementById('id_due_date');
                        const btnSave = formElement ? formElement.querySelector('.btn-form-save') : null;
                        const warningDiv = document.getElementById('payment-warning-workorder-js');
                        const warningMessage = warningDiv ? warningDiv.querySelector('.payment-warning-message') : null;
                        const pendingValue = parseFloat('{pending_amount_js}') || 0;
                        const todayValue = '{today_iso}';
                        const discountMoneyDisplay = document.getElementById('id_discount_value_0_display');
                        const discountMoneyHidden = document.getElementById('id_discount_value_0');
                        const discountPercentageDisplay = document.getElementById('id_discount_percentage_display');
                        const discountPercentageHidden = document.getElementById('id_discount_percentage');
                        const discountDisplay = document.getElementById('workorder-discount-display');
                        const totalDisplay = document.getElementById('workorder-total-final-display');
                        const percentageChip = document.getElementById('workorder-discount-percentage-display');
                        let discountTimeout = null;

                        if (!paymentMethodInput || !firstAmountInput || !btnSave) {{
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
                        const persistDiscount = () => {{
                            if (!discountMoneyHidden || !discountPercentageHidden) {{
                                return;
                            }}
                            clearTimeout(discountTimeout);
                            discountTimeout = setTimeout(() => {{
                                htmx.ajax('POST', '{reverse("workorder:update_discount", args=[self.workorder.pk]) if self.workorder else ""}', {{
                                    target: '#payment-section',
                                    swap: 'innerHTML',
                                    values: {{
                                        discount_value_0: discountMoneyHidden.value,
                                        discount_percentage: discountPercentageHidden.value,
                                    }},
                                }});
                            }}, 700);
                        }};
                        const updatePaymentPlan = () => {{
                            const firstAmount = parseFloat(firstAmountInput.value) || 0;

                            if (pendingValue <= 0) {{
                                btnSave.disabled = true;
                                btnSave.classList.add('btn-disabled', 'opacity-50');
                                toggleWarning(true, 'A ordem de serviço não possui saldo pendente para um novo plano de pagamento.');
                                return;
                            }}

                            if (firstAmount > (pendingValue + 0.001)) {{
                                btnSave.disabled = true;
                                btnSave.classList.add('btn-disabled', 'opacity-50');
                                toggleWarning(true, 'O valor a ser pago não pode exceder o saldo disponível da ordem de serviço.');
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

                        if (firstAmountDisplay) {{
                            firstAmountDisplay.addEventListener('input', function() {{
                                requestAnimationFrame(updatePaymentPlan);
                            }});
                            firstAmountDisplay.addEventListener('blur', function() {{
                                setTimeout(updatePaymentPlan, 0);
                            }});
                        }}

                        if (discountMoneyDisplay && discountMoneyDisplay.dataset.discountSyncBound !== 'true') {{
                            const handleMoneyInput = () => {{
                                window.setTimeout(() => {{
                                    syncFromValue(false);
                                    persistDiscount();
                                }}, 0);
                            }};
                            discountMoneyDisplay.addEventListener('input', handleMoneyInput);
                            discountMoneyDisplay.addEventListener('blur', handleMoneyInput);
                            discountMoneyDisplay.dataset.discountSyncBound = 'true';
                        }}

                        if (discountPercentageHidden && discountPercentageHidden.dataset.discountSyncBound !== 'true') {{
                            const handlePercentageInput = () => {{
                                window.setTimeout(() => {{
                                    syncFromPercentage();
                                    persistDiscount();
                                }}, 0);
                            }};
                            discountPercentageHidden.addEventListener('widget:formatted-change', handlePercentageInput);
                            discountPercentageHidden.dataset.discountSyncBound = 'true';
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
        first_amount = cleaned_data.get("first_installment_amount")
        due_date = cleaned_data.get("due_date")

        if payment_method is None or first_amount is None:
            return cleaned_data

        if due_date is None:
            due_date = timezone.localdate()
            cleaned_data["due_date"] = due_date

        total_os = self.workorder.total_budget_value.amount
        paid_amount = self._get_paid_amount()
        pending_amount = total_os - paid_amount

        if pending_amount <= MONEY_ZERO:
            raise ValidationError("A ordem de serviço não possui saldo pendente para um novo plano de pagamento.")

        if first_amount.amount <= MONEY_ZERO:
            self.add_error("first_installment_amount", "Informe um valor maior que zero para o valor a ser pago.")
            return cleaned_data

        if first_amount.amount > pending_amount:
            self.add_error("first_installment_amount", f"O valor a ser pago não pode exceder o saldo pendente da O.S. (R$ {_format_brl_amount(pending_amount)}).")
            return cleaned_data

        installments_count = self._resolve_installments_count(payment_method)

        cleaned_data["installments_count"] = installments_count
        cleaned_data["remaining_installments_amount"] = Money(MONEY_ZERO, "BRL")

        return cleaned_data

    def save(self, commit: bool = True) -> WorkOrderPaymentMethod:
        instance = super().save(commit=False)
        payment_method = self.cleaned_data.get("payment_method")
        installments_count = self.cleaned_data.get("installments_count", 1)
        remaining_amount = self.cleaned_data.get("remaining_installments_amount", Money(MONEY_ZERO, "BRL"))

        instance.payment_method = payment_method
        instance.installments_count = int(installments_count)
        instance.remaining_installments_amount = remaining_amount

        if commit:
            instance.save()

        return instance


class WorkOrderAttachmentForm(forms.ModelForm):
    file_upload = forms.FileField(
        required=False,
        widget=forms.FileInput(
            attrs={
                "class": "hidden",
                "id": "file-upload-input",
                "hx-post": "",
                "hx-trigger": "change",
                "hx-target": "#customer-approvement-section",
                "hx-swap": "innerHTML",
                "hx-encoding": "multipart/form-data",
            }
        ),
    )

    class Meta:
        model = WorkOrderAttachment
        fields = []

    def __init__(self, *args, **kwargs):
        self.workorder = kwargs.pop("workorder", None)
        super().__init__(*args, **kwargs)

        self.fields["file_upload"].label = None

        if self.workorder:
            self.fields["file_upload"].widget.attrs["hx-post"] = reverse("workorder:upload_attachment", args=[self.workorder.pk])

        self.helper = FormHelper()
        self.helper.form_tag = False

        layout_elements = []

        if self.instance and self.instance.pk:
            layout_elements.append(
                Div(
                    Div(
                        #
                        HTML('<div class="mr-4"><i class="material-icons text-3xl">description</i></div>'),
                        #
                        Div(HTML(f'<p class="font-boldleading-tight">{self.instance.content_name}</p>'), HTML(f'<p class="text-xs">{self.instance.criado_em.strftime("%d/%m/%Y %H:%M")}</p>'), css_class="flex-grow"),
                        #
                        Div(
                            HTML(f'<a href="{reverse("workorder:view_attachment", args=[self.instance.pk])}" target="_blank" class="btn btn-outline flex items-center mr-4 font-medium"><i class="material-icons text-base mr-1">visibility</i> Abrir</a>'),
                            HTML(
                                f'<button hx-delete="{reverse("workorder:delete_attachment", args=[self.instance.pk])}" hx-swap="innerHTML" hx-target="#customer-approvement-section" hx-confirm="Tem certeza que deseja remover este anexo?" class="flex items-center btn btn-outline text-red-600 hover:text-red-800 font-medium"><i class="material-icons text-base mr-1">delete</i> Excluir</button>'
                            ),
                            css_class="flex items-center",
                        ),
                        css_class="flex items-center p-4 border rounded-lg shadow-sm mb-4",
                    ),
                    css_class="col-span-12",
                )
            )

        layout_elements.append(
            Div(
                HTML("""
                        <label for="file-upload-input" class="flex flex-col items-center justify-center w-full h-48 border-2 border-gray-500 border-dashed rounded-lg cursor-pointer bg-transparent">
                            <div class="flex flex-col items-center justify-center pt-5 pb-6">
                                <i class="fas fa-cloud-upload-alt text-4xl text-gray-500 mb-3"></i>
                                <p class="mb-2 text-sm text-gray-700 font-semibold">Clique para enviar ou arraste e solte</p>
                                <p class="text-xs text-gray-500 uppercase font-medium">PDF, PNG, JPG (MÁX. 10MB)</p>
                            </div>
                        </label>
                    """),
                Field("file_upload"),
                css_class="col-span-12",
            )
        )

        self.helper.layout = Layout(*layout_elements)


class WorkOrderItemEditForm(forms.ModelForm):
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


class WorkOrderKitProductEditRowForm(forms.Form):
    quantity = forms.IntegerField(min_value=0, widget=NumberInput(attrs={"data-field": "quantity", "min": "0"}))
    cost = MoneyField(required=False, widget=MoneyInput(attrs={"data-field": "cost"}))
    price = MoneyField(required=False, widget=MoneyInput(attrs={"data-field": "price"}))
    shipping = MoneyField(required=False, widget=MoneyInput(attrs={"data-field": "shipping"}))


class WorkOrderKitServiceEditRowForm(forms.Form):
    quantity = forms.IntegerField(min_value=0, widget=NumberInput(attrs={"data-field": "quantity", "min": "0"}))
    cost = MoneyField(required=False, widget=MoneyInput(attrs={"data-field": "cost"}))
    price = MoneyField(required=False, widget=MoneyInput(attrs={"data-field": "price"}))
    duration = forms.CharField(required=False, widget=DurationInput(attrs={"data-field": "duration"}))
