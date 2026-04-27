from django.urls import path
from . import views

app_name = "core"

urlpatterns = [
    path("cep-lookup/", views.CEPLookupView.as_view(), name="cep_lookup"),
    path("navbar-favorites/toggle/", views.FavoritePageToggleView.as_view(), name="favorite_page_toggle"),
    path("navbar-favorites/reorder/", views.FavoritePageReorderView.as_view(), name="favorite_page_reorder"),
    path("", views.DashboardView.as_view(), name="dashboard"),
]
