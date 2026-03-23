from __future__ import annotations

from django.test import RequestFactory, TestCase

from apps.customer.models import Customer
from apps.customer.views import CustomerListView
from apps.workshops.models.workshops import Workshop


def create_workshop(*, suffix: int = 1) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina Customer {suffix}",
        cnpj=f"31.222.333/0001-{suffix:02d}",
        phone="+5511999999999",
        address="Rua Teste, 123",
    )


def create_customer(*, workshop: Workshop, suffix: int, is_active: bool) -> Customer:
    return Customer.objects.create(
        workshop=workshop,
        name=f"Cliente {suffix}",
        cpf_or_cnpj=f"1234567890{suffix:02d}",
        email=f"cliente{suffix}@example.com",
        is_active=is_active,
    )


class CustomerListViewFilterTests(TestCase):
    def test_customer_list_hides_inactive_by_default_but_allows_explicit_filters(self) -> None:
        workshop = create_workshop(suffix=1)
        active_customer = create_customer(workshop=workshop, suffix=1, is_active=True)
        inactive_customer = create_customer(workshop=workshop, suffix=2, is_active=False)
        factory = RequestFactory()

        default_view = CustomerListView()
        default_view.request = factory.get("/customer/")
        default_view.workshop = workshop
        default_queryset = default_view.get_queryset()

        inactive_view = CustomerListView()
        inactive_view.request = factory.get("/customer/", {"is_active": "0"})
        inactive_view.workshop = workshop
        inactive_queryset = inactive_view.get_queryset()

        all_view = CustomerListView()
        all_view.request = factory.get("/customer/", {"is_active": "all"})
        all_view.workshop = workshop
        all_queryset = all_view.get_queryset()

        self.assertIn(active_customer, default_queryset)
        self.assertNotIn(inactive_customer, default_queryset)
        self.assertNotIn(active_customer, inactive_queryset)
        self.assertIn(inactive_customer, inactive_queryset)
        self.assertIn(active_customer, all_queryset)
        self.assertIn(inactive_customer, all_queryset)
