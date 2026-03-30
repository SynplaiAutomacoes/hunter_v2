from __future__ import annotations

from apps.finance.services.webmania_b2b import sync_b2b_companies_to_database
from .financial_group import FinancialGroupCreateView, FinancialGroupDeleteView, FinancialGroupListView, FinancialGroupUpdateView
from .common import DirectorWorkshopAccessMixin
from .emission import EmissionPreviewView, EmissionRequestCreateView, EmissionWorkOrderItemUpdateView, EmissionWorkOrderKitComponentUpdateView, NfeCreateRedirectView, NfseCreateRedirectView
from .issued_documents import IssuedDocumentsArchiveDownloadView, IssuedDocumentsListView
from .nfe import NfeDocumentDownloadView, NfeRequestCancelView, NfeRequestCreateView, NfeRequestDetailView, NfeRequestListView, NfeRequestReconcileView, NfeRequestUpdateView
from .nfse import NfseDocumentDownloadView, NfseRequestCancelView, NfseRequestCreateView, NfseRequestDetailView, NfseRequestListView, NfseRequestUpdateView
from .reports import FinancialReportsHomeView
from .tax_class import TaxClassCreateView, TaxClassListView, TaxClassManagerView, TaxClassPresetCreateView, TaxClassPresetListView, TaxClassPresetUpdateView, TaxClassUpdateView
from .webhook import WebhookView
from .webmania import (
    WebmaniaCompanyDetailView,
    WebmaniaCompanyListView,
    WebmaniaCompanySyncView,
    WebmaniaCompanyUpdateView,
    WebmaniaRequestsView,
)
from .dre import DreExcelView, DrePdfPreviewView, DrePdfView, DreReportView, DreResultsView


__all__ = [
    "DirectorWorkshopAccessMixin",
    "EmissionPreviewView",
    "EmissionRequestCreateView",
    "EmissionWorkOrderKitComponentUpdateView",
    "EmissionWorkOrderItemUpdateView",
    "FinancialGroupCreateView",
    "FinancialGroupDeleteView",
    "FinancialGroupListView",
    "FinancialReportsHomeView",
    "FinancialGroupUpdateView",
    "IssuedDocumentsArchiveDownloadView",
    "IssuedDocumentsListView",
    "NfeCreateRedirectView",
    "NfeDocumentDownloadView",
    "NfeRequestCancelView",
    "NfeRequestCreateView",
    "NfeRequestDetailView",
    "NfeRequestListView",
    "NfeRequestReconcileView",
    "NfeRequestUpdateView",
    "NfseCreateRedirectView",
    "NfseRequestCancelView",
    "NfseDocumentDownloadView",
    "NfseRequestCreateView",
    "NfseRequestDetailView",
    "NfseRequestListView",
    "NfseRequestUpdateView",
    "TaxClassCreateView",
    "TaxClassListView",
    "TaxClassManagerView",
    "TaxClassPresetCreateView",
    "TaxClassPresetListView",
    "TaxClassPresetUpdateView",
    "TaxClassUpdateView",
    "WebhookView",
    "WebmaniaCompanyDetailView",
    "WebmaniaCompanyListView",
    "WebmaniaCompanySyncView",
    "WebmaniaCompanyUpdateView",
    "WebmaniaRequestsView",
    "sync_b2b_companies_to_database",
    "DreReportView",
    "DreResultsView",
    "DrePdfView",
    "DrePdfPreviewView",
    "DreExcelView",
]
