from __future__ import annotations

from typing import Any

from apps.catalog.models.kits import Kit
from apps.catalog.models.services import Service
from apps.core.infrastructure.services.management_reports.period import ReportPeriod
from apps.core.infrastructure.services.management_reports.types import ManagementReport, ReportColumnDef
from apps.customer.models import Customer
from apps.suppliers.models import Supplier
from apps.workshops.models.workshops import Workshop


def _workshop_name(workshop: Workshop) -> str:
    return workshop.pdf_name or workshop.name or "-"


def _money_amount(value: object):
    from decimal import Decimal

    amount = getattr(value, "amount", value)
    if amount is None:
        return Decimal("0.00")
    return Decimal(str(amount))


CUSTOMER_COLUMN_DEFINITIONS: tuple[ReportColumnDef, ...] = (
    ReportColumnDef("nome", "Nome", width=28, optional=True, default_selected=True),
    ReportColumnDef("cpf_cnpj", "CPF/CNPJ", width=18, optional=True, default_selected=True),
    ReportColumnDef("telefone", "Telefone", width=16, optional=True, default_selected=True),
    ReportColumnDef("email", "E-mail", width=28, optional=True, default_selected=True),
    ReportColumnDef("tipo", "Tipo", width=10, optional=True, default_selected=False),
    ReportColumnDef("veiculos", "Veículos (placas)", width=28, optional=True, default_selected=False),
    ReportColumnDef("endereco", "Endereço", width=36, optional=True, default_selected=False),
    ReportColumnDef("cidade", "Cidade", width=18, optional=True, default_selected=False),
    ReportColumnDef("estado", "Estado", width=10, optional=True, default_selected=False),
    ReportColumnDef("cep", "CEP", width=12, optional=True, default_selected=False),
    ReportColumnDef("rg", "RG", width=14, optional=True, default_selected=False),
    ReportColumnDef("nascimento", "Nascimento", kind="date", width=14, optional=True, default_selected=False),
    ReportColumnDef("nome_fantasia", "Nome fantasia", width=24, optional=True, default_selected=False),
    ReportColumnDef("ativo", "Ativo", width=10, optional=True, default_selected=True),
)


def _selected_columns(available: tuple[ReportColumnDef, ...] | list[ReportColumnDef], selected_keys: list[str] | None) -> list[ReportColumnDef]:
    if not selected_keys:
        return [col for col in available if col.default_selected]
    by_key = {col.key: col for col in available}
    return [by_key[key] for key in selected_keys if key in by_key]


def build_clientes(*, workshop: Workshop, period: ReportPeriod, selected_columns: list[str] | None = None) -> ManagementReport:
    customers = (
        Customer.objects.filter(workshop=workshop)
        .prefetch_related("vehicles")
        .order_by("name")
    )
    available = list(CUSTOMER_COLUMN_DEFINITIONS)
    columns = _selected_columns(available, selected_columns)
    rows: list[dict[str, Any]] = []
    for customer in customers:
        plates = ", ".join(v.plate for v in customer.vehicles.all()) or "-"
        full_row = {
            "nome": customer.name,
            "cpf_cnpj": customer.cpf_or_cnpj_formatted,
            "telefone": str(customer.phone or "-"),
            "email": customer.email or "-",
            "tipo": customer.get_customer_type_display() if hasattr(customer, "get_customer_type_display") else customer.customer_type,
            "veiculos": plates,
            "endereco": customer.full_address,
            "cidade": customer.cidade or "-",
            "estado": customer.estado or "-",
            "cep": customer.cep or "-",
            "rg": customer.rg or "-",
            "nascimento": customer.birth_date,
            "nome_fantasia": customer.fantasy_name or "-",
            "ativo": "Sim" if customer.is_active else "Não",
        }
        rows.append({col.key: full_row.get(col.key) for col in columns})
    return ManagementReport(
        report_key="clientes",
        title="Clientes",
        period_label=period.label if period else "Cadastro completo",
        workshop_name=_workshop_name(workshop),
        columns=columns,
        rows=rows,
        available_columns=available,
        selected_column_keys=[col.key for col in columns],
    )


