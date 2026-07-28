from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.test import TestCase
from djmoney.money import Money

from apps.accounts.models import Account
from apps.collaborators.forms import WorkshopCollaboratorUpdateForm
from apps.collaborators.models import WorkshopCollaborator
from apps.workshops.models.workshops import Workshop


class CollaboratorTransportAllowanceNullNormalizationTests(TestCase):
    def setUp(self) -> None:
        self.account = Account.objects.create(name="Conta VT Null")
        self.workshop = Workshop.objects.create(
            account=self.account,
            name="Oficina VT Null",
            cnpj="31.222.333/0001-99",
            phone="+5511999999999",
            address="Rua Teste, 123",
        )
        self.collaborator = WorkshopCollaborator.objects.create(
            workshop=self.workshop,
            name="Lucas Gomes Moreira",
            cpf="40676429890",
            birth_date=date(1992, 12, 8),
            sex=WorkshopCollaborator.Sex.MALE,
            position="DEV",
            salary=Decimal("50.00"),
            transport_allowance_daily=Decimal("12.50"),
            admission_date=date(2001, 1, 1),
            collaborator_type=WorkshopCollaborator.CollaboratorType.ADMINISTRATIVE,
            is_active=True,
        )

    def test_model_save_coerces_null_transport_allowance_daily_to_zero(self) -> None:
        self.collaborator.transport_allowance_daily = None
        self.collaborator.save()

        self.collaborator.refresh_from_db()
        self.assertEqual(self.collaborator.transport_allowance_daily, Money("0.00", "BRL"))

    def test_model_save_coerces_null_salary_to_zero(self) -> None:
        self.collaborator.salary = None
        self.collaborator.save()

        self.collaborator.refresh_from_db()
        self.assertEqual(self.collaborator.salary, Money("0.00", "BRL"))

    def test_update_form_with_empty_transport_allowance_persists_zero(self) -> None:
        form = WorkshopCollaboratorUpdateForm(
            data={
                "name": self.collaborator.name,
                "cpf": self.collaborator.cpf,
                "rg": "",
                "birth_date": self.collaborator.birth_date.isoformat(),
                "sex": self.collaborator.sex,
                "phone": "",
                "email": "",
                "position": self.collaborator.position,
                "salary_0": "50.00",
                "salary_1": "BRL",
                "payment_day_type": WorkshopCollaborator.PaymentDayType.FIFTH_BUSINESS_DAY,
                "payment_day_of_month": "",
                "transport_allowance_daily_0": "",
                "transport_allowance_daily_1": "BRL",
                "admission_date": self.collaborator.admission_date.isoformat(),
                "termination_date": "",
                "collaborator_type": self.collaborator.collaborator_type,
                "receives_commission": False,
                "commission_percentage": "",
                "is_active": True,
                "system_access": False,
                "system_username": "",
                "role": "",
                "password1": "",
                "password2": "",
            },
            instance=self.collaborator,
            account=self.account,
            workshop=self.workshop,
        )

        self.assertTrue(form.is_valid(), form.errors.as_json())
        form.instance.workshop = self.workshop
        if form.instance.transport_allowance_daily is None:
            form.instance.transport_allowance_daily = 0
        form.save()

        self.collaborator.refresh_from_db()
        self.assertEqual(self.collaborator.transport_allowance_daily, Money("0.00", "BRL"))
