from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Div, Field, Submit, HTML
from django.core.exceptions import ValidationError
from django.urls import reverse
from djmoney.forms import MoneyField
from djmoney.money import Money

from apps.core.widgets import DurationInput, MoneyInput, NumberInput, SelectInput, TextInput
from apps.workorder.models import WorkOrderAttachment, WorkOrderItem, WorkOrderPaymentMethod


class WorkOrderPaymentForm(forms.ModelForm):
    total_value = forms.CharField(label="Valor Total", required=False, widget=MoneyInput)
    paid_value = forms.CharField(label="Valor Pago", required=False, widget=MoneyInput)
    pending_value = forms.CharField(label="Valor Pendente", required=False, widget=MoneyInput)

    class Meta:
        model = WorkOrderPaymentMethod
        fields = ["payment_method", "installments_count", "first_installment_amount", "remaining_installments_amount"]
        widgets = {
            "payment_method": SelectInput(),
            "installments_count": NumberInput(),
            "first_installment_amount": MoneyInput(),
            "remaining_installments_amount": MoneyInput(),
        }

    def __init__(self, *args, **kwargs):
        self.workorder = kwargs.pop("workorder", None)
        super().__init__(*args, **kwargs)

        total_os = self.workorder.total_budget_value.amount if self.workorder else 0
        pago = sum(p.total_paid.amount for p in self.workorder.payments.all()) if self.workorder else 0
        valor_pendente = total_os - pago

        for field in ["total_value", "paid_value", "pending_value"]:
            self.fields[field].widget.attrs.update({"readonly": True, "class": "cursor-not-allowed"})

        if self.workorder:
            self.initial["total_value"] = Money(total_os, "BRL")
            self.initial["paid_value"] = Money(pago, "BRL")
            self.initial["pending_value"] = Money(valor_pendente, "BRL")

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            HTML(f"""
            <script>
                document.addEventListener('DOMContentLoaded', function() {{
                    const checkWorkOrderLimit = () => {{
                        const firstAmountInput = document.getElementById('id_first_installment_amount_0');
                        const remainingAmountInput = document.getElementById('id_remaining_installments_amount_0');
                        const installmentsInput = document.getElementById('id_installments_count');

                        const pendingValue = parseFloat("{str(valor_pendente).replace(",", ".")}") || 0;
                        const btnSave = document.querySelector('.btn-form-save');
                        const warningDiv = document.getElementById('payment-warning-workorder-js');

                        if (!firstAmountInput || !installmentsInput || !btnSave) return;

                        const firstAmt = parseFloat(firstAmountInput.value) || 0;
                        const remainingAmt = parseFloat(remainingAmountInput ? remainingAmountInput.value : 0) || 0;
                        const qty = parseInt(installmentsInput.value) || 1;

                        const totalProposed = firstAmt + (remainingAmt * (qty - 1));

                        if (totalProposed > (pendingValue + 0.01)) {{
                            btnSave.disabled = true;
                            btnSave.classList.add('btn-disabled', 'opacity-50');
                            if (warningDiv) {{
                                warningDiv.classList.remove('hidden');
                                const excess = totalProposed - pendingValue;
                                warningDiv.querySelector('.excess-amount').innerText = 
                                    "R$ " + excess.toLocaleString('pt-BR', {{minimumFractionDigits: 2, maximumFractionDigits: 2}});
                            }}
                        }} else {{
                            btnSave.disabled = false;
                            btnSave.classList.remove('btn-disabled', 'opacity-50');
                            if (warningDiv) warningDiv.classList.add('hidden');
                        }}
                    }};

                    document.addEventListener('focusout', function(e) {{
                        const ids = ['id_first_installment_amount_0', 'id_remaining_installments_amount_0', 'id_installments_count'];
                        if (ids.some(id => e.target.id.includes(id) || e.target.id === id + '_display')) {{
                            setTimeout(checkWorkOrderLimit, 50);
                        }}
                    }});

                    setTimeout(checkWorkOrderLimit, 500);
                }});
            </script>
            """),
            HTML(f"""
                <div id="payment-warning-workorder-js" class="hidden col-span-12 mb-4">
                    <div class="alert alert-error shadow-lg border-2 border-error">
                        <span class="material-icons">error_outline</span>
                        <div>
                            <h3 class="font-bold text-sm">Valor Não Permitido</h3>
                            <div class="text-xs">
                                O valor excede o saldo disponível de <strong>R$ {valor_pendente:,.2f}</strong>. 
                                Excesso de <strong class="excess-amount"></strong>.
                            </div>
                        </div>
                    </div>
                </div>
            """),
            Div(Field("total_value", wrapper_class="col-span-12 lg:col-span-4"), Field("paid_value", wrapper_class="col-span-12 lg:col-span-4"), Field("pending_value", wrapper_class="col-span-12 lg:col-span-4"), css_class="grid grid-cols-12 gap-4 mb-2 pb-4 border-b-2 border-base-50"),
            Div(
                Field("payment_method", wrapper_class="col-span-12 lg:col-span-3"),
                Field("installments_count", wrapper_class="col-span-12 lg:col-span-3"),
                Field("first_installment_amount", wrapper_class="col-span-12 lg:col-span-3"),
                Field("remaining_installments_amount", wrapper_class="col-span-12 lg:col-span-3"),
                css_class="grid grid-cols-12 gap-4 mb-2 mt-4",
            ),
            Div(
                Submit("submit", "Salvar Plano de Pagamento", css_class="btn-form-save btn-primary"),
                css_class="flex justify-end mt-4"
            ),
        )

    def clean(self):
        cleaned_data = super().clean()
        if not self.workorder:
            return cleaned_data

        first_amount = cleaned_data.get("first_installment_amount")
        remaining_amount = cleaned_data.get("remaining_installments_amount") or 0
        installments = cleaned_data.get("installments_count") or 1

        total_proposed = first_amount.amount + ((installments - 1) * remaining_amount.amount)

        total_os = self.workorder.total_budget_value.amount
        ja_pago = sum(p.total_paid.amount for p in self.workorder.payments.all())
        saldo_disponivel = total_os - ja_pago

        if total_proposed > saldo_disponivel:
            raise ValidationError(
                f"O valor total deste pagamento (R$ {total_proposed:,.2f}) "
                f"excede o saldo pendente da O.S. (R$ {saldo_disponivel:,.2f})."
            )

        return cleaned_data


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
