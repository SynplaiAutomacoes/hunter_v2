from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Div, Field, Submit, HTML
from djmoney.money import Money

from apps.core.widgets import SelectInput, NumberInput, MoneyInput
from apps.workorder.models import WorkOrderPaymentMethod


class WorkOrderPaymentForm(forms.ModelForm):
    total_value = forms.CharField(label="Valor Total", required=False, widget=MoneyInput)
    paid_value = forms.CharField(label="Valor Pago", required=False, widget=MoneyInput)
    pending_value = forms.CharField(label="Valor Pendente", required=False, widget=MoneyInput)

    class Meta:
        model = WorkOrderPaymentMethod
        fields = [
            "payment_method",
            "installments_count",
            "first_installment_amount",
            "remaining_installments_amount"
        ]
        widgets = {
            "payment_method": SelectInput(),
            "installments_count": NumberInput(),
            "first_installment_amount": MoneyInput(),
            "remaining_installments_amount": MoneyInput(),
        }

    def __init__(self, *args, **kwargs):
        self.workorder = kwargs.pop("workorder", None)
        super().__init__(*args, **kwargs)

        self.fields["remaining_installments_amount"].required = False

        for field in ["total_value", "paid_value", "pending_value"]:
            self.fields[field].widget.attrs.update({"readonly": True, "class": "cursor-not-allowed"})

        if self.workorder:
            total = self.workorder.budget.total_budget_value
            pago = Money(sum(p.total_paid.amount for p in self.workorder.payments.all()), 'BRL')

            self.fields["total_value"].initial = total
            self.fields["paid_value"].initial = pago
            self.fields["pending_value"].initial = total - pago

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            # Resumo Financeiro
            Div(
                Field("total_value", wrapper_class="col-span-12 lg:col-span-4"),
                Field("paid_value", wrapper_class="col-span-12 lg:col-span-4"),
                Field("pending_value", wrapper_class="col-span-12 lg:col-span-4"),
                css_class="grid grid-cols-12 gap-4 mb-2 pb-4"
            ),

            # Input de Dados
            Div(
                Field("payment_method", wrapper_class="col-span-12 lg:col-span-3"),
                Field("installments_count", wrapper_class="col-span-12 lg:col-span-3"),
                Field("first_installment_amount", wrapper_class="col-span-12 lg:col-span-3"),
                Field("remaining_installments_amount", wrapper_class="col-span-12 lg:col-span-3"),
                css_class="grid grid-cols-12 gap-4 mb-2 pb-4"
            ),

            Div(
                Submit("submit", "Salvar Plano de Pagamento", css_class="btn-form-save"),
                css_class="flex justify-end mt-4"
            ),
        )
