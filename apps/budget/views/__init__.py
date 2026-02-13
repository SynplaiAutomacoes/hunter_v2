from .customer_vehicle_views import CustomerDetailView, VehicleDetailView, VehicleListView
from .item_views import AddItemToBudgetView, AddItemsBatchToBudgetView, BudgetImageView, BudgetItemCalculateView, BudgetItemUpdateView, BudgetStep3CollaboratorFieldView, BudgetSummaryView, ItemSelectionModalView, RemoveBudgetItemView, RemoveItemFromBudgetView
from .kit_views import BudgetKitEditView
from .local_item_views import CalculateLocalServiceView, CreateLocalItemView, QuickCreateProductView, RegisterLocalItemView
from .pdf_views import visualizar_pdf, visualizar_pdf_gestor, visualizar_pdf_mecanico
from .shared import reset_steps_after_step_4
from .workflow_views import BudgetCreateView, BudgetDeleteView, BudgetListView, BudgetUpdateView, MarkStep5CalculationViewedView, SaveObservationView, UpdateBudgetDiscountView, UpdateBudgetStatusView, UpdateSliderView

__all__ = [
    "BudgetListView",
    "BudgetCreateView",
    "BudgetUpdateView",
    "BudgetDeleteView",
    "CustomerDetailView",
    "VehicleListView",
    "VehicleDetailView",
    "ItemSelectionModalView",
    "AddItemToBudgetView",
    "RemoveItemFromBudgetView",
    "RemoveBudgetItemView",
    "BudgetItemUpdateView",
    "BudgetItemCalculateView",
    "BudgetKitEditView",
    "UpdateSliderView",
    "MarkStep5CalculationViewedView",
    "UpdateBudgetDiscountView",
    "UpdateBudgetStatusView",
    "SaveObservationView",
    "BudgetImageView",
    "visualizar_pdf",
    "visualizar_pdf_gestor",
    "visualizar_pdf_mecanico",
    "AddItemsBatchToBudgetView",
    "BudgetSummaryView",
    "BudgetStep3CollaboratorFieldView",
    "CreateLocalItemView",
    "RegisterLocalItemView",
    "CalculateLocalServiceView",
    "QuickCreateProductView",
    "reset_steps_after_step_4",
]