def build_fornecedores(*, workshop: Workshop, period: ReportPeriod) -> ManagementReport:
    suppliers = Supplier.objects.filter(workshop=workshop).order_by("name")
    rows = [
        {
            "nome": supplier.name,
            "documento": str(supplier.cnpj or "-"),
            "telefone": str(supplier.phone or "-"),
            "email": supplier.email or "-",
            "cidade": supplier.cidade or "-",
            "ativo": "Sim" if supplier.is_active else "Não",
        }
        for supplier in suppliers
    ]
    columns = [
        ReportColumnDef("nome", "Nome", width=32),
        ReportColumnDef("documento", "Documento", width=18),
        ReportColumnDef("telefone", "Telefone", width=16),
        ReportColumnDef("email", "E-mail", width=28),
        ReportColumnDef("cidade", "Cidade", width=18),
        ReportColumnDef("ativo", "Ativo", width=10),
    ]
    return ManagementReport(
        report_key="fornecedores",
        title="Fornecedores",
        period_label=period.label,
        workshop_name=_workshop_name(workshop),
        columns=columns,
        rows=rows,
    )


def build_servicos_cadastro(*, workshop: Workshop, period: ReportPeriod) -> ManagementReport:
    services = Service.objects.filter(workshop=workshop).order_by("name")
    rows = [
        {
            "nome": service.name,
            "descricao": service.description or "-",
            "duracao": service.duration_display,
            "venda": _money_amount(service.selling_price),
            "custo": _money_amount(service.suggested_cost),
            "ativo": "Sim" if service.is_active else "Não",
        }
        for service in services
    ]
    columns = [
        ReportColumnDef("nome", "Serviço", width=36),
        ReportColumnDef("descricao", "Descrição", width=32),
        ReportColumnDef("duracao", "Duração", width=12),
        ReportColumnDef("venda", "Valor venda", kind="money_sale", align="right", width=14),
        ReportColumnDef("custo", "Custo", kind="money_cost", align="right", width=14),
        ReportColumnDef("ativo", "Ativo", width=10),
    ]
    return ManagementReport(
        report_key="servicos_cadastro",
        title="Serviços",
        period_label=period.label,
        workshop_name=_workshop_name(workshop),
        columns=columns,
        rows=rows,
    )


def build_kits(*, workshop: Workshop, period: ReportPeriod) -> ManagementReport:
    kits = Kit.objects.filter(workshop=workshop).order_by("name")
    rows = [
        {
            "nome": kit.name,
            "descricao": getattr(kit, "description", None) or "-",
            "preco": _money_amount(getattr(kit, "total_price", None)),
            "duracao": (
                f"{int(kit.total_duration.total_seconds() // 3600):02d}h {int((kit.total_duration.total_seconds() % 3600) // 60):02d}m"
                if kit.total_duration
                else "-"
            ),
            "ativo": "Sim" if getattr(kit, "is_active", True) else "Não",
        }
        for kit in kits
    ]
    columns = [
        ReportColumnDef("nome", "Kit", width=36),
        ReportColumnDef("descricao", "Descrição", width=36),
        ReportColumnDef("preco", "Preço total", kind="money_sale", align="right", width=14),
        ReportColumnDef("duracao", "Duração", width=12),
        ReportColumnDef("ativo", "Ativo", width=10),
    ]
    return ManagementReport(
        report_key="kits",
        title="Kits",
        period_label=period.label,
        workshop_name=_workshop_name(workshop),
        columns=columns,
        rows=rows,
    )


def build_cadastro_report(
    *,
    workshop: Workshop,
    period: ReportPeriod,
    report_key: str,
    selected_columns: list[str] | None = None,
) -> ManagementReport | None:
    if report_key == "clientes":
        return build_clientes(workshop=workshop, period=period, selected_columns=selected_columns)
    builders = {
        "fornecedores": build_fornecedores,
        "servicos_cadastro": build_servicos_cadastro,
        "kits": build_kits,
    }
    builder = builders.get(report_key)
    if builder is None:
        return None
    return builder(workshop=workshop, period=period)
