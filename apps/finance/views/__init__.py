from __future__ import annotations

from apps.finance.services.webmania_b2b import sync_b2b_companies_to_database
from .financial_group import FinancialGroupCreateView, FinancialGroupDeleteView, FinancialGroupListView, FinancialGroupUpdateView
from .common import DirectorWorkshopAccessMixin
from .emission import EmissionPreviewView, EmissionRequestCreateView, EmissionWorkOrderItemUpdateView, EmissionWorkOrderKitComponentUpdateView, NfeCreateRedirectView, NfseCreateRedirectView
from .issued_documents import IssuedDocumentsArchiveDownloadView, IssuedDocumentsListView
from .commissions import CommissionReportView
from .nfe import NfeAdjustmentDownloadView, NfeAdjustmentIssueView, NfeComplementaryDownloadView, NfeComplementaryPriceQuantityIssueView, NfeCorrectionDownloadView, NfeCorrectionIssueView, NfeDocumentDownloadView, NfePreviewPdfView, NfeRequestCancelView, NfeRequestCreateView, NfeRequestDetailView, NfeRequestInvalidateView, NfeRequestListView, NfeRequestReconcileView, NfeRequestUpdateView, NfeReturnDownloadView, NfeReturnIssueView
from .nfce import NfceCancellationDownloadView, NfceCancellationView, NfceDocumentDownloadView, NfceDocumentListView, NfceDocumentPayloadView, NfceManualEmissionView
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
    "NfeCreateRedirectView",
    "NfeAdjustmentDownloadView",
    "NfeAdjustmentIssueView",
    "NfeComplementaryDownloadView",
    "NfeComplementaryPriceQuantityIssueView",
    "NfeCorrectionDownloadView",
    "NfeCorrectionIssueView",
    "NfeDocumentDownloadView",
    "NfePreviewPdfView",
    "NfeRequestCancelView",
    "NfeRequestCreateView",
    "NfeRequestDetailView",
    "NfeRequestInvalidateView",
    "NfeRequestListView",
    "NfeRequestReconcileView",
    "NfeRequestUpdateView",
    "NfeReturnDownloadView",
    "NfeReturnIssueView",
    "NfceDocumentDownloadView",
    "NfceDocumentListView",
    "NfceDocumentPayloadView",
    "NfceManualEmissionView",
    "NfceCancellationDownloadView",
    "NfceCancellationView",
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
