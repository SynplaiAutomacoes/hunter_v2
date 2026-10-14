from __future__ import annotations

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password

from apps.billing.domain.plans import Plan
from apps.core.presentation.widgets import CPForCNPJInput, EmailInput, PasswordInput, TextInput

User = get_user_model()


class SubscribeSignupForm(forms.Form):
    first_name = forms.CharField(label="Nome", max_length=150, widget=TextInput(attrs={"placeholder": "Nome"}))
    last_name = forms.CharField(
        label="Sobrenome",
        max_length=150,
        required=False,
        widget=TextInput(attrs={"placeholder": "Sobrenome"}),
    )
    username = forms.CharField(label="Usuário", max_length=150, widget=TextInput(attrs={"placeholder": "user123"}))
    email = forms.EmailField(label="E-mail", widget=EmailInput())
    cpf = forms.CharField(label="CPF", widget=CPForCNPJInput(mode="cpf"))
    password1 = forms.CharField(label="Senha", widget=PasswordInput())
    password2 = forms.CharField(label="Confirmar senha", widget=PasswordInput())
    plan = forms.ChoiceField(choices=[(Plan.BASIC, "Orçamento"), (Plan.FULL, "Completo")])

    def clean_username(self) -> str:
        username = str(self.cleaned_data.get("username") or "").lower().strip()
        if not username:
            raise forms.ValidationError("Informe um usuário.")
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("Este usuário já está em uso.")
        return username

    def clean_email(self) -> str:
        email = str(self.cleaned_data.get("email") or "").lower().strip()
        if not email:
            raise forms.ValidationError("Informe um e-mail.")
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Este e-mail já está em uso.")
        return email

    def clean_cpf(self) -> str:
        cpf = "".join(character for character in str(self.cleaned_data.get("cpf") or "") if character.isdigit())
        if len(cpf) != 11:
            raise forms.ValidationError("Informe um CPF válido.")
        if User.objects.filter(cpf=cpf, is_account_owner=True).exists():
            raise forms.ValidationError("Este CPF já está vinculado a uma conta.")
        return cpf

    def clean(self):
        cleaned = super().clean()
        password1 = cleaned.get("password1")
        password2 = cleaned.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", "As senhas não coincidem.")
        return cleaned

    def build_password_hash(self) -> str:
        return make_password(str(self.cleaned_data["password1"]))
