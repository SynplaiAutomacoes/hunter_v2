from __future__ import annotations

from decimal import Decimal
from typing import TypedDict

from apps.finance.models import FinancialGroup, PaymentMethod
from apps.quote.models.investigative_questions import InvestigativeQuestion
from apps.workshops.models.workshops import Workshop


class PaymentMethodSeed(TypedDict):
    description: str
    payment_type: str
    installments_count: int
    tax_percentage: str | None
    is_active: bool


class FinancialGroupSeed(TypedDict):
    name: str
    parent: str | None


class InvestigativeQuestionSeed(TypedDict):
    text: str
    response_type: str
    options: list[str]
    order: int
    is_active: bool


# Catalog derived from workshop 19 (Hunter), cleaned for product defaults.
# Order of financial groups matters: Departamento Pessoal must be the 5th root
# so payroll codes 5.1.5 / 5.1.11 / 5.1.13 match PAYROLL_COMPONENT_PLAN_CODES.

DEFAULT_PAYMENT_METHODS: list[PaymentMethodSeed] = [
    {"description": "Cartão credito elo 1x", "payment_type": PaymentMethod.PaymentType.CREDIT, "installments_count": 1, "tax_percentage": "4.53", "is_active": True},
    {"description": "Cartão credito elo 3x", "payment_type": PaymentMethod.PaymentType.CREDIT, "installments_count": 3, "tax_percentage": "6.00", "is_active": True},
    {"description": "Cartão credito elo 6x", "payment_type": PaymentMethod.PaymentType.CREDIT, "installments_count": 6, "tax_percentage": "7.83", "is_active": True},
    {"description": "Cartão credito fisica santander", "payment_type": PaymentMethod.PaymentType.CREDIT, "installments_count": 1, "tax_percentage": None, "is_active": True},
    {"description": "Cartão credito juridica santander", "payment_type": PaymentMethod.PaymentType.CREDIT, "installments_count": 1, "tax_percentage": None, "is_active": True},
    {"description": "Cartão credito master/visa a 10x", "payment_type": PaymentMethod.PaymentType.CREDIT, "installments_count": 10, "tax_percentage": "7.99", "is_active": True},
    {"description": "Cartão credito master/visa a 1x", "payment_type": PaymentMethod.PaymentType.CREDIT, "installments_count": 1, "tax_percentage": "2.69", "is_active": True},
    {"description": "Cartão credito master/visa a 2x", "payment_type": PaymentMethod.PaymentType.CREDIT, "installments_count": 2, "tax_percentage": "3.94", "is_active": True},
    {"description": "Cartão credito master/visa a 3x", "payment_type": PaymentMethod.PaymentType.CREDIT, "installments_count": 3, "tax_percentage": "4.46", "is_active": True},
    {"description": "Cartão credito master/visa a 4x", "payment_type": PaymentMethod.PaymentType.CREDIT, "installments_count": 4, "tax_percentage": "4.98", "is_active": True},
    {"description": "Cartão credito master/visa a 5x", "payment_type": PaymentMethod.PaymentType.CREDIT, "installments_count": 5, "tax_percentage": "5.49", "is_active": True},
    {"description": "Cartão credito master/visa a 6x", "payment_type": PaymentMethod.PaymentType.CREDIT, "installments_count": 6, "tax_percentage": "5.99", "is_active": True},
    {"description": "Cartão credito master/visa a 8x", "payment_type": PaymentMethod.PaymentType.CREDIT, "installments_count": 8, "tax_percentage": "6.99", "is_active": True},
    {"description": "Cartão de credito juros por conta do cliente", "payment_type": PaymentMethod.PaymentType.CREDIT, "installments_count": 1, "tax_percentage": "1.00", "is_active": True},
    {"description": "Cartão de credito porto seguro", "payment_type": PaymentMethod.PaymentType.CREDIT, "installments_count": 1, "tax_percentage": None, "is_active": True},
    {"description": "Cartão debito elo", "payment_type": PaymentMethod.PaymentType.CREDIT, "installments_count": 1, "tax_percentage": "1.00", "is_active": True},
    {"description": "Cartão debito master/visa", "payment_type": PaymentMethod.PaymentType.BOTH, "installments_count": 1, "tax_percentage": "0.75", "is_active": True},
    {"description": "Dinheiro a vista", "payment_type": PaymentMethod.PaymentType.BOTH, "installments_count": 1, "tax_percentage": None, "is_active": True},
    {"description": "Garantia interna", "payment_type": PaymentMethod.PaymentType.CREDIT, "installments_count": 1, "tax_percentage": None, "is_active": True},
    {"description": "Transferencia bancaria ou pix", "payment_type": PaymentMethod.PaymentType.BOTH, "installments_count": 1, "tax_percentage": None, "is_active": True},
    {"description": "Cartão credito master/visa a 7x", "payment_type": PaymentMethod.PaymentType.CREDIT, "installments_count": 7, "tax_percentage": None, "is_active": True},
    {"description": "Boleto", "payment_type": PaymentMethod.PaymentType.BOTH, "installments_count": 1, "tax_percentage": None, "is_active": True},
]

