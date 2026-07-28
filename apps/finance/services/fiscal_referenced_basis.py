from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.finance.models.finance import (
    FiscalDocument,
    FiscalDocumentOrigin,
    FiscalDocumentPurpose,
    FiscalDocumentStatus,
    FiscalDocumentType,
    FiscalHypothesis,
    FiscalReferencedBasis,
    FiscalReferencedBasisItem,
    FiscalReferencedBasisStatus,
    FiscalReferencedBasisType,
    WebmaniaCompany,
)
from apps.finance.services.fiscal_attempts import sanitize_fiscal_payload


FINANCIAL_REQUIRED_HYPOTHESES = {
    FiscalHypothesis.CREDIT_FINE_INTEREST,
    FiscalHypothesis.CREDIT_ZFM_PRESUMED,
    FiscalHypothesis.CREDIT_VALUE_REDUCTION,
    FiscalHypothesis.CREDIT_SUCCESSION,
    FiscalHypothesis.DEBIT_COOPERATIVE,
    FiscalHypothesis.DEBIT_EXEMPT_OUTPUT,
    FiscalHypothesis.DEBIT_UNPROCESSED_INVOICE,
    FiscalHypothesis.DEBIT_FINE_INTEREST,
    FiscalHypothesis.DEBIT_SUCCESSION,
    FiscalHypothesis.DEBIT_ADVANCE_PAYMENT,
    FiscalHypothesis.DEBIT_SN_EXCLUSION,
}
STOCK_REQUIRED_HYPOTHESES = {FiscalHypothesis.DEBIT_STOCK_LOSS}
MONEY_QUANTIZER = Decimal("0.01")
QUANTITY_QUANTIZER = Decimal("0.000001")


def is_credit_debit_basis_enabled(*, workshop: Any) -> bool:
    return WebmaniaCompany.objects.filter(workshop=workshop, credit_debit_basis_enabled=True).exists()


@transaction.atomic
def set_credit_debit_basis_enabled(*, workshop: Any, enabled: bool, actor: Any) -> WebmaniaCompany:
    company, _created = WebmaniaCompany.objects.select_for_update().get_or_create(workshop=workshop)
    company.credit_debit_basis_enabled = enabled
    company.credit_debit_basis_enabled_by = actor
    company.credit_debit_basis_enabled_at = timezone.now()
    company.save(update_fields=["credit_debit_basis_enabled", "credit_debit_basis_enabled_by", "credit_debit_basis_enabled_at", "atualizado_em"])
    return company


def _payload_sources(document: FiscalDocument) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for payload in (document.request_payload, document.response_payload):
        if isinstance(payload, dict):
            sources.append(payload)
    legacy_item = document.legacy_nfe_item
    if legacy_item is not None:
        for payload in (legacy_item.raw_payload, legacy_item.log_payload):
            if isinstance(payload, dict):
                sources.append(payload)
    return sources


def _products(payload: dict[str, Any]) -> list[dict[str, Any]]:
    products = payload.get("produtos")
    if isinstance(products, list):
        return [item for item in products if isinstance(item, dict)]
    nested = payload.get("nfe")
    if isinstance(nested, dict) and isinstance(nested.get("produtos"), list):
        return [item for item in nested["produtos"] if isinstance(item, dict)]
    return []


def _sequence(product: dict[str, Any], fallback: int) -> int:
    for key in ("item", "sequencial", "sequencia", "numero_item", "nItem"):
        value = product.get(key)
        if value not in (None, ""):
            try:
                return int(str(value).strip())
            except ValueError:
                return -1
    return fallback


def _ibs_cbs(product: dict[str, Any]) -> dict[str, Any]:
    direct = product.get("ibs_cbs")
    if isinstance(direct, dict) and direct:
        return direct
    taxes = product.get("impostos")
    if isinstance(taxes, dict) and isinstance(taxes.get("ibs_cbs"), dict):
        return taxes["ibs_cbs"]
    return {}


def extract_ibs_cbs_snapshot(*, document: FiscalDocument, item_sequence: int) -> dict[str, Any]:
    missing = ["produto"]
    for payload in _payload_sources(document):
        for position, product in enumerate(_products(payload), start=1):
            if _sequence(product, position) != item_sequence:
                continue
            snapshot = _ibs_cbs(product)
            if not snapshot:
                missing = ["impostos.ibs_cbs"]
                continue
            missing = [key for key in ("situacao_tributaria", "classificacao_tributaria") if not str(snapshot.get(key) or "").strip()]
            if missing:
                continue
            return sanitize_fiscal_payload(snapshot)
    raise ValidationError(f"Item fiscal {item_sequence} sem snapshot IBS/CBS completo. Campos ausentes: {', '.join(missing)}.")


def _decimal(value: Any, *, places: Decimal, field_name: str) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        normalized = Decimal(str(value).replace(",", "."))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError(f"{field_name} do snapshot fiscal e invalido.") from exc
    if normalized < 0:
        raise ValidationError(f"{field_name} nao pode ser negativo.")
    return normalized.quantize(places, rounding=ROUND_HALF_UP)


