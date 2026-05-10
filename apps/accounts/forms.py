from django import forms
from django.contrib.auth import get_user_model, authenticate
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm, UsernameField
from django.db.models import Q

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit

from apps.core.widgets import EmailInput, TextInput, CPForCNPJInput, PasswordInput

User = get_user_model()

USER_PLACEHOLDER = {"placeholder": "user123"}


class LoginForm(AuthenticationForm):
    username = UsernameField(label="Usuário", widget=TextInput(attrs=USER_PLACEHOLDER))
    password = forms.CharField(label="Senha", widget=PasswordInput())

    def __init__(self, request=None, *args, **kwargs):
        super().__init__(request=request, *args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.add_input(Submit("submit", "Entrar", css_class="btn btn-primary w-full"))

    def clean_username(self) -> str:
        username = str(self.cleaned_data.get("username") or "").lower()
        if username:
            # Suporta login por username ou email de forma case-insensitive
            try:
                user = User.objects.get(Q(username__iexact=username) | Q(email__iexact=username))
                return str(getattr(user, "username", ""))
            except (User.DoesNotExist, User.MultipleObjectsReturned):
                return username
        return username


class SignUpForm(UserCreationForm):
    first_name = forms.CharField(label="Nome", widget=TextInput(attrs={"placeholder": "Nome"}))
    last_name = forms.CharField(label="Sobrenome", widget=TextInput(attrs={"placeholder": "Sobrenome"}), required=False)
    email = forms.EmailField(label="E-mail", widget=EmailInput())
    cpf = forms.CharField(label="CPF", widget=CPForCNPJInput(mode="cpf"))

    class Meta(UserCreationForm.Meta):  # type: ignore[attr-defined]
        model = User
        fields = ("first_name", "last_name", "username", "email", "cpf", "password1", "password2")
        widgets = {
            "username": TextInput(attrs=USER_PLACEHOLDER),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Ajusta classes dos campos de senha (UserCreationForm define widgets próprios)
        self.fields["password1"].widget = PasswordInput()
        self.fields["password2"].widget = PasswordInput()

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.add_input(Submit("submit", "Criar conta", css_class="btn btn-primary w-full"))

    def clean_username(self) -> str:
        username = str(self.cleaned_data.get("username") or "")
        return username.lower()

    def clean_email(self) -> str:
        email = str(self.cleaned_data.get("email") or "")
        if email:
            email = email.lower()
            # Verifica se o e-mail já existe (case-insensitive)
            qs = User.objects.filter(email__iexact=email)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError("Este e-mail já está em uso.")
            return email
        return email
