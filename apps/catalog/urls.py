from django.urls import path

from apps.catalog.views.groups import (
    CatalogGroupListView,
    CatalogGroupCreateView,
    CatalogGroupUpdateView,
    CatalogGroupDeleteView,
)

app_name = "catalog"

urlpatterns = [
    path("groups/", CatalogGroupListView.as_view(), name="group_list"),
    path("groups/create/", CatalogGroupCreateView.as_view(), name="group_create"),
    path("groups/<int:pk>/edit/", CatalogGroupUpdateView.as_view(), name="group_update"),
    path("groups/<int:pk>/delete/", CatalogGroupDeleteView.as_view(), name="group_delete"),
]
