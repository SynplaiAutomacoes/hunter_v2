from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from djmoney.money import Money

from apps.accounts.models import Account
from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.products import Product
from apps.collaborators.models import WorkshopMember
from apps.iam.models import WorkshopRole
from apps.stock.models import StockMovement, StockProduct
from apps.stock.services.adjust_stock import adjust_stock_quantity
from apps.workshops.models.workshops import Workshop


User = get_user_model()


def _create_workshop(*, suffix: int = 1) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina Adjust {suffix}",
        cnpj=f"44.555.666/0001-{suffix:02d}",
        phone="+5511999999999",
        address="Rua Teste, 123",
    )


class AdjustStockQuantityServiceTests(TestCase):
    def setUp(self) -> None:
        self.workshop = _create_workshop(suffix=1)
        self.group = CatalogGroup.objects.create(workshop=self.workshop, name="Grupo Adjust")
        self.product = Product.objects.create(
            workshop=self.workshop,
            group=self.group,
            code="ADJ-001",
            name="Produto Adjust",
            unit=Product.Unit.UND,
            cost_price=Money("10.00", "BRL"),
            selling_price=Money("20.00", "BRL"),
        )
        self.stock = StockProduct.objects.get(product=self.product, workshop=self.workshop)
        self.stock.current_quantity = 10
        self.stock.save(update_fields=["current_quantity"])
        self.user = User.objects.create_user(username="adjust-user", password="secret", cpf="12345678901")

    def test_entry_when_new_quantity_is_higher(self) -> None:
        movement = adjust_stock_quantity(
            stock_product=self.stock,
            new_quantity=15,
            reason="inventário físico",
            user=self.user,
        )
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.current_quantity, 15)
        self.assertEqual(movement.type, StockMovement.MovementType.ENTRY)
        self.assertEqual(movement.quantity, 5)
        self.assertEqual(movement.status, StockMovement.MovementStatus.APPROVED)
        self.assertEqual(movement.reason, "Inventário físico")
        self.assertEqual(movement.transcation_by_id, self.user.pk)
        self.assertIsNone(movement.supplier_id)

    def test_exit_when_new_quantity_is_lower(self) -> None:
        movement = adjust_stock_quantity(
            stock_product=self.stock,
            new_quantity=7,
            reason="correção de lançamento",
            user=self.user,
        )
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.current_quantity, 7)
        self.assertEqual(movement.type, StockMovement.MovementType.EXIT)
        self.assertEqual(movement.quantity, 3)
        self.assertEqual(movement.reason, "Correção de lançamento")

    def test_rejects_same_quantity(self) -> None:
        with self.assertRaises(ValidationError):
            adjust_stock_quantity(
                stock_product=self.stock,
                new_quantity=10,
                reason="sem alteração",
                user=self.user,
            )

    def test_rejects_negative_quantity(self) -> None:
        with self.assertRaises(ValidationError):
            adjust_stock_quantity(
                stock_product=self.stock,
                new_quantity=-1,
                reason="inválido",
                user=self.user,
            )

    def test_rejects_empty_reason(self) -> None:
        with self.assertRaises(ValidationError):
            adjust_stock_quantity(
                stock_product=self.stock,
                new_quantity=12,
                reason="   ",
                user=self.user,
            )


class StockAdjustViewTests(TestCase):
    def setUp(self) -> None:
        self.account = Account.objects.create(name="Conta Adjust")
        self.user = User.objects.create_user(username="adjust-view-user", password="secret", cpf="98765432100")
        self.user.account = self.account
        self.user.save(update_fields=["account"])
        self.workshop = Workshop.objects.create(
            account=self.account,
            name="Oficina Adjust View",
            cnpj="55.666.777/0001-01",
            phone="+5511999999999",
            address="Rua Teste, 456",
        )
        role = WorkshopRole.objects.create(account=self.account, name="Diretor")
        WorkshopMember.objects.create(user=self.user, workshop=self.workshop, role=role, is_active=True)
        self.group = CatalogGroup.objects.create(workshop=self.workshop, name="Grupo View")
        self.product = Product.objects.create(
            workshop=self.workshop,
            group=self.group,
            code="ADJ-V-001",
            name="Produto View Adjust",
            unit=Product.Unit.UND,
            cost_price=Money("10.00", "BRL"),
            selling_price=Money("20.00", "BRL"),
        )
        self.stock = StockProduct.objects.get(product=self.product, workshop=self.workshop)
        self.stock.current_quantity = 4
        self.stock.save(update_fields=["current_quantity"])
        self.client.force_login(self.user)
        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

    def test_post_creates_movement_with_reason_and_updates_quantity(self) -> None:
        url = reverse("catalog:stock_adjust", kwargs={"product_id": self.product.pk})
        response = self.client.post(
            url,
            {"quantity": "9", "reason": "ajuste manual de inventário"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["HX-Redirect"],
            f"{reverse('catalog:product_update', kwargs={'pk': self.product.pk})}?active_tab=movimentacao",
        )

        self.stock.refresh_from_db()
        self.assertEqual(self.stock.current_quantity, 9)

        movement = StockMovement.objects.get(stock_product=self.stock)
        self.assertEqual(movement.type, StockMovement.MovementType.ENTRY)
        self.assertEqual(movement.quantity, 5)
        self.assertEqual(movement.reason, "Ajuste manual de inventário")
        self.assertEqual(movement.transcation_by_id, self.user.pk)
        self.assertEqual(movement.workshop_id, self.workshop.pk)

    def test_post_rejects_same_quantity(self) -> None:
        url = reverse("catalog:stock_adjust", kwargs={"product_id": self.product.pk})
        response = self.client.post(
            url,
            {"quantity": "4", "reason": "sem mudança"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(StockMovement.objects.filter(stock_product=self.stock).count(), 0)
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.current_quantity, 4)
