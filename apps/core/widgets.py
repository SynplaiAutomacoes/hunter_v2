from django import forms
from typing import List, Tuple, Literal

from djmoney.forms import MoneyWidget


class MoneyInput(MoneyWidget):
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

    def __init__(self, *args, mode: Literal["hours", "minutes", "hours_minutes"] = "hours_minutes", **kwargs):
        super().__init__(*args, **kwargs)
        self.mode = mode

    def get_context(self, name, value, attrs):
        ctx = super().get_context(name, value, attrs)
        ctx["widget"]["mode"] = self.mode
        return ctx


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


class SearchableSelectInput(SelectInput):
    template_name = "widgets/searchable_select.html"


class CalendarDateInput(forms.DateInput):
    template_name = "widgets/calendar_date_input.html"

    def __init__(self, format="%Y-%m-%d", *args, **kwargs):
        # HTML date input (abre picker nativo no mobile/desktop quando suportado)
        attrs = kwargs.setdefault("attrs", {})
        attrs.setdefault("type", "date")
        super().__init__(*args, **kwargs, format=format)


class TextInput(forms.TextInput):
    template_name = "widgets/text_input.html"


class PlateInput(TextInput):
    def __init__(self, *args, **kwargs):
        attrs = kwargs.setdefault("attrs", {})
        attrs.setdefault("oninput", "this.value = this.value.toUpperCase()")
        attrs.setdefault("autocapitalize", "characters")
        super().__init__(*args, **kwargs)


class TextareaInput(forms.Textarea):
    template_name = "widgets/textarea_input.html"

    def __init__(self, *args, rows=2, **kwargs):
        # Podemos definir um padrão de linhas (rows) aqui
        attrs = kwargs.setdefault("attrs", {})
        attrs.setdefault("rows", rows)
        super().__init__(*args, **kwargs)


class PasswordInput(forms.PasswordInput):
    template_name = "widgets/password_input.html"


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


class DecimalInput(forms.TextInput):
    template_name = "widgets/decimal_input.html"

    def __init__(self, *args, min_value: float | None = None, max_value: float | None = None, decimal_places: int = 2, **kwargs):
        super().__init__(*args, **kwargs)
        self.min_value = min_value
        self.max_value = max_value
        self.decimal_places = decimal_places

    def get_context(self, name, value, attrs):
        ctx = super().get_context(name, value, attrs)
        ctx["widget"]["min_value"] = self.min_value
        ctx["widget"]["max_value"] = self.max_value
        ctx["widget"]["decimal_places"] = self.decimal_places
        return ctx


class PercentageInput(forms.TextInput):
    template_name = "widgets/percentage_input.html"

    def __init__(
        self,
        *args,
        min_percent: float = 0,
        max_percent: float = 100,
        decimal_places: int = 2,
        behavior: Literal["free_decimal", "digit_stream"] = "free_decimal",
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.min_percent = min_percent
        self.max_percent = max_percent
        self.decimal_places = decimal_places
        self.behavior = behavior

    def get_context(self, name, value, attrs):
        ctx = super().get_context(name, value, attrs)
        ctx["widget"]["min_percent"] = self.min_percent
        ctx["widget"]["max_percent"] = self.max_percent
        ctx["widget"]["decimal_places"] = self.decimal_places
        ctx["widget"]["behavior"] = self.behavior
        return ctx


class ImageInput(forms.ClearableFileInput):
    template_name = "widgets/image_input.html"
