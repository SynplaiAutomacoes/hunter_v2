from __future__ import annotations

from datetime import date

from django.test import RequestFactory, TestCase
from djmoney.money import Money

from apps.collaborators.models import WorkshopCollaborator
from apps.collaborators.views import WorkshopCollaboratorListView
from apps.workshops.models.workshops import Workshop


def create_workshop(*, suffix: int = 1) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina Collaborator {suffix}",
        cnpj=f"32.222.333/0001-{suffix:02d}",
        phone="+5511999999999",
        address="Rua Teste, 123",
    )


def create_collaborator(*, workshop: Workshop, suffix: int, is_active: bool) -> WorkshopCollaborator:
    return WorkshopCollaborator.objects.create(
        workshop=workshop,
        name=f"Colaborador {suffix}",
        cpf=f"123456789{suffix:02d}",
        birth_date=date(1990, 1, 1),
        salary=Money("0.00", "BRL"),
        admission_date=date(2024, 1, 1),
        collaborator_type=WorkshopCollaborator.CollaboratorType.PRODUCTIVE,
        is_active=is_active,
    )


class CollaboratorListViewFilterTests(TestCase):
    def test_collaborator_list_hides_inactive_by_default_but_allows_explicit_filters(self) -> None:
        workshop = create_workshop(suffix=1)
        active_collaborator = create_collaborator(workshop=workshop, suffix=1, is_active=True)
        inactive_collaborator = create_collaborator(workshop=workshop, suffix=2, is_active=False)
        factory = RequestFactory()

        default_view = WorkshopCollaboratorListView()
        default_view.request = factory.get("/collaborators/")
        default_view.workshop = workshop
        default_queryset = default_view.get_queryset()

        inactive_view = WorkshopCollaboratorListView()
        inactive_view.request = factory.get("/collaborators/", {"is_active": "0"})
        inactive_view.workshop = workshop
        inactive_queryset = inactive_view.get_queryset()

        all_view = WorkshopCollaboratorListView()
        all_view.request = factory.get("/collaborators/", {"is_active": "all"})
        all_view.workshop = workshop
        all_queryset = all_view.get_queryset()

        self.assertIn(active_collaborator, default_queryset)
        self.assertNotIn(inactive_collaborator, default_queryset)
        self.assertNotIn(active_collaborator, inactive_queryset)
        self.assertIn(inactive_collaborator, inactive_queryset)
        self.assertIn(active_collaborator, all_queryset)
        self.assertIn(inactive_collaborator, all_queryset)
