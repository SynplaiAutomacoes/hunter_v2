from django.urls import path

from .views.workshops import (
    NavbarWorkshopSelectView,
    WorkshopEmissionHistoryView,
    WorkshopCreateView,
    WorkshopDeleteView,
    WorkshopListView,
    WorkshopWebmaniaSyncView,
    WorkshopUpdateView,
)

from apps.workshops.views.monthly_costs import (
    MonthlyCostListView,
    MonthlyCostCreateView,
    MonthlyCostUpdateView,
    MonthlyCostDeleteView,
)

from apps.workshops.views.workshop_costs import (
    WorkshopCostCalculateView,
    WorkshopCostListView,
    WorkshopCostCreateView,
    WorkshopCostUpdateView,
    WorkshopCostDeleteView,
    WorkshopCostCopyView,
)

app_name = "workshops"

urlpatterns = [
    path("", WorkshopListView.as_view(), name="list"),
    path("webmania/empresas/sync/", WorkshopWebmaniaSyncView.as_view(), name="webmania_company_sync"),
    path("historico-emissoes/", WorkshopEmissionHistoryView.as_view(), name="emission_history"),
    path("create/", WorkshopCreateView.as_view(), name="create"),
    path("<int:pk>/edit/", WorkshopUpdateView.as_view(), name="update"),
    path("<int:pk>/delete/", WorkshopDeleteView.as_view(), name="delete"),
    path("workshop-select/", NavbarWorkshopSelectView.as_view(), name="workshop_select"),
    path("monthly_costs/", MonthlyCostListView.as_view(), name="cost_list"),
    path("monthly_costs/create/", MonthlyCostCreateView.as_view(), name="cost_create"),
    path("monthly_costs/<int:pk>/edit/", MonthlyCostUpdateView.as_view(), name="cost_update"),
    path("monthly_costs/<int:pk>/delete/", MonthlyCostDeleteView.as_view(), name="cost_delete"),
    path("workshops_costs/", WorkshopCostListView.as_view(), name="workshop_cost_list"),
    path("workshops_costs/create/", WorkshopCostCreateView.as_view(), name="workshop_cost_create"),
    path("workshops_costs/<int:pk>/edit/", WorkshopCostUpdateView.as_view(), name="workshop_cost_update"),
    path("copy/<int:pk>/", WorkshopCostCopyView.as_view(), name="workshop_cost_copy"),
    path("workshops_costs/<int:pk>/delete/", WorkshopCostDeleteView.as_view(), name="workshop_cost_delete"),
    path("workshops_costs/calculate/", WorkshopCostCalculateView.as_view(), name="workshop_cost_calculate"),
]
