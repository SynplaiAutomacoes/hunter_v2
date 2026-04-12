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
    CalculateServiceCatalogPricesView,
)

from apps.catalog.views.products import (
    ProductListView,
    ProductCreateView,
    ProductUpdateView,
    ProductDeleteView,
    ProductSearchSelectView,
    StockFieldsUpdateView,
)

from apps.catalog.views.kits import (
    KitListView,
    KitCreateView,
    KitDeleteView,
    KitProductSearchView,
    KitServiceSearchView,
    KitUpdateView,
    KitsByProductHXView,
    KitServiceBulkPricingView,
    ProductQuickUpdateView,
    ServiceQuickUpdateView,
)

app_name = "catalog"

urlpatterns = [
    # Groups
    path("groups/", CatalogGroupListView.as_view(), name="group_list"),
    path("groups/create/", CatalogGroupCreateView.as_view(), name="group_create"),
    path("groups/<int:pk>/edit/", CatalogGroupUpdateView.as_view(), name="group_update"),
    path("groups/<int:pk>/delete/", CatalogGroupDeleteView.as_view(), name="group_delete"),
    # Services
    path("services/", ServiceListView.as_view(), name="services_list"),
    path("services/create/", ServiceCreateView.as_view(), name="services_create"),
    path("services/<int:pk>/edit/", ServiceUpdateView.as_view(), name="services_update"),
    path("services/<int:pk>/delete/", ServiceDeleteView.as_view(), name="services_delete"),
    path("services/search/", ServiceNameSearchView.as_view(), name="services_search"),
    path("edit_service_modal_form/<int:pk>/", ServiceQuickUpdateView.as_view(), name="edit_service_modal_form"),
    path("calculate-prices/", CalculateServiceCatalogPricesView.as_view(), name="calculate_service_prices"),
    # Products
    path("products/", ProductListView.as_view(), name="product_list"),
    path("products/create/", ProductCreateView.as_view(), name="product_create"),
    path("products/<int:pk>/edit/", ProductUpdateView.as_view(), name="product_update"),
    path("products/<int:pk>/delete/", ProductDeleteView.as_view(), name="product_delete"),
    path("products/search/", ProductSearchSelectView.as_view(), name="product_search"),
    path("update_stock_fields/", StockFieldsUpdateView.as_view(), name="update_stock_fields"),
    path("edit_product_modal_form/<int:pk>/", ProductQuickUpdateView.as_view(), name="edit_product_modal_form"),
    # Kits
    path("kits/", KitListView.as_view(), name="kits_list"),
    path("kits/create/", KitCreateView.as_view(), name="kits_create"),
    path("kits/<int:pk>/edit/", KitUpdateView.as_view(), name="kits_update"),
    path("kits/<int:pk>/delete/", KitDeleteView.as_view(), name="kits_delete"),
    path("kits/services/bulk-pricing/", KitServiceBulkPricingView.as_view(), name="kits_service_bulk_pricing"),
    path("kits/products/search/", KitProductSearchView.as_view(), name="kits_product_search"),
    path("kits/services/search/", KitServiceSearchView.as_view(), name="kits_service_search"),
    path("hx/kits-by-product/", KitsByProductHXView.as_view(), name="kits-by-product-hx"),
]
