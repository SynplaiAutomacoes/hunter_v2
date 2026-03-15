from __future__ import annotations

import re
from decimal import Decimal
from typing import Any, cast

from django.core.management import call_command
from django.test import TestCase

from djmoney.money import Money

from apps.catalog.models.kits import Kit
from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.checklist.models import Checklist, ChecklistItem
from apps.collaborators.models import WorkshopCollaborator
from apps.core.management.commands.seed_demo_data import (
    BANK_ACCOUNT_SPECS,
    CHECKLIST_BLUEPRINTS,
    COLLABORATOR_NAMES,
    FINANCIAL_MOVEMENT_SPECS,
    KIT_SPECS,
    NFE_TAX_CLASS_SPECS,
    NFSE_TAX_CLASS_SPECS,
    PF_CUSTOMERS,
    PJ_CUSTOMERS,
    PRODUCT_SPECS,
    QUESTION_SPECS,
    SERVICE_SPECS,
    SOURCE_SPECS,
    SUPPLIER_SPECS,
    WORKSHOP_ID,
)
from apps.customer.models import Customer
from apps.finance.models.bank_account import BankAccount
from apps.finance.models.finance import TaxClassNfe, TaxClassNfse, TaxClassPreset, TaxClassSyncState
from apps.finance.models.financial_movement import FinancialMovement
from apps.finance.services.tax_class_presets import get_default_tax_class_presets
from apps.quote.models.investigative_questions import InvestigativeQuestion
from apps.sources.models import Source
from apps.stock.models import StockProduct
from apps.suppliers.models import Supplier
from apps.workshops.models.monthly_costs import MonthlyCost
from apps.workshops.models.workshop_costs import WorkshopCost
from apps.workshops.models.workshops import Workshop
from apps.workshops.util.monthly_costs import DEFAULT_MONTHLY_COSTS


