from __future__ import annotations

from .financial_group import FinancialGroupCreateView, FinancialGroupDeleteView, FinancialGroupListView, FinancialGroupUpdateView
from .common import DirectorWorkshopAccessMixin
from .emission import EmissionPreviewView, EmissionRequestCreateView, EmissionWorkOrderItemUpdateView, EmissionWorkOrderKitComponentUpdateView, NfeCreateRedirectView, NfseCreateRedirectView
from .issued_documents import IssuedDocumentsArchiveDownloadView, IssuedDocumentsListView
from .commissions import CommissionReportPdfView, CommissionReportView
from .nfe import NfeDocumentDownloadView, NfePreviewPdfView, NfeRequestCancelView, NfeRequestCreateView, NfeRequestDetailView, NfeRequestInvalidateView, NfeRequestListView, NfeRequestReconcileView, NfeRequestUpdateView
from .nfse import NfseDocumentDownloadView, NfsePreviewPdfView, NfseRequestCancelView, NfseRequestCreateView, NfseRequestDetailView, NfseRequestListView, NfseRequestReconcileView, NfseRequestUpdateView
from .payroll import PayrollBulkPayView, PayrollBulkUnpayView, PayrollEditModalView, PayrollListView
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


def sync_b2b_companies_to_database(*args, **kwargs):
    from apps.core.infrastructure.providers import get_fiscal_service

    return get_fiscal_service().sync_b2b_companies_to_database(*args, **kwargs)


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
    "PayrollBulkPayView",
    "PayrollBulkUnpayView",
    "PayrollEditModalView",
    "PayrollListView",
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
