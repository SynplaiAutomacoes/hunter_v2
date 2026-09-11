from __future__ import annotations

from .financial_group import FinancialGroupBulkDeleteView, FinancialGroupCreateView, FinancialGroupDeleteView, FinancialGroupListView, FinancialGroupUpdateView
from .common import DirectorWorkshopAccessMixin
from .emission import EmissionPreviewView, EmissionRequestCreateView, EmissionWorkOrderItemUpdateView, EmissionWorkOrderKitComponentUpdateView, NfeCreateRedirectView, NfseCreateRedirectView
from .fiscal_gateway import FiscalOperationGatewayView
from .standalone_emission import StandaloneCustomerSearchView, StandaloneEmissionCreateView
from .issued_documents import IssuedDocumentsArchiveDownloadView, IssuedDocumentsListView
from .commissions import CommissionReportPdfView, CommissionReportView
from .nfe import NfeCorrectionDownloadView, NfeCorrectionIssueView, NfeDocumentDownloadView, NfePreviewPdfView, NfeRequestCancelView, NfeRequestCreateView, NfeRequestDetailView, NfeRequestInvalidateView, NfeRequestListView, NfeRequestReconcileView, NfeRequestUpdateView, NfeReturnDownloadView, NfeReturnIssueView
from .nfse import NfseDocumentDownloadView, NfsePreviewPdfView, NfseRequestCancelView, NfseRequestCreateView, NfseRequestDetailView, NfseRequestListView, NfseRequestReconcileView, NfseRequestUpdateView
from .payroll import (
    PayrollAddManualBenefitView,
    PayrollAddManualCommissionView,
    PayrollBulkConciliateView,
    PayrollBulkPayView,
    PayrollBulkUnpayView,
    PayrollCommissionHistoryPartialView,
    PayrollDeleteManualCommissionView,
    PayrollEditModalView,
    PayrollListView,
    PayrollSyncComponentView,
)
from .purchase_return import PurchaseReturnCreateView, PurchaseReturnPreviewPdfView, PurchaseReturnPreviewView, PurchaseReturnTransmitView, PurchaseReturnWorkflowView
from .reports import FinancialReportsHomeView, ReportMovementEditView, ReportMovementDeleteView
from .tax_class import TaxClassCreateView, TaxClassDeleteView, TaxClassListView, TaxClassManagerView, TaxClassPresetCreateView, TaxClassPresetListView, TaxClassPresetUpdateView, TaxClassUpdateView
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
    "FiscalOperationGatewayView",
    "StandaloneEmissionCreateView",
    "StandaloneCustomerSearchView",
    "EmissionWorkOrderKitComponentUpdateView",
    "EmissionWorkOrderItemUpdateView",
    "FinancialGroupCreateView",
    "FinancialGroupBulkDeleteView",
    "FinancialGroupDeleteView",
    "FinancialGroupListView",
    "FinancialReportsHomeView",
    "ReportMovementEditView",
    "ReportMovementDeleteView",
    "PayrollAddManualBenefitView",
    "PayrollAddManualCommissionView",
    "PayrollBulkConciliateView",
    "PayrollBulkPayView",
    "PayrollBulkUnpayView",
    "PayrollDeleteManualCommissionView",
    "PayrollEditModalView",
    "PayrollCommissionHistoryPartialView",
    "PayrollListView",
    "PayrollSyncComponentView",
    "PurchaseReturnCreateView",
    "PurchaseReturnPreviewPdfView",
    "PurchaseReturnPreviewView",
    "PurchaseReturnTransmitView",
    "PurchaseReturnWorkflowView",
    "FinancialGroupUpdateView",
    "IssuedDocumentsArchiveDownloadView",
    "IssuedDocumentsListView",
    "CommissionReportView",
    "CommissionReportPdfView",
    "NfeCreateRedirectView",
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
    "TaxClassDeleteView",
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
