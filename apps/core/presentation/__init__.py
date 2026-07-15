"""Presentation package.

Keep this module lightweight: Django MIDDLEWARE imports submodules under this
package during startup. Eagerly re-exporting views/widgets here can deadlock
under Python 3.14 + StatReloader — import those from their own modules.
"""

from apps.core.presentation.mixins import (
    BaseModalFormView,
    HtmxDeleteResponseMixin,
    HtmxTemplateResponseMixin,
    PageFavoriteMixin,
)
from apps.core.presentation.navigation import *  # noqa: F401, F403
from apps.core.presentation.favorites import *  # noqa: F401, F403
from apps.core.presentation.context_processors import *  # noqa: F401, F403
from apps.core.presentation.tables import *  # noqa: F401, F403
from apps.core.presentation.middlewares import *  # noqa: F401, F403
from apps.core.presentation.forms import *  # noqa: F401, F403
from apps.core.utils import alert_confirm_layout

__all__ = [
    "BaseModalFormView",
    "HtmxDeleteResponseMixin",
    "HtmxTemplateResponseMixin",
    "PageFavoriteMixin",
    "VisibilityPredicate",
    "BUDGET_CREATE_FAVORITE_PAGE",
    "CREATE_CLIENT_FAVORITE_PAGE",
    "COLLABORATOR_CREATE_FAVORITE_PAGE",
    "SUPPLIER_CREATE_FAVORITE_PAGE",
    "PRODUCT_CREATE_FAVORITE_PAGE",
    "SERVICE_CREATE_FAVORITE_PAGE",
    "KIT_CREATE_FAVORITE_PAGE",
    "CATALOG_GROUP_CREATE_FAVORITE_PAGE",
    "CHECKLIST_CREATE_FAVORITE_PAGE",
    "APPOINTMENT_CREATE_FAVORITE_PAGE",
    "STOCK_IMPORT_CREATE_FAVORITE_PAGE",
    "FINANCIAL_MOVEMENT_CREATE_FAVORITE_PAGE",
    "NAVBAR_MENU_DEFINITIONS",
    "EXTRA_FAVORITABLE_PAGE_DEFINITIONS",
    "build_favoritable_page",
    "get_navbar_menus",
    "get_favoritable_pages",
    "FavoritePageError",
    "InvalidFavoritePageError",
    "FavoritePageLimitError",
    "normalize_favorite_url",
    "list_favorite_pages_for_user",
    "toggle_favorite_page",
    "reorder_favorite_pages",
    "navbar",
    "TableActionDefaults",
    "RequestPerformanceLoggingMiddleware",
    "RequireFirstWorkshopMiddleware",
    "TextNormalizationFormMixin",
    "CoreForm",
    "CoreModelForm",
    "AddressFormMixin",
    "address_layout",
    "MultiStepFormMixin",
    "alert_confirm_layout",
]
