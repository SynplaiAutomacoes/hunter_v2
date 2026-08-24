from __future__ import annotations

from types import SimpleNamespace

from django.test import SimpleTestCase
from django.urls import reverse

from apps.workorder.models import WorkOrderStatus
from apps.workorder.util import WORKORDER_DETAIL_STEPS, build_workorder_collaborators_next_url, resolve_workorder_detail_navigation


class WorkOrderDetailNavigationTests(SimpleTestCase):
    def test_defaults_to_first_step(self) -> None:
        navigation = resolve_workorder_detail_navigation(request=SimpleNamespace(GET={}))

        self.assertEqual(navigation.current_step, 1)
        self.assertFalse(navigation.payments_open)
        self.assertFalse(navigation.history_open)
        self.assertEqual(navigation.max_reached_step, 4)
        self.assertEqual(navigation.continue_label, "Iniciar")

    def test_draft_locks_later_steps(self) -> None:
        workorder = SimpleNamespace(current_step=1, status=WorkOrderStatus.DRAFT, pk=None)
        navigation = resolve_workorder_detail_navigation(
            request=SimpleNamespace(GET={"step": "4"}),
            workorder=workorder,
        )

        self.assertEqual(navigation.current_step, 1)
        self.assertEqual(navigation.max_reached_step, 1)
        self.assertEqual(workorder.status, WorkOrderStatus.DRAFT)

    def test_start_sets_waiting_collaborator(self) -> None:
        workorder = SimpleNamespace(current_step=1, status=WorkOrderStatus.DRAFT, pk=None)
        navigation = resolve_workorder_detail_navigation(
            request=SimpleNamespace(GET={"step": "2"}),
            workorder=workorder,
        )

        self.assertEqual(navigation.current_step, 2)
        self.assertEqual(workorder.status, WorkOrderStatus.WAITING_COLLABORATOR)
        self.assertEqual(workorder.current_step, 2)
        self.assertEqual(navigation.next_step, 4)

    def test_payment_step_does_not_unlock_delivery(self) -> None:
        workorder = SimpleNamespace(current_step=2, status=WorkOrderStatus.WAITING_COLLABORATOR, pk=None)
        navigation = resolve_workorder_detail_navigation(
            request=SimpleNamespace(GET={"step": "3"}),
            workorder=workorder,
        )

        self.assertEqual(navigation.current_step, 3)
        self.assertTrue(navigation.payments_open)
        self.assertEqual(workorder.status, WorkOrderStatus.WAITING_COLLABORATOR)
        self.assertEqual(workorder.current_step, 2)

    def test_collaborator_step_unlocks_delivery(self) -> None:
        workorder = SimpleNamespace(current_step=2, status=WorkOrderStatus.WAITING_COLLABORATOR, pk=None)
        navigation = resolve_workorder_detail_navigation(
            request=SimpleNamespace(GET={"step": "4"}),
            workorder=workorder,
        )

        self.assertEqual(navigation.current_step, 4)
        self.assertEqual(workorder.status, WorkOrderStatus.WAITING_DELIVERY)
        self.assertEqual(workorder.current_step, 4)

    def test_step_titles_match_os_flow(self) -> None:
        titles = [str(step["title"]) for step in WORKORDER_DETAIL_STEPS]
        self.assertEqual(titles, ["Resumo", "Colaboradores e comissões", "Pagamento", "Dados de entrega"])

    def test_collaborators_next_url_keeps_step_query(self) -> None:
        url = build_workorder_collaborators_next_url(workorder_pk=15, raw_next="?step=4")
        self.assertEqual(url, f"{reverse('workorder:workorder_detail', kwargs={'pk': 15})}?step=4")
