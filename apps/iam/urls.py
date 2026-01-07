from django.urls import path

from apps.iam.views import WorkshopRoleCreateView, WorkshopRoleDeleteView, WorkshopRoleListView, WorkshopRoleUpdateView

app_name = "iam"

urlpatterns = [
    path("", WorkshopRoleListView.as_view(), name="role_list"),
    path("create/", WorkshopRoleCreateView.as_view(), name="role_create"),
    path("<int:pk>/edit/", WorkshopRoleUpdateView.as_view(), name="role_update"),
    path("<int:pk>/delete/", WorkshopRoleDeleteView.as_view(), name="role_delete"),
]
