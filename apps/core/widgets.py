from django import forms


class MoneyInput(forms.TextInput):
    template_name = 'money_input.html'


class CPForCNPJInput(forms.TextInput):
    """
    mode:
      - "cpf"  -> máscara/limite CPF
      - "cnpj" -> máscara/limite CNPJ
      - "both" -> alterna CPF até 11 dígitos e CNPJ acima
    """
    template_name = "cpf_or_cpnj_input.html"

    def __init__(self, *args, mode: str = "both", **kwargs):
        super().__init__(*args, **kwargs)
        self.mode = mode

    def get_context(self, name, value, attrs):
        ctx = super().get_context(name, value, attrs)
        ctx["widget"]["doc_mode"] = self.mode
        return ctx