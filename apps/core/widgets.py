from django import forms
from typing import List, Tuple, Literal


class MoneyInput(forms.TextInput):
    template_name = "widgets/money_input.html"


class CPForCNPJInput(forms.TextInput):
    """
    mode:
      - "cpf"  -> máscara/limite CPF
      - "cnpj" -> máscara/limite CNPJ
      - "both" -> alterna CPF até 11 dígitos e CNPJ acima
    """

    template_name = "widgets/cpf_or_cpnj_input.html"

    def __init__(self, *args, mode: Literal["both", "cnpj", "cpf"] = "both", **kwargs):
        super().__init__(*args, **kwargs)
        self.mode = mode

    def get_context(self, name, value, attrs):
        ctx = super().get_context(name, value, attrs)
        ctx["widget"]["doc_mode"] = self.mode
        return ctx


class RGInput(forms.TextInput):
    template_name = "widgets/rg_input.html"


class PhoneInput(forms.TextInput):
    template_name = "widgets/phone_input.html"


class CEPInput(forms.TextInput):
    template_name = "widgets/cep_input.html"


class DurationInput(forms.TextInput):
    template_name = "widgets/duration_input.html"


class EmailInput(forms.EmailInput):
    template_name = "widgets/email_input.html"


# Não usei "forms.Select" por que não consegui estilizá-lo corretamente, portanto fiz está "gambiarra".
class SelectInput(forms.TextInput):
    template_name = "widgets/select_input.html"

    def __init__(self, *args, choices: List[Tuple[str, str]] | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.choices = choices or []

    def get_context(self, name, value, attrs):
        ctx = super().get_context(name, value, attrs)
        ctx["widget"]["optgroups"] = self.optgroups(name, value, attrs)
        return ctx

    def optgroups(self, name, value, attrs=None):
        if value is None:
            value = []
        if not isinstance(value, (list, tuple)):
            value = [value]
        str_values = {"" if v is None else str(v) for v in value}

        groups = []
        group_name = None
        subgroup = []
        group_index = 0

        has_selected = False
        for index, (opt_value, opt_label) in enumerate(self.choices):
            opt_value_str = "" if opt_value is None else str(opt_value)
            selected = (opt_value_str in str_values) and (not has_selected)
            if selected:
                has_selected = True

            subgroup.append({"name": name, "value": opt_value_str, "label": opt_label, "selected": selected, "attrs": attrs or {}})

        groups.append((group_name, subgroup, group_index))
        return groups

    def value_from_datadict(self, data, files, name):
        return data.get(name, "")


class CalendarDateInput(forms.DateInput):
    template_name = "widgets/calendar_date_input.html"

    def __init__(self, *args, **kwargs):
        # HTML date input (abre picker nativo no mobile/desktop quando suportado)
        attrs = kwargs.setdefault("attrs", {})
        attrs.setdefault("type", "date")
        super().__init__(*args, **kwargs)


class TextInput(forms.TextInput):
    template_name = "widgets/text_input.html"


class CheckboxInput(forms.CheckboxInput):
    template_name = "widgets/checkbox_input.html"


class NumberInput(forms.TextInput):
    """
    mode:
      - "positive" (default): só >= 0
      - "negative": só <= 0
      - "both": permite sinal +/- (um único '-' no começo)
    """

    template_name = "widgets/number_input.html"

    def __init__(self, *args, mode: Literal["positive", "negative", "both"] = "positive", **kwargs):
        super().__init__(*args, **kwargs)
        self.mode = mode

    def get_context(self, name, value, attrs):
        ctx = super().get_context(name, value, attrs)
        ctx["widget"]["number_mode"] = self.mode
        return ctx
