from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from apps.budget.models import BudgetStatus
from apps.messaging.rendering import MISSING, VariableContext, format_phone_value, format_variable_value
from apps.workorder.models import WorkOrderStatus

VariableResolver = Callable[[VariableContext], object]


@dataclass(frozen=True)
class VariableDefinition:
    key: str
    group: str
    label: str
    description: str
    resolver: VariableResolver

    @property
    def token(self) -> str:
        return f"%%{self.key}%%"


VARIABLE_GROUPS: tuple[tuple[str, str], ...] = (
    ("cliente", "Cliente"),
    ("veiculo", "Veículo"),
    ("orcamento", "Orçamento"),
    ("os", "O.S."),
)


def _customer(ctx: VariableContext) -> Any:
    return ctx.customer


def _vehicle(ctx: VariableContext) -> Any:
    return ctx.vehicle


def _budget(ctx: VariableContext) -> Any:
    return ctx.budget


def _workorder(ctx: VariableContext) -> Any:
    return ctx.workorder


def _attr(source: Any, attr_name: str) -> object:
    if source is None:
        return MISSING
    return getattr(source, attr_name, "")


def _customer_attr(ctx: VariableContext, attr_name: str) -> object:
    return _attr(_customer(ctx), attr_name)


def _vehicle_attr(ctx: VariableContext, attr_name: str) -> object:
    return _attr(_vehicle(ctx), attr_name)


def _budget_attr(ctx: VariableContext, attr_name: str) -> object:
    return _attr(_budget(ctx), attr_name)


def _workorder_attr(ctx: VariableContext, attr_name: str) -> object:
    return _attr(_workorder(ctx), attr_name)


def _formatted_customer_document(ctx: VariableContext) -> object:
    customer = _customer(ctx)
    if customer is None:
        return MISSING
    return getattr(customer, "cpf_or_cnpj_formatted", "")


def _formatted_customer_phone(ctx: VariableContext) -> object:
    value = _customer_attr(ctx, "phone")
    if value is MISSING:
        return MISSING
    return format_phone_value(value)


def _vehicle_year_display(ctx: VariableContext) -> object:
    vehicle = _vehicle(ctx)
    if vehicle is None:
        return MISSING

    year_model = str(getattr(vehicle, "year_model", "") or "").strip()
    year_fabrication = str(getattr(vehicle, "year_fabrication", "") or "").strip()

    if year_model and year_fabrication and year_model != year_fabrication:
        return f"{year_model}/{year_fabrication}"
    return year_model or year_fabrication


def _budget_status_label(ctx: VariableContext) -> object:
    budget = _budget(ctx)
    if budget is None:
        return MISSING
    status = str(getattr(budget, "status", "") or "").strip()
    if not status:
        return ""
    return BudgetStatus(status).label


def _workorder_status_label(ctx: VariableContext) -> object:
    workorder = _workorder(ctx)
    if workorder is None:
        return MISSING
    status = str(getattr(workorder, "status", "") or "").strip()
    if not status:
        return ""
    return WorkOrderStatus(status).label


