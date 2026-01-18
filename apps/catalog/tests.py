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
