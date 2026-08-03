import re

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, SetPasswordForm, UserCreationForm, UsernameField
from django.db.models import Q

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit

from apps.core.presentation.widgets import EmailInput, TextInput, CPForCNPJInput, PasswordInput

User = get_user_model()

USER_PLACEHOLDER = {"placeholder": "user123"}


def _phone_lookup_q(identifier: str) -> Q | None:
    digits = re.sub(r"\D", "", identifier)
    if not digits or len(digits) < 8:
        return None
    patterns = [digits]
    if not digits.startswith("55"):
        patterns.append("55" + digits)
    phone_q = Q(phone__regex="\\D*".join(patterns[0]))
    for pattern in patterns[1:]:
        phone_q |= Q(phone__regex="\\D*".join(pattern))
    return phone_q


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


class UserIdentificationForm(forms.Form):
    identifier = forms.CharField(
        label="Usuário, e-mail ou número de WhatsApp",
        widget=TextInput(attrs={"placeholder": "Digite seu usuário, e-mail ou WhatsApp"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = None
        self.helper = FormHelper()
        self.helper.form_tag = False

    def clean_identifier(self):
        identifier = str(self.cleaned_data.get("identifier") or "").strip().lower()
        if not identifier:
            raise forms.ValidationError("Informe seu usuário, e-mail ou número de WhatsApp.")

        base_qs = User.objects.filter(Q(username__iexact=identifier) | Q(email__iexact=identifier))
        phone_q = _phone_lookup_q(identifier)
        if phone_q is not None:
            base_qs = base_qs | User.objects.filter(phone_q)

        users = list(base_qs.distinct())

        if not users:
            users = self._users_from_collaborator(identifier, phone_q)

        if not users:
            raise forms.ValidationError("Usuário não encontrado.")
        if len(users) > 1:
            raise forms.ValidationError("Identificação ambígua. Use o e-mail.")

        self.user = users[0]
        return identifier

    def _users_from_collaborator(self, identifier: str, phone_q):
        from apps.collaborators.models import WorkshopCollaborator

        collab_qs = WorkshopCollaborator.objects.filter(Q(email__iexact=identifier))
        if phone_q is not None:
            collab_qs = collab_qs | WorkshopCollaborator.objects.filter(phone_q)

        linked_users = [collab.user for collab in collab_qs.select_related("user").distinct() if collab.user_id]
        if not linked_users:
            return []
        seen = set()
        unique_users = []
        for user in linked_users:
            if user.pk not in seen:
                seen.add(user.pk)
                unique_users.append(user)
        return unique_users


class CodeVerificationForm(forms.Form):
    code = forms.CharField(
        label="Código de verificação",
        widget=TextInput(
            attrs={
                "placeholder": "XXXXXX",
                "maxlength": 6,
                "class": "tracking-widest text-center text-2xl font-mono",
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.token = None
        self.helper = FormHelper()
        self.helper.form_tag = False

    def clean_code(self):
        code = str(self.cleaned_data.get("code") or "").strip().upper()
        if not code or len(code) != 6:
            raise forms.ValidationError("Código inválido.")
        return code


class PasswordResetForm(SetPasswordForm):
    def __init__(self, user, *args, **kwargs):
        super().__init__(user, *args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.fields["new_password1"].widget = PasswordInput(attrs={"placeholder": "Nova senha"})
        self.fields["new_password2"].widget = PasswordInput(attrs={"placeholder": "Confirmar senha"})
