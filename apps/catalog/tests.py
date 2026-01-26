from __future__ import annotations

import datetime

from django.db import IntegrityError
from django.test import TestCase

from djmoney.money import Money

from apps.catalog.forms.kits import KitForm
from apps.catalog.models.kits import Kit, KitService
from apps.catalog.models.services import Service
from apps.workshops.models.workshops import Workshop


class KitTests(TestCase):
    def setUp(self):
        self.workshop = Workshop.objects.create(name="Oficina Teste")

    def test_unique_service_per_kit_constraint(self):
        kit = Kit.objects.create(workshop=self.workshop, name="Kit A", description="", is_active=True)
        service = Service.objects.create(
            workshop=self.workshop,
            name="Serviço 1",
            description="",
            duration=datetime.timedelta(minutes=30),
            selling_price=Money(10, "BRL"),
            suggested_cost=None,
            is_third_party=False,
            is_active=True,
        )

        KitService.objects.create(kit=kit, service=service)
        with self.assertRaises(IntegrityError):
            KitService.objects.create(kit=kit, service=service)

    def test_kit_form_rejects_duplicate_services(self):
        service = Service.objects.create(
            workshop=self.workshop,
            name="Serviço 1",
            description="",
            duration=datetime.timedelta(minutes=30),
            selling_price=Money(10, "BRL"),
            suggested_cost=None,
            is_third_party=False,
            is_active=True,
        )

        form = KitForm(
            data={
                "name": "Kit A",
                "description": "",
                "is_active": "on",
                "kit_services": [str(service.id), str(service.id)],
            },
            workshop=self.workshop,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("Existem serviços repetidos no kit.", form.non_field_errors())

    def test_kit_form_persists_service_quantity(self):
        kit = Kit.objects.create(workshop=self.workshop, name="Kit A", description="", is_active=True)
        service = Service.objects.create(
            workshop=self.workshop,
            name="Serviço 1",
            description="",
            duration=datetime.timedelta(minutes=30),
            selling_price=Money(10, "BRL"),
            suggested_cost=None,
            is_third_party=False,
            is_active=True,
        )

        form = KitForm(
            instance=kit,
            data={
                "name": "Kit A",
                "description": "",
                "is_active": "on",
                "kit_services": [str(service.id)],
                f"kit_service_qty_{service.id}": "2",
            },
            workshop=self.workshop,
        )

        self.assertTrue(form.is_valid(), form.errors.as_json())
        form.save()

        item = KitService.objects.get(kit=kit, service=service)
        self.assertEqual(item.quantity, 2)

    def test_kit_form_rejects_invalid_service_quantity(self):
        service = Service.objects.create(
            workshop=self.workshop,
            name="Serviço 1",
            description="",
            duration=datetime.timedelta(minutes=30),
            selling_price=Money(10, "BRL"),
            suggested_cost=None,
            is_third_party=False,
            is_active=True,
        )

        form = KitForm(
            data={
                "name": "Kit A",
                "description": "",
                "is_active": "on",
                "kit_services": [str(service.id)],
                f"kit_service_qty_{service.id}": "0",
            },
            workshop=self.workshop,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("Quantidade inválida para serviço.", form.non_field_errors())

    def test_service_money_fields_work_with_only_including_currency_fields(self):
        """Regressão: `djmoney` precisa do campo `*_currency` junto com o valor.

        Em alguns fluxos (ex.: HTMX do modal de Kits) usamos `.only(...)`.
        Se não incluirmos `*_currency`, acessar `service.suggested_cost` pode quebrar
        durante renderização de template.
        """

        service = Service.objects.create(
            workshop=self.workshop,
            name="Serviço 1",
            description="",
            duration=datetime.timedelta(minutes=30),
            selling_price=Money(10, "BRL"),
            suggested_cost=Money(5, "BRL"),
            is_third_party=False,
            is_active=True,
        )

        s = Service.objects.only(
            "id",
            "name",
            "suggested_cost",
            "suggested_cost_currency",
            "selling_price",
            "selling_price_currency",
        ).get(pk=service.pk)

        # Não deve levantar exceção
        self.assertEqual(str(s.suggested_cost), "R$\xa05,00")
        self.assertEqual(str(s.selling_price), "R$\xa010,00")
