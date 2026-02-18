from __future__ import annotations

from apps.finance.services.webmania_b2b import sync_b2b_companies_to_database
from apps.finance.views_common import DirectorWorkshopAccessMixin
from apps.finance.views_nfse import NfePlaceholderView, NfseRequestCreateView, NfseRequestListView, NfseRequestUpdateView
from apps.finance.views_tax_class import TaxClassCreateView, TaxClassListView, TaxClassManagerView, TaxClassUpdateView
from apps.finance.views_webhook import WebhookView
from apps.finance.views_webmania import (
    WebmaniaCompanyDetailView,
    WebmaniaCompanyListView,
    WebmaniaCompanySyncView,
    WebmaniaCompanyUpdateView,
    WebmaniaRequestsView,
)


__all__ = [
    "DirectorWorkshopAccessMixin",
    "NfePlaceholderView",
    "NfseRequestCreateView",
    "NfseRequestListView",
    "NfseRequestUpdateView",
    "TaxClassCreateView",
    "TaxClassListView",
    "TaxClassManagerView",
    "TaxClassUpdateView",
    "WebhookView",
    "WebmaniaCompanyDetailView",
    "WebmaniaCompanyListView",
    "WebmaniaCompanySyncView",
    "WebmaniaCompanyUpdateView",
    "WebmaniaRequestsView",
    "sync_b2b_companies_to_database",
]
