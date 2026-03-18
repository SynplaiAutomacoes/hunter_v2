from django.urls import path

from apps.scheduling import views

app_name = "scheduling"

urlpatterns = [
    path("", views.AppointmentCalendarView.as_view(), name="appointment_calendar"),
    path("events/", views.AppointmentEventsView.as_view(), name="appointment_events"),
    path("create/", views.AppointmentCreateView.as_view(), name="appointment_create"),
    path("<int:pk>/detail/", views.AppointmentDetailView.as_view(), name="appointment_detail"),
    path("<int:pk>/edit/", views.AppointmentUpdateView.as_view(), name="appointment_update"),
    path("<int:pk>/delete/", views.AppointmentDeleteView.as_view(), name="appointment_delete"),
    path("<int:pk>/move/", views.AppointmentMoveView.as_view(), name="appointment_move"),
    path("get-vehicles/", views.VehicleByCustomerListView.as_view(), name="get_vehicles"),
    path("get-budgets/", views.BudgetByVehicleListView.as_view(), name="get_budgets"),
    path("get-workorders/", views.WorkOrderByVehicleListView.as_view(), name="get_workorders"),
]
