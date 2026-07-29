from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import Account
from apps.customer.forms import CustomerForm
from apps.customer.models import Customer
from apps.customer.services.messaging_consent import disable_workshop_customer_messaging
from apps.customer.views import CustomerDisableAllMessagingView, CustomerListView, CustomerUpdateView
from apps.messaging.models import ScheduledOutboundMessage
from apps.workshops.models.workshops import Workshop

User = get_user_model()


def create_workshop(*, suffix: int = 1) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina Consent Cliente {suffix}",
        cnpj=f"41.222.333/0001-{suffix:02d}",
        phone="+5511999999999",
        address="Rua Teste, 123",
    )


def build_customer_post_data(customer: Customer, *, accepts_messages: bool) -> dict[str, str]:
    data = {
        "customer_type": customer.customer_type,
        "cpf_or_cnpj": customer.cpf_or_cnpj,
        "name": customer.name,
        "email": customer.email,
        "phone": str(customer.phone or ""),
        "is_active": "on",
        "cep": "01001-000",
        "logradouro": "Praca da Se",
        "numero": "1",
        "bairro": "Se",
        "cidade": "Sao Paulo",
        "estado": "SP",
        "vehicles-TOTAL_FORMS": "0",
        "vehicles-INITIAL_FORMS": "0",
        "vehicles-MIN_NUM_FORMS": "0",
        "vehicles-MAX_NUM_FORMS": "1000",
    }
    if accepts_messages:
        data["accepts_messages"] = "on"
    return data


class CustomerMessagingToggleTests(TestCase):
    def setUp(self) -> None:
        self.workshop = create_workshop(suffix=1)
        self.customer = Customer.objects.create(
            workshop=self.workshop,
            name="Cliente Toggle",
            cpf_or_cnpj="52998224725",
            email="toggle@example.com",
            phone="+5511988887777",
            accepts_messages=True,
        )

    def _post_update(self, *, accepts_messages: bool):
        request = RequestFactory().post(
            f"/customer/{self.customer.pk}/update/",
            data=build_customer_post_data(self.customer, accepts_messages=accepts_messages),
        )
        view = CustomerUpdateView()
        view.setup(request, pk=self.customer.pk)
        view.workshop = self.workshop
        view.object = self.customer
        form = CustomerForm(request.POST, instance=self.customer, workshop=self.workshop)
        self.assertTrue(form.is_valid(), form.errors)
        return view.form_valid(form)

    @override_settings(ENVIRONMENT="development")
    def test_form_creates_customer_without_messaging_consent_by_default_outside_prod(self) -> None:
        form = CustomerForm(workshop=self.workshop)
        self.assertIn("accepts_messages", form.fields)
        self.assertFalse(form.initial.get("accepts_messages", False))
        self.assertFalse(Customer(workshop=self.workshop).accepts_messages)

    @override_settings(ENVIRONMENT="production")
    def test_form_creates_customer_with_messaging_consent_by_default_in_production(self) -> None:
        self.assertTrue(Customer(workshop=self.workshop).accepts_messages)

    def test_turning_toggle_off_cancels_pending_outbound_messages(self) -> None:
        pending = ScheduledOutboundMessage.objects.create(
            workshop=self.workshop,
            customer=self.customer,
            phone="5511988887777",
            message="Lembrete",
            run_at=timezone.now() + timedelta(days=1),
            status=ScheduledOutboundMessage.Status.PENDING,
            source=ScheduledOutboundMessage.Source.APPOINTMENT_ALERT,
        )

        response = self._post_update(accepts_messages=False)

        self.assertEqual(response.status_code, 302)
        self.customer.refresh_from_db()
        pending.refresh_from_db()
        self.assertFalse(self.customer.accepts_messages)
        self.assertEqual(pending.status, ScheduledOutboundMessage.Status.CANCELLED)

    def test_keeping_toggle_on_preserves_pending_outbound_messages(self) -> None:
        pending = ScheduledOutboundMessage.objects.create(
            workshop=self.workshop,
            customer=self.customer,
            phone="5511988887777",
            message="Lembrete",
            run_at=timezone.now() + timedelta(days=1),
            status=ScheduledOutboundMessage.Status.PENDING,
            source=ScheduledOutboundMessage.Source.APPOINTMENT_ALERT,
        )

        response = self._post_update(accepts_messages=True)

        self.assertEqual(response.status_code, 302)
        self.customer.refresh_from_db()
        pending.refresh_from_db()
        self.assertTrue(self.customer.accepts_messages)
        self.assertEqual(pending.status, ScheduledOutboundMessage.Status.PENDING)


