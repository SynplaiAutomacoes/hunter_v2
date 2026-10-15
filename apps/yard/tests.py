from __future__ import annotations

from datetime import date, datetime, time, timedelta

from django.test import TestCase
from django.utils import timezone

from apps.budget.models import Budget, BudgetImage, BudgetImageType, BudgetStatus
from apps.collaborators.models import WorkshopCollaborator
from apps.customer.models import Customer, Vehicle
from apps.yard.forms import YardColumnForm
from apps.yard.models import STATUS_ALL, YardColumn, YardColumnTarget, YardDateBase
from apps.yard.services import ensure_default_columns, get_board_data, period_range
from apps.workorder.models import WorkOrder, WorkOrderStatus
from apps.workshops.models.workshops import Workshop


def create_workshop(*, suffix: int) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina Pátio {suffix}",
        cnpj=f"77.888.999/0001-{(suffix % 100):02d}",
        phone="+5511999999999",
        address="Rua Pátio, 123",
    )


def create_collaborator(*, workshop: Workshop, name: str, suffix: int) -> WorkshopCollaborator:
    from datetime import date as date_class

    from djmoney.money import Money

    return WorkshopCollaborator.objects.create(
        workshop=workshop,
        name=name,
        cpf=f"{suffix:011d}"[-11:],
        birth_date=date_class(1990, 1, 1),
        salary=Money(2000, "BRL"),
        admission_date=date_class(2025, 1, 1),
        collaborator_type=WorkshopCollaborator.CollaboratorType.PRODUCTIVE,
    )


class YardPeriodRangeTests(TestCase):
    def test_monthly_returns_first_day_and_today(self) -> None:
        today = date(2026, 11, 14)
        self.assertEqual(period_range(date_base=YardDateBase.MONTHLY, today=today), (date(2026, 11, 1), today))

    def test_weekly_returns_monday_to_sunday(self) -> None:
        start, end = period_range(date_base=YardDateBase.WEEKLY, today=date(2026, 11, 14))
        self.assertEqual((start, end), (date(2026, 11, 9), date(2026, 11, 15)))

    def test_daily_returns_today(self) -> None:
        today = date(2026, 11, 14)
        self.assertEqual(period_range(date_base=YardDateBase.DAILY, today=today), (today, today))


class YardDefaultColumnsTests(TestCase):
    def test_first_access_seeds_four_default_columns(self) -> None:
        workshop = create_workshop(suffix=1)
        columns = ensure_default_columns(workshop=workshop)
        self.assertEqual(len(columns), 4)
        self.assertEqual(
            [(column.target, column.status, column.date_base) for column in columns],
            [
                (YardColumnTarget.BUDGET, STATUS_ALL, YardDateBase.MONTHLY),
                (YardColumnTarget.WORKORDER, STATUS_ALL, YardDateBase.MONTHLY),
                (YardColumnTarget.WORKORDER, WorkOrderStatus.APPROVED, YardDateBase.DAILY),
                (YardColumnTarget.BUDGET, BudgetStatus.REJECTED, YardDateBase.DAILY),
            ],
        )
        self.assertEqual([column.title for column in columns], ["Orçamentos do mês", "OS do mês", "Veículos Entregues do dia", "Reprovados do dia"])

    def test_second_access_does_not_duplicate(self) -> None:
        workshop = create_workshop(suffix=2)
        ensure_default_columns(workshop=workshop)
        ensure_default_columns(workshop=workshop)
        self.assertEqual(YardColumn.objects.filter(workshop=workshop).count(), 4)


class YardColumnFormTests(TestCase):
    def test_status_widget_renders_grouped_choices(self) -> None:
        form = YardColumnForm()
        rendered = str(form["status"])
        self.assertIn('value="all"', rendered)
        self.assertIn('value="waiting_delivery"', rendered)
        self.assertIn('value="waiting_approval"', rendered)

    def test_rejects_duplicate_target_status(self) -> None:
        workshop = create_workshop(suffix=3)
        YardColumn.objects.create(workshop=workshop, target=YardColumnTarget.BUDGET, status=STATUS_ALL, title="Orçamentos", color="#3b82f6", date_base=YardDateBase.MONTHLY)
        form = YardColumnForm(
            {"target": YardColumnTarget.BUDGET, "status": STATUS_ALL, "title": "Outra", "color": "#ef4444", "date_base": YardDateBase.MONTHLY}
        )
        form.instance.workshop = workshop
        self.assertFalse(form.is_valid())
        self.assertIn("status", form.errors)

    def test_rejects_status_of_other_target(self) -> None:
        workshop = create_workshop(suffix=4)
        form = YardColumnForm(
            {"target": YardColumnTarget.BUDGET, "status": WorkOrderStatus.WAITING_COLLABORATOR, "title": "Inválida", "color": "#1e40af", "date_base": YardDateBase.DAILY}
        )
        form.instance.workshop = workshop
        self.assertFalse(form.is_valid())
        self.assertIn("status", form.errors)