DEFAULT_FINANCIAL_GROUPS: list[FinancialGroupSeed] = [
    {"name": "Aporte Financeiro", "parent": None},
    {"name": "Compras Para Uso Interno", "parent": None},
    {"name": "Equipamentos e Mobiliario (Ativos)", "parent": "Compras Para Uso Interno"},
    {"name": "Ferramentas Para Oficina", "parent": "Compras Para Uso Interno"},
    {"name": "Reforma e Melhorias Prediais", "parent": "Compras Para Uso Interno"},
    {"name": "Contas Fixas", "parent": None},
    {"name": "Aluguel Imovel", "parent": "Contas Fixas"},
    {"name": "Conta de Consumo", "parent": "Contas Fixas"},
    {"name": "Agua/ Luz/ Telefone Internet", "parent": "Conta de Consumo"},
    {"name": "Monitoramento e Segurança", "parent": "Conta de Consumo"},
    {"name": "Financiamentos e Emprestimos", "parent": "Contas Fixas"},
    {"name": "Impostos e Guias", "parent": "Contas Fixas"},
    {"name": "Fgts", "parent": "Impostos e Guias"},
    {"name": "Inss", "parent": "Impostos e Guias"},
    {"name": "Iptu Imovel", "parent": "Impostos e Guias"},
    {"name": "Simples Nacional", "parent": "Impostos e Guias"},
    {"name": "Sindicato", "parent": "Impostos e Guias"},
    {"name": "Tarifas Bancárias", "parent": "Impostos e Guias"},
    {"name": "Taxa Licença Funcionamento", "parent": "Impostos e Guias"},
    {"name": "Marketing e Propaganda", "parent": "Contas Fixas"},
    {"name": "Seguro", "parent": "Contas Fixas"},
    {"name": "Sistemas", "parent": "Contas Fixas"},
    {"name": "Contas Variáveis", "parent": None},
    {"name": "Fornecedores de Peças", "parent": "Contas Variáveis"},
    {"name": "Fornecedores de Serviços", "parent": "Contas Variáveis"},
    {"name": "Taxa de Maquininhas", "parent": "Contas Variáveis"},
    {"name": "Transporte e Fretes", "parent": "Contas Variáveis"},
    {"name": "Motoboy Tercerizado", "parent": "Transporte e Fretes"},
    {"name": "Uber/ Lalamove", "parent": "Transporte e Fretes"},
    {"name": "Departamento Pessoal", "parent": None},
    {"name": "Despesas Trabalhistas", "parent": "Departamento Pessoal"},
    {"name": "13º Terceiro Salário", "parent": "Despesas Trabalhistas"},
    {"name": "Alimentação Funcionarios", "parent": "Despesas Trabalhistas"},
    {"name": "Alimentação Socios", "parent": "Despesas Trabalhistas"},
    {"name": "Combustivel Veículos Empresa", "parent": "Despesas Trabalhistas"},
    {"name": "Comissão", "parent": "Despesas Trabalhistas"},
    {"name": "Contabilidade", "parent": "Despesas Trabalhistas"},
    {"name": "Cursos e Treinamentos", "parent": "Despesas Trabalhistas"},
    {"name": "Férias", "parent": "Despesas Trabalhistas"},
    {"name": "Horas Extras Mensais", "parent": "Despesas Trabalhistas"},
    {"name": "Recisão Trabalhista", "parent": "Despesas Trabalhistas"},
    {"name": "Salarios Mensais", "parent": "Despesas Trabalhistas"},
    {"name": "Segurança e Saude Ocupacional", "parent": "Despesas Trabalhistas"},
    {"name": "Vale Transporte de Funcionários", "parent": "Despesas Trabalhistas"},
    {"name": "Retirada Mensal Proprietário", "parent": "Departamento Pessoal"},
    {"name": "Material de Consumo Interno (Insumos)", "parent": None},
    {"name": "Materiais de Escritório", "parent": "Material de Consumo Interno (Insumos)"},
    {"name": "Materiais de Limpeza", "parent": "Material de Consumo Interno (Insumos)"},
    {"name": "Materiais de Oficina", "parent": "Material de Consumo Interno (Insumos)"},
    {"name": "Prejuizos e Garantias", "parent": None},
    {"name": "Garantias de Ordens de Servicos", "parent": "Prejuizos e Garantias"},
    {"name": "Servicos Terceiros Prejuizos (Funilaria e Etc)", "parent": "Prejuizos e Garantias"},
    {"name": "Transferencia Entre Contas", "parent": None},
    {"name": "Veiculos/ Multas e Taxas", "parent": None},
    {"name": "Vendas", "parent": None},
    {"name": "Despesas", "parent": None},
    {"name": "Folha de Pagamento", "parent": "Despesas"},
]

