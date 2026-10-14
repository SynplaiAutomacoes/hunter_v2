from __future__ import annotations

from decimal import Decimal

from django.test import TestCase
from djmoney.money import Money

from apps.catalog.importing import ProductImportAdapter
from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.products import Product
from apps.core.infrastructure.importing.persistence import persist_import_batch
from apps.core.infrastructure.importing.rollback import build_rollback_plan, execute_rollback
from apps.core.infrastructure.importing.schema import ImportBatchResult, ImportRowResult
from apps.core.infrastructure.models.data_import import DataImportBatch, DataImportBatchItem
from apps.workshops.models.workshops import Workshop


def create_workshop(*, suffix: int = 1) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina History {suffix}",
        cnpj=f"22.333.444/0001-{suffix:02d}",
        phone="+5511888888888",
        address="Rua Histórico, 10",
    )


class PersistImportBatchTests(TestCase):
    def test_persists_batch_and_dedupes_object_ids(self) -> None:
        workshop = create_workshop(suffix=1)
        result = ImportBatchResult()
        result.add(ImportRowResult(row_number=2, success=True, message="ok", created_id=10))
        result.add(ImportRowResult(row_number=3, success=True, message="ok", created_id=10))
        result.add(ImportRowResult(row_number=4, success=False, message="falhou"))

        batch = persist_import_batch(
            workshop=workshop,
            entity_key="kits",
            filename="kits.csv",
            mapping={"name": "Nome"},
            options={},
            user=None,
            batch_result=result,
        )

        self.assertEqual(batch.success_count, 2)
        self.assertEqual(batch.error_count, 1)
        self.assertEqual(batch.items.filter(success=True).count(), 1)
        self.assertEqual(batch.items.filter(success=False).count(), 1)
        self.assertEqual(batch.items.get(success=True).object_id, 10)


class RollbackImportBatchTests(TestCase):
    def test_full_rollback_deletes_products(self) -> None:
        workshop = create_workshop(suffix=2)
        CatalogGroup.objects.create(workshop=workshop, name="Geral")
        adapter = ProductImportAdapter()
        product_id = adapter.create_row(
            workshop,
            {
                "code": "RB-01",
                "name": "Produto Rollback",
                "unit": "UND",
                "group": "Geral",
                "cost_price": Decimal("1.00"),
                "selling_price": Decimal("2.00"),
            },
        )
        result = ImportBatchResult()
        result.add(ImportRowResult(row_number=2, success=True, message="ok", created_id=product_id))
        batch = persist_import_batch(
            workshop=workshop,
            entity_key="products",
            filename="produtos.csv",
            mapping={},
            options={},
            user=None,
            batch_result=result,
        )

        plan = build_rollback_plan(batch)
        self.assertEqual(plan.deletable_count, 1)
        self.assertEqual(plan.blocked_count, 0)

        rollback = execute_rollback(batch, force_partial=False)
        batch.refresh_from_db()
        self.assertEqual(rollback.deleted_count, 1)
        self.assertEqual(batch.status, DataImportBatch.Status.ROLLED_BACK)
        self.assertFalse(Product.objects.filter(pk=product_id).exists())

    def test_partial_rollback_keeps_used_product(self) -> None:
        workshop = create_workshop(suffix=3)
        group = CatalogGroup.objects.create(workshop=workshop, name="Geral")
        free = Product.objects.create(
            workshop=workshop,
            code="FREE-1",
            name="Livre",
            unit=Product.Unit.UND,
            group=group,
            cost_price=Money("1.00", "BRL"),
            selling_price=Money("2.00", "BRL"),
        )
        used = Product.objects.create(
            workshop=workshop,
            code="USED-1",
            name="Usado",
            unit=Product.Unit.UND,
            group=group,
            cost_price=Money("1.00", "BRL"),
            selling_price=Money("2.00", "BRL"),
        )
        # Simulate usage via kit membership (is_used checks product_kits).
        from apps.catalog.models.kits import Kit, KitProduct

        kit = Kit.objects.create(workshop=workshop, name="Kit Uso")
        KitProduct.objects.create(kit=kit, product=used, quantity=1)

        result = ImportBatchResult()
        result.add(ImportRowResult(row_number=2, success=True, message="ok", created_id=free.pk))
        result.add(ImportRowResult(row_number=3, success=True, message="ok", created_id=used.pk))
        batch = persist_import_batch(
            workshop=workshop,
            entity_key="products",
            filename="produtos.csv",
            mapping={},
            options={},
            user=None,
            batch_result=result,
        )

        plan = build_rollback_plan(batch)
        self.assertEqual(plan.deletable_count, 1)
        self.assertEqual(plan.blocked_count, 1)

        with self.assertRaises(ValueError):
            execute_rollback(batch, force_partial=False)

        rollback = execute_rollback(batch, force_partial=True)
        batch.refresh_from_db()
        self.assertEqual(rollback.deleted_count, 1)
        self.assertEqual(rollback.blocked_count, 1)
        self.assertEqual(batch.status, DataImportBatch.Status.PARTIALLY_ROLLED_BACK)
        self.assertFalse(Product.objects.filter(pk=free.pk).exists())
        self.assertTrue(Product.objects.filter(pk=used.pk).exists())
        blocked_item = batch.items.get(object_id=used.pk)
        self.assertEqual(blocked_item.rollback_status, DataImportBatchItem.RollbackStatus.BLOCKED)

    def test_import_stock_adjustment_does_not_block_rollback(self) -> None:
        workshop = create_workshop(suffix=5)
        CatalogGroup.objects.create(workshop=workshop, name="Geral")
        adapter = ProductImportAdapter()
        product_id = adapter.create_row(
            workshop,
            {
                "code": "STK-01",
                "name": "Com Estoque",
                "unit": "UND",
                "group": "Geral",
                "cost_price": Decimal("1.00"),
                "selling_price": Decimal("2.00"),
                "stock_quantity": Decimal("8"),
            },
            options={"include_stock": True},
        )
        product = Product.objects.get(pk=product_id)
        self.assertTrue(product.is_used)  # movimento de ajuste existe
        self.assertTrue(product.stock_products.movements.filter(is_stock_adjustment=True).exists())

        result = ImportBatchResult()
        result.add(ImportRowResult(row_number=2, success=True, message="ok", created_id=product_id))
        batch = persist_import_batch(
            workshop=workshop,
            entity_key="products",
            filename="estoque.csv",
            mapping={},
            options={"include_stock": True},
            user=None,
            batch_result=result,
        )
        plan = build_rollback_plan(batch)
        self.assertEqual(plan.deletable_count, 1)
        self.assertEqual(plan.blocked_count, 0)
        rollback = execute_rollback(batch, force_partial=False)
        self.assertEqual(rollback.deleted_count, 1)
        self.assertFalse(Product.objects.filter(pk=product_id).exists())

    def test_already_rolled_back_cannot_run_again(self) -> None:
        workshop = create_workshop(suffix=4)
        batch = DataImportBatch.objects.create(
            workshop=workshop,
            entity_key="products",
            status=DataImportBatch.Status.ROLLED_BACK,
        )
        with self.assertRaises(ValueError):
            execute_rollback(batch, force_partial=True)
