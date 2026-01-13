from django.urls import path

from .views.workshops import (
    NavbarWorkshopSelectView,
    WorkshopCreateView,
    WorkshopDeleteView,
    WorkshopListView,
    WorkshopUpdateView,
)

from apps.workshops.views.monthly_costs import (
    MonthlyCostListView,
    MonthlyCostCreateView,
    MonthlyCostUpdateView,
    MonthlyCostDeleteView,
)

app_name = "workshops"

urlpatterns = [
    path("", WorkshopListView.as_view(), name="list"),
    path("create/", WorkshopCreateView.as_view(), name="create"),
    path("<int:pk>/edit/", WorkshopUpdateView.as_view(), name="update"),
    path("<int:pk>/delete/", WorkshopDeleteView.as_view(), name="delete"),
    path("workshop-select/", NavbarWorkshopSelectView.as_view(), name="workshop_select"),
    path("costs/", MonthlyCostListView.as_view(), name="cost_list"),
    path("costs/create/", MonthlyCostCreateView.as_view(), name="cost_create"),
    path("costs/<int:pk>/edit/", MonthlyCostUpdateView.as_view(), name="cost_update"),
    path("costs/<int:pk>/delete/", MonthlyCostDeleteView.as_view(), name="cost_delete"),
]
