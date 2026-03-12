from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Field, HTML, Layout, Submit
from django import forms
from django.urls import reverse

from apps.core.widgets import CheckboxInput, NumberInput, TextInput, MoneyInput, PercentageInput
from apps.finance.models.payment_method import PaymentMethod


class PaymentMethodForm(forms.ModelForm):
    class Meta:
        model = PaymentMethod
        fields = ["description", "installments_count", "tax_percentage", "tax_value", "is_active"]
        widgets = {
            "description": TextInput(attrs={"placeholder": "Ex: Cartão de Crédito, Pix..."}),
            "installments_count": NumberInput(),
            "tax_percentage": PercentageInput(),
            "tax_value": MoneyInput(),
            "is_active": CheckboxInput(),
        }

    def __init__(self, *args, workshop=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.workshop = workshop
        self.helper = FormHelper()
        self.helper.form_tag = False

        alpine_tax_logic = """
                    {
                        taxP: '%s',
                        taxV: '%s',
                        init() {
                            // Sincroniza estado inicial se for edição
                            this.taxP = document.getElementById('id_tax_percentage')?.value || '';
                            this.taxV = document.getElementById('id_tax_value_0')?.value || '';
                        },
                        clearOther(type) {
                            if(type === 'percentage') {
                                // Limpa o valor de Dinheiro
                                this.taxV = '';
                                let moneyHidden = document.getElementById('id_tax_value_0');
                                let moneyDisplay = document.getElementById('id_tax_value_0_display');
                                if(moneyHidden) moneyHidden.value = '';
                                if(moneyDisplay) { 
                                    moneyDisplay.value = '';
                                    moneyDisplay.dispatchEvent(new Event('input')); 
                                }
                            } else {
                                // Limpa o valor de Porcentagem
                                this.taxP = '';
                                let percHidden = document.getElementById('id_tax_percentage');
                                let percDisplay = document.getElementById('id_tax_percentage_display');
                                if(percHidden) percHidden.value = '';
                                if(percDisplay) { 
                                    percDisplay.value = '';
                                    percDisplay.dispatchEvent(new Event('input'));
                                }
                            }
                        }
                    }
                """ % (str(self.instance.tax_percentage or ""), str(self.instance.tax_value.amount if self.instance.tax_value else ""))

        self.helper.layout = Layout(
            Div(
                Field("description", wrapper_class="col-span-12 lg:col-span-12"),
                Field("installments_count", wrapper_class="col-span-12 lg:col-span-3"),

                Div(
                    Div(Field("tax_percentage", **{"x-model": "taxP", "@input": "if(taxP) clearOther('percentage')", ":class": "{'opacity-40 pointer-events-none': taxV && !taxP}"}), css_class="flex-1"),
                    HTML('<div class="flex items-center justify-center font-bold text-xs opacity-50 px-2 mt-10">OU</div>'),
                    Div(Field("tax_value", **{"x-model": "taxV", "@input": "if(taxV) clearOther('value')", ":class": "{'opacity-40 pointer-events-none': taxP && !taxV}"}), css_class="flex-1"),
                    css_class="col-span-12 lg:col-span-9 flex items-start gap-1",
                    **{"x-data": alpine_tax_logic},
                ),

                Field("is_active", wrapper_class="col-span-12"),
                css_class="grid grid-cols-12 gap-4",
            ),
            HTML('<div class="divider"></div>'),
            Div(HTML(f'<a href="{reverse("finance:payment_methods_list")}" class="btn-form-cancel">Cancelar</a>'), Submit("submit", "Salvar", css_class="btn-form-save"), css_class="flex items-center justify-end gap-2"),
        )

    def clean(self):
        cleaned_data = super().clean()
        tax_percentage = cleaned_data.get("tax_percentage")
        tax_value = cleaned_data.get("tax_value")

        if tax_percentage and tax_value:
            raise forms.ValidationError("Preencha apenas a taxa em percentual (%) OU a taxa em valor (R$), nunca ambos.")
        return cleaned_data
