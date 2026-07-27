from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.accounts.models import Account
from apps.collaborators.forms import CollaboratorBenefitFormSet, WorkshopCollaboratorUpdateForm
from apps.collaborators.models import WorkshopCollaborator, WorkshopMember
from apps.collaborators.views import WorkshopCollaboratorUpdateView
from apps.iam.models import WorkshopRole
from apps.workshops.models.workshops import Workshop

User = get_user_model()


class CollaboratorPasswordUpdateTests(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.account = Account.objects.create(name="Conta Senha Colaborador")
        self.workshop = Workshop.objects.create(
            account=self.account,
            name="Oficina Senha Colaborador",
            cnpj="31.222.333/0001-88",
            phone="+5511999999999",
            address="Rua Teste, 123",
        )
        self.role = WorkshopRole.objects.create(account=self.account, name="Operador")
        self.actor = User.objects.create_user(
            username="admin_senha",
            password="admin-pass",
            cpf="11144477735",
            account=self.account,
        )
        self.user = User.objects.create_user(
            username="colab_user",
            password="senha-antiga",
            cpf="39053344705",
            email="colab@example.com",
            account=self.account,
        )
        self.collaborator = WorkshopCollaborator.objects.create(
            workshop=self.workshop,
            user=self.user,
            name="Colaborador Senha",
            cpf="39053344705",
            birth_date=date(1990, 1, 10),
            sex=WorkshopCollaborator.Sex.MALE,
            phone="+5511999999999",
            email="colab@example.com",
            position="Mecanico",
            salary=Decimal("2500.00"),
            payment_day_type=WorkshopCollaborator.PaymentDayType.FIFTH_BUSINESS_DAY,
            transport_allowance_daily=Decimal("0.00"),
            admission_date=date(2025, 1, 1),
            collaborator_type=WorkshopCollaborator.CollaboratorType.PRODUCTIVE,
            is_active=True,
            system_access=True,
        )
        WorkshopMember.objects.create(
            user=self.user,
            workshop=self.workshop,
            role=self.role,
            is_active=True,
        )

    def _base_form_data(self, *, password1: str = "", password2: str = "") -> dict[str, str]:
        return {
            "name": self.collaborator.name,
            "cpf": self.collaborator.cpf,
            "rg": "",
            "birth_date": self.collaborator.birth_date.isoformat(),
            "sex": self.collaborator.sex,
            "phone": self.collaborator.phone or "",
            "email": self.collaborator.email or "",
            "position": self.collaborator.position,
            "salary_0": "2500.00",
            "salary_1": "BRL",
            "payment_day_type": self.collaborator.payment_day_type,
            "payment_day_of_month": "",
            "transport_allowance_daily_0": "0.00",
            "transport_allowance_daily_1": "BRL",
            "admission_date": self.collaborator.admission_date.isoformat(),
            "termination_date": "",
            "collaborator_type": self.collaborator.collaborator_type,
            "receives_commission": False,
            "commission_percentage": "",
            "is_active": True,
            "system_access": True,
            "system_username": self.user.username,
            "role": str(self.role.pk),
            "password1": password1,
            "password2": password2,
            "benefits-TOTAL_FORMS": "0",
            "benefits-INITIAL_FORMS": "0",
            "benefits-MIN_NUM_FORMS": "0",
            "benefits-MAX_NUM_FORMS": "1000",
        }

    def _build_update_form(self, *, password1: str = "", password2: str = "") -> WorkshopCollaboratorUpdateForm:
        return WorkshopCollaboratorUpdateForm(
            data=self._base_form_data(password1=password1, password2=password2),
            instance=self.collaborator,
            account=self.account,
            workshop=self.workshop,
        )

    def _call_forms_valid(self, *, password1: str = "", password2: str = "") -> None:
        form = self._build_update_form(password1=password1, password2=password2)
        self.assertTrue(form.is_valid(), form.errors.as_json())

        benefit_formset = CollaboratorBenefitFormSet(
            data=self._base_form_data(password1=password1, password2=password2),
            instance=self.collaborator,
            prefix="benefits",
            form_kwargs={"workshop": self.workshop},
        )
        self.assertTrue(benefit_formset.is_valid(), benefit_formset.errors)

        request = self.factory.post(
            reverse("collaborators:collaborator_update", kwargs={"pk": self.collaborator.pk}),
            self._base_form_data(password1=password1, password2=password2),
        )
        request.user = self.actor
        session_middleware = SessionMiddleware(lambda req: HttpResponse())
        session_middleware.process_request(request)
        request.session.save()
        setattr(request, "_messages", FallbackStorage(request))

        view = WorkshopCollaboratorUpdateView()
        view.request = request
        view.workshop = self.workshop
        view.object = self.collaborator
        view.forms_valid(form, benefit_formset)

    def test_update_form_rejects_mismatched_passwords_for_existing_user(self) -> None:
        form = self._build_update_form(password1="nova-senha", password2="outra-senha")

        self.assertFalse(form.is_valid())
        self.assertIn("password2", form.errors)
        self.assertIn("As senhas não conferem.", form.errors["password2"])

    def test_update_form_allows_blank_passwords_for_existing_user(self) -> None:
        form = self._build_update_form(password1="", password2="")

        self.assertTrue(form.is_valid(), form.errors.as_json())

    def test_update_view_changes_password_when_provided(self) -> None:
        self._call_forms_valid(password1="nova-senha", password2="nova-senha")

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("nova-senha"))
        self.assertFalse(self.user.check_password("senha-antiga"))

    def test_update_view_preserves_password_when_blank(self) -> None:
        self._call_forms_valid(password1="nova-senha", password2="nova-senha")
        self._call_forms_valid(password1="", password2="")

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("nova-senha"))
