from __future__ import annotations

from apps.finance.services.webmania_b2b import sync_b2b_companies_to_database
from .common import DirectorWorkshopAccessMixin
from .nfse import NfePlaceholderView, NfseRequestCreateView, NfseRequestListView, NfseRequestUpdateView
from .tax_class import TaxClassCreateView, TaxClassListView, TaxClassManagerView, TaxClassUpdateView
from .webhook import WebhookView
from .webmania import (
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
