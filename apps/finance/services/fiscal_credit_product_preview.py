from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.finance.models.finance import (
    FiscalCreditProductPreview,
    FiscalHypothesis,
    FiscalProductPreviewStatus,
    FiscalReferencedBasis,
    FiscalReferencedBasisItem,
    FiscalReferencedBasisStatus,
)
from apps.finance.services.fiscal_attempts import sanitize_fiscal_payload
from apps.finance.services.fiscal_referenced_basis import is_credit_debit_basis_enabled


FORBIDDEN_TAX_GROUPS = {"icms", "ipi", "pis", "cofins", "issqn", "ii", "imposto_devolvido"}
FORBIDDEN_PRODUCT_FIELDS = {"dfe_referenciado", "evento_ibs_cbs", "cod_evento", "tipo_debito"}


def _format_decimal(value: Decimal, *, places: str) -> str:
    return format(value.quantize(Decimal(places), rounding=ROUND_HALF_UP), "f")


def detect_forbidden_groups(product_payload: dict[str, Any]) -> list[str]:
    detected = {field for field in FORBIDDEN_PRODUCT_FIELDS if field in product_payload}
    taxes = product_payload.get("impostos")
    if isinstance(taxes, dict):
        detected.update(f"impostos.{key}" for key in FORBIDDEN_TAX_GROUPS if key in taxes)
        detected.update(f"impostos.{key}" for key in taxes if key != "ibs_cbs")
    return sorted(detected)


