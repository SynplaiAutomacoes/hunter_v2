from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

from django.test import SimpleTestCase
from djmoney.money import Money

from apps.budget.pricing import build_pricing_snapshot, zero_money


def _money(amount: str) -> Money:
    return Money(amount, "BRL")


def _product(*, product_id: int, name: str = "Produto") -> SimpleNamespace:
    return SimpleNamespace(id=product_id, name=name, code="", application="", location="")


def _service(*, service_id: int, name: str = "Servico") -> SimpleNamespace:
    return SimpleNamespace(id=service_id, name=name, is_third_party=False)


def _direct_product_item(*, product_id: int, quantity: int, selling: str, shipping: str = "0.00", cost: str = "0.00") -> SimpleNamespace:
    product = _product(product_id=product_id)
    return SimpleNamespace(
        id=None,
        product_id=product_id,
        service_id=None,
        kit_id=None,
        quantity=quantity,
        item_benefit_type="normal",
        product_selling_price=_money(selling),
        product_cost_price=_money(cost),
        shipping=_money(shipping),
        description=product.name,
        is_customer_supplied=False,
        product=product,
    )


def _direct_service_item(*, service_id: int, quantity: int, selling: str, cost: str = "0.00", duration: timedelta | None = None) -> SimpleNamespace:
    service = _service(service_id=service_id)
    return SimpleNamespace(
        id=None,
        product_id=None,
        service_id=service_id,
        kit_id=None,
        quantity=quantity,
        item_benefit_type="normal",
        service_selling_price=_money(selling),
        service_cost_price=_money(cost),
        service_shipping=_money("0.00"),
        duration=duration if duration is not None else timedelta(hours=1),
        description=service.name,
        service=service,
    )


def _kit_product_override(*, product_id: int, quantity: int, selling: str, shipping: str = "0.00", cost: str = "0.00") -> SimpleNamespace:
    product = _product(product_id=product_id)
    return SimpleNamespace(
        product=product,
        product_id=product_id,
        quantity=quantity,
        shipping=_money(shipping),
        product_selling_price=_money(selling),
        product_cost_price=_money(cost),
    )


def _kit_service_override(*, service_id: int, quantity: int, selling: str, cost: str = "0.00", duration: timedelta | None = None) -> SimpleNamespace:
    service = _service(service_id=service_id)
    return SimpleNamespace(
        service=service,
        service_id=service_id,
        quantity=quantity,
        service_selling_price=_money(selling),
        service_cost_price=_money(cost),
        duration=duration if duration is not None else timedelta(hours=1),
    )


def _kit_item(*, kit_id: int, quantity: int, products: tuple[SimpleNamespace, ...] = (), services: tuple[SimpleNamespace, ...] = ()) -> SimpleNamespace:
    return SimpleNamespace(
        id=None,
        product_id=None,
        service_id=None,
        kit_id=kit_id,
        quantity=quantity,
        item_benefit_type="normal",
        _iter_frozen_kit_product_overrides=lambda: iter(products),
        _iter_frozen_kit_service_overrides=lambda: iter(services),
    )


def _snapshot(*items: SimpleNamespace):
    return build_pricing_snapshot(items=items, slider=0, discount_value=zero_money(), discount_percentage=Decimal("0"))


