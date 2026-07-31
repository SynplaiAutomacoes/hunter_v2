"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include
from django.views.generic import RedirectView

from apps.core.presentation.views import permission_denied
from apps.messaging.presentation.views.satisfaction_review_views import PublicSatisfactionReviewView

handler403 = permission_denied

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="accounts:login", permanent=False)),
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("roles/", include(("apps.iam.urls", "iam"), namespace="iam")),
    path("workshops/", include("apps.workshops.urls")),
    path("collaborators/", include("apps.collaborators.urls")),
    path("catalog/", include("apps.catalog.urls")),
    path("suppliers/", include("apps.suppliers.urls")),
    path("quote/", include("apps.quote.urls")),
    path("checklist/", include("apps.checklist.urls")),
    path("core/", include("apps.core.urls")),
    path("customer/", include("apps.customer.urls")),
    path("budget/", include("apps.budget.urls")),
    path("workorder/", include("apps.workorder.urls")),
    path("scheduling/", include("apps.scheduling.urls")),
    path("stock/", include("apps.stock.urls")),
    path("finance/", include("apps.finance.urls")),
    path("messaging/", include("apps.messaging.urls")),
    path("review/<str:token>/", PublicSatisfactionReviewView.as_view(), name="public_satisfaction_review"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
