from django.urls import path

from apps.catalog.views.groups import (
    CatalogGroupListView,
    CatalogGroupCreateView,
    CatalogGroupUpdateView,
    CatalogGroupDeleteView,
)

from apps.catalog.views.services import (
    ServiceListView,
    ServiceCreateView,
    ServiceUpdateView,
    ServiceDeleteView,
)

app_name = "catalog"

urlpatterns = [
    path("groups/", CatalogGroupListView.as_view(), name="group_list"),
    path("groups/create/", CatalogGroupCreateView.as_view(), name="group_create"),
    path("groups/<int:pk>/edit/", CatalogGroupUpdateView.as_view(), name="group_update"),
    path("groups/<int:pk>/delete/", CatalogGroupDeleteView.as_view(), name="group_delete"),
    path("services/", ServiceListView.as_view(), name="services_list"),
    path("services/create/", ServiceCreateView.as_view(), name="services_create"),
    path("services/<int:pk>/edit/", ServiceUpdateView.as_view(), name="services_update"),
    path("services/<int:pk>/delete/", ServiceDeleteView.as_view(), name="services_delete"),
]
