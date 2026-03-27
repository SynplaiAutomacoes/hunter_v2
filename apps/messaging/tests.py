from __future__ import annotations

from datetime import date

from django.db import connection
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Account, User
from apps.budget.models import Budget
from apps.collaborators.models import WorkshopMember
from apps.customer.models import Customer, Vehicle
from apps.iam.utils import get_or_create_director_role
from apps.messaging.models import MessageTemplate
from apps.messaging.rendering import render_message_template
from apps.messaging.views import MessageTemplateListView
from apps.workorder.models import WorkOrder, WorkOrderStatus
from apps.workshops.models.workshops import Workshop


MESSAGE_TEST_DEFAULTS_PREPARED = False


def create_director_user_with_workshop(*, suffix: int = 1) -> tuple[User, Workshop]:
    user = User.objects.create_user(username=f"messaging-director{suffix}", password="123", cpf=f"87654321{suffix:03d}")
    account = Account.objects.create(name=f"Conta Messaging {suffix}", owner=user)
    user.account = account
    user.is_account_owner = True
    user.save(update_fields=["account", "is_account_owner"])

    workshop = Workshop.objects.create(
        account=account,
        name=f"Oficina Messaging {suffix}",
        cnpj=f"22.333.444/0001-{suffix:02d}",
        phone="+5511999999999",
        address="Rua Messaging, 123",
    )

    director_role = get_or_create_director_role(account=account, with_all_permissions=True)
    WorkshopMember.objects.create(user=user, workshop=workshop, role=director_role, is_active=True)
    return user, workshop


def create_message_template(*, workshop: Workshop, suffix: int = 1, is_active: bool = True) -> MessageTemplate:
    return MessageTemplate.objects.create(
        workshop=workshop,
        name=f"Mensagem {suffix}",
        message="Olá %%nome%%, seu orçamento %%orcamento_numero%% está disponível.",
        is_active=is_active,
    )


def create_budget(*, workshop: Workshop, customer: Customer, vehicle: Vehicle) -> Budget:
    global MESSAGE_TEST_DEFAULTS_PREPARED

    if not MESSAGE_TEST_DEFAULTS_PREPARED:
        with connection.cursor() as cursor:
            cursor.execute("ALTER TABLE budget_budget ALTER COLUMN discount_percentage SET DEFAULT 0")
        MESSAGE_TEST_DEFAULTS_PREPARED = True

    budget = Budget(
        workshop=workshop,
        customer=customer,
        vehicle=vehicle,
        entry_date=timezone.now().date(),
        current_km=54321,
        problem_description="Troca de óleo e revisão geral.",
        technical_diagnosis="Necessário revisar filtros.",
        notes="Cliente prefere atendimento pela manhã.",
    )
    budget.save()
    return budget


class MessageTemplateListViewFilterTests(TestCase):
    def test_message_template_list_hides_inactive_by_default_but_allows_explicit_filters(self) -> None:
        user, workshop = create_director_user_with_workshop(suffix=11)
        active_template = create_message_template(workshop=workshop, suffix=1, is_active=True)
        inactive_template = create_message_template(workshop=workshop, suffix=2, is_active=False)
        factory = RequestFactory()

        default_view = MessageTemplateListView()
        default_view.request = factory.get("/messaging/")
        default_view.request.user = user
        default_view.workshop = workshop
        default_queryset = default_view.get_queryset()

        inactive_view = MessageTemplateListView()
        inactive_view.request = factory.get("/messaging/", {"is_active": "0"})
        inactive_view.request.user = user
        inactive_view.workshop = workshop
        inactive_queryset = inactive_view.get_queryset()

        all_view = MessageTemplateListView()
        all_view.request = factory.get("/messaging/", {"is_active": "all"})
        all_view.request.user = user
        all_view.workshop = workshop
        all_queryset = all_view.get_queryset()

        self.assertIn(active_template, default_queryset)
        self.assertNotIn(inactive_template, default_queryset)
        self.assertNotIn(active_template, inactive_queryset)
        self.assertIn(inactive_template, inactive_queryset)
        self.assertIn(active_template, all_queryset)
        self.assertIn(inactive_template, all_queryset)


class MessageTemplateRenderingTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=12)
        self.customer = Customer.objects.create(
            workshop=self.workshop,
            name="Mariana Souza",
            cpf_or_cnpj="12345678901",
            rg="123456789",
            birth_date=date(1990, 5, 20),
            phone="+5511998887777",
            email="mariana@example.com",
        )
        self.vehicle = Vehicle.objects.create(
            workshop=self.workshop,
            customer=self.customer,
            plate="ABC1D23",
            brand="Toyota",
            model="Corolla",
            year_fabrication="2023",
            year_model="2024",
            color="Prata",
            fuel="Flex",
            km=65432,
            engine="2.0",
        )
        self.budget = create_budget(workshop=self.workshop, customer=self.customer, vehicle=self.vehicle)
        self.workorder = WorkOrder.objects.create(workshop=self.workshop, budget=self.budget, status=WorkOrderStatus.APPROVED, km_final=65500)

    def test_render_message_template_replaces_variables_from_all_supported_groups(self) -> None:
        rendered = render_message_template(
            "Olá %%nome%%, contato %%telefone%%, veículo %%modelo%% %%placa%%, ano %%ano%%, orçamento %%orcamento_numero%% (%%orcamento_status%%) e O.S. %%os_numero%% (%%os_status%%).",
            workorder=self.workorder,
        )

        self.assertIn("Mariana Souza", rendered)
        self.assertIn("(11) 99888-7777", rendered)
        self.assertIn("Corolla", rendered)
        self.assertIn("ABC1D23", rendered)
        self.assertIn("2024/2023", rendered)
        self.assertIn(str(self.budget.pk), rendered)
        self.assertIn("Em Aberto", rendered)
        self.assertIn(str(self.workorder.pk), rendered)
        self.assertIn("Aprovado", rendered)

    def test_render_message_template_preserves_budget_and_workorder_tokens_when_context_is_missing(self) -> None:
        rendered = render_message_template("Olá %%nome%%, orçamento %%orcamento_status%% e O.S. %%os_status%%.", customer=self.customer)

        self.assertEqual(rendered, "Olá Mariana Souza, orçamento %%orcamento_status%% e O.S. %%os_status%%.")


class MessageTemplateViewTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=13)
        self.client.force_login(self.user)

        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

    def test_create_message_template(self) -> None:
        response = self.client.post(
            reverse("messaging:message_template_create"),
            {
                "name": "Pós-serviço",
                "message": "Olá %%nome%%, sua O.S. %%os_numero%% está pronta.",
                "is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers.get("Location"), reverse("messaging:message_template_list"))

        template = MessageTemplate.objects.get(workshop=self.workshop, name="Pós-serviço")
        self.assertEqual(template.message, "Olá %%nome%%, sua O.S. %%os_numero%% está pronta.")
        self.assertTrue(template.is_active)

    def test_create_form_renders_sidebar_accordion_with_variable_groups(self) -> None:
        response = self.client.get(reverse("messaging:message_template_create"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Variáveis disponíveis")
        self.assertContains(response, "collapse collapse-arrow", html=False)
        self.assertContains(response, "Cliente")
        self.assertContains(response, "Veículo")
        self.assertContains(response, "Orçamento")
        self.assertContains(response, "O.S.")
        self.assertContains(response, "%%orcamento_status%%")
        self.assertContains(response, "%%os_status%%")

    def test_update_can_disable_message_template(self) -> None:
        template = create_message_template(workshop=self.workshop, suffix=20, is_active=True)

        response = self.client.post(
            reverse("messaging:message_template_update", kwargs={"pk": template.pk}),
            {
                "name": template.name,
                "message": "Mensagem atualizada para %%nome%%.",
            },
        )

        self.assertEqual(response.status_code, 302)
        template.refresh_from_db()
        self.assertEqual(template.message, "Mensagem atualizada para %%nome%%.")
        self.assertFalse(template.is_active)

    def test_delete_message_template_via_htmx(self) -> None:
        template = create_message_template(workshop=self.workshop, suffix=21, is_active=True)
        delete_url = reverse("messaging:message_template_delete", kwargs={"pk": template.pk})

        modal_response = self.client.get(delete_url, HTTP_HX_REQUEST="true")
        self.assertEqual(modal_response.status_code, 200)
        self.assertContains(modal_response, "Excluir mensagem WhatsApp")

        delete_response = self.client.post(delete_url, HTTP_HX_REQUEST="true")
        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(delete_response.headers.get("HX-Trigger"), "message-templates-table-refresh")
        self.assertFalse(MessageTemplate.objects.filter(pk=template.pk).exists())