def _build_product_payload(
    *,
    basis: FiscalReferencedBasis,
    basis_item: FiscalReferencedBasisItem,
    quantity: Decimal,
    unit_price: Decimal,
    total_amount: Decimal,
    cfop: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    item = basis_item
    ibs_cbs = sanitize_fiscal_payload(basis.ibs_cbs_snapshot)
    product = {
        "nome": item.source_item_description,
        "codigo": item.source_item_code,
        "ncm": item.source_item_ncm,
        "quantidade": _format_decimal(quantity, places="0.000001"),
        "unidade": item.source_unit,
        "subtotal": _format_decimal(unit_price, places="0.01"),
        "total": _format_decimal(total_amount, places="0.01"),
        "codigo_cfop": cfop,
        "impostos": {"ibs_cbs": ibs_cbs},
    }
    return sanitize_fiscal_payload(product), ibs_cbs


@transaction.atomic
def create_credit_product_preview(
    *,
    workshop: Any,
    basis: FiscalReferencedBasis,
    quantity: Decimal,
    unit_price: Decimal,
    total_amount: Decimal,
    cfop: str,
    created_by: Any,
    explicit_value_confirmation: bool,
) -> FiscalCreditProductPreview:
    if not is_credit_debit_basis_enabled(workshop=workshop):
        raise ValidationError("A preparacao fiscal de credito/debito esta desabilitada para esta oficina.")
    locked_basis = FiscalReferencedBasis.objects.select_for_update().get(pk=basis.pk, workshop=workshop)
    if locked_basis.status != FiscalReferencedBasisStatus.APPROVED:
        raise ValidationError("A previa exige base fiscal aprovada.")
    if locked_basis.fiscal_hypothesis != FiscalHypothesis.CREDIT_FINE_INTEREST:
        raise ValidationError("A previa suporta somente credito tipo 1 por multa/juros.")
    if locked_basis.external_origin and not locked_basis.external_xml_validated:
        raise ValidationError("Documento externo exige XML/importacao validada.")
    try:
        commercial_item = FiscalReferencedBasisItem.objects.select_for_update().get(basis=locked_basis)
    except FiscalReferencedBasisItem.DoesNotExist as exc:
        raise ValidationError("A base aprovada nao possui item monetario/comercial congelado.") from exc
    missing_commercial = [
        label
        for label, value in (
            ("descricao", commercial_item.source_item_description),
            ("NCM", commercial_item.source_item_ncm),
            ("unidade", commercial_item.source_unit),
        )
        if not str(value or "").strip()
    ]
    if missing_commercial:
        raise ValidationError(f"Snapshot comercial insuficiente: {', '.join(missing_commercial)}.")
    if not explicit_value_confirmation:
        raise ValidationError("Confirme que quantidade, valor unitario, total e CFOP foram definidos explicitamente.")
    normalized_cfop = "".join(char for char in str(cfop or "") if char.isdigit())
    if len(normalized_cfop) != 4:
        raise ValidationError("O CFOP deve possuir 4 digitos e ser informado explicitamente.")
    quantity = quantity.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    unit_price = unit_price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    total_amount = total_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if quantity <= 0 or unit_price <= 0 or total_amount <= 0:
        raise ValidationError("Quantidade, valor unitario e total devem ser positivos.")
    expected_total = (quantity * unit_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if abs(expected_total - total_amount) > Decimal("0.01"):
        raise ValidationError("Quantidade x valor unitario diverge do total alem da tolerancia de R$ 0,01.")
    if total_amount != commercial_item.credit_debit_base_amount:
        raise ValidationError("O total deve ser exatamente igual a multa + juros da base aprovada.")
    product_payload, ibs_cbs_payload = _build_product_payload(basis=locked_basis, basis_item=commercial_item, quantity=quantity, unit_price=unit_price, total_amount=total_amount, cfop=normalized_cfop)
    forbidden = detect_forbidden_groups(product_payload)
    if forbidden:
        raise ValidationError(f"Produto contem grupos proibidos: {', '.join(forbidden)}.")
    missing_ibs = [field for field in ("situacao_tributaria", "classificacao_tributaria") if not str(ibs_cbs_payload.get(field) or "").strip()]
    if missing_ibs:
        raise ValidationError(f"Snapshot IBS/CBS insuficiente: {', '.join(missing_ibs)}.")
    latest_revision = locked_basis.credit_product_previews.aggregate(max_revision=Max("revision"))["max_revision"] or 0
    preview_payload = sanitize_fiscal_payload(
        {
            "modelo": 1,
            "finalidade": 5,
            "tipo_credito": 1,
            "nfe_referenciada": [locked_basis.source_access_key],
            "produtos": [product_payload],
        }
    )
    preview = FiscalCreditProductPreview(
        workshop=workshop,
        basis=locked_basis,
        basis_item=commercial_item,
        revision=latest_revision + 1,
        source_access_key=locked_basis.source_access_key,
        source_item_sequence=locked_basis.source_item_sequence,
        product_cfop=normalized_cfop,
        product_quantity=quantity,
        product_unit_price=unit_price,
        product_total_amount=total_amount,
        product_payload=product_payload,
        ibs_cbs_payload=ibs_cbs_payload,
        preview_payload=preview_payload,
        forbidden_tax_groups_detected=forbidden,
        validation_status=FiscalProductPreviewStatus.VALIDATED,
        validation_errors=[],
        explicit_value_confirmation=True,
        created_by=created_by,
    )
    preview.save()
    return preview


@transaction.atomic
def approve_credit_product_preview(*, preview: FiscalCreditProductPreview, approved_by: Any) -> FiscalCreditProductPreview:
    locked = FiscalCreditProductPreview.objects.select_for_update().select_related("basis", "basis_item").get(pk=preview.pk, workshop=preview.workshop)
    if not is_credit_debit_basis_enabled(workshop=locked.workshop):
        raise ValidationError("A preparacao fiscal de credito/debito esta desabilitada para esta oficina.")
    if locked.validation_status != FiscalProductPreviewStatus.VALIDATED:
        raise ValidationError("Somente previa validada pode ser aprovada.")
    locked.full_clean()
    locked.validation_status = FiscalProductPreviewStatus.APPROVED
    locked.approved_by = approved_by
    locked.approved_at = timezone.now()
    locked.save(update_fields=["validation_status", "approved_by", "approved_at", "atualizado_em"])
    return locked
