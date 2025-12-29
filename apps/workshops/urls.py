from django.urls import path

from .views import WorkshopCreateView, WorkshopDeleteView, WorkshopListView, WorkshopUpdateView

app_name = "workshops"

urlpatterns = [
    path("", WorkshopListView.as_view(), name="list"),
    path("create/", WorkshopCreateView.as_view(), name="create"),
    path("<int:pk>/edit/", WorkshopUpdateView.as_view(), name="update"),
    path("<int:pk>/delete/", WorkshopDeleteView.as_view(), name="delete"),
]
