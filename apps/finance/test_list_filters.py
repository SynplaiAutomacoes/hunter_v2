from __future__ import annotations

from django.test import RequestFactory, TestCase

from apps.finance.models.bank_account import BankAccount
from apps.finance.models.finance import TaxClassPreset, TaxClassPresetKind
from apps.finance.models.financial_group import FinancialGroup
from apps.finance.models.payment_method import PaymentMethod
from apps.finance.views.bank_account import BankAccountListView
from apps.finance.views.financial_group import FinancialGroupListView
from apps.finance.views.payment_method import PaymentMethodListView
from apps.finance.views.tax_class import TaxClassPresetListView
from apps.workshops.models.workshops import Workshop


def create_workshop(*, suffix: int = 1) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina Finance {suffix}",
        cnpj=f"34.222.333/0001-{suffix:02d}",
        phone="+5511999999999",
        address="Rua Teste, 123",
    )


class FinanceListViewFilterTests(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.workshop = create_workshop(suffix=1)

    def test_payment_method_list_hides_inactive_by_default_but_allows_explicit_filters(self) -> None:
        active_payment_method = PaymentMethod.objects.create(workshop=self.workshop, description="Pix", is_active=True)
        inactive_payment_method = PaymentMethod.objects.create(workshop=self.workshop, description="Cartao", is_active=False)

        default_view = PaymentMethodListView()
        default_view.request = self.factory.get("/finance/payment-methods/")
        default_view.workshop = self.workshop
        default_queryset = default_view.get_queryset()

        inactive_view = PaymentMethodListView()
        inactive_view.request = self.factory.get("/finance/payment-methods/", {"is_active": "0"})
        inactive_view.workshop = self.workshop
        inactive_queryset = inactive_view.get_queryset()

        all_view = PaymentMethodListView()
        all_view.request = self.factory.get("/finance/payment-methods/", {"is_active": "all"})
        all_view.workshop = self.workshop
        all_queryset = all_view.get_queryset()

        self.assertIn(active_payment_method, default_queryset)
        self.assertNotIn(inactive_payment_method, default_queryset)
        self.assertNotIn(active_payment_method, inactive_queryset)
        self.assertIn(inactive_payment_method, inactive_queryset)
        self.assertIn(active_payment_method, all_queryset)
        self.assertIn(inactive_payment_method, all_queryset)

    def test_bank_account_list_hides_inactive_by_default_but_allows_explicit_filters(self) -> None:
        active_account = BankAccount.objects.create(workshop=self.workshop, bank_code="001", bank_name="Banco A", agency="0001", account_number="12345-6", is_active=True)
        inactive_account = BankAccount.objects.create(workshop=self.workshop, bank_code="002", bank_name="Banco B", agency="0001", account_number="65432-1", is_active=False)

        default_view = BankAccountListView()
        default_view.request = self.factory.get("/finance/bank-account/")
        default_view.workshop = self.workshop
        default_queryset = default_view.get_queryset()

        inactive_view = BankAccountListView()
        inactive_view.request = self.factory.get("/finance/bank-account/", {"is_active": "0"})
        inactive_view.workshop = self.workshop
        inactive_queryset = inactive_view.get_queryset()

        all_view = BankAccountListView()
        all_view.request = self.factory.get("/finance/bank-account/", {"is_active": "all"})
        all_view.workshop = self.workshop
        all_queryset = all_view.get_queryset()

        self.assertIn(active_account, default_queryset)
        self.assertNotIn(inactive_account, default_queryset)
        self.assertNotIn(active_account, inactive_queryset)
        self.assertIn(inactive_account, inactive_queryset)
        self.assertIn(active_account, all_queryset)
        self.assertIn(inactive_account, all_queryset)

    def test_financial_group_list_hides_inactive_by_default_but_allows_explicit_filters(self) -> None:
        active_group = FinancialGroup.objects.create(workshop=self.workshop, name="Receitas", is_active=True)
        inactive_group = FinancialGroup.objects.create(workshop=self.workshop, name="Despesas", is_active=False)

        default_view = FinancialGroupListView()
        default_view.request = self.factory.get("/finance/financial-groups/")
        default_view.workshop = self.workshop
        default_queryset = default_view.get_queryset()

        inactive_view = FinancialGroupListView()
        inactive_view.request = self.factory.get("/finance/financial-groups/", {"is_active": "0"})
        inactive_view.workshop = self.workshop
        inactive_queryset = inactive_view.get_queryset()

        all_view = FinancialGroupListView()
        all_view.request = self.factory.get("/finance/financial-groups/", {"is_active": "all"})
        all_view.workshop = self.workshop
        all_queryset = all_view.get_queryset()

        self.assertIn(active_group, default_queryset)
        self.assertNotIn(inactive_group, default_queryset)
        self.assertNotIn(active_group, inactive_queryset)
        self.assertIn(inactive_group, inactive_queryset)
        self.assertIn(active_group, all_queryset)
        self.assertIn(inactive_group, all_queryset)

    def test_tax_class_preset_list_hides_inactive_by_default_but_allows_explicit_filters(self) -> None:
        active_preset = TaxClassPreset.objects.create(workshop=self.workshop, kind=TaxClassPresetKind.NFE, name="Preset Ativo", is_active=True, payload={"descricao": "Ativo"})
        inactive_preset = TaxClassPreset.objects.create(workshop=self.workshop, kind=TaxClassPresetKind.NFE, name="Preset Inativo", is_active=False, payload={"descricao": "Inativo"})

        default_view = TaxClassPresetListView()
        default_view.request = self.factory.get("/finance/classe-imposto/presets/", {"tab": "nfe"})
        default_view.workshop = self.workshop
        default_queryset = default_view._get_queryset_by_tab(tab=TaxClassPresetKind.NFE)

        inactive_view = TaxClassPresetListView()
        inactive_view.request = self.factory.get("/finance/classe-imposto/presets/", {"tab": "nfe", "is_active": "0"})
        inactive_view.workshop = self.workshop
        inactive_queryset = inactive_view._get_queryset_by_tab(tab=TaxClassPresetKind.NFE)

        all_view = TaxClassPresetListView()
        all_view.request = self.factory.get("/finance/classe-imposto/presets/", {"tab": "nfe", "is_active": "all"})
        all_view.workshop = self.workshop
        all_queryset = all_view._get_queryset_by_tab(tab=TaxClassPresetKind.NFE)

        self.assertIn(active_preset, default_queryset)
        self.assertNotIn(inactive_preset, default_queryset)
        self.assertNotIn(active_preset, inactive_queryset)
        self.assertIn(inactive_preset, inactive_queryset)
        self.assertIn(active_preset, all_queryset)
        self.assertIn(inactive_preset, all_queryset)
