from __future__ import annotations

import datetime
from decimal import Decimal

from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from djmoney.money import Money

from apps.catalog.forms.kits import KitForm
from apps.catalog.forms.products import ProductForm
from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.kits import Kit, KitService
from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.workshops.tests import create_director_user_with_workshop
from apps.workshops.models.workshops import Workshop


class KitTests(TestCase):
    def setUp(self):
        self.workshop = Workshop.objects.create(name="Oficina Teste", phone="+5511999999999", address="Rua Teste, 123")

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

    def test_kit_form_rejects_duplicate_name_in_same_workshop(self):
        Kit.objects.create(workshop=self.workshop, name="Kit Revisao", description="", is_active=True)

        form = KitForm(
            data={
                "name": "Kit Revisao",
                "description": "",
                "is_active": "on",
            },
            workshop=self.workshop,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("Já existe um kit com este nome na oficina ativa.", form.errors.get("name", []))

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

    def test_kit_form_persists_service_duration(self):
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
                f"kit_service_duration_{service.id}": "01:20:00",
            },
            workshop=self.workshop,
        )

        self.assertTrue(form.is_valid(), form.errors.as_json())
        form.save()

        item = KitService.objects.get(kit=kit, service=service)
        self.assertEqual(item.duration, datetime.timedelta(hours=1, minutes=20))

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

    def test_kit_form_rejects_invalid_service_duration(self):
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
                f"kit_service_duration_{service.id}": "01:75:00",
            },
            workshop=self.workshop,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("Duração inválida para serviço.", form.non_field_errors())

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