class YardBoardDataTests(TestCase):
    def _make_budget(self, *, workshop, status, entry_date, plate="ABC1234", suffix="1"):
        customer = Customer.objects.create(
            workshop=workshop,
            name="Anderson Silva Oliveira",
            cpf_or_cnpj=f"123456789{suffix}",
            email=f"a{suffix}@example.com",
        )
        vehicle = Vehicle.objects.create(
            workshop=workshop,
            customer=customer,
            plate=plate,
            brand="Jeep",
            model="Renegade",
            year_fabrication="2024",
            year_model="2024",
            color="Branco",
        )
        return Budget.objects.create(
            workshop=workshop,
            customer=customer,
            vehicle=vehicle,
            entry_date=entry_date,
            status=status,
            budget_type="sale",
        )

    def test_all_column_excludes_status_with_dedicated_column(self) -> None:
        workshop = create_workshop(suffix=5)
        today = timezone.localdate()
        rejected = self._make_budget(workshop=workshop, status=BudgetStatus.REJECTED, entry_date=today, plate="REJ0001", suffix="01")
        draft = self._make_budget(workshop=workshop, status=BudgetStatus.DRAFT, entry_date=today, plate="DRA0002", suffix="02")
        YardColumn.objects.create(workshop=workshop, target=YardColumnTarget.BUDGET, status=STATUS_ALL, title="Orçamentos do mês", color="#3b82f6", date_base=YardDateBase.MONTHLY, position=0)
        YardColumn.objects.create(workshop=workshop, target=YardColumnTarget.BUDGET, status=BudgetStatus.REJECTED, title="Reprovados do dia", color="#ef4444", date_base=YardDateBase.DAILY, position=1)

        board = get_board_data(workshop=workshop)
        all_column = next(entry for entry in board if entry["column"].status == STATUS_ALL)
        rejected_column = next(entry for entry in board if entry["column"].status == BudgetStatus.REJECTED)

        self.assertEqual([card["plate"] for card in all_column["cards"]], ["DRA0002"])
        self.assertEqual([card["plate"] for card in rejected_column["cards"]], ["REJ0001"])
        self.assertTrue(all_column["show_status"])
        self.assertFalse(rejected_column["show_status"])
        self.assertEqual(all_column["cards"][0]["status_label"], BudgetStatus.DRAFT.label)
        self.assertEqual(draft.public_number, all_column["cards"][0]["show_id"])
        self.assertEqual(rejected.public_number, rejected_column["cards"][0]["show_id"])

    def test_card_omits_photo_and_formats_expected_date(self) -> None:
        workshop = create_workshop(suffix=6)
        today = timezone.localdate()
        budget = self._make_budget(workshop=workshop, status=BudgetStatus.DRAFT, entry_date=today, plate="SEMFT01")
        budget.service_expected_completion_at = timezone.make_aware(timezone.datetime(2026, 11, 14, 19, 56))
        budget.save(update_fields=["service_expected_completion_at"])
        YardColumn.objects.create(workshop=workshop, target=YardColumnTarget.BUDGET, status=STATUS_ALL, title="Orçamentos do mês", color="#3b82f6", date_base=YardDateBase.MONTHLY, position=0)

        board = get_board_data(workshop=workshop)
        card = board[0]["cards"][0]
        self.assertIsNone(card["photo_url"])
        self.assertEqual(card["expected_label"], "Nov 14 - 19:56")
        self.assertEqual(card["responsibles"], ["—"])
        self.assertEqual(card["brand"], "Jeep")

    def test_card_includes_principal_photo(self) -> None:
        workshop = create_workshop(suffix=7)
        today = timezone.localdate()
        budget = self._make_budget(workshop=workshop, status=BudgetStatus.DRAFT, entry_date=today, plate="COMFT02")
        BudgetImage.objects.create(workshop=workshop, budget=budget, image_type=BudgetImageType.PRINCIPAL, content=b"fake", content_type="image/jpeg")
        YardColumn.objects.create(workshop=workshop, target=YardColumnTarget.BUDGET, status=STATUS_ALL, title="Orçamentos do mês", color="#3b82f6", date_base=YardDateBase.MONTHLY, position=0)

        board = get_board_data(workshop=workshop)
        card = board[0]["cards"][0]
        self.assertIsNotNone(card["photo_url"])
        self.assertIn("/budget/image-view/", card["photo_url"])

    def test_workorder_column_uses_delivered_date_for_approved(self) -> None:
        workshop = create_workshop(suffix=8)
        today = timezone.localdate()
        old_date = today - timedelta(days=10)
        budget = self._make_budget(workshop=workshop, status=BudgetStatus.APPROVED, entry_date=old_date, plate="ENTRGO3")
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget, status=WorkOrderStatus.APPROVED, budget_type="sale")
        workorder.delivered_at = timezone.make_aware(datetime.combine(today, time.min))
        workorder.save(update_fields=["delivered_at"])
        YardColumn.objects.create(workshop=workshop, target=YardColumnTarget.WORKORDER, status=WorkOrderStatus.APPROVED, title="Veículos Entregues do dia", color="#14b8a6", date_base=YardDateBase.DAILY, position=0)

        board = get_board_data(workshop=workshop)
        self.assertEqual(len(board[0]["cards"]), 1)
        self.assertEqual(board[0]["cards"][0]["plate"], "ENTRGO3")

    def test_budget_card_shows_principal_collaborator(self) -> None:
        workshop = create_workshop(suffix=9)
        today = timezone.localdate()
        customer = Customer.objects.create(workshop=workshop, name="Cliente X", cpf_or_cnpj="12345678909", email="x@example.com")
        vehicle = Vehicle.objects.create(workshop=workshop, customer=customer, plate="PRIN01", brand="Jeep", model="Renegade", year_fabrication="2024", year_model="2024", color="Branco")
        principal = create_collaborator(workshop=workshop, name="Principal da Silva", suffix=901)
        additional = create_collaborator(workshop=workshop, name="Adicional de Souza", suffix=902)
        budget = Budget.objects.create(workshop=workshop, customer=customer, vehicle=vehicle, entry_date=today, status=BudgetStatus.DRAFT, budget_type="sale", collaborator=principal)
        budget.collaborators.add(additional)
        YardColumn.objects.create(workshop=workshop, target=YardColumnTarget.BUDGET, status=STATUS_ALL, title="Orçamentos do mês", color="#3b82f6", date_base=YardDateBase.MONTHLY, position=0)

        board = get_board_data(workshop=workshop)
        self.assertEqual(board[0]["cards"][0]["responsibles"], ["Principal da Silva"])

    def test_workorder_card_lists_all_mechanics(self) -> None:
        workshop = create_workshop(suffix=10)
        today = timezone.localdate()
        budget = self._make_budget(workshop=workshop, status=BudgetStatus.APPROVED, entry_date=today, plate="MECA03")
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget, status=WorkOrderStatus.DRAFT, budget_type="sale")
        mechanic_one = create_collaborator(workshop=workshop, name="Mecânico Um", suffix=903)
        mechanic_two = create_collaborator(workshop=workshop, name="Mecânico Dois", suffix=904)
        mechanic_three = create_collaborator(workshop=workshop, name="Mecânico Três", suffix=905)
        workorder.collaborators.add(mechanic_one, mechanic_two, mechanic_three)
        YardColumn.objects.create(workshop=workshop, target=YardColumnTarget.WORKORDER, status=STATUS_ALL, title="OS do mês", color="#22c55e", date_base=YardDateBase.MONTHLY, position=0)

        board = get_board_data(workshop=workshop)
        self.assertEqual(board[0]["cards"][0]["responsibles"], ["Mecânico Um", "Mecânico Dois", "Mecânico Três"])
