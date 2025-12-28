from django.urls import path

from .views import WorkshopCreateView, WorkshopListView

app_name = "workshops"

urlpatterns = [
    path("", WorkshopListView.as_view(), name="list"),
    path("create/", WorkshopCreateView.as_view(), name="create"),
]
