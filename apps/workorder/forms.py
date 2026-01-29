from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Div, Field, Submit, HTML
from django.urls import reverse
from djmoney.money import Money

from apps.core.widgets import SelectInput, NumberInput, MoneyInput, ImageInput, TextInput
from apps.workorder.models import WorkOrderPaymentMethod, WorkOrderAttachment


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


class WorkOrderAttachmentForm(forms.ModelForm):
    file_upload = forms.FileField(
        required=False,
        widget=forms.FileInput(
            attrs={
                "class": "hidden",
                "id": "file-upload-input",
                "hx-post": "",
                "hx-trigger": "change",
                "hx-target": "#customer-section-container",
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

        self.fields['file_upload'].label = False

        if self.workorder:
            upload_url = reverse("workorder:upload_attachment", args=[self.workorder.pk])
            self.fields["file_upload"].widget.attrs["hx-post"] = upload_url

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
                        Div(
                            HTML(f'<p class="font-boldleading-tight">{self.instance.content_name}</p>'),
                            HTML(f'<p class="text-xs">{self.instance.criado_em.strftime("%d/%m/%Y %H:%M")}</p>'),
                            css_class="flex-grow"
                        ),
                        #
                        Div(
                            HTML(f'<a href="{reverse("workorder:view_attachment", args=[self.instance.pk])}" target="_blank" class="btn btn-outline flex items-center mr-4 font-medium"><i class="material-icons text-base mr-1">visibility</i> Abrir</a>'),
                            HTML(f'<button hx-delete="{reverse("workorder:delete_attachment", args=[self.instance.pk])}" hx-target="#customer-section-container" hx-confirm="Tem certeza que deseja remover este anexo?" class="flex items-center btn btn-outline text-red-600 hover:text-red-800 font-medium"><i class="material-icons text-base mr-1">delete</i> Excluir</button>'),
                            css_class="flex items-center",
                        ),
                        css_class="flex items-center p-4 border rounded-lg shadow-sm mb-4",
                    ),
                    css_class="col-span-12",
                )
            )

        layout_elements.append(Div(
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
                    css_class="col-span-12"
                ))

        self.helper.layout = Layout(*layout_elements)
