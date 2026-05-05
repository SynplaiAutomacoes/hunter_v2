from __future__ import annotations

import json
from datetime import date, timedelta

from django.db import connection
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Account, User
from apps.budget.models import Budget
from apps.collaborators.models import WorkshopMember
from apps.customer.models import Customer, Vehicle
from apps.iam.utils import get_or_create_director_role
from apps.messaging.models import CustomerMessageGroup, CustomerMessageGroupMembership, MessageTemplate
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


def create_customer_record(*, workshop: Workshop, suffix: int, is_active: bool = True, birth_date: date | None = None) -> Customer:
    return Customer.objects.create(
        workshop=workshop,
        name=f"Cliente {suffix}",
        cpf_or_cnpj=str(10_000_000_000 + suffix),
        birth_date=birth_date,
        phone=f"+551199000{suffix:04d}",
        email=f"cliente{suffix}@example.com",
        is_active=is_active,
    )


def create_vehicle_record(*, workshop: Workshop, customer: Customer, suffix: int) -> Vehicle:
    return Vehicle.objects.create(
        workshop=workshop,
        customer=customer,
        plate=f"MSG1A{suffix:02d}",
        brand="Toyota",
        model=f"Modelo {suffix}",
        year_fabrication="2023",
        year_model="2024",
        color="Prata",
    )


def create_workorder_for_customer(*, workshop: Workshop, customer: Customer, suffix: int, created_at) -> WorkOrder:
    vehicle = create_vehicle_record(workshop=workshop, customer=customer, suffix=suffix)
    budget = create_budget(workshop=workshop, customer=customer, vehicle=vehicle)
    workorder = WorkOrder.objects.create(workshop=workshop, budget=budget, status=WorkOrderStatus.APPROVED)
    WorkOrder.objects.filter(pk=workorder.pk).update(criado_em=created_at)
    workorder.refresh_from_db()
    return workorder


def create_customer_message_group(*, workshop: Workshop, suffix: int = 1, is_active: bool = True) -> CustomerMessageGroup:
    return CustomerMessageGroup.objects.create(
        workshop=workshop,
        name=f"Grupo {suffix}",
        description=f"Descricao do grupo {suffix}",
        message="Ola %%nome%%, temos uma nova campanha para voce.",
        is_active=is_active,
    )


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
        self.assertIn("Veículo Entregue", rendered)

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


class CustomerMessageGroupCustomerPickerViewTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=30)
        self.client.force_login(self.user)

        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

    def test_customer_picker_hides_inactive_by_default(self) -> None:
        active_customer = create_customer_record(workshop=self.workshop, suffix=31, is_active=True, birth_date=date(1991, 5, 20))
        inactive_customer = create_customer_record(workshop=self.workshop, suffix=32, is_active=False, birth_date=date(1988, 7, 10))

        create_workorder_for_customer(workshop=self.workshop, customer=active_customer, suffix=31, created_at=timezone.now() - timedelta(days=20))
        create_workorder_for_customer(workshop=self.workshop, customer=inactive_customer, suffix=32, created_at=timezone.now() - timedelta(days=200))

        response = self.client.get(reverse("messaging:customer_message_group_customer_picker"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, active_customer.name)
        self.assertNotContains(response, inactive_customer.name)

    def test_customer_picker_filters_by_birth_date_and_latest_os_range(self) -> None:
        birthday_customer = create_customer_record(workshop=self.workshop, suffix=33, birth_date=date(1990, 5, 20))
        recent_customer = create_customer_record(workshop=self.workshop, suffix=34, birth_date=date(1992, 10, 10))
        older_customer = create_customer_record(workshop=self.workshop, suffix=35, birth_date=date(1985, 1, 15))

        create_workorder_for_customer(workshop=self.workshop, customer=birthday_customer, suffix=33, created_at=timezone.now() - timedelta(days=15))
        create_workorder_for_customer(workshop=self.workshop, customer=recent_customer, suffix=34, created_at=timezone.now() - timedelta(days=45))
        create_workorder_for_customer(workshop=self.workshop, customer=older_customer, suffix=35, created_at=timezone.now() - timedelta(days=240))

        birthday_response = self.client.get(
            reverse("messaging:customer_message_group_customer_picker"),
            {
                "is_active": "all",
                "birth_date_start": "1990-05-01",
                "birth_date_end": "1990-05-31",
            },
        )

        self.assertContains(birthday_response, birthday_customer.name)
        self.assertNotContains(birthday_response, recent_customer.name)
        self.assertNotContains(birthday_response, older_customer.name)

        latest_os_response = self.client.get(
            reverse("messaging:customer_message_group_customer_picker"),
            {
                "is_active": "all",
                "latest_os_start": (timezone.now().date() - timedelta(days=60)).isoformat(),
                "latest_os_end": timezone.now().date().isoformat(),
            },
        )

        self.assertContains(latest_os_response, birthday_customer.name)
        self.assertContains(latest_os_response, recent_customer.name)
        self.assertNotContains(latest_os_response, older_customer.name)

    def test_customer_picker_highlights_customers_already_in_group(self) -> None:
        selected_customer = create_customer_record(workshop=self.workshop, suffix=36, is_active=True)
        create_customer_record(workshop=self.workshop, suffix=37, is_active=True)

        response = self.client.get(
            reverse("messaging:customer_message_group_customer_picker"),
            {
                "selected_customers": [str(selected_customer.pk)],
            },
        )

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertEqual(html.count("bg-success/10 hover:bg-success/20 transition-colors"), 1)
        self.assertEqual(html.count("border-success/30 bg-success/10"), 1)


class CustomerMessageGroupViewTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=40)
        self.client.force_login(self.user)

        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

        self.customer_one = create_customer_record(workshop=self.workshop, suffix=41, birth_date=date(1990, 4, 5))
        self.customer_two = create_customer_record(workshop=self.workshop, suffix=42, birth_date=date(1987, 9, 18))

    def test_create_form_only_shows_active_message_templates(self) -> None:
        active_template = create_message_template(workshop=self.workshop, suffix=43, is_active=True)
        inactive_template = create_message_template(workshop=self.workshop, suffix=44, is_active=False)

        response = self.client.get(reverse("messaging:customer_message_group_create"))

        self.assertEqual(response.status_code, 200)
        form_queryset = response.context["form"].fields["message_template"].queryset
        payload_ids = {template_payload["id"] for template_payload in response.context["message_templates_payload"]}

        self.assertIn(active_template, form_queryset)
        self.assertNotIn(inactive_template, form_queryset)
        self.assertIn(active_template.pk, payload_ids)
        self.assertNotIn(inactive_template.pk, payload_ids)

    def test_create_group_rejects_inactive_message_template(self) -> None:
        inactive_template = create_message_template(workshop=self.workshop, suffix=45, is_active=False)

        response = self.client.post(
            reverse("messaging:customer_message_group_create"),
            {
                "name": "Grupo com mensagem inativa",
                "description": "Nao deve aceitar mensagens inativas.",
                "message_template": str(inactive_template.pk),
                "message": "Ola %%nome%%, mensagem teste.",
                "is_active": "on",
                "selected_customers": [str(self.customer_one.pk)],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("message_template", response.context["form"].errors)
        self.assertFalse(CustomerMessageGroup.objects.filter(workshop=self.workshop, name="Grupo com mensagem inativa").exists())

    def test_create_group_with_selected_customers_and_message_template(self) -> None:
        template = create_message_template(workshop=self.workshop, suffix=41, is_active=True)

        response = self.client.post(
            reverse("messaging:customer_message_group_create"),
            {
                "name": "Clientes aniversario",
                "description": "Clientes para mensagens promocionais de aniversario.",
                "message_template": str(template.pk),
                "message": "Ola %%nome%%, preparamos um desconto especial para seu aniversario.",
                "is_active": "on",
                "selected_customers": [str(self.customer_one.pk), str(self.customer_two.pk)],
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers.get("Location"), reverse("messaging:customer_message_group_list"))

        group = CustomerMessageGroup.objects.get(workshop=self.workshop, name="Clientes aniversario")
        self.assertEqual(group.description, "Clientes para mensagens promocionais de aniversario.")
        self.assertEqual(group.message_template, template)
        self.assertEqual(group.message, "Ola %%nome%%, preparamos um desconto especial para seu aniversario.")
        self.assertTrue(group.is_active)
        self.assertSetEqual(
            set(CustomerMessageGroupMembership.objects.filter(group=group).values_list("customer_id", flat=True)),
            {self.customer_one.pk, self.customer_two.pk},
        )

    def test_update_form_keeps_current_inactive_message_template_visible(self) -> None:
        active_template = create_message_template(workshop=self.workshop, suffix=46, is_active=True)
        current_inactive_template = create_message_template(workshop=self.workshop, suffix=47, is_active=False)
        other_inactive_template = create_message_template(workshop=self.workshop, suffix=48, is_active=False)
        group = create_customer_message_group(workshop=self.workshop, suffix=49, is_active=True)
        group.message_template = current_inactive_template
        group.save(update_fields=["message_template"])

        response = self.client.get(reverse("messaging:customer_message_group_update", kwargs={"pk": group.pk}))

        self.assertEqual(response.status_code, 200)
        form_queryset = response.context["form"].fields["message_template"].queryset
        payload_ids = {template_payload["id"] for template_payload in response.context["message_templates_payload"]}

        self.assertIn(active_template, form_queryset)
        self.assertIn(current_inactive_template, form_queryset)
        self.assertNotIn(other_inactive_template, form_queryset)
        self.assertIn(active_template.pk, payload_ids)
        self.assertIn(current_inactive_template.pk, payload_ids)
        self.assertNotIn(other_inactive_template.pk, payload_ids)

    def test_update_group_can_keep_current_inactive_message_template(self) -> None:
        current_inactive_template = create_message_template(workshop=self.workshop, suffix=50, is_active=False)
        group = create_customer_message_group(workshop=self.workshop, suffix=51, is_active=True)
        group.message_template = current_inactive_template
        group.save(update_fields=["message_template"])
        CustomerMessageGroupMembership.objects.create(group=group, customer=self.customer_one)

        response = self.client.post(
            reverse("messaging:customer_message_group_update", kwargs={"pk": group.pk}),
            {
                "name": group.name,
                "description": "Grupo ajustado com mensagem inativa existente.",
                "message_template": str(current_inactive_template.pk),
                "message": "Ola %%nome%%, mantivemos a mensagem cadastrada atual.",
                "is_active": "on",
                "selected_customers": [str(self.customer_one.pk)],
            },
        )

        self.assertEqual(response.status_code, 302)
        group.refresh_from_db()
        self.assertEqual(group.message_template, current_inactive_template)
        self.assertEqual(group.description, "Grupo ajustado com mensagem inativa existente.")
        self.assertEqual(group.message, "Ola %%nome%%, mantivemos a mensagem cadastrada atual.")
        self.assertTrue(group.is_active)

    def test_update_group_can_remove_customers_and_disable_it(self) -> None:
        group = create_customer_message_group(workshop=self.workshop, suffix=50, is_active=True)
        CustomerMessageGroupMembership.objects.create(group=group, customer=self.customer_one)
        CustomerMessageGroupMembership.objects.create(group=group, customer=self.customer_two)

        response = self.client.post(
            reverse("messaging:customer_message_group_update", kwargs={"pk": group.pk}),
            {
                "name": group.name,
                "description": "Grupo ajustado para uma nova campanha.",
                "message": "Ola %%nome%%, esta e a nova mensagem do grupo.",
                "selected_customers": [str(self.customer_two.pk)],
            },
        )

        self.assertEqual(response.status_code, 302)
        group.refresh_from_db()
        self.assertEqual(group.description, "Grupo ajustado para uma nova campanha.")
        self.assertEqual(group.message, "Ola %%nome%%, esta e a nova mensagem do grupo.")
        self.assertFalse(group.is_active)
        self.assertSetEqual(
            set(CustomerMessageGroupMembership.objects.filter(group=group).values_list("customer_id", flat=True)),
            {self.customer_two.pk},
        )

    def test_create_group_requires_at_least_one_customer(self) -> None:
        response = self.client.post(
            reverse("messaging:customer_message_group_create"),
            {
                "name": "Grupo vazio",
                "description": "Nao deve salvar sem clientes.",
                "message": "Mensagem teste",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Selecione pelo menos um cliente para o grupo.")
        self.assertFalse(CustomerMessageGroup.objects.filter(workshop=self.workshop, name="Grupo vazio").exists())

    def test_quick_create_message_template_returns_htmx_trigger_payload(self) -> None:
        response = self.client.post(
            reverse("messaging:message_template_quick_create"),
            {
                "name": "Mensagem rapida",
                "message": "Ola %%nome%%, esta mensagem foi criada no modal.",
                "is_active": "on",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        trigger_payload = json.loads(response.headers.get("HX-Trigger", "{}"))
        self.assertIn("message-template-added", trigger_payload)

        created_template = MessageTemplate.objects.get(workshop=self.workshop, name="Mensagem rapida")
        self.assertEqual(trigger_payload["message-template-added"]["id"], str(created_template.pk))
        self.assertEqual(trigger_payload["message-template-added"]["name"], "Mensagem rapida")
        self.assertEqual(trigger_payload["message-template-added"]["message"], "Ola %%nome%%, esta mensagem foi criada no modal.")
        self.assertTrue(trigger_payload["message-template-added"]["is_active"])

    def test_quick_create_inactive_message_template_returns_inactive_payload(self) -> None:
        response = self.client.post(
            reverse("messaging:message_template_quick_create"),
            {
                "name": "Mensagem inativa",
                "message": "Ola %%nome%%, esta mensagem foi criada como inativa.",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        trigger_payload = json.loads(response.headers.get("HX-Trigger", "{}"))
        self.assertIn("message-template-added", trigger_payload)

        created_template = MessageTemplate.objects.get(workshop=self.workshop, name="Mensagem inativa")
        self.assertFalse(created_template.is_active)
        self.assertFalse(trigger_payload["message-template-added"]["is_active"])
