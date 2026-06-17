from __future__ import annotations

def sync_b2b_companies_to_database(*args, **kwargs):
    from apps.core.infrastructure.providers import get_fiscal_service
    return get_fiscal_service().sync_b2b_companies_to_database(*args, **kwargs)
from .financial_group import FinancialGroupCreateView, FinancialGroupDeleteView, FinancialGroupListView, FinancialGroupUpdateView
from .common import DirectorWorkshopAccessMixin
from .emission import EmissionPreviewView, EmissionRequestCreateView, EmissionWorkOrderItemUpdateView, EmissionWorkOrderKitComponentUpdateView, NfeCreateRedirectView, NfseCreateRedirectView
from .issued_documents import IssuedDocumentsArchiveDownloadView, IssuedDocumentsListView
from .commissions import CommissionReportView, CommissionReportPdfView
from .nfe import NfeDocumentDownloadView, NfePreviewPdfView, NfeRequestCancelView, NfeRequestCreateView, NfeRequestDetailView, NfeRequestInvalidateView, NfeRequestListView, NfeRequestReconcileView, NfeRequestUpdateView
from .nfse import NfseDocumentDownloadView, NfsePreviewPdfView, NfseRequestCancelView, NfseRequestCreateView, NfseRequestDetailView, NfseRequestListView, NfseRequestReconcileView, NfseRequestUpdateView
from .reports import FinancialReportsHomeView, ReportMovementEditView, ReportMovementDeleteView
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
    "ReportMovementEditView",
    "ReportMovementDeleteView",
    "FinancialGroupUpdateView",
    "IssuedDocumentsArchiveDownloadView",
    "IssuedDocumentsListView",
    "CommissionReportView",
    "CommissionReportPdfView",
    "NfeCreateRedirectView",
    "NfeDocumentDownloadView",
    "NfePreviewPdfView",
    "NfeRequestCancelView",
    "NfeRequestCreateView",
    "NfeRequestDetailView",
    "NfeRequestInvalidateView",
    "NfeRequestListView",
    "NfeRequestReconcileView",
    "NfeRequestUpdateView",
    "NfseCreateRedirectView",
    "NfseRequestCancelView",
    "NfseDocumentDownloadView",
    "NfsePreviewPdfView",
    "NfseRequestCreateView",
    "NfseRequestDetailView",
    "NfseRequestListView",
    "NfseRequestReconcileView",
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