class PricingSnapshotKitWinnerTests(SimpleTestCase):
    def test_kit_vs_kit_keeps_higher_quantity_instead_of_summing(self) -> None:
        snapshot = _snapshot(
            _kit_item(
                kit_id=1,
                quantity=1,
                products=(_kit_product_override(product_id=10, quantity=2, selling="10.00"),),
            ),
            _kit_item(
                kit_id=2,
                quantity=1,
                products=(_kit_product_override(product_id=10, quantity=3, selling="10.00"),),
            ),
        )

        line = snapshot.product_lines[0]
        self.assertEqual(line.quantity, 3)
        self.assertEqual(line.raw_total, _money("30.00"))

    def test_kit_vs_kit_equal_quantity_keeps_higher_total(self) -> None:
        snapshot = _snapshot(
            _kit_item(
                kit_id=1,
                quantity=1,
                products=(_kit_product_override(product_id=10, quantity=2, selling="10.00"),),
            ),
            _kit_item(
                kit_id=2,
                quantity=1,
                products=(_kit_product_override(product_id=10, quantity=2, selling="15.00"),),
            ),
        )

        line = snapshot.product_lines[0]
        self.assertEqual(line.quantity, 2)
        self.assertEqual(line.raw_total, _money("30.00"))

    def test_kit_vs_kit_full_tie_keeps_first_kit(self) -> None:
        snapshot = _snapshot(
            _kit_item(
                kit_id=1,
                quantity=1,
                products=(_kit_product_override(product_id=10, quantity=2, selling="10.00", cost="4.00"),),
            ),
            _kit_item(
                kit_id=2,
                quantity=1,
                products=(_kit_product_override(product_id=10, quantity=2, selling="10.00", cost="9.00"),),
            ),
        )

        line = snapshot.product_lines[0]
        self.assertEqual(line.quantity, 2)
        self.assertEqual(line.raw_total, _money("20.00"))
        self.assertEqual(line.cost_total, _money("8.00"))

    def test_kit_vs_kit_winner_is_compared_to_avulso_without_summing_kits(self) -> None:
        snapshot = _snapshot(
            _kit_item(
                kit_id=1,
                quantity=1,
                products=(_kit_product_override(product_id=10, quantity=2, selling="10.00"),),
            ),
            _kit_item(
                kit_id=2,
                quantity=1,
                products=(_kit_product_override(product_id=10, quantity=3, selling="10.00"),),
            ),
            _direct_product_item(product_id=10, quantity=4, selling="10.00"),
        )

        line = snapshot.product_lines[0]
        self.assertEqual(line.quantity, 4)
        self.assertEqual(line.raw_total, _money("40.00"))
        self.assertTrue(line.has_direct_source)
        self.assertTrue(line.has_kit_source)

    def test_kit_vs_avulso_still_keeps_higher_quantity(self) -> None:
        snapshot = _snapshot(
            _kit_item(
                kit_id=1,
                quantity=1,
                products=(_kit_product_override(product_id=10, quantity=5, selling="10.00"),),
            ),
            _direct_product_item(product_id=10, quantity=4, selling="10.00"),
        )

        line = snapshot.product_lines[0]
        self.assertEqual(line.quantity, 5)
        self.assertEqual(line.raw_total, _money("50.00"))

    def test_kit_vs_kit_services_keeps_higher_duration_instead_of_summing(self) -> None:
        snapshot = _snapshot(
            _kit_item(
                kit_id=1,
                quantity=1,
                services=(_kit_service_override(service_id=20, quantity=5, selling="10.00", duration=timedelta(minutes=15)),),
            ),
            _kit_item(
                kit_id=2,
                quantity=1,
                services=(_kit_service_override(service_id=20, quantity=1, selling="10.00", duration=timedelta(hours=3)),),
            ),
        )

        line = snapshot.service_lines[0]
        self.assertEqual(line.quantity, 1)
        self.assertEqual(line.duration, timedelta(hours=3))
        self.assertEqual(line.raw_total, _money("10.00"))

    def test_kit_vs_kit_services_equal_duration_keeps_higher_total(self) -> None:
        snapshot = _snapshot(
            _kit_item(
                kit_id=1,
                quantity=1,
                services=(_kit_service_override(service_id=20, quantity=2, selling="10.00", duration=timedelta(hours=1)),),
            ),
            _kit_item(
                kit_id=2,
                quantity=1,
                services=(_kit_service_override(service_id=20, quantity=1, selling="25.00", duration=timedelta(hours=2)),),
            ),
        )

        line = snapshot.service_lines[0]
        self.assertEqual(line.quantity, 1)
        self.assertEqual(line.duration, timedelta(hours=2))
        self.assertEqual(line.raw_total, _money("25.00"))

    def test_kit_vs_kit_service_winner_is_compared_to_avulso_without_summing_kits(self) -> None:
        snapshot = _snapshot(
            _kit_item(
                kit_id=1,
                quantity=1,
                services=(_kit_service_override(service_id=20, quantity=2, selling="10.00", duration=timedelta(hours=1)),),
            ),
            _kit_item(
                kit_id=2,
                quantity=1,
                services=(_kit_service_override(service_id=20, quantity=1, selling="10.00", duration=timedelta(hours=3)),),
            ),
            _direct_service_item(service_id=20, quantity=1, selling="10.00", duration=timedelta(hours=4)),
        )

        line = snapshot.service_lines[0]
        self.assertEqual(line.quantity, 1)
        self.assertEqual(line.duration, timedelta(hours=4))
        self.assertEqual(line.raw_total, _money("10.00"))
        self.assertTrue(line.has_direct_source)
        self.assertTrue(line.has_kit_source)

    def test_kit_vs_avulso_service_keeps_higher_duration(self) -> None:
        snapshot = _snapshot(
            _kit_item(
                kit_id=1,
                quantity=1,
                services=(_kit_service_override(service_id=20, quantity=5, selling="10.00", duration=timedelta(minutes=15)),),
            ),
            _direct_service_item(service_id=20, quantity=1, selling="10.00", duration=timedelta(hours=2)),
        )

        line = snapshot.service_lines[0]
        self.assertEqual(line.quantity, 1)
        self.assertEqual(line.duration, timedelta(hours=2))
        self.assertEqual(line.raw_total, _money("10.00"))

    def test_avulso_vs_avulso_services_keeps_higher_duration(self) -> None:
        snapshot = _snapshot(
            _direct_service_item(service_id=20, quantity=4, selling="10.00", duration=timedelta(minutes=15)),
            _direct_service_item(service_id=20, quantity=1, selling="10.00", duration=timedelta(hours=2)),
        )

        line = snapshot.service_lines[0]
        self.assertEqual(line.quantity, 1)
        self.assertEqual(line.duration, timedelta(hours=2))
        self.assertEqual(line.raw_total, _money("10.00"))

    def test_avulso_vs_avulso_services_equal_duration_keeps_higher_total(self) -> None:
        snapshot = _snapshot(
            _direct_service_item(service_id=20, quantity=2, selling="10.00", duration=timedelta(hours=1)),
            _direct_service_item(service_id=20, quantity=1, selling="25.00", duration=timedelta(hours=2)),
        )

        line = snapshot.service_lines[0]
        self.assertEqual(line.quantity, 1)
        self.assertEqual(line.duration, timedelta(hours=2))
        self.assertEqual(line.raw_total, _money("25.00"))
