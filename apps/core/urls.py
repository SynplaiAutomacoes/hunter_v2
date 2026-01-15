from django.urls import path
from . import views

app_name = "core"

urlpatterns = [
    path("cep-lookup/", views.cep_lookup, name="cep_lookup"),
]