class CustomerDisableAllMessagingTests(TestCase):
    def setUp(self) -> None:
        self.workshop = create_workshop(suffix=3)
        self.other_workshop = create_workshop(suffix=4)
        self.opted_in = Customer.objects.create(
            workshop=self.workshop,
            name="Recebe",
            cpf_or_cnpj="39053344705",
            email="recebe@example.com",
            accepts_messages=True,
        )
        self.opted_out = Customer.objects.create(
            workshop=self.workshop,
            name="Nao recebe",
            cpf_or_cnpj="12345678909",
            email="naorecebe@example.com",
            accepts_messages=False,
        )
        self.other_customer = Customer.objects.create(
            workshop=self.other_workshop,
            name="Outra oficina",
            cpf_or_cnpj="11144477735",
            email="outra@example.com",
            accepts_messages=True,
        )

    def test_disable_workshop_customer_messaging_only_touches_active_workshop(self) -> None:
        pending = ScheduledOutboundMessage.objects.create(
            workshop=self.workshop,
            customer=self.opted_in,
            phone="5511988887777",
            message="Lembrete",
            run_at=timezone.now() + timedelta(days=1),
            status=ScheduledOutboundMessage.Status.PENDING,
            source=ScheduledOutboundMessage.Source.APPOINTMENT_ALERT,
        )

        result = disable_workshop_customer_messaging(workshop=self.workshop)

        self.opted_in.refresh_from_db()
        self.opted_out.refresh_from_db()
        self.other_customer.refresh_from_db()
        pending.refresh_from_db()

        self.assertEqual(result["customers_updated"], 1)
        self.assertEqual(result["outbound_cancelled"], 1)
        self.assertFalse(self.opted_in.accepts_messages)
        self.assertFalse(self.opted_out.accepts_messages)
        self.assertTrue(self.other_customer.accepts_messages)
        self.assertEqual(pending.status, ScheduledOutboundMessage.Status.CANCELLED)

    @override_settings(ENVIRONMENT="production")
    def test_disable_all_messaging_view_forbidden_in_production(self) -> None:
        account = Account.objects.create(name="Conta Disable")
        user = User.objects.create_user(
            username="owner_disable",
            password="senha123",
            cpf="52998224725",
            account=account,
            is_account_owner=True,
        )
        self.workshop.account = account
        self.workshop.save(update_fields=["account"])

        request = RequestFactory().post("/customer/disable-all-messaging/")
        request.user = user
        request.session = {"active_workshop_id": self.workshop.pk}

        view = CustomerDisableAllMessagingView()
        view.setup(request)
        view.workshop = self.workshop

        with self.assertRaises(PermissionDenied):
            view.post(request)


class CustomerListMessagingFilterTests(TestCase):
    def test_list_filter_separates_customers_by_messaging_consent(self) -> None:
        workshop = create_workshop(suffix=2)
        opted_in = Customer.objects.create(
            workshop=workshop,
            name="Recebe",
            cpf_or_cnpj="39053344705",
            email="recebe@example.com",
            accepts_messages=True,
        )
        opted_out = Customer.objects.create(
            workshop=workshop,
            name="Nao recebe",
            cpf_or_cnpj="12345678909",
            email="naorecebe@example.com",
            accepts_messages=False,
        )
        factory = RequestFactory()

        opted_in_view = CustomerListView()
        opted_in_view.request = factory.get("/customer/", {"accepts_messages": "1"})
        opted_in_view.workshop = workshop

        opted_out_view = CustomerListView()
        opted_out_view.request = factory.get("/customer/", {"accepts_messages": "0"})
        opted_out_view.workshop = workshop

        self.assertIn(opted_in, opted_in_view.get_queryset())
        self.assertNotIn(opted_out, opted_in_view.get_queryset())
        self.assertIn(opted_out, opted_out_view.get_queryset())
        self.assertNotIn(opted_in, opted_out_view.get_queryset())