class ProductFormTests(TestCase):
    def setUp(self) -> None:
        self.workshop = Workshop.objects.create(name="Oficina Produto", phone="+5511999999999", address="Rua Produto, 123")
        self.group = CatalogGroup.objects.create(workshop=self.workshop, name="Grupo Produto")

    def test_product_form_accepts_profit_margin_value_without_digit_error(self) -> None:
        form = ProductForm(
            data={
                "code": "PROD-001",
                "name": "Produto Teste",
                "description": "",
                "unit": Product.Unit.UND,
                "group": str(self.group.pk),
                "brand": "",
                "model": "",
                "sku": "",
                "barcode": "",
                "location": "",
                "cost_price_0": "10.00",
                "cost_price_1": "BRL",
                "selling_price_0": "10.11",
                "selling_price_1": "BRL",
                "profit_margin": "1.10",
                "ncm": "87089990",
                "cest": "",
                "origin_cst": str(Product.OriginCST.NACIONAL),
                "purpose": Product.Purpose.RESALE,
                "application": "",
                "is_active": "on",
            },
            workshop=self.workshop,
        )

        self.assertTrue(form.is_valid(), form.errors.as_json())
        product = form.save(commit=False)
        self.assertEqual(product.profit_margin, Decimal("1.09"))

    def test_product_form_converts_fractional_profit_margin_to_percent_value(self) -> None:
        form = ProductForm(
            data={
                "code": "PROD-002",
                "name": "Produto Fracao",
                "description": "",
                "unit": Product.Unit.UND,
                "group": str(self.group.pk),
                "brand": "",
                "model": "",
                "sku": "",
                "barcode": "",
                "location": "",
                "cost_price_0": "10.00",
                "cost_price_1": "BRL",
                "selling_price_0": "20.00",
                "selling_price_1": "BRL",
                "profit_margin": "0.500000",
                "ncm": "87089990",
                "cest": "",
                "origin_cst": str(Product.OriginCST.NACIONAL),
                "purpose": Product.Purpose.RESALE,
                "application": "",
                "is_active": "on",
            },
            workshop=self.workshop,
        )

        self.assertTrue(form.is_valid(), form.errors.as_json())
        product = form.save(commit=False)
        self.assertEqual(product.profit_margin, Decimal("50.00"))

    def test_product_form_requires_confirmation_for_price_below_last_used_price(self) -> None:
        product = Product.objects.create(
            workshop=self.workshop,
            code="PROD-003",
            name="Produto Historico",
            description="",
            unit=Product.Unit.UND,
            group=self.group,
            cost_price=Money("10.00", "BRL"),
            selling_price=Money("40.00", "BRL"),
            last_used_price=Money("30.00", "BRL"),
            ncm="87089990",
        )

        form = ProductForm(
            instance=product,
            data={
                "code": product.code,
                "name": product.name,
                "description": "",
                "unit": Product.Unit.UND,
                "group": str(self.group.pk),
                "brand": "",
                "model": "",
                "sku": "",
                "barcode": "",
                "location": "",
                "cost_price_0": "10.00",
                "cost_price_1": "BRL",
                "selling_price_0": "20.00",
                "selling_price_1": "BRL",
                "profit_margin": "50.00",
                "ncm": "87089990",
                "cest": "",
                "origin_cst": str(Product.OriginCST.NACIONAL),
                "purpose": Product.Purpose.RESALE,
                "application": "",
                "is_active": "on",
            },
            workshop=self.workshop,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("Último valor usado: R$ 30,00", str(form.errors["selling_price"][0]))

    def test_product_form_allows_confirmed_price_below_last_used_price(self) -> None:
        product = Product.objects.create(
            workshop=self.workshop,
            code="PROD-004",
            name="Produto Historico Confirmado",
            description="",
            unit=Product.Unit.UND,
            group=self.group,
            cost_price=Money("10.00", "BRL"),
            selling_price=Money("40.00", "BRL"),
            last_used_price=Money("30.00", "BRL"),
            ncm="87089990",
        )

        form = ProductForm(
            instance=product,
            data={
                "code": product.code,
                "name": product.name,
                "description": "",
                "unit": Product.Unit.UND,
                "group": str(self.group.pk),
                "brand": "",
                "model": "",
                "sku": "",
                "barcode": "",
                "location": "",
                "cost_price_0": "10.00",
                "cost_price_1": "BRL",
                "selling_price_0": "20.00",
                "selling_price_1": "BRL",
                "profit_margin": "50.00",
                "ncm": "87089990",
                "cest": "",
                "origin_cst": str(Product.OriginCST.NACIONAL),
                "purpose": Product.Purpose.RESALE,
                "application": "",
                "is_active": "on",
                "confirm_lower_price": "1",
            },
            workshop=self.workshop,
        )

        self.assertTrue(form.is_valid(), form.errors.as_json())


class ProductUpdateNavigationTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=31)
        self.client.force_login(self.user)

        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

        self.group = CatalogGroup.objects.create(workshop=self.workshop, name="Grupo Navegacao")
        self.product = Product.objects.create(
            workshop=self.workshop,
            code="PROD-NAV-001",
            name="Produto Navegacao",
            description="",
            unit=Product.Unit.UND,
            group=self.group,
            cost_price=Money("10.00", "BRL"),
            selling_price=Money("20.00", "BRL"),
            profit_margin=Decimal("50.00"),
            ncm="87089990",
        )

    def test_product_update_uses_next_url_for_back_and_success(self) -> None:
        next_url = "/emissao/?step=6"

        response = self.client.get(reverse("catalog:product_update", kwargs={"pk": self.product.pk}), data={"next": next_url})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'href="{next_url}"')
        self.assertContains(response, f'href="{next_url}" class="btn-form-cancel"')

        response = self.client.post(
            f"{reverse('catalog:product_update', kwargs={'pk': self.product.pk})}?next=%2Femissao%2F%3Fstep%3D6",
            data={
                "code": self.product.code,
                "name": "Produto Navegacao Atualizado",
                "description": "",
                "unit": Product.Unit.UND,
                "group": str(self.group.pk),
                "brand": "",
                "model": "",
                "sku": "",
                "barcode": "",
                "location": "",
                "cost_price_0": "10.00",
                "cost_price_1": "BRL",
                "selling_price_0": "20.00",
                "selling_price_1": "BRL",
                "profit_margin": "50.00",
                "ncm": "87089990",
                "cest": "",
                "origin_cst": str(Product.OriginCST.NACIONAL),
                "purpose": Product.Purpose.RESALE,
                "application": "",
                "is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers.get("Location"), next_url)
