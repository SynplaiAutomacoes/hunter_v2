from django.urls import path

from .views import (
    UpdateNavbarWorkshopSelectView,
    WorkshopEmployeeCreateView,
    WorkshopEmployeeDeleteView,
    WorkshopEmployeeListView,
    WorkshopEmployeeUpdateView,
    WorkshopCreateView,
    WorkshopDeleteView,
    WorkshopListView,
    WorkshopUpdateView,
)

app_name = "workshops"

urlpatterns = [
    path("", WorkshopListView.as_view(), name="list"),
    path("create/", WorkshopCreateView.as_view(), name="create"),
    path("<int:pk>/edit/", WorkshopUpdateView.as_view(), name="update"),
    path("<int:pk>/delete/", WorkshopDeleteView.as_view(), name="delete"),
    path("workshop-select/", UpdateNavbarWorkshopSelectView.as_view(), name="workshop_select"),
    path("employees/", WorkshopEmployeeListView.as_view(), name="employee_list"),
    path("employees/create/", WorkshopEmployeeCreateView.as_view(), name="employee_create"),
    path("employees/<int:pk>/edit/", WorkshopEmployeeUpdateView.as_view(), name="employee_update"),
    path("employees/<int:pk>/delete/", WorkshopEmployeeDeleteView.as_view(), name="employee_delete"),
]
