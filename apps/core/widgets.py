from django import forms

class MoneyInput(forms.TextInput):
    template_name = 'money_input.html'