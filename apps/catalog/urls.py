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
    ServiceNameSearchView,
)

from apps.catalog.views.products import (
    ProductListView,
    ProductCreateView,
    ProductUpdateView,
    ProductDeleteView,
    ProductSearchSelectView,
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
    path("services/search/", ServiceNameSearchView.as_view(), name="services_search"),
    path("products/", ProductListView.as_view(), name="product_list"),
    path("products/create/", ProductCreateView.as_view(), name="product_create"),
    path("products/<int:pk>/edit/", ProductUpdateView.as_view(), name="product_update"),
    path("products/<int:pk>/delete/", ProductDeleteView.as_view(), name="product_delete"),
    path("products/search/", ProductSearchSelectView.as_view(), name="product_search"),
]
