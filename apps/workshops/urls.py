from django.urls import path

from .views.workshops import (
    NavbarWorkshopSelectView,
    PublicWorkshopLogoView,
    WorkshopEmissionHistoryView,
    WorkshopCreateView,
    WorkshopDeleteView,
    WorkshopListView,
    WorkshopLogoView,
    WorkshopWebmaniaSyncView,
    WorkshopUpdateView,
)

from .views.whatsapp_connection import (
    WhatsAppConnectView,
    WhatsAppDisconnectView,
    WhatsAppPhoneAutosaveView,
    WhatsAppQrcodeRefreshView,
    WhatsAppStatusView,
)

from apps.workshops.views.monthly_costs import (
    MonthlyCostListView,
    MonthlyCostCreateView,
    MonthlyCostUpdateView,
    MonthlyCostDeleteView,
)
from apps.workshops.views.oil_types import (
    OilTypeCreateView,
    OilTypeDeleteView,
    OilTypeListView,
    OilTypeUpdateView,
)

from apps.workshops.views.workshop_costs import (
    WorkshopCostCalculateView,
    WorkshopCostHolidaysView,
    WorkshopCostListView,
    WorkshopCostCreateView,
    WorkshopCostUpdateView,
    WorkshopCostDeleteView,
    WorkshopCostCopyView,
    WorkshopCostSelectionModalView,
)

app_name = "workshops"

urlpatterns = [
    # Workshop
    path("", WorkshopListView.as_view(), name="list"),
    path("create/", WorkshopCreateView.as_view(), name="create"),
    path("<int:pk>/edit/", WorkshopUpdateView.as_view(), name="update"),
    path("<int:pk>/logo/", WorkshopLogoView.as_view(), name="logo"),
    path("logo/public/<str:token>/", PublicWorkshopLogoView.as_view(), name="logo_public"),
    path("<int:pk>/delete/", WorkshopDeleteView.as_view(), name="delete"),
    path("workshop-select/", NavbarWorkshopSelectView.as_view(), name="workshop_select"),
    # Monthly Costs
    path("monthly_costs/", MonthlyCostListView.as_view(), name="cost_list"),
    path("monthly_costs/create/", MonthlyCostCreateView.as_view(), name="cost_create"),
    path("monthly_costs/<int:pk>/edit/", MonthlyCostUpdateView.as_view(), name="cost_update"),
    path("monthly_costs/<int:pk>/delete/", MonthlyCostDeleteView.as_view(), name="cost_delete"),
    # Oil types
    path("oil_types/", OilTypeListView.as_view(), name="oil_type_list"),
    path("oil_types/create/", OilTypeCreateView.as_view(), name="oil_type_create"),
    path("oil_types/<int:pk>/edit/", OilTypeUpdateView.as_view(), name="oil_type_update"),
    path("oil_types/<int:pk>/delete/", OilTypeDeleteView.as_view(), name="oil_type_delete"),
    # Workshop Costs
    path("workshops_costs/", WorkshopCostListView.as_view(), name="workshop_cost_list"),
    path("workshops_costs/create/", WorkshopCostCreateView.as_view(), name="workshop_cost_create"),
    path("workshops_costs/<int:pk>/edit/", WorkshopCostUpdateView.as_view(), name="workshop_cost_update"),
    path("copy/<int:pk>/", WorkshopCostCopyView.as_view(), name="workshop_cost_copy"),
    path("workshops_costs/<int:pk>/delete/", WorkshopCostDeleteView.as_view(), name="workshop_cost_delete"),
    path("workshops_costs/calculate/", WorkshopCostCalculateView.as_view(), name="workshop_cost_calculate"),
    path("workshops_costs/holidays/", WorkshopCostHolidaysView.as_view(), name="workshop_cost_holidays"),
    path("workshops_costs/copy-selection/", WorkshopCostSelectionModalView.as_view(), name="workshop_cost_copy_selection"),
    #
    path("webmania/empresas/sync/", WorkshopWebmaniaSyncView.as_view(), name="webmania_company_sync"),
    path("historico-emissoes/", WorkshopEmissionHistoryView.as_view(), name="emission_history"),
    # WhatsApp
    path("<int:pk>/whatsapp/connect/", WhatsAppConnectView.as_view(), name="whatsapp_connect"),
    path("<int:pk>/whatsapp/qrcode/", WhatsAppQrcodeRefreshView.as_view(), name="whatsapp_qrcode_refresh"),
    path("<int:pk>/whatsapp/status/", WhatsAppStatusView.as_view(), name="whatsapp_status"),
    path("<int:pk>/whatsapp/disconnect/", WhatsAppDisconnectView.as_view(), name="whatsapp_disconnect"),
    path("<int:pk>/whatsapp-phone/", WhatsAppPhoneAutosaveView.as_view(), name="autosave_whatsapp_phone"),
]