def extract_commercial_snapshot(*, document: FiscalDocument, item_sequence: int) -> dict[str, Any]:
    for payload in _payload_sources(document):
        for position, product in enumerate(_products(payload), start=1):
            if _sequence(product, position) != item_sequence:
                continue
            quantity = _decimal(product.get("quantidade") or product.get("quantity"), places=QUANTITY_QUANTIZER, field_name="Quantidade")
            unit_price = _decimal(product.get("subtotal") or product.get("valor_unitario") or product.get("unit_value"), places=MONEY_QUANTIZER, field_name="Valor unitario")
            total = _decimal(product.get("total") or product.get("valor_total") or product.get("total_value"), places=MONEY_QUANTIZER, field_name="Valor total")
            commercial = {
                "source_item_sequence": item_sequence,
                "source_item_description": str(product.get("nome") or product.get("descricao") or "").strip(),
                "source_item_code": str(product.get("codigo") or product.get("codigo_produto") or product.get("sku") or "").strip(),
                "source_item_ncm": "".join(char for char in str(product.get("ncm") or "") if char.isdigit()),
                "source_item_cfop": "".join(char for char in str(product.get("codigo_cfop") or product.get("cfop") or "") if char.isdigit()),
                "source_quantity": quantity,
                "source_unit": str(product.get("unidade") or product.get("unit") or "").strip(),
                "source_unit_price": unit_price,
                "source_total_amount": total,
            }
            commercial["commercial_snapshot"] = sanitize_fiscal_payload(
                {
                    "sequencial": item_sequence,
                    "descricao": commercial["source_item_description"],
                    "codigo": commercial["source_item_code"],
                    "ncm": commercial["source_item_ncm"],
                    "codigo_cfop": commercial["source_item_cfop"],
                    "quantidade": format(quantity, "f") if quantity is not None else "",
                    "unidade": commercial["source_unit"],
                    "valor_unitario": format(unit_price, "f") if unit_price is not None else "",
                    "valor_total": format(total, "f") if total is not None else "",
                }
            )
            return commercial
    return {
        "source_item_sequence": item_sequence,
        "source_item_description": "",
        "source_item_code": "",
        "source_item_ncm": "",
        "source_item_cfop": "",
        "source_quantity": None,
        "source_unit": "",
        "source_unit_price": None,
        "source_total_amount": None,
        "commercial_snapshot": {},
    }


def _monetary_values(
    *,
    hypothesis: str,
    principal_amount: Decimal,
    fine_amount: Decimal,
    interest_amount: Decimal,
    other_amount: Decimal,
) -> tuple[Decimal, dict[str, str]]:
    values = {
        "principal": principal_amount.quantize(MONEY_QUANTIZER, rounding=ROUND_HALF_UP),
        "multa": fine_amount.quantize(MONEY_QUANTIZER, rounding=ROUND_HALF_UP),
        "juros": interest_amount.quantize(MONEY_QUANTIZER, rounding=ROUND_HALF_UP),
        "outros": other_amount.quantize(MONEY_QUANTIZER, rounding=ROUND_HALF_UP),
    }
    if any(value < 0 for value in values.values()):
        raise ValidationError("Valores da composicao monetaria nao podem ser negativos.")
    fine_interest = hypothesis in {FiscalHypothesis.CREDIT_FINE_INTEREST, FiscalHypothesis.DEBIT_FINE_INTEREST}
    base = values["multa"] + values["juros"] if fine_interest else sum(values.values(), Decimal("0"))
    rule = "fine_plus_interest" if fine_interest else "principal_plus_fine_plus_interest_plus_other"
    snapshot = {key: format(value, "f") for key, value in values.items()}
    snapshot["regra_composicao"] = rule
    snapshot["base_credito_debito"] = format(base, "f")
    return base, snapshot


def _basis_type(hypothesis: str) -> str:
    if hypothesis.startswith("credit_"):
        return FiscalReferencedBasisType.CREDIT
    if hypothesis.startswith("debit_"):
        return FiscalReferencedBasisType.DEBIT
    raise ValidationError("Hipotese fiscal desconhecida.")


def validate_hypothesis_sources(*, hypothesis: str, financial_reference: Any | None, stock_reference: Any | None) -> None:
    if hypothesis not in FiscalHypothesis.values:
        raise ValidationError("Hipotese fiscal desconhecida.")
    if hypothesis in FINANCIAL_REQUIRED_HYPOTHESES and financial_reference is None:
        raise ValidationError("A hipotese fiscal selecionada exige uma movimentacao financeira vinculada.")
    if hypothesis in STOCK_REQUIRED_HYPOTHESES and stock_reference is None:
        raise ValidationError("A hipotese fiscal selecionada exige uma movimentacao de estoque vinculada.")


