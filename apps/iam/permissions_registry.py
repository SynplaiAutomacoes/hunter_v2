from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PermissionInfo:
    visible: bool = True
    auto_grant: bool = False
    description: str = ""


REGISTRY: dict[tuple[str, str], PermissionInfo] = {
    # ---- Contas ----
    ("accounts", "user"): PermissionInfo(
        visible=True,
        description="Gerenciar usuários da conta: criar, editar, ativar/desativar e controlar o acesso ao sistema.",
    ),
    ("accounts", "account"): PermissionInfo(
        visible=True,
        description="Gerenciar os dados da conta empresarial: razão social, CNPJ, endereço e configurações gerais.",
    ),
    ("accounts", "favoritepage"): PermissionInfo(
        visible=True,
        description="Gerenciar páginas favoritas dos usuários para acesso rápido às funcionalidades mais usadas.",
    ),
    ("accounts", "passwordresettoken"): PermissionInfo(visible=False, auto_grant=False),
    ("accounts", "logincodetoken"): PermissionInfo(visible=False, auto_grant=False),
    # ---- Orçamentos ----
    ("budget", "budget"): PermissionInfo(
        visible=True,
        description="Gerenciar orçamentos: criar propostas para clientes, aprovar, revisar valores e prazos dos serviços.",
    ),
    ("budget", "defect"): PermissionInfo(
        visible=True,
        description="Gerenciar defeitos identificados nos veículos durante o processo de orçamento.",
    ),
    ("budget", "budgetitem"): PermissionInfo(
        visible=True,
        description="Gerenciar os itens dentro dos orçamentos: produtos, serviços e seus respectivos valores.",
    ),
    ("budget", "budgetimage"): PermissionInfo(
        visible=True,
        description="Gerenciar imagens anexadas aos orçamentos para registro visual dos serviços.",
    ),
    ("budget", "budgetkititemoverride"): PermissionInfo(visible=False, auto_grant=True),
    ("budget", "budgethistory"): PermissionInfo(visible=False, auto_grant=True),
    # ---- Catálogos ----
    ("catalog", "cataloggroup"): PermissionInfo(
        visible=True,
        description="Gerenciar grupos e categorias para organizar produtos e serviços no catálogo.",
    ),
    ("catalog", "product"): PermissionInfo(
        visible=True,
        description="Gerenciar produtos do catálogo: criar, editar preços e configurar controle de estoque.",
    ),
    ("catalog", "service"): PermissionInfo(
        visible=True,
        description="Gerenciar serviços prestados: mão de obra, valores e tempo estimado de execução.",
    ),
    ("catalog", "kit"): PermissionInfo(
        visible=True,
        description="Gerenciar kits: combos de produtos e serviços para agilizar a criação de orçamentos.",
    ),
    ("catalog", "kitapplication"): PermissionInfo(
        visible=True,
        description="Gerenciar aplicações dos kits por modelo de veículo.",
    ),
    ("catalog", "kitproduct"): PermissionInfo(
        visible=True,
        description="Gerenciar produtos vinculados aos kits do catálogo.",
    ),
    ("catalog", "kitservice"): PermissionInfo(
        visible=True,
        description="Gerenciar serviços vinculados aos kits do catálogo.",
    ),
    ("catalog", "fipevehiclebrand"): PermissionInfo(visible=False, auto_grant=True),
    ("catalog", "fipevehiclemodel"): PermissionInfo(visible=False, auto_grant=True),
    ("catalog", "fipemodelfuelcache"): PermissionInfo(visible=False, auto_grant=True),
    ("catalog", "fipesyncstate"): PermissionInfo(visible=False, auto_grant=True),
    # ---- Checklists ----
    ("checklist", "checklist"): PermissionInfo(
        visible=True,
        description="Gerenciar checklists de vistoria utilizados no recebimento e na entrega de veículos.",
    ),
    ("checklist", "checklistitem"): PermissionInfo(
        visible=True,
        description="Gerenciar itens dos checklists de vistoria.",
    ),
    # ---- Colaboradores ----
    ("collaborators", "workshopmember"): PermissionInfo(visible=False, auto_grant=True),
    ("collaborators", "workshopcollaborator"): PermissionInfo(
        visible=True,
        description="Gerenciar colaboradores da oficina: dados cadastrais, funções e vínculo.",
    ),
    ("collaborators", "collaboratorbenefit"): PermissionInfo(
        visible=True,
        description="Gerenciar benefícios oferecidos aos colaboradores.",
    ),
    ("collaborators", "collaboratorpayroll"): PermissionInfo(
        visible=True,
        description="Gerenciar a folha de pagamento dos colaboradores.",
    ),
    ("collaborators", "collaboratorpayrollitem"): PermissionInfo(
        visible=True,
        description="Gerenciar os itens que compõem a folha de pagamento.",
    ),
    ("collaborators", "collaboratorcommissionentry"): PermissionInfo(
        visible=True,
        description="Gerenciar lançamentos de comissão dos colaboradores.",
    ),
    # ---- Clientes ----
    ("customer", "customer"): PermissionInfo(
        visible=True,
        description="Gerenciar clientes: cadastro, histórico de serviços e veículos associados.",
    ),
    ("customer", "vehicle"): PermissionInfo(
        visible=True,
        description="Gerenciar veículos dos clientes: placa, marca, modelo e associação ao cliente.",
    ),
    # ---- Financeiro ----
    ("finance", "paymentmethod"): PermissionInfo(
        visible=True,
        description="Gerenciar formas de pagamento disponíveis no sistema.",
    ),
    ("finance", "bankaccount"): PermissionInfo(
        visible=True,
        description="Gerenciar contas bancárias da empresa.",
    ),
    ("finance", "financialgroup"): PermissionInfo(
        visible=True,
        description="Gerenciar grupos financeiros para categorizar receitas e despesas.",
    ),
    ("finance", "financialmovement"): PermissionInfo(
        visible=True,
        description="Gerenciar movimentações financeiras: lançamentos de receitas, despesas e conciliação.",
    ),
    ("finance", "movementgroup"): PermissionInfo(visible=False, auto_grant=True),
    ("finance", "taxclassnfe"): PermissionInfo(
        visible=True,
        description="Gerenciar classes fiscais para emissão de Notas Fiscais (NF-e).",
    ),
    ("finance", "taxclassnfeicmsscenario"): PermissionInfo(visible=False, auto_grant=True),
    ("finance", "taxclassnfeipiscenario"): PermissionInfo(visible=False, auto_grant=True),
    ("finance", "taxclassnfepisscenario"): PermissionInfo(visible=False, auto_grant=True),
    ("finance", "taxclassnfecofinsscenario"): PermissionInfo(visible=False, auto_grant=True),
    ("finance", "taxclassnfse"): PermissionInfo(visible=False, auto_grant=True),
    ("finance", "taxclasssyncstate"): PermissionInfo(visible=False, auto_grant=True),
    ("finance", "taxclasspreset"): PermissionInfo(
        visible=True,
        description="Gerenciar presets de classes fiscais para agilizar a configuração tributária.",
    ),
    ("finance", "webmaniacompany"): PermissionInfo(visible=False, auto_grant=True),
    ("finance", "nfserequest"): PermissionInfo(visible=False, auto_grant=True),
    ("finance", "nferequest"): PermissionInfo(visible=False, auto_grant=True),
    ("finance", "nfsebatch"): PermissionInfo(visible=False, auto_grant=True),
    ("finance", "nfseitem"): PermissionInfo(visible=False, auto_grant=True),
    ("finance", "nfeitem"): PermissionInfo(visible=False, auto_grant=True),
    ("finance", "webmaniawebhookevent"): PermissionInfo(visible=False, auto_grant=True),
    # ---- Estoque ----
    ("stock", "stockproduct"): PermissionInfo(
        visible=True,
        description="Gerenciar produtos no estoque: controle de entrada, saída e quantidade.",
    ),
    ("stock", "stockmovement"): PermissionInfo(
        visible=True,
        description="Gerenciar movimentações de estoque: ajustes manuais, entradas e saídas.",
    ),
    ("stock", "stockpaymentmethod"): PermissionInfo(
        visible=True,
        description="Gerenciar formas de pagamento utilizadas nas movimentações de estoque.",
    ),
    ("stock", "sefazzipcache"): PermissionInfo(visible=False, auto_grant=True),
    ("stock", "stockimport"): PermissionInfo(
        visible=True,
        description="Gerenciar importações de estoque a partir de arquivos.",
    ),
    ("stock", "stocktransfer"): PermissionInfo(
        visible=True,
        description="Gerenciar transferências de produtos entre oficinas ou depósitos.",
    ),
    # ---- IAM ----
    ("iam", "workshoprole"): PermissionInfo(
        visible=True,
        description="Gerenciar cargos e permissões de acesso ao sistema.",
    ),
    # ---- Mensagens ----
    ("messaging", "messagetemplate"): PermissionInfo(
        visible=True,
        description="Gerenciar modelos de mensagens para envio via WhatsApp.",
    ),
    ("messaging", "customermessagegroup"): PermissionInfo(
        visible=True,
        description="Gerenciar grupos de clientes para disparo de mensagens em lote.",
    ),
    ("messaging", "customermessagegroupmembership"): PermissionInfo(
        visible=True,
        description="Gerenciar a associação de clientes aos grupos de mensagem.",
    ),
    # ---- Triagem ----
    ("quote", "investigativequestion"): PermissionInfo(
        visible=True,
        description="Gerenciar perguntas investigativas usadas na triagem de serviços.",
    ),
    ("quote", "investigativeresponse"): PermissionInfo(
        visible=True,
        description="Gerenciar respostas das perguntas investigativas.",
    ),
    # ---- Agendamentos ----
    ("scheduling", "appointment"): PermissionInfo(
        visible=True,
        description="Gerenciar agendamentos de serviços para os clientes.",
    ),
    # ---- Origens ----
    ("sources", "source"): PermissionInfo(
        visible=True,
        description="Gerenciar origens de captação e cadastro de clientes.",
    ),
    # ---- Fornecedores ----
    ("suppliers", "supplier"): PermissionInfo(
        visible=True,
        description="Gerenciar fornecedores de produtos e serviços.",
    ),
    # ---- Ordens de Serviço ----
    ("workorder", "workorder"): PermissionInfo(
        visible=True,
        description="Gerenciar ordens de serviço: abertura, execução, faturamento e entrega dos serviços.",
    ),
    ("workorder", "workorderpaymentmethod"): PermissionInfo(
        visible=True,
        description="Gerenciar planos de pagamento vinculados às ordens de serviço.",
    ),
    ("workorder", "workorderattachment"): PermissionInfo(
        visible=True,
        description="Gerenciar imagens e arquivos anexados às ordens de serviço.",
    ),
    ("workorder", "workorderitem"): PermissionInfo(
        visible=True,
        description="Gerenciar os itens executados nas ordens de serviço.",
    ),
    ("workorder", "workorderkititemoverride"): PermissionInfo(visible=False, auto_grant=True),
    ("workorder", "workorderhistory"): PermissionInfo(visible=False, auto_grant=True),
    # ---- Oficinas ----
    ("workshops", "workshop"): PermissionInfo(
        visible=True,
        description="Gerenciar os dados da oficina: endereço, contato e configurações operacionais.",
    ),
    ("workshops", "monthlycost"): PermissionInfo(
        visible=True,
        description="Gerenciar custos mensais fixos da oficina.",
    ),
    ("workshops", "workshopcost"): PermissionInfo(
        visible=True,
        description="Gerenciar custos variáveis e despesas da oficina.",
    ),
    ("workshops", "workshopcostitem"): PermissionInfo(
        visible=True,
        description="Gerenciar itens que compõem os custos da oficina.",
    ),
    ("workshops", "workshopcostworkday"): PermissionInfo(
        visible=True,
        description="Gerenciar dias trabalhados para apuração de custos operacionais.",
    ),
    ("workshops", "workshopcostholiday"): PermissionInfo(visible=False, auto_grant=True),
}


def get_perm_info(app_label: str, model: str) -> PermissionInfo:
    return REGISTRY.get((app_label, model.lower()), PermissionInfo())


def is_visible(app_label: str, model: str) -> bool:
    return get_perm_info(app_label, model).visible


def is_auto_grant(app_label: str, model: str) -> bool:
    info = get_perm_info(app_label, model)
    return not info.visible and info.auto_grant


def get_description(app_label: str, model: str) -> str:
    return get_perm_info(app_label, model).description
