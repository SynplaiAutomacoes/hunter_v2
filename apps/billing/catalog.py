from __future__ import annotations

from decimal import Decimal

from apps.billing.domain.plans import Plan

PLAN_CATALOG: tuple[dict[str, object], ...] = (
    {
        "key": Plan.BASIC,
        "fallback_name": "Orçamento",
        "fallback_description": "Tudo o que você precisa para cadastrar produtos, serviços, kits, termos e emitir orçamentos.",
        "features": (
            "Clientes e veículos",
            "Produtos, serviços e kits",
            "Termos de assinatura",
            "Fluxo completo de orçamento",
            "Checklist e perguntas investigativas",
        ),
    },
    {
        "key": Plan.FULL,
        "fallback_name": "Completo",
        "fallback_description": "Libera o sistema inteiro: ordens de serviço, estoque, financeiro, fiscal, agendamentos e mais.",
        "features": (
            "Tudo do plano Orçamento",
            "Ordens de serviço",
            "Estoque e fornecedores",
            "Financeiro, DRE e emissão fiscal",
            "Agendamentos e mensagens WhatsApp",
        ),
    },
)


def features_from_stripe_product(*, description: str, marketing_features: list[str]) -> tuple[str, ...]:
    names = [item.strip() for item in marketing_features if item and item.strip()]
    if names:
        return tuple(names)

    lines: list[str] = []
    for line in (description or "").splitlines():
        item = line.strip().lstrip("-•").strip()
        if item:
            lines.append(item)
    return tuple(lines)


def description_for_plan_card(*, description: str, features: tuple[str, ...], used_marketing_features: bool) -> str:
    text = (description or "").strip()
    if used_marketing_features:
        return text
    if features:
        return ""
    return text


def format_money_label(*, unit_amount: int | None, currency: str) -> str:
    if unit_amount is None:
        return "Consulte"
    value = Decimal(unit_amount) / Decimal(100)
    currency_code = (currency or "").lower()
    if currency_code == "brl":
        formatted = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {formatted}"
    formatted = f"{value:,.2f}"
    return f"{currency_code.upper()} {formatted}"


def interval_label_for(interval: str) -> str:
    normalized = (interval or "").lower()
    if normalized == "month":
        return "/mês"
    if normalized == "year":
        return "/ano"
    if normalized == "week":
        return "/semana"
    if normalized == "day":
        return "/dia"
    return ""