class SeedDemoDataCommandTests(TestCase):
    def setUp(self) -> None:
        self.workshop = Workshop.objects.create(
            pk=WORKSHOP_ID,
            name="Oficina Seed",
            cnpj="12.345.678/0001-90",
            phone="+5511999999999",
            address="Rua Seed, 100",
            uf="SP",
        )

    def test_seed_command_is_idempotent_and_populates_valid_ncm(self) -> None:
        call_command("seed_demo_data", seed=123)

        self.assertEqual(Product.objects.filter(workshop=self.workshop).count(), len(PRODUCT_SPECS))
        self.assertEqual(StockProduct.objects.filter(workshop=self.workshop).count(), len(PRODUCT_SPECS))
        self.assertEqual(Service.objects.filter(workshop=self.workshop).count(), len(SERVICE_SPECS))
        self.assertEqual(Kit.objects.filter(workshop=self.workshop).count(), len(KIT_SPECS))
        self.assertEqual(Supplier.objects.filter(workshop=self.workshop).count(), len(SUPPLIER_SPECS))
        self.assertEqual(Customer.objects.filter(workshop=self.workshop).count(), len(PF_CUSTOMERS) + len(PJ_CUSTOMERS))
        self.assertEqual(WorkshopCollaborator.objects.filter(workshop=self.workshop).count(), len(COLLABORATOR_NAMES))
        self.assertEqual(Checklist.objects.filter(workshop=self.workshop).count(), len(CHECKLIST_BLUEPRINTS))
        self.assertEqual(cast(Any, InvestigativeQuestion).objects.filter(workshop=self.workshop).count(), len(QUESTION_SPECS))
        self.assertEqual(MonthlyCost.objects.filter(workshop=self.workshop).count(), len(DEFAULT_MONTHLY_COSTS))
        self.assertEqual(WorkshopCost.objects.filter(workshop=self.workshop).count(), 6)
        self.assertEqual(Source.objects.filter(workshop=self.workshop).count(), len(SOURCE_SPECS))
        self.assertEqual(BankAccount.objects.filter(workshop=self.workshop).count(), len(BANK_ACCOUNT_SPECS))
        self.assertEqual(FinancialMovement.objects.filter(workshop=self.workshop).count(), len(FINANCIAL_MOVEMENT_SPECS))
        self.assertEqual(TaxClassPreset.objects.filter(workshop=self.workshop).count(), sum(len(items) for items in get_default_tax_class_presets().values()))
        self.assertEqual(TaxClassNfe.objects.filter(workshop=self.workshop).count(), len(NFE_TAX_CLASS_SPECS))
        self.assertEqual(TaxClassNfse.objects.filter(workshop=self.workshop).count(), len(NFSE_TAX_CLASS_SPECS))
        self.assertTrue(TaxClassSyncState.objects.filter(workshop=self.workshop, synced_once=True).exists())
        self.assertEqual(
            ChecklistItem.objects.filter(checklist__workshop=self.workshop).count(),
            sum(blueprint.item_count for blueprint in CHECKLIST_BLUEPRINTS),
        )

        first_counts = self._counts_snapshot()

        for product in Product.objects.filter(workshop=self.workshop).order_by("code"):
            normalized_ncm = re.sub(r"\D", "", product.ncm)
            self.assertEqual(len(normalized_ncm), 8, f"Produto {product.code} ficou sem NCM valido")

        self.assertTrue(
            FinancialMovement.objects.filter(
                workshop=self.workshop,
                direction=FinancialMovement.MovementDirection.CREDIT,
            ).exists()
        )
        self.assertTrue(
            FinancialMovement.objects.filter(
                workshop=self.workshop,
                direction=FinancialMovement.MovementDirection.DEBIT,
            ).exists()
        )

        movement = FinancialMovement.objects.filter(workshop=self.workshop).select_related("source", "payment_method", "budget_plan", "bank_account").first()
        assert movement is not None
        self.assertIsNotNone(movement.source)
        self.assertIsNotNone(movement.payment_method)
        self.assertIsNotNone(movement.budget_plan)

        tax_class_nfe = TaxClassNfe.objects.filter(workshop=self.workshop).prefetch_related("icms_scenarios", "ipi_scenarios", "pis_scenarios", "cofins_scenarios").first()
        assert tax_class_nfe is not None
        tax_class_nfe_any = cast(Any, tax_class_nfe)
        self.assertGreater(tax_class_nfe_any.icms_scenarios.count(), 0)
        self.assertGreater(tax_class_nfe_any.ipi_scenarios.count(), 0)
        self.assertGreater(tax_class_nfe_any.pis_scenarios.count(), 0)
        self.assertGreater(tax_class_nfe_any.cofins_scenarios.count(), 0)

        tax_class_nfse = TaxClassNfse.objects.filter(workshop=self.workshop).first()
        assert tax_class_nfse is not None
        self.assertTrue(tax_class_nfse.codigo_servico)

        call_command("seed_demo_data", seed=123)

        self.assertEqual(self._counts_snapshot(), first_counts)
        self.assertEqual(
            ChecklistItem.objects.filter(checklist__workshop=self.workshop).count(),
            sum(blueprint.item_count for blueprint in CHECKLIST_BLUEPRINTS),
        )

    def test_seed_command_preserves_existing_product_values_and_backfills_missing_fields(self) -> None:
        spec = PRODUCT_SPECS[0]
        group = CatalogGroup.objects.create(workshop=self.workshop, name=spec.group_name)
        product = Product.objects.create(
            workshop=self.workshop,
            code=spec.code,
            name="Produto manual",
            description="",
            unit=spec.unit,
            group=group,
            brand="Marca manual",
            model="",
            sku="",
            barcode="",
            location="",
            cost_price=Decimal("10.00"),
            selling_price=Decimal("20.00"),
            profit_margin=Decimal("0.500000"),
            ncm="99999999",
            cest="",
            application="",
            is_active=True,
        )

        call_command("seed_demo_data", seed=123)

        product.refresh_from_db()
        self.assertEqual(product.name, "Produto manual")
        self.assertEqual(product.brand, "Marca manual")
        self.assertEqual(product.cost_price, Money(10, "BRL"))
        self.assertEqual(product.selling_price, Money(20, "BRL"))
        self.assertEqual(product.ncm, "99999999")
        self.assertEqual(product.description, spec.description)
        self.assertEqual(product.model, spec.model)
        self.assertEqual(product.sku, f"SKU-{spec.code}")
        self.assertEqual(product.location, spec.location)
        self.assertEqual(product.application, spec.application)

    def _counts_snapshot(self) -> dict[str, int]:
        return {
            "products": Product.objects.filter(workshop=self.workshop).count(),
            "stock_products": StockProduct.objects.filter(workshop=self.workshop).count(),
            "services": Service.objects.filter(workshop=self.workshop).count(),
            "kits": Kit.objects.filter(workshop=self.workshop).count(),
            "suppliers": Supplier.objects.filter(workshop=self.workshop).count(),
            "customers": Customer.objects.filter(workshop=self.workshop).count(),
            "collaborators": WorkshopCollaborator.objects.filter(workshop=self.workshop).count(),
            "checklists": Checklist.objects.filter(workshop=self.workshop).count(),
            "checklist_items": ChecklistItem.objects.filter(checklist__workshop=self.workshop).count(),
            "questions": cast(Any, InvestigativeQuestion).objects.filter(workshop=self.workshop).count(),
            "monthly_costs": MonthlyCost.objects.filter(workshop=self.workshop).count(),
            "workshop_costs": WorkshopCost.objects.filter(workshop=self.workshop).count(),
            "sources": Source.objects.filter(workshop=self.workshop).count(),
            "bank_accounts": BankAccount.objects.filter(workshop=self.workshop).count(),
            "financial_movements": FinancialMovement.objects.filter(workshop=self.workshop).count(),
            "tax_class_presets": TaxClassPreset.objects.filter(workshop=self.workshop).count(),
            "tax_classes_nfe": TaxClassNfe.objects.filter(workshop=self.workshop).count(),
            "tax_classes_nfse": TaxClassNfse.objects.filter(workshop=self.workshop).count(),
            "tax_class_sync_state": TaxClassSyncState.objects.filter(workshop=self.workshop).count(),
        }
