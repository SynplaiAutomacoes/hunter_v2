from __future__ import annotations

from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Field, HTML, Layout, Submit

from apps.core.widgets import (
    CalendarDateInput,
    CheckboxInput,
    CPForCNPJInput,
    EmailInput,
    MoneyInput,
    PasswordInput,
    PhoneInput,
    RGInput,
    SelectInput,
    TextInput,
)
from apps.iam.models import WorkshopRole
from apps.workshops.models import Workshop, WorkshopEmployee, WorkshopMember

User = get_user_model()


class WorkshopForm(forms.ModelForm):
    class Meta:
        model = Workshop
        fields = ["name", "cnpj", "is_active"]
        widgets = {
            "name": TextInput(attrs={"placeholder": "Oficina Hunter"}),
            "cnpj": CPForCNPJInput(mode="cnpj"),
            "is_active": CheckboxInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        cancel_url = reverse("workshops:list")

        self.helper = FormHelper()
        self.helper.layout = Layout(
            Div(
                Field(Workshop.name.field.name, wrapper_class="w-full"),
                Field(Workshop.cnpj.field.name, wrapper_class="w-full"),
                Field(Workshop.is_active.field.name, wrapper_class="w-fit"),
                css_class="grid grid-cols-1 lg:grid-cols-[1fr_1fr_auto] gap-4 items-start",
            ),
            HTML('<div class="divider"></div>'),
            Div(
                HTML(f'<a href="{cancel_url}" class="btn-form-cancel">Cancelar</a>'),
                Submit("submit", "Salvar", css_class="btn-form-save"),
                css_class="flex items-center justify-end gap-2",
            ),
        )


class BaseWorkshopEmployeeForm(forms.ModelForm):
    # Campos extras (não estão no model)
    system_username = forms.CharField(label="Usuário", required=False, widget=TextInput())
    role = forms.ModelChoiceField(label="Grupo", queryset=WorkshopRole.objects.none(), required=False, widget=SelectInput())

    # Atalhos para nomes de campos (evita strings espalhadas)
    F_NAME = WorkshopEmployee.name.field.name
    F_CPF = WorkshopEmployee.cpf.field.name
    F_RG = WorkshopEmployee.rg.field.name
    F_BIRTH_DATE = WorkshopEmployee.birth_date.field.name
    F_SEX = WorkshopEmployee.sex.field.name
    F_PHONE = WorkshopEmployee.phone.field.name
    F_EMAIL = WorkshopEmployee.email.field.name
    F_POSITION = WorkshopEmployee.position.field.name
    F_SALARY = WorkshopEmployee.salary.field.name
    F_ADMISSION_DATE = WorkshopEmployee.admission_date.field.name
    F_TERMINATION_DATE = WorkshopEmployee.termination_date.field.name
    F_EMPLOYEE_TYPE = WorkshopEmployee.employee_type.field.name
    F_RECEIVES_COMMISSION = WorkshopEmployee.receives_commission.field.name
    F_COMMISSION_PERCENTAGE = WorkshopEmployee.commission_percentage.field.name
    F_IS_ACTIVE = WorkshopEmployee.is_active.field.name
    F_SYSTEM_ACCESS = WorkshopEmployee.system_access.field.name

    # Campos extras
    F_SYSTEM_USERNAME = "system_username"
    F_ROLE = "role"

    class Meta:
        model = WorkshopEmployee
        fields = [
            WorkshopEmployee.name.field.name,
            WorkshopEmployee.cpf.field.name,
            WorkshopEmployee.rg.field.name,
            WorkshopEmployee.birth_date.field.name,
            WorkshopEmployee.sex.field.name,
            WorkshopEmployee.phone.field.name,
            WorkshopEmployee.email.field.name,
            WorkshopEmployee.position.field.name,
            WorkshopEmployee.salary.field.name,
            WorkshopEmployee.admission_date.field.name,
            WorkshopEmployee.termination_date.field.name,
            WorkshopEmployee.employee_type.field.name,
            WorkshopEmployee.receives_commission.field.name,
            WorkshopEmployee.commission_percentage.field.name,
            WorkshopEmployee.is_active.field.name,
            WorkshopEmployee.system_access.field.name,
        ]
        widgets = {
            WorkshopEmployee.name.field.name: TextInput(attrs={"placeholder": "Nome do colaborador"}),
            WorkshopEmployee.cpf.field.name: CPForCNPJInput(mode="cpf"),
            WorkshopEmployee.rg.field.name: RGInput(),
            WorkshopEmployee.birth_date.field.name: CalendarDateInput(),
            WorkshopEmployee.sex.field.name: SelectInput(choices=WorkshopEmployee.Sex.choices),
            WorkshopEmployee.phone.field.name: PhoneInput(),
            WorkshopEmployee.email.field.name: EmailInput(),
            WorkshopEmployee.position.field.name: TextInput(attrs={"placeholder": "Cargo"}),
            WorkshopEmployee.salary.field.name: MoneyInput(attrs={"placeholder": "0,00"}),
            WorkshopEmployee.admission_date.field.name: CalendarDateInput(),
            WorkshopEmployee.termination_date.field.name: CalendarDateInput(),
            WorkshopEmployee.employee_type.field.name: SelectInput(choices=WorkshopEmployee.EmployeeType.choices),
            WorkshopEmployee.receives_commission.field.name: CheckboxInput(),
            WorkshopEmployee.commission_percentage.field.name: MoneyInput(attrs={"placeholder": "0,00"}),
            WorkshopEmployee.is_active.field.name: CheckboxInput(),
            WorkshopEmployee.system_access.field.name: CheckboxInput(),
        }

    def __init__(self, *args, account=None, workshop: Workshop | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.account = account
        self.workshop = workshop

        # Roles por conta
        roles_qs = WorkshopRole.objects.filter(account=account).order_by("name") if account else WorkshopRole.objects.none()
        self.fields[self.F_ROLE].queryset = roles_qs
        self.fields[self.F_ROLE].widget = SelectInput(choices=[("", "---------")] + [(str(r.pk), r.name) for r in roles_qs])

        # Preenche username/role quando já existe user vinculado
        if self.instance and getattr(self.instance, "user_id", None):
            self.fields[self.F_SYSTEM_USERNAME].initial = self.instance.user.username
            member = WorkshopMember.objects.filter(user_id=self.instance.user_id, workshop=self.instance.workshop).select_related("role").first()
            if member:
                self.fields[self.F_ROLE].initial = member.role

        cancel_url = reverse("workshops:employee_list")

        self.helper = FormHelper()
        self.helper.form_method = "post"
        self.helper.layout = Layout(
            Div(
                Field(self.F_NAME, wrapper_class="w-full"),
                Field(self.F_CPF, wrapper_class="w-full"),
                Field(self.F_RG, wrapper_class="w-full"),
                Field(self.F_BIRTH_DATE, wrapper_class="w-full"),
                Field(self.F_SEX, wrapper_class="w-full"),
                Field(self.F_PHONE, wrapper_class="w-full"),
                Field(self.F_EMAIL, wrapper_class="w-full"),
                Field(self.F_POSITION, wrapper_class="w-full"),
                Field(self.F_SALARY, wrapper_class="w-full"),
                Field(self.F_ADMISSION_DATE, wrapper_class="w-full"),
                Field(self.F_TERMINATION_DATE, wrapper_class="w-full"),
                Field(self.F_EMPLOYEE_TYPE, wrapper_class="w-full"),
                Field(self.F_RECEIVES_COMMISSION, wrapper_class="w-fit"),
                Field(self.F_COMMISSION_PERCENTAGE, wrapper_class="w-full"),
                Field(self.F_IS_ACTIVE, wrapper_class="w-fit"),
                Field(self.F_SYSTEM_ACCESS, wrapper_class="w-fit"),
                Field(self.F_SYSTEM_USERNAME, wrapper_class="w-full"),
                Field(self.F_ROLE, wrapper_class="w-full"),
                *self.get_access_extra_layout_fields(),
                css_class="grid grid-cols-1 lg:grid-cols-3 gap-4 items-start",
            ),
            HTML('<div class="divider"></div>'),
            Div(
                HTML(f'<a href="{cancel_url}" class="btn-form-cancel">Cancelar</a>'),
                Submit("submit", "Salvar", css_class="btn-form-save"),
                css_class="flex items-center justify-end gap-2",
            ),
        )

    @property
    def is_create(self) -> bool:
        return self.instance.pk is None

    def get_access_extra_layout_fields(self) -> list[Field]:
        """Campos extras do layout (ex.: senha) dependendo do modo do form."""
        return []

    def clean(self):
        cleaned = super().clean()

        # Comissão
        receives_commission = cleaned.get(self.F_RECEIVES_COMMISSION)
        commission_percentage = cleaned.get(self.F_COMMISSION_PERCENTAGE)
        if receives_commission and commission_percentage is None:
            self.add_error(self.F_COMMISSION_PERCENTAGE, "Informe o percentual de comissão.")
        if not receives_commission:
            cleaned[self.F_COMMISSION_PERCENTAGE] = None

        # Acesso ao sistema
        if cleaned.get(self.F_SYSTEM_ACCESS):
            username = cleaned.get(self.F_SYSTEM_USERNAME)
            role = cleaned.get(self.F_ROLE)

            if not username:
                self.add_error(self.F_SYSTEM_USERNAME, "Informe o usuário de acesso.")
            else:
                qs = User.objects.filter(username=username)
                if not self.is_create and getattr(self.instance, "user_id", None):
                    qs = qs.exclude(pk=self.instance.user_id)
                if qs.exists():
                    self.add_error(self.F_SYSTEM_USERNAME, "Este usuário já está em uso.")

            if role is None:
                self.add_error(self.F_ROLE, "Selecione um grupo de permissões.")
            elif self.account and role.account_id != self.account.id:
                raise ValidationError("Grupo inválido para esta conta.")

            # Regras específicas do update
            if not self.is_create:
                if self.instance.system_access is False and cleaned.get(self.F_SYSTEM_ACCESS) is True:
                    self.add_error(self.F_SYSTEM_ACCESS, "Para liberar acesso ao sistema, use o fluxo de criação do colaborador com acesso.")

                if not getattr(self.instance, "user_id", None):
                    self.add_error(self.F_SYSTEM_ACCESS, "Este colaborador não possui usuário vinculado.")

        return cleaned


class WorkshopEmployeeCreateForm(BaseWorkshopEmployeeForm):
    password1 = forms.CharField(label="Senha", required=False, widget=PasswordInput())
    password2 = forms.CharField(label="Confirmar senha", required=False, widget=PasswordInput())

    F_PASSWORD1 = "password1"
    F_PASSWORD2 = "password2"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # placeholder só no create
        self.fields[self.F_SYSTEM_USERNAME].widget = TextInput(attrs={"placeholder": "usuario"})

    def get_access_extra_layout_fields(self) -> list[Field]:
        return [
            Field(self.F_PASSWORD1, wrapper_class="w-full"),
            Field(self.F_PASSWORD2, wrapper_class="w-full"),
        ]

    def clean(self):
        cleaned = super().clean()

        if cleaned.get(self.F_SYSTEM_ACCESS):
            p1 = cleaned.get(self.F_PASSWORD1)
            p2 = cleaned.get(self.F_PASSWORD2)

            if not p1:
                self.add_error(self.F_PASSWORD1, "Informe a senha.")
            if not p2:
                self.add_error(self.F_PASSWORD2, "Confirme a senha.")
            if p1 and p2 and p1 != p2:
                self.add_error(self.F_PASSWORD2, "As senhas não conferem.")

        return cleaned


class WorkshopEmployeeUpdateForm(BaseWorkshopEmployeeForm):
    pass
