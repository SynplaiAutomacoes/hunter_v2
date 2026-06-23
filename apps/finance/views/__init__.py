from __future__ import annotations

from apps.finance.services.webmania_b2b import sync_b2b_companies_to_database
from .financial_group import FinancialGroupCreateView, FinancialGroupDeleteView, FinancialGroupListView, FinancialGroupUpdateView
from .fiscal_referenced_basis import FiscalReferencedBasisApproveView, FiscalReferencedBasisCreateView, FiscalReferencedBasisDetailView, FiscalReferencedBasisFeatureToggleView, FiscalReferencedBasisListView, FiscalReferencedBasisPayloadView
from .fiscal_credit_product_preview import FiscalCreditProductPreviewApproveView, FiscalCreditProductPreviewCreateView, FiscalCreditProductPreviewDetailView, FiscalCreditProductPreviewListView, FiscalCreditProductPreviewPayloadView
from .fiscal_debit_product_preview import (
    FiscalDebitProductPreviewApproveView as FiscalDebitProductPreviewApproveView,
    FiscalDebitProductPreviewCreateView as FiscalDebitProductPreviewCreateView,
    FiscalDebitProductPreviewDetailView as FiscalDebitProductPreviewDetailView,
    FiscalDebitProductPreviewListView as FiscalDebitProductPreviewListView,
    FiscalDebitProductPreviewPayloadView as FiscalDebitProductPreviewPayloadView,
)
from .nfe_credit import NfeCreditCancellationDownloadView, NfeCreditCancellationPayloadView, NfeCreditCancellationView, NfeCreditDownloadView, NfeCreditIssueView, NfeCreditPayloadView
from .nfe_debit import NfeDebitCancellationDownloadView as NfeDebitCancellationDownloadView, NfeDebitCancellationPayloadView as NfeDebitCancellationPayloadView, NfeDebitCancellationView as NfeDebitCancellationView, NfeDebitDownloadView as NfeDebitDownloadView, NfeDebitEmissionFeatureToggleView as NfeDebitEmissionFeatureToggleView, NfeDebitIssueView as NfeDebitIssueView, NfeDebitPayloadView as NfeDebitPayloadView
from .common import DirectorWorkshopAccessMixin
from .emission import EmissionPreviewView, EmissionRequestCreateView, EmissionWorkOrderItemUpdateView, EmissionWorkOrderKitComponentUpdateView, NfeCreateRedirectView, NfseCreateRedirectView
from .issued_documents import IssuedDocumentsArchiveDownloadView, IssuedDocumentsListView
from .commissions import CommissionReportView
from .nfe import NfeAdjustmentDownloadView, NfeAdjustmentIssueView, NfeComplementaryDownloadView, NfeComplementaryPriceQuantityIssueView, NfeCorrectionDownloadView, NfeCorrectionIssueView, NfeDocumentDownloadView, NfeIbsCbsEvent112110CancelView, NfeIbsCbsEvent112110IssueView, NfeIbsCbsEvent112130CancelView, NfeIbsCbsEvent112130IssueView, NfeIbsCbsEvent112150CancelView, NfeIbsCbsEvent112150IssueView, NfeIbsCbsEventDownloadView, NfeIbsCbsEventPayloadView, NfePreviewPdfView, NfeRequestCancelView, NfeRequestCreateView, NfeRequestDetailView, NfeRequestInvalidateView, NfeRequestListView, NfeRequestReconcileView, NfeRequestUpdateView, NfeReturnDownloadView, NfeReturnIssueView
from .nfce import NfceCancellationDownloadView, NfceCancellationView, NfceDocumentDownloadView, NfceDocumentListView, NfceDocumentPayloadView, NfceInutilizationDownloadView, NfceInutilizationPayloadView, NfceInutilizationView, NfceManualEmissionView
from .nfse import NfseDocumentDownloadView, NfsePreviewPdfView, NfseRequestCancelView, NfseRequestCreateView, NfseRequestDetailView, NfseRequestListView, NfseRequestReconcileView, NfseRequestUpdateView
from .nfse_capabilities import NfseMunicipalCapabilityCreateView, NfseMunicipalCapabilityListView, NfseMunicipalCapabilityUpdateView
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
    "FiscalReferencedBasisApproveView",
    "FiscalReferencedBasisCreateView",
    "FiscalReferencedBasisDetailView",
    "FiscalReferencedBasisFeatureToggleView",
    "FiscalReferencedBasisListView",
    "FiscalReferencedBasisPayloadView",
    "FiscalCreditProductPreviewApproveView",
    "FiscalCreditProductPreviewCreateView",
    "FiscalCreditProductPreviewDetailView",
    "FiscalCreditProductPreviewListView",
    "FiscalCreditProductPreviewPayloadView",
    "NfeCreditDownloadView",
    "NfeCreditIssueView",
    "NfeCreditPayloadView",
    "NfeCreditCancellationView",
    "NfeCreditCancellationPayloadView",
    "NfeCreditCancellationDownloadView",
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
    "NfeIbsCbsEvent112110CancelView",
    "NfeIbsCbsEvent112110IssueView",
    "NfeIbsCbsEvent112130CancelView",
    "NfeIbsCbsEvent112130IssueView",
    "NfeIbsCbsEvent112150CancelView",
    "NfeIbsCbsEvent112150IssueView",
    "NfeIbsCbsEventDownloadView",
    "NfeIbsCbsEventPayloadView",
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
    "NfceInutilizationDownloadView",
    "NfceInutilizationPayloadView",
    "NfceInutilizationView",
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
    "NfseMunicipalCapabilityCreateView",
    "NfseMunicipalCapabilityListView",
    "NfseMunicipalCapabilityUpdateView",
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
