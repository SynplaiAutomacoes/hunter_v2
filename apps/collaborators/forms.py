from __future__ import annotations

from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Div, Field, Layout, Submit
from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import CharField
from django.urls import reverse

from apps.collaborators.models import WorkshopCollaborator, WorkshopMember
from apps.core.widgets import (
    CalendarDateInput,
    CheckboxInput,
    CPForCNPJInput,
    EmailInput,
    MoneyInput,
    PasswordInput,
    PercentageInput,
    PhoneInput,
    RGInput,
    SelectInput,
    TextInput,
)
from apps.iam.models import WorkshopRole
from apps.workshops.models.workshops import Workshop

User = get_user_model()


class BaseWorkshopCollaboratorForm(forms.ModelForm):
    system_username = forms.CharField(label="Usuário", required=False)
    role = forms.ModelChoiceField(label="Grupo", queryset=WorkshopRole.objects.none(), required=False)

    class Meta:
        model = WorkshopCollaborator
        fields = [
            "name",
            "cpf",
            "rg",
            "birth_date",
            "sex",
            "phone",
            "email",
            "position",
            "salary",
            "admission_date",
            "termination_date",
            "collaborator_type",
            "receives_commission",
            "commission_percentage",
            "is_active",
            "system_access",
        ]
        widgets = {
            "name": TextInput(attrs={"placeholder": "Nome do colaborador"}),
            "cpf": CPForCNPJInput(mode="cpf"),
            "rg": RGInput(),
            "birth_date": CalendarDateInput(),
            "sex": SelectInput(),
            "phone": PhoneInput(),
            "email": EmailInput(),
            "position": TextInput(attrs={"placeholder": "Cargo"}),
            "salary": MoneyInput(),
            "admission_date": CalendarDateInput(),
            "termination_date": CalendarDateInput(),
            "collaborator_type": SelectInput(),
            "receives_commission": CheckboxInput(),
            "commission_percentage": PercentageInput(),
            "is_active": CheckboxInput(),
            "system_access": CheckboxInput(),
        }

    def __init__(self, *args, account=None, workshop: Workshop | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.account = account
        self.workshop = workshop

        self.fields["system_username"].widget = TextInput(attrs={"placeholder": "usuario"})

        roles_qs = WorkshopRole.objects.filter(account=account).order_by("name") if account else WorkshopRole.objects.none()
        self.fields["role"].queryset = roles_qs
        self.fields["role"].widget = SelectInput(choices=[(str(r.pk), r.name) for r in roles_qs])

        if self.instance and getattr(self.instance, "user_id", None):
            self.fields["system_username"].initial = self.instance.user.username
            member = WorkshopMember.objects.filter(user_id=self.instance.user_id, workshop=self.instance.workshop).select_related("role").first()
            if member:
                self.fields["role"].initial = member.role

        receives_commission = self._get_checkbox_state("receives_commission")
        system_access = self._get_checkbox_state("system_access")

        self.fields["receives_commission"].widget.attrs["x-model"] = "receives_commission"
        self.fields["commission_percentage"].widget.attrs["x-bind:disabled"] = "!receives_commission"
        if not receives_commission:
            self.fields["commission_percentage"].widget.attrs["disabled"] = True

        self.fields["system_access"].widget.attrs["x-model"] = "system_access"
        self.fields["system_username"].widget.attrs["x-bind:disabled"] = "!system_access"
        self.fields["role"].widget.attrs["x-bind:disabled"] = "!system_access"
        if not system_access:
            self.fields["system_username"].widget.attrs["disabled"] = True
            self.fields["role"].widget.attrs["disabled"] = True

        if "password1" in self.fields:
            self.fields["password1"].widget.attrs["x-bind:disabled"] = "!system_access"
            if not system_access:
                self.fields["password1"].widget.attrs["disabled"] = True
        if "password2" in self.fields:
            self.fields["password2"].widget.attrs["x-bind:disabled"] = "!system_access"
            if not system_access:
                self.fields["password2"].widget.attrs["disabled"] = True

        self.helper = FormHelper()
        self.helper.form_method = "post"
        self.helper.layout = self.get_layout()

    def get_layout(self):
        cancel_url = reverse("collaborators:collaborator_list")

        receives_commission = self._get_checkbox_state("receives_commission")
        system_access = self._get_checkbox_state("system_access")

        return Layout(
            Div(
                Field("name", wrapper_class="col-span-12 lg:col-span-4"),
                Field("cpf", wrapper_class="col-span-12 lg:col-span-4"),
                Field("rg", wrapper_class="col-span-12 lg:col-span-4"),
                #
                Field("email", wrapper_class="col-span-12 lg:col-span-4"),
                Field("phone", wrapper_class="col-span-12 lg:col-span-4"),
                Field("birth_date", wrapper_class="col-span-12 lg:col-span-4"),
                #
                Field("position", wrapper_class="col-span-12 lg:col-span-4"),
                Field("collaborator_type", wrapper_class="col-span-12 lg:col-span-4"),
                Field("sex", wrapper_class="col-span-12 lg:col-span-4"),
                #
                Field("salary", wrapper_class="col-span-12 lg:col-span-4"),
                Field("admission_date", wrapper_class="col-span-12 lg:col-span-4"),
                Field("termination_date", wrapper_class="col-span-12 lg:col-span-4"),
                #
                Field("is_active", wrapper_class="col-span-12 lg:col-span-1"),
                #
                HTML('<div class="col-span-12 divider"></div>'),
                #
                Field("receives_commission", wrapper_class="col-span-12 lg:col-span-1", x_model="receives_commission"),
                Field("commission_percentage", wrapper_class="col-span-12 lg:col-span-11", x_ref="commission_percentage"),
                #
                HTML('<div class="col-span-12 divider"></div>'),
                #
                Field("system_access", wrapper_class="col-span-12 lg:col-span-1", x_model="system_access"),
                Field("system_username", wrapper_class="col-span-12 lg:col-span-6", x_ref="system_username"),
                Field("role", wrapper_class="col-span-12 lg:col-span-5", x_ref="role"),
                *self.get_access_extra_layout_fields(),
                css_class="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start",
                x_data=f"{{ receives_commission: {str(receives_commission).lower()}, system_access: {str(system_access).lower()} }}",
                x_effect=(
                    "$refs.commission_percentage && ($refs.commission_percentage.disabled = !receives_commission);"
                    "$refs.system_username && ($refs.system_username.disabled = !system_access);"
                    "$refs.role && ($refs.role.disabled = !system_access);"
                    "$refs.password1 && ($refs.password1.disabled = !system_access);"
                    "$refs.password2 && ($refs.password2.disabled = !system_access);"
                ),
            ),
            #
            HTML('<div class="divider"></div>'),
            #
            Div(
                HTML(f'<a href="{cancel_url}" class="btn-form-cancel">Cancelar</a>'),
                Submit("submit", "Salvar", css_class="btn-form-save"),
                css_class="flex items-center justify-end gap-2",
            ),
        )

    @property
    def is_create(self) -> bool:
        return self.instance.pk is None

    def _get_checkbox_state(self, field_name: str) -> bool:
        if self.is_bound:
            return field_name in self.data

        initial = self.initial.get(field_name)
        if initial is not None:
            return bool(initial)

        return bool(getattr(self.instance, field_name, False))

    def get_access_extra_layout_fields(self) -> list[Field]:
        return []

    def clean(self):
        cleaned = super().clean()

        receives_commission = cleaned.get("receives_commission")
        commission_percentage = cleaned.get("commission_percentage")

        if receives_commission and commission_percentage is None:
            self.add_error("commission_percentage", "Informe o percentual de comissão.")
        if not receives_commission:
            cleaned["commission_percentage"] = None

        if cleaned.get("system_access"):
            username = cleaned.get("system_username")
            role = cleaned.get("role")

            if not username:
                self.add_error("system_username", "Informe o usuário de acesso.")
            else:
                qs = User.objects.filter(username=username)
                if not self.is_create and getattr(self.instance, "user_id", None):
                    qs = qs.exclude(pk=self.instance.user_id)
                if qs.exists():
                    self.add_error("system_username", "Este usuário já está em uso.")

            if role is None:
                self.add_error("role", "Selecione um grupo de permissões.")
            elif self.account and role.account_id != self.account.id:
                raise ValidationError("Grupo inválido para esta conta.")

            if not self.is_create:
                if self.instance.system_access is False and cleaned.get("system_access") is True:
                    self.add_error(
                        "system_access",
                        "Para liberar acesso ao sistema, use o fluxo de criação do colaborador com acesso.",
                    )

                if not getattr(self.instance, "user_id", None):
                    self.add_error("system_access", "Este colaborador não possui usuário vinculado.")

        return cleaned


class WorkshopCollaboratorCreateForm(BaseWorkshopCollaboratorForm):
    password1 = forms.CharField(label="Senha", required=False, widget=PasswordInput())
    password2 = forms.CharField(label="Confirmar senha", required=False, widget=PasswordInput())

    def get_access_extra_layout_fields(self) -> list[Field]:
        return [
            Field("password1", wrapper_class="col-span-12 lg:col-span-6", x_ref="password1"),
            Field("password2", wrapper_class="col-span-12 lg:col-span-6", x_ref="password2"),
        ]

    def clean(self):
        cleaned = super().clean()

        if cleaned.get("system_access"):
            p1 = cleaned.get("password1")
            p2 = cleaned.get("password2")

            if not p1:
                self.add_error("password1", "Informe a senha.")
            if not p2:
                self.add_error("password2", "Confirme a senha.")
            if p1 and p2 and p1 != p2:
                self.add_error("password2", "As senhas não conferem.")

        return cleaned


class WorkshopCollaboratorUpdateForm(BaseWorkshopCollaboratorForm):
    pass


class WorkshopCollaboratorModalForm(forms.ModelForm):
    class Meta:
        model = WorkshopCollaborator
        fields = ["name", "cpf", "email", "phone", "birth_date", "position", "collaborator_type", "admission_date", "salary"]
        labels = {
            "name": "Nome Completo",
            "cpf": "CPF",
            "email": "E-mail",
            "phone": "Telefone",
            "birth_date": "Data de Nascimento",
            "position": "Cargo",
            "collaborator_type": "Tipo",
            "admission_date": "Data de Admissão",
        }
        widgets = {
            "name": TextInput(attrs={"placeholder": "Nome do colaborador"}),
            "cpf": CPForCNPJInput(mode="cpf"),
            "email": EmailInput(),
            "phone": PhoneInput(),
            "birth_date": CalendarDateInput(),
            "position": TextInput(attrs={"placeholder": "Ex: Mecânico Chefe"}),
            "collaborator_type": SelectInput(),
            "admission_date": CalendarDateInput(),
        }

    def __init__(self, *args, **kwargs):
        # Removemos kwargs que não são do ModelForm se existirem
        account = kwargs.pop("account", None)
        workshop = kwargs.pop("workshop", None)

        super().__init__(*args, **kwargs)

        # O Salário não é obrigatório no form visual, fallback definido na View
        self.fields["salary"].required = False

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                Field("name", wrapper_class="col-span-12"),
                Field("cpf", wrapper_class="col-span-12 lg:col-span-6"),
                Field("email", wrapper_class="col-span-12 lg:col-span-6"),
                Field("phone", wrapper_class="col-span-12 lg:col-span-6"),
                Field("birth_date", wrapper_class="col-span-12 lg:col-span-6"),
                Field("position", wrapper_class="col-span-12 lg:col-span-6"),
                Field("collaborator_type", wrapper_class="col-span-12 lg:col-span-6"),
                Field("admission_date", wrapper_class="col-span-12 lg:col-span-6"),
                css_class="grid grid-cols-1 lg:grid-cols-12 gap-x-4 gap-y-2",
            )
        )