@transaction.atomic
def create_referenced_basis(
    *,
    workshop: Any,
    source_document: FiscalDocument,
    source_item_sequence: int,
    fiscal_hypothesis: str,
    created_by: Any,
    financial_reference: Any | None = None,
    stock_reference: Any | None = None,
    notes: str = "",
    principal_amount: Decimal = Decimal("0"),
    fine_amount: Decimal = Decimal("0"),
    interest_amount: Decimal = Decimal("0"),
    other_amount: Decimal = Decimal("0"),
) -> FiscalReferencedBasis:
    if not is_credit_debit_basis_enabled(workshop=workshop):
        raise ValidationError("A preparacao de bases fiscais de credito/debito nao esta habilitada para esta oficina.")
    locked_document = FiscalDocument.objects.select_for_update().get(pk=source_document.pk, workshop=workshop)
    if locked_document.document_type != FiscalDocumentType.NFE or locked_document.origin != FiscalDocumentOrigin.LOCAL or locked_document.purpose != FiscalDocumentPurpose.NORMAL or locked_document.status != FiscalDocumentStatus.APPROVED:
        raise ValidationError("A base exige NF-e normal local e autorizada da oficina ativa.")
    if not locked_document.access_key or len("".join(char for char in locked_document.access_key if char.isdigit())) != 44:
        raise ValidationError("A NF-e de origem nao possui chave de acesso valida.")
    validate_hypothesis_sources(hypothesis=fiscal_hypothesis, financial_reference=financial_reference, stock_reference=stock_reference)
    for reference, label in ((financial_reference, "financeira"), (stock_reference, "de estoque")):
        if reference is not None and reference.workshop_id != workshop.pk:
            raise ValidationError(f"A movimentacao {label} pertence a outra oficina.")
    snapshot = extract_ibs_cbs_snapshot(document=locked_document, item_sequence=source_item_sequence)
    commercial = extract_commercial_snapshot(document=locked_document, item_sequence=source_item_sequence)
    base_amount, monetary_snapshot = _monetary_values(
        hypothesis=fiscal_hypothesis,
        principal_amount=principal_amount,
        fine_amount=fine_amount,
        interest_amount=interest_amount,
        other_amount=other_amount,
    )
    basis = FiscalReferencedBasis(
        workshop=workshop,
        source_document=locked_document,
        source_nfe_item=locked_document.legacy_nfe_item,
        source_access_key="".join(char for char in locked_document.access_key if char.isdigit()),
        source_item_sequence=source_item_sequence,
        source_document_type=FiscalDocumentType.NFE,
        basis_type=_basis_type(fiscal_hypothesis),
        fiscal_hypothesis=fiscal_hypothesis,
        ibs_cbs_snapshot=snapshot,
        financial_reference=financial_reference,
        stock_reference=stock_reference,
        external_origin=False,
        external_xml_validated=False,
        status=FiscalReferencedBasisStatus.DRAFT,
        created_by=created_by,
        notes=notes.strip(),
    )
    basis.save()
    basis_item = FiscalReferencedBasisItem(
        basis=basis,
        **commercial,
        principal_amount=principal_amount,
        fine_amount=fine_amount,
        interest_amount=interest_amount,
        other_amount=other_amount,
        credit_debit_base_amount=base_amount,
        monetary_snapshot=sanitize_fiscal_payload(monetary_snapshot),
    )
    basis_item.save()
    if not basis_item.approval_errors():
        basis.status = FiscalReferencedBasisStatus.READY
        basis.save(update_fields=["status", "atualizado_em"])
    return basis


@transaction.atomic
def approve_referenced_basis(*, basis: FiscalReferencedBasis, approved_by: Any) -> FiscalReferencedBasis:
    locked = FiscalReferencedBasis.objects.select_for_update().get(pk=basis.pk, workshop=basis.workshop)
    if not is_credit_debit_basis_enabled(workshop=locked.workshop):
        raise ValidationError("A preparacao de bases fiscais esta desabilitada para esta oficina.")
    if locked.status not in {FiscalReferencedBasisStatus.DRAFT, FiscalReferencedBasisStatus.READY}:
        raise ValidationError("Somente bases em rascunho ou prontas podem ser aprovadas.")
    validate_hypothesis_sources(hypothesis=locked.fiscal_hypothesis, financial_reference=locked.financial_reference, stock_reference=locked.stock_reference)
    if not str(locked.ibs_cbs_snapshot.get("situacao_tributaria") or "").strip() or not str(locked.ibs_cbs_snapshot.get("classificacao_tributaria") or "").strip():
        raise ValidationError("Snapshot IBS/CBS incompleto; situacao e classificacao tributaria sao obrigatorias.")
    if locked.external_origin and not locked.external_xml_validated:
        raise ValidationError("Documento externo sem XML/importacao validada nao pode ser aprovado.")
    if not locked.notes.strip():
        raise ValidationError("A aprovacao exige evidencia/observacao fiscal registrada.")
    try:
        basis_item = locked.commercial_item
    except FiscalReferencedBasisItem.DoesNotExist as exc:
        raise ValidationError("A base nao possui snapshot monetario/comercial por item.") from exc
    missing = basis_item.approval_errors()
    if missing:
        raise ValidationError(f"Base monetaria/comercial incompleta: {', '.join(missing)}.")
    basis_item.full_clean()
    locked.status = FiscalReferencedBasisStatus.APPROVED
    locked.approved_by = approved_by
    locked.approved_at = timezone.now()
    locked.save(update_fields=["status", "approved_by", "approved_at", "atualizado_em"])
    return locked