VARIABLE_DEFINITIONS: tuple[VariableDefinition, ...] = (
    VariableDefinition(key="nome", group="cliente", label="Nome", description="Nome do cliente.", resolver=lambda ctx: _customer_attr(ctx, "name")),
    VariableDefinition(key="cpf", group="cliente", label="CPF/CNPJ", description="Documento do cliente cadastrado.", resolver=_formatted_customer_document),
    VariableDefinition(key="rg", group="cliente", label="RG", description="RG do cliente.", resolver=lambda ctx: _customer_attr(ctx, "rg")),
    VariableDefinition(key="data_nascimento", group="cliente", label="Data de nascimento", description="Data de nascimento do cliente.", resolver=lambda ctx: _customer_attr(ctx, "birth_date")),
    VariableDefinition(key="telefone", group="cliente", label="Telefone", description="Telefone principal do cliente.", resolver=_formatted_customer_phone),
    VariableDefinition(key="email", group="cliente", label="Email", description="Email do cliente.", resolver=lambda ctx: _customer_attr(ctx, "email")),
    VariableDefinition(key="placa", group="veiculo", label="Placa", description="Placa do veículo.", resolver=lambda ctx: _vehicle_attr(ctx, "plate")),
    VariableDefinition(key="marca", group="veiculo", label="Marca", description="Marca do veículo.", resolver=lambda ctx: _vehicle_attr(ctx, "brand")),
    VariableDefinition(key="modelo", group="veiculo", label="Modelo", description="Modelo do veículo.", resolver=lambda ctx: _vehicle_attr(ctx, "model")),
    VariableDefinition(key="km", group="veiculo", label="KM", description="Quilometragem atual do veículo.", resolver=lambda ctx: _vehicle_attr(ctx, "km")),
    VariableDefinition(key="ano", group="veiculo", label="Ano", description="Ano do veículo (modelo/fabricação).", resolver=_vehicle_year_display),
    VariableDefinition(key="ano_fabricacao", group="veiculo", label="Ano de fabricação", description="Ano de fabricação do veículo.", resolver=lambda ctx: _vehicle_attr(ctx, "year_fabrication")),
    VariableDefinition(key="ano_modelo", group="veiculo", label="Ano do modelo", description="Ano do modelo do veículo.", resolver=lambda ctx: _vehicle_attr(ctx, "year_model")),
    VariableDefinition(key="cor", group="veiculo", label="Cor", description="Cor do veículo.", resolver=lambda ctx: _vehicle_attr(ctx, "color")),
    VariableDefinition(key="combustivel", group="veiculo", label="Combustível", description="Combustível do veículo.", resolver=lambda ctx: _vehicle_attr(ctx, "fuel")),
    VariableDefinition(key="motor", group="veiculo", label="Motor", description="Motor do veículo.", resolver=lambda ctx: _vehicle_attr(ctx, "engine")),
    VariableDefinition(key="orcamento_numero", group="orcamento", label="Número do orçamento", description="Identificador do orçamento.", resolver=lambda ctx: _budget_attr(ctx, "pk")),
    VariableDefinition(key="orcamento_status", group="orcamento", label="Status do orçamento", description="Status atual do orçamento.", resolver=_budget_status_label),
    VariableDefinition(key="orcamento_data_criacao", group="orcamento", label="Data de criação", description="Data de criação do orçamento.", resolver=lambda ctx: _budget_attr(ctx, "criado_em")),
    VariableDefinition(key="orcamento_data_entrada", group="orcamento", label="Data de entrada", description="Data de entrada do veículo no orçamento.", resolver=lambda ctx: _budget_attr(ctx, "entry_date")),
    VariableDefinition(key="orcamento_data_validade", group="orcamento", label="Data de validade", description="Data de validade do orçamento.", resolver=lambda ctx: _budget_attr(ctx, "expiration_date")),
    VariableDefinition(key="orcamento_km_atual", group="orcamento", label="KM atual do orçamento", description="Quilometragem registrada no orçamento.", resolver=lambda ctx: _budget_attr(ctx, "current_km")),
    VariableDefinition(key="orcamento_valor_total", group="orcamento", label="Valor total do orçamento", description="Valor total calculado do orçamento.", resolver=lambda ctx: _budget_attr(ctx, "total_budget_value")),
    VariableDefinition(key="orcamento_desconto", group="orcamento", label="Desconto do orçamento", description="Desconto aplicado ao orçamento.", resolver=lambda ctx: _budget_attr(ctx, "resolved_discount_value")),
    VariableDefinition(key="orcamento_relato_cliente", group="orcamento", label="Relato do cliente", description="Relato principal do cliente no orçamento.", resolver=lambda ctx: _budget_attr(ctx, "problem_description")),
    VariableDefinition(key="orcamento_diagnostico_tecnico", group="orcamento", label="Diagnóstico técnico", description="Diagnóstico técnico do orçamento.", resolver=lambda ctx: _budget_attr(ctx, "technical_diagnosis")),
    VariableDefinition(key="orcamento_observacoes", group="orcamento", label="Observações", description="Observações complementares do orçamento.", resolver=lambda ctx: _budget_attr(ctx, "notes")),
    VariableDefinition(key="orcamento_colaborador", group="orcamento", label="Colaborador", description="Colaborador responsável pelo orçamento.", resolver=lambda ctx: _budget_attr(ctx, "collaborator_name")),
    VariableDefinition(key="os_numero", group="os", label="Número da O.S.", description="Identificador da ordem de serviço.", resolver=lambda ctx: _workorder_attr(ctx, "pk")),
    VariableDefinition(key="os_status", group="os", label="Status da O.S.", description="Status atual da ordem de serviço.", resolver=_workorder_status_label),
    VariableDefinition(key="os_data_criacao", group="os", label="Data de criação", description="Data de criação da ordem de serviço.", resolver=lambda ctx: _workorder_attr(ctx, "criado_em")),
    VariableDefinition(key="os_valor_total", group="os", label="Valor total da O.S.", description="Valor total calculado da ordem de serviço.", resolver=lambda ctx: _workorder_attr(ctx, "total_budget_value")),
    VariableDefinition(key="os_desconto", group="os", label="Desconto da O.S.", description="Desconto aplicado à ordem de serviço.", resolver=lambda ctx: _workorder_attr(ctx, "discount_value")),
    VariableDefinition(key="os_km_final", group="os", label="KM final", description="Quilometragem final registrada na ordem de serviço.", resolver=lambda ctx: _workorder_attr(ctx, "km_final")),
)


def get_variable_definition_map() -> dict[str, VariableDefinition]:
    return {definition.key: definition for definition in VARIABLE_DEFINITIONS}


def get_variable_groups() -> list[dict[str, Any]]:
    grouped_definitions: dict[str, list[dict[str, str]]] = {group_key: [] for group_key, _ in VARIABLE_GROUPS}
    for definition in VARIABLE_DEFINITIONS:
        grouped_definitions[definition.group].append(
            {
                "key": definition.key,
                "token": definition.token,
                "label": definition.label,
                "description": definition.description,
            }
        )

    return [
        {
            "key": group_key,
            "title": group_title,
            "variables": grouped_definitions[group_key],
        }
        for group_key, group_title in VARIABLE_GROUPS
    ]


def resolve_variable(definition: VariableDefinition, context: VariableContext) -> object:
    value = definition.resolver(context)
    if value is MISSING:
        return MISSING
    return format_variable_value(value)
