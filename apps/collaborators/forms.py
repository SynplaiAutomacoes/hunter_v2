from __future__ import annotations

from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Field, HTML, Layout, Submit

from apps.collaborators.models import WorkshopCollaborator, WorkshopMember
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
    NumberInput,
)
from apps.iam.models import WorkshopRole
from apps.workshops.models import Workshop

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
            "commission_percentage": NumberInput(),
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

        self.helper = FormHelper()
        self.helper.form_method = "post"
        self.helper.layout = self.get_layout()

    def get_layout(self):
        cancel_url = reverse("collaborators:collaborator_list")

        init_commission = "true" if self.instance.receives_commission else "false"
        init_sys_access = "true" if self.instance.system_access else "false"

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
                Field("receives_commission", wrapper_class="col-span-12 lg:col-span-1"),
                Field("commission_percentage", wrapper_class="col-span-12 lg:col-span-11"),
                #
                HTML('<div class="col-span-12 divider"></div>'),
                #
                Field("system_access", wrapper_class="col-span-12 lg:col-span-1"),
                Field("system_username", wrapper_class="col-span-12 lg:col-span-6"),
                Field("role", wrapper_class="col-span-12 lg:col-span-5"),
                *self.get_access_extra_layout_fields(),
                css_class="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start",
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
            Field("password1", wrapper_class="col-span-12 lg:col-span-6"),
            Field("password2", wrapper_class="col-span-12 lg:col-span-6"),
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
