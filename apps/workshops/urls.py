from django.urls import path

from .views import WorkshopCreateView

app_name = "workshops"

urlpatterns = [
    path("create/", WorkshopCreateView.as_view(), name="create"),
]
