from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Field, HTML, Layout, Submit
from django import forms
from django.urls import reverse

from apps.core.widgets import CheckboxInput, MoneyInput, NumberInput, PercentageInput, SearchableSelectInput, TextInput
from apps.finance.models.payment_method import PaymentMethod
from apps.core.text_normalization import sentence_case
from apps.core.forms import CoreModelForm


class PaymentMethodForm(CoreModelForm):
    tax_percentage = forms.DecimalField(
        required=False,
        max_digits=9,
        decimal_places=6,
        widget=PercentageInput(),
    )

    class Meta:
        model = PaymentMethod
        fields = ["description", "payment_type", "installments_count", "tax_percentage", "tax_value", "is_active"]
        widgets = {
            "description": TextInput(attrs={"placeholder": "Ex: Cartão de Crédito, Pix..."}),
            "payment_type": SearchableSelectInput(),
            "installments_count": NumberInput(),
            "tax_value": MoneyInput(),
            "is_active": CheckboxInput(),
        }

    def __init__(self, *args, workshop=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.workshop = workshop

        if self.instance.pk and self.instance.tax_percentage is not None:
            from decimal import Decimal

            self.initial["tax_percentage"] = (Decimal(str(self.instance.tax_percentage)) / Decimal("100")).quantize(Decimal("0.000001"))

        self.helper = FormHelper()

        self.helper.layout = Layout(
            Div(
                Field("description", wrapper_class="col-span-12 lg:col-span-12"),
                Field("payment_type", wrapper_class="col-span-12 lg:col-span-3"),
                Field("installments_count", wrapper_class="col-span-12 lg:col-span-3"),
                Div(
                    Div(Field("tax_percentage"), css_class="flex-1"),
                    HTML('<div class="flex items-center justify-center font-bold text-xs opacity-50 px-2 mt-10">OU</div>'),
                    Div(Field("tax_value"), css_class="flex-1"),
                    css_class="col-span-12 lg:col-span-6 flex items-start gap-1",
                ),
                Field("is_active", wrapper_class="col-span-12"),
                css_class="grid grid-cols-12 gap-4",
            ),
            HTML('<div class="divider"></div>'),
            Div(HTML(f'<a href="{reverse("finance:payment_methods_list")}" class="btn-form-cancel">Cancelar</a>'), Submit("submit", "Salvar", css_class="btn-form-save"), css_class="flex items-center justify-end gap-2"),
            HTML("""<script>
                (function() {
                    const updateLogic = () => {
                        const percInput = document.getElementById('id_tax_percentage');
                        const percDisplay = document.getElementById('id_tax_percentage_display');
                        const valInput = document.getElementById('id_tax_value_0');
                        const valDisplay = document.getElementById('id_tax_value_0_display');

                        if (!percInput || !valInput) return;

                        const check = () => {
                            const hasPerc = percInput.value && parseFloat(percInput.value) !== 0;
                            const hasVal = valInput.value && parseFloat(valInput.value) !== 0;

                            // Regra para Dinheiro (R$)
                            if (hasPerc) {
                                valDisplay.disabled = true;
                                valDisplay.classList.add('opacity-50', 'cursor-not-allowed');
                            } else {
                                valDisplay.disabled = false;
                                valDisplay.classList.remove('opacity-50', 'cursor-not-allowed');
                            }

                            // Regra para Porcentagem (%)
                            if (hasVal) {
                                percDisplay.disabled = true;
                                percDisplay.classList.add('opacity-50', 'cursor-not-allowed');
                            } else {
                                percDisplay.disabled = false;
                                percDisplay.classList.remove('opacity-50', 'cursor-not-allowed');
                            }
                        };

                        [percDisplay, valDisplay].forEach(el => {
                            if (el) el.addEventListener('input', () => setTimeout(check, 10));
                        });

                        const observer = new MutationObserver(check);
                        [percInput, valInput].forEach(input => {
                            observer.observe(input, { attributes: true, attributeFilter: ['value'] });
                        });

                        check();
                    };

                    if (document.readyState === 'loading') {
                        document.addEventListener('DOMContentLoaded', updateLogic);
                    } else {
                        updateLogic();
                    }
                })();
            </script>"""),
        )

    def clean_tax_percentage(self):
        tax_percentage = self.cleaned_data.get("tax_percentage")
        if tax_percentage is not None:
            from decimal import Decimal

            return (tax_percentage * Decimal("100")).quantize(Decimal("0.01"))
        return None

    def clean_description(self):
        value = self.cleaned_data.get("description")
        return sentence_case(value) if value else value

    def clean(self) -> dict[str, object]:
        cleaned_data = super().clean()
        if cleaned_data is None:
            return {}

        description = cleaned_data.get("description")
        tax_percentage = cleaned_data.get("tax_percentage")
        tax_value = cleaned_data.get("tax_value")

        qs = PaymentMethod.objects.filter(workshop=self.workshop, description=description)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            self.add_error("description", "Já existe uma forma de pagamento com esta descrição nesta Oficina.")

        if tax_percentage and tax_value:
            raise forms.ValidationError("Preencha apenas a taxa em percentual (%) OU a taxa em valor (R$), nunca ambos.")
        return cleaned_data
