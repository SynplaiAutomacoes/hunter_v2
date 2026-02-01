from django.urls import path
from . import views

app_name = "core"

urlpatterns = [
    path("cep-lookup/", views.CEPLookupView.as_view(), name="cep_lookup"),
]