DEFAULT_INVESTIGATIVE_QUESTIONS: list[InvestigativeQuestionSeed] = [
    {
        "text": "Veículo possui seguro?",
        "response_type": InvestigativeQuestion.ResponseType.BOOLEAN,
        "options": [],
        "order": 0,
        "is_active": True,
    },
    {
        "text": "Este problema já ocorreu antes?",
        "response_type": InvestigativeQuestion.ResponseType.MULTIPLE_CHOICE,
        "options": ["Primeira vez", "Já aconteceu algumas vezes", "Acontece sempre", "Não sei informar"],
        "order": 1,
        "is_active": True,
    },
    {
        "text": "Há quanto tempo este problema começou?",
        "response_type": InvestigativeQuestion.ResponseType.MULTIPLE_CHOICE,
        "options": ["Hoje/Ontem", "Esta semana", "Este mês", "Há mais de um mês", "Não lembro"],
        "order": 2,
        "is_active": True,
    },
    {
        "text": "Já levou este veículo em outras oficinas para este problema?",
        "response_type": InvestigativeQuestion.ResponseType.MULTIPLE_CHOICE,
        "options": ["Não", "Sim", "Apenas em uma oficina", "Em mais de uma oficina"],
        "order": 3,
        "is_active": True,
    },
    {
        "text": "O veículo está fazendo algum ruído estranho?",
        "response_type": InvestigativeQuestion.ResponseType.BOOLEAN,
        "options": [],
        "order": 4,
        "is_active": True,
    },
    {
        "text": "Acende alguma luz de aviso no painel?",
        "response_type": InvestigativeQuestion.ResponseType.MULTIPLE_CHOICE,
        "options": ["Injeção eletronica", "ABS", "airbag", "outros"],
        "order": 5,
        "is_active": True,
    },
    {
        "text": "Você sente o carro fraco ou falhando?",
        "response_type": InvestigativeQuestion.ResponseType.BOOLEAN,
        "options": [],
        "order": 6,
        "is_active": True,
    },
]


def create_default_workshop_setup(*, workshop: Workshop) -> dict[str, int]:
    """Idempotente: cria formas de pagamento, grupos financeiros e perguntas padrão."""
    return {
        "payment_methods_created": _create_default_payment_methods(workshop=workshop),
        "financial_groups_created": _create_default_financial_groups(workshop=workshop),
        "investigative_questions_created": _create_default_investigative_questions(workshop=workshop),
    }


def _create_default_payment_methods(*, workshop: Workshop) -> int:
    created = 0
    for seed in DEFAULT_PAYMENT_METHODS:
        tax_percentage = Decimal(seed["tax_percentage"]) if seed["tax_percentage"] is not None else None
        _, was_created = PaymentMethod.objects.get_or_create(
            workshop=workshop,
            description=seed["description"],
            defaults={
                "payment_type": seed["payment_type"],
                "installments_count": seed["installments_count"],
                "tax_percentage": tax_percentage,
                "is_active": seed["is_active"],
            },
        )
        if was_created:
            created += 1
    return created


def _create_default_financial_groups(*, workshop: Workshop) -> int:
    created = 0
    groups_by_name: dict[str, FinancialGroup] = {group.name: group for group in FinancialGroup.objects.filter(workshop=workshop).select_related("parent")}

    for seed in DEFAULT_FINANCIAL_GROUPS:
        parent_name = seed["parent"]
        parent = groups_by_name.get(parent_name) if parent_name else None
        if parent_name and parent is None:
            raise ValueError(f"Grupo pai '{parent_name}' não encontrado ao criar '{seed['name']}'.")

        existing = next(
            (group for group in groups_by_name.values() if group.name == seed["name"] and getattr(group, "parent_id", None) == (parent.pk if parent else None)),
            None,
        )
        if existing is not None:
            groups_by_name[seed["name"]] = existing
            continue

        new_group = FinancialGroup.objects.create(
            workshop=workshop,
            parent=parent,
            name=seed["name"],
            is_active=True,
        )
        groups_by_name[seed["name"]] = new_group
        created += 1
    return created


def _create_default_investigative_questions(*, workshop: Workshop) -> int:
    created = 0
    for seed in DEFAULT_INVESTIGATIVE_QUESTIONS:
        _, was_created = InvestigativeQuestion.objects.get_or_create(
            workshop=workshop,
            text=seed["text"],
            defaults={
                "response_type": seed["response_type"],
                "options": seed["options"],
                "order": seed["order"],
                "is_active": seed["is_active"],
            },
        )
        if was_created:
            created += 1
    return created
