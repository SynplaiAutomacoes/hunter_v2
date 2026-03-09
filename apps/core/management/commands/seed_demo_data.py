from __future__ import annotations

import random
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from itertools import cycle

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from djmoney.money import Money

from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.kits import Kit, KitProduct, KitService
from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.checklist.models import Checklist, ChecklistItem
from apps.collaborators.models import WorkshopCollaborator
from apps.customer.models import Customer
from apps.quote.models.investigative_questions import InvestigativeQuestion
from apps.stock.models import StockProduct
from apps.suppliers.models import Supplier
from apps.workshops.models.monthly_costs import MonthlyCost
from apps.workshops.models.workshop_costs import WorkshopCost, WorkshopCostItem
from apps.workshops.models.workshops import Workshop
from apps.workshops.util.monthly_costs import DEFAULT_MONTHLY_COSTS, MECHANIC_SALARY_MONTHLY_COST_NAME

WORKSHOP_ID = 1
DEFAULT_SEED = 20260309
BRL = "BRL"
PRICE_QUANTIZER = Decimal("0.01")
MARGIN_QUANTIZER = Decimal("0.000001")

CHECKLIST_RESPONSE_BRR = "BOM_REGULAR_RUIM"
CHECKLIST_RESPONSE_SIM_NAO = "SIM_NAO"
CHECKLIST_RESPONSE_TEXT = "TEXTO_LIVRE"
CHECKLIST_RESPONSE_LEVEL = "NIVEL"

CITY_STATE_POOL: tuple[tuple[str, str], ...] = (
    ("Sao Paulo", "SP"),
    ("Campinas", "SP"),
    ("Santos", "SP"),
    ("Sorocaba", "SP"),
    ("Jundiai", "SP"),
    ("Guarulhos", "SP"),
    ("Santo Andre", "SP"),
    ("Curitiba", "PR"),
    ("Joinville", "SC"),
    ("Belo Horizonte", "MG"),
    ("Porto Alegre", "RS"),
    ("Londrina", "PR"),
)

NEIGHBORHOODS: tuple[str, ...] = (
    "Centro",
    "Boa Vista",
    "Ipiranga",
    "Mooca",
    "Pauliceia",
    "Jardim Europa",
    "Vila Nova",
    "Sao Jose",
    "Bela Vista",
    "Santa Luzia",
    "Industrial",
    "Jardim Flora",
)

STREETS: tuple[str, ...] = (
    "Rua das Oficinas",
    "Avenida Brasil",
    "Rua do Comercio",
    "Rua Nove de Julho",
    "Avenida Independencia",
    "Rua Sao Jose",
    "Rua dos Pinhais",
    "Rua Tiradentes",
    "Avenida Atlantica",
    "Rua do Carmo",
    "Rua das Mangueiras",
    "Rua Bento Freitas",
)

COMPLEMENTS: tuple[str | None, ...] = (
    None,
    None,
    None,
    "Sala 2",
    "Fundos",
    "Loja 3",
    "Galpao B",
    None,
)

EMAIL_DOMAINS: tuple[str, ...] = (
    "gmail.com",
    "outlook.com",
    "uol.com.br",
    "terra.com.br",
)

DDD_POOL: tuple[int, ...] = (11, 19, 21, 31, 41, 47, 48, 51, 54)

PF_CUSTOMERS: tuple[tuple[str, str], ...] = (
    ("Bruno Araujo", "M"),
    ("Camila Pereira", "F"),
    ("Daniel Rocha", "M"),
    ("Fernanda Lima", "F"),
    ("Gabriel Martins", "M"),
    ("Juliana Costa", "F"),
    ("Leandro Alves", "M"),
    ("Marina Duarte", "F"),
    ("Rafael Nogueira", "M"),
    ("Tatiane Ribeiro", "F"),
)

PJ_CUSTOMERS: tuple[tuple[str, str], ...] = (
    ("Auto Center Horizonte Ltda", "Horizonte Auto Center"),
    ("Transportes Vale Forte Ltda", "Vale Forte Frotas"),
    ("Padaria Pao do Bairro Ltda", "Pao do Bairro"),
    ("Construtora Atria Sul Ltda", "Atria Sul Obras"),
    ("Clinica Sao Lucas Servicos Medicos", "Clinica Sao Lucas"),
    ("Techlog Solucoes em Campo Ltda", "Techlog Campo"),
    ("Mercado Santa Clara Ltda", "Mercado Santa Clara"),
    ("Agro Serra Verde Comercio Ltda", "Serra Verde Agro"),
    ("Instaladora Prisma Energia Ltda", "Prisma Energia"),
    ("Floricultura Jardim Vivo Ltda", "Jardim Vivo"),
)

COLLABORATOR_NAMES: tuple[tuple[str, str], ...] = (
    ("Andre Farias", "M"),
    ("Bianca Mello", "F"),
    ("Carlos Vinicius", "M"),
    ("Diego Moraes", "M"),
    ("Eduardo Prado", "M"),
    ("Felipe Bastos", "M"),
    ("Gustavo Pires", "M"),
    ("Helena Moraes", "F"),
    ("Igor Rezende", "M"),
    ("Joana Campos", "F"),
    ("Kaique Teles", "M"),
    ("Larissa Azevedo", "F"),
    ("Marcelo Vieira", "M"),
    ("Natalia Freitas", "F"),
    ("Otavio Borges", "M"),
    ("Paula Mota", "F"),
    ("Ricardo Tavares", "M"),
    ("Simone Rocha", "F"),
    ("Thiago Furtado", "M"),
    ("Vanessa Brito", "F"),
    ("Wesley Matos", "M"),
    ("Yasmin Duarte", "F"),
    ("Alan Cardoso", "M"),
    ("Renata Lisboa", "F"),
    ("Victor Meireles", "M"),
)

SUPPLIER_SPECS: tuple[tuple[str, str, str], ...] = (
    ("Distribuidora Via Pistao", "Marcio Sales", "vendas@viapistao.com.br"),
    ("Nova Torque Autopecas", "Elaine Braga", "comercial@novatorque.com.br"),
    ("Prime Lub Auto Supply", "Joao Teles", "atendimento@primelub.com.br"),
    ("Frente Sul Componentes", "Carla Nunes", "contato@frentesul.com.br"),
    ("Casa do Radiador Paulista", "Rogeria Leal", "pedidos@radiadorpaulista.com.br"),
)

PRODUCTIVE_POSITIONS: tuple[str, ...] = (
    "Mecanico pleno",
    "Mecanico diesel",
    "Mecanico chefe",
    "Eletricista automotivo",
    "Alinhador tecnico",
    "Tecnico de diagnostico",
    "Lubrificador",
)

ADMINISTRATIVE_POSITIONS: tuple[str, ...] = (
    "Consultor tecnico",
    "Recepcionista",
    "Estoquista",
    "Assistente financeiro",
    "Comprador",
    "Gerente operacional",
)


@dataclass(frozen=True)
class ProductSpec:
    code: str
    group_name: str
    name: str
    description: str
    unit: str
    brand: str
    model: str
    cost_price: Decimal
    selling_price: Decimal
    location: str
    application: str


@dataclass(frozen=True)
class ServiceSpec:
    name: str
    description: str
    duration: timedelta
    suggested_cost: Decimal
    selling_price: Decimal
    is_third_party: bool = False


@dataclass(frozen=True)
class KitProductSpec:
    code: str
    quantity: int = 1


@dataclass(frozen=True)
class KitServiceSpec:
    name: str
    quantity: int = 1
    duration: timedelta | None = None


@dataclass(frozen=True)
class KitSpec:
    name: str
    description: str
    products: tuple[KitProductSpec, ...]
    services: tuple[KitServiceSpec, ...]


@dataclass(frozen=True)
class ChecklistBlueprint:
    name: str
    groups: tuple[str, ...]
    item_count: int


@dataclass(frozen=True)
class QuestionSpec:
    text: str
    response_type: str
    options: tuple[str, ...] = ()


def _decimal(value: Decimal | str | int | float) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _money(value: Decimal | str | int | float) -> Money:
    amount = _decimal(value).quantize(PRICE_QUANTIZER, rounding=ROUND_HALF_UP)
    return Money(amount, BRL)


def _margin(cost_price: Decimal, selling_price: Decimal) -> Decimal:
    if cost_price <= 0:
        return Decimal("0.000000")
    return ((selling_price - cost_price) / cost_price).quantize(MARGIN_QUANTIZER, rounding=ROUND_HALF_UP)


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(char for char in normalized if not unicodedata.combining(char)).casefold().strip()


def _slugify(value: str) -> str:
    chars: list[str] = []
    previous_dot = False
    for char in value.lower().strip():
        if char.isalnum():
            chars.append(char)
            previous_dot = False
            continue
        if not previous_dot:
            chars.append(".")
            previous_dot = True
    return "".join(chars).strip(".") or "contato"


def _email_from_name(name: str, index: int) -> str:
    local_part = _slugify(name)
    domain = EMAIL_DOMAINS[index % len(EMAIL_DOMAINS)]
    return f"{local_part}@{domain}"


def _mobile_phone(index: int) -> str:
    ddd = DDD_POOL[index % len(DDD_POOL)]
    subscriber = 900000000 + ((index * 13791) % 100000000)
    return f"+55{ddd}{subscriber:09d}"


def _landline_phone(index: int) -> str:
    ddd = DDD_POOL[index % len(DDD_POOL)]
    subscriber = 30000000 + ((index * 7919) % 10000000)
    return f"+55{ddd}{subscriber:08d}"


def _postal_code(index: int) -> str:
    prefix = 10000 + ((index * 137) % 89999)
    suffix = 100 + ((index * 29) % 899)
    return f"{prefix:05d}-{suffix:03d}"


def _address(index: int) -> dict[str, object]:
    city, state = CITY_STATE_POOL[index % len(CITY_STATE_POOL)]
    return {
        "cep": _postal_code(index),
        "logradouro": STREETS[index % len(STREETS)],
        "numero": 50 + ((index * 17) % 850),
        "complemento": COMPLEMENTS[index % len(COMPLEMENTS)],
        "bairro": NEIGHBORHOODS[(index * 3) % len(NEIGHBORHOODS)],
        "cidade": city,
        "estado": state,
    }


def _format_cpf(digits: str) -> str:
    return f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}"


def _format_cnpj(digits: str) -> str:
    return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"


def _generate_cpf(index: int) -> str:
    base = f"{123456789 + index * 97:09d}"[-9:]
    if len(set(base)) == 1:
        base = "123456789"
    digits = [int(char) for char in base]

    total = sum(number * weight for number, weight in zip(digits, range(10, 1, -1), strict=False))
    first_digit = ((total * 10) % 11) % 10
    digits.append(first_digit)

    total = sum(number * weight for number, weight in zip(digits, range(11, 1, -1), strict=False))
    second_digit = ((total * 10) % 11) % 10
    return _format_cpf(f"{base}{first_digit}{second_digit}")


def _generate_cnpj(index: int) -> str:
    base = f"{index + 1:08d}0001"
    digits = [int(char) for char in base]
    first_weights = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    second_weights = [6] + first_weights

    total = sum(number * weight for number, weight in zip(digits, first_weights, strict=False))
    remainder = total % 11
    first_digit = 0 if remainder < 2 else 11 - remainder
    digits.append(first_digit)

    total = sum(number * weight for number, weight in zip(digits, second_weights, strict=False))
    remainder = total % 11
    second_digit = 0 if remainder < 2 else 11 - remainder
    return _format_cnpj(f"{base}{first_digit}{second_digit}")


def _reference_month(reference_date: date, months_back: int) -> tuple[int, int]:
    month_index = (reference_date.year * 12) + reference_date.month - 1 - months_back
    year = month_index // 12
    month = (month_index % 12) + 1
    return month, year


def _build_product_specs() -> list[ProductSpec]:
    raw_groups = (
        (
            "Lubrificantes",
            (
                ("Oleo sintetico 5W30 1L", "Lubrificante para motores flex de baixa friccao.", Product.Unit.LT, "Lubrax", "Valora", "29.90", "54.90", "A1-01", "Motores 1.0 a 2.0 flex."),
                ("Oleo semissintetico 10W40 1L", "Oleo para motores com uso urbano intenso.", Product.Unit.LT, "Mobil", "Super 2000", "24.50", "46.90", "A1-02", "Modelos com kilometragem intermediaria."),
                ("Fluido de freio DOT4 500ml", "Fluido hidraulico para sistema de freio.", Product.Unit.UND, "Bosch", "DOT4", "16.90", "34.90", "A1-03", "Veiculos leves nacionais e importados."),
                ("Aditivo para radiador organico 1L", "Aditivo concentrado para arrefecimento.", Product.Unit.LT, "Radiex", "Long Life", "18.90", "39.90", "A1-04", "Sistemas de arrefecimento com agua desmineralizada."),
            ),
        ),
        (
            "Filtros",
            (
                ("Filtro de oleo blindado", "Filtro rosqueavel para trocas periodicas.", Product.Unit.UND, "Tecfil", "PSL55", "19.80", "42.90", "B1-01", "Aplicacao em motores flex de manutencao rapida."),
                ("Filtro de ar do motor", "Elemento filtrante de papel resinada.", Product.Unit.UND, "Tecfil", "ARL4156", "21.40", "44.90", "B1-02", "Motores aspirados de uso urbano."),
                ("Filtro de cabine com carvao", "Filtro interno com camada antiodor.", Product.Unit.UND, "Mann", "CUK26009", "28.50", "59.90", "B1-03", "Sistemas de ventilacao com filtro interno."),
                ("Filtro de combustivel flex", "Filtro de linha para combustivel com etanol.", Product.Unit.UND, "Mahle", "KL582", "23.10", "48.90", "B1-04", "Aplicacao em linhas flex com manutencao preventiva."),
            ),
        ),
        (
            "Freios",
            (
                ("Pastilha de freio dianteira ceramica", "Jogo de pastilhas com baixo ruido.", Product.Unit.JG, "Fras-le", "Ceramic", "78.00", "159.90", "C1-01", "Hatches e sedans compactos."),
                ("Pastilha de freio traseira premium", "Pastilha para eixo traseiro com alto rendimento.", Product.Unit.JG, "Cobreq", "Topline", "64.00", "129.90", "C1-02", "Sedans medios com freio a disco traseiro."),
                ("Disco de freio ventilado dianteiro", "Disco ventilado para melhor dissipacao termica.", Product.Unit.PC, "Fremax", "Vent Max", "118.00", "229.90", "C1-03", "Eixo dianteiro de veiculos leves."),
                ("Sapata de freio traseira", "Jogo de sapatas para freio a tambor.", Product.Unit.JG, "Syl", "Duratec", "58.00", "119.90", "C1-04", "Aplicacao em eixo traseiro com tambor."),
            ),
        ),
        (
            "Suspensao",
            (
                ("Amortecedor dianteiro pressurizado", "Amortecedor dianteiro com carga de gas.", Product.Unit.PC, "Cofap", "TurboGas", "189.00", "369.90", "D1-01", "Compactos e sedans de uso misto."),
                ("Amortecedor traseiro pressurizado", "Amortecedor traseiro com resposta progressiva.", Product.Unit.PC, "Monroe", "Oespectrum", "162.00", "319.90", "D1-02", "Aplicacao em eixo traseiro de passeio."),
                ("Bieleta da barra estabilizadora", "Bieleta com terminais reforcados.", Product.Unit.UND, "Axios", "Heavy Duty", "34.00", "79.90", "D1-03", "Sistema dianteiro com barra estabilizadora."),
                ("Bandeja dianteira completa", "Bandeja com pivor e buchas montadas.", Product.Unit.UND, "Nakata", "Full Arm", "138.00", "289.90", "D1-04", "Suspensao dianteira tipo McPherson."),
            ),
        ),
        (
            "Arrefecimento",
            (
                ("Valvula termostatica", "Valvula para controle de temperatura do motor.", Product.Unit.UND, "Wahler", "Therm 87", "52.00", "109.90", "E1-01", "Motores flex compactos e medios."),
                ("Bomba dagua com junta", "Bomba de circulacao com vedacao inclusa.", Product.Unit.UND, "Urba", "UB075", "96.00", "199.90", "E1-02", "Motores com troca conjunta da correia."),
                ("Reservatorio de expansao", "Reservatorio translucido com tampa.", Product.Unit.UND, "Gonel", "Clear Tank", "46.00", "99.90", "E1-03", "Sistemas de arrefecimento pressurizados."),
                ("Sensor de temperatura do motor", "Sensor de leitura para modulo e painel.", Product.Unit.UND, "Delphi", "TempSense", "39.00", "89.90", "E1-04", "Controle eletrico de arrefecimento."),
            ),
        ),
        (
            "Ignicao",
            (
                ("Vela de ignicao iridium", "Vela de maior vida util para motores modernos.", Product.Unit.UND, "NGK", "Iridium IX", "34.00", "69.90", "F1-01", "Aplicacao em motores flex com bobina individual."),
                ("Jogo de cabos de vela silicone", "Cabos de baixa resistencia com capa siliconada.", Product.Unit.JG, "Delphi", "Silicor", "74.00", "149.90", "F1-02", "Motores com sistema convencional de ignicao."),
                ("Bobina de ignicao compacta", "Bobina para sistema de ignicao eletronica.", Product.Unit.UND, "Bosch", "Compact Coil", "118.00", "239.90", "F1-03", "Motores 1.0 a 1.6 com bobina integrada."),
                ("Bateria 60Ah selada", "Bateria livre de manutencao para uso diario.", Product.Unit.UND, "Heliar", "Free 60", "298.00", "469.90", "F1-04", "Veiculos de passeio com eletrica original."),
            ),
        ),
        (
            "Transmissao",
            (
                ("Kit de embreagem completo", "Kit com disco, plato e rolamento.", Product.Unit.JG, "Luk", "RepSet", "468.00", "829.90", "G1-01", "Transmissoes manuais de hatch e sedan."),
                ("Coxim de cambio dianteiro", "Coxim para reducao de vibracao.", Product.Unit.UND, "Axios", "Hydro", "82.00", "169.90", "G1-02", "Aplicacao em cambio manual e automatizado."),
                ("Oleo ATF sintetico 1L", "Fluido sintetico para transmissoes automaticas.", Product.Unit.LT, "Castrol", "Transmax", "42.00", "84.90", "G1-03", "Cambios automaticos multivias."),
                ("Oleo cambio manual 75W80 1L", "Lubrificante para cambio mecanico.", Product.Unit.LT, "Motul", "Gear 75W80", "38.00", "79.90", "G1-04", "Caixas manuais de uso leve e medio."),
            ),
        ),
        (
            "Eletrica",
            (
                ("Lampada H7 12V 55W", "Lampada halogena para farol principal.", Product.Unit.PC, "Osram", "Original H7", "16.00", "34.90", "H1-01", "Farol baixo e alto em aplicacoes H7."),
                ("Fusivel mini 15A", "Fusivel laminado para reposicao rapida.", Product.Unit.PC, "Bosch", "Mini Fuse", "2.50", "6.90", "H1-02", "Caixa de fusivel interna e cofre do motor."),
                ("Sensor ABS dianteiro", "Sensor de roda para sistema ABS.", Product.Unit.UND, "Ate", "WheelSense", "74.00", "159.90", "H1-03", "Eixo dianteiro com leitura magnetica."),
                ("Rele auxiliar universal", "Rele 12V para comando de circuitos.", Product.Unit.UND, "Kostal", "Mini Relay", "12.00", "29.90", "H1-04", "Ventoinha, farol auxiliar e acessorios."),
            ),
        ),
        (
            "Limpeza",
            (
                ("Palheta silicone 24 pol", "Palheta com lamina siliconada para chuva forte.", Product.Unit.PC, "Valeo", "Silencio", "24.00", "49.90", "I1-01", "Limpadores dianteiros de veiculos medios."),
                ("Limpa contato eletrico 300ml", "Spray para conectores e sensores.", Product.Unit.UND, "Orbi", "Clean Contact", "18.00", "39.90", "I1-02", "Terminais eletricos e chicotes."),
                ("Limpa bicos concentrado 500ml", "Aditivo concentrado para limpeza de injecao.", Product.Unit.UND, "STP", "Injector Clean", "21.00", "44.90", "I1-03", "Aplicacao preventiva em combustivel flex."),
                ("Higienizador de ar interno 200ml", "Aerossol bactericida para cabine.", Product.Unit.UND, "Wurth", "Air Fresh", "17.00", "38.90", "I1-04", "Cabines com ar-condicionado e filtro interno."),
            ),
        ),
        (
            "Acessorios",
            (
                ("Aditivo de combustivel flex", "Aditivo para uso continuo em etanol e gasolina.", Product.Unit.UND, "Bardahl", "Max Fuel", "14.00", "29.90", "J1-01", "Tanques de veiculos flex em uso urbano."),
                ("Trava de roda antifurto", "Jogo com chave segredo para rodas.", Product.Unit.JG, "McGard", "Wheel Lock", "88.00", "169.90", "J1-02", "Rodas de liga leve e uso diario."),
                ("Tapete de borracha universal", "Jogo de tapetes lavaveis para cabine.", Product.Unit.JG, "Keko", "All Weather", "74.00", "149.90", "J1-03", "Hatches, sedans e SUVs compactos."),
                ("Capa de volante couro sintetico", "Capa costurada para melhor pegada.", Product.Unit.UND, "Luxcar", "Soft Grip", "26.00", "54.90", "J1-04", "Volantes padrao aro medio."),
            ),
        ),
    )

    specs: list[ProductSpec] = []
    next_code = 1001
    for group_name, items in raw_groups:
        for name, description, unit, brand, model, cost_price, selling_price, location, application in items:
            specs.append(
                ProductSpec(
                    code=f"PRD-{next_code}",
                    group_name=group_name,
                    name=name,
                    description=description,
                    unit=unit,
                    brand=brand,
                    model=model,
                    cost_price=_decimal(cost_price),
                    selling_price=_decimal(selling_price),
                    location=location,
                    application=application,
                )
            )
            next_code += 1
    return specs


def _build_service_specs() -> list[ServiceSpec]:
    raw_services = (
        ("Troca de oleo do motor", "Troca de lubrificante com conferencia visual de vazamentos.", 40, "55.00", "119.00", False),
        ("Troca do filtro de oleo", "Substituicao do filtro rosqueavel ou refil do motor.", 15, "18.00", "45.00", False),
        ("Troca do filtro de ar do motor", "Troca do elemento de admissao com limpeza da caixa.", 20, "12.00", "39.00", False),
        ("Troca do filtro de cabine", "Substituicao do filtro interno com conferencia do fluxo de ar.", 20, "12.00", "39.00", False),
        ("Higienizacao do ar-condicionado", "Aplicacao de bactericida e limpeza do sistema interno.", 45, "40.00", "129.00", False),
        ("Alinhamento dianteiro", "Ajuste basico de convergencia e volante centralizado.", 50, "35.00", "99.00", False),
        ("Balanceamento das 4 rodas", "Balanceamento dinamico das rodas do veiculo.", 45, "30.00", "89.00", False),
        ("Rodizio de pneus", "Reorganizacao de pneus conforme desgaste e tracao.", 35, "20.00", "59.00", False),
        ("Troca de pastilhas dianteiras", "Substituicao do jogo dianteiro com limpeza das guias.", 70, "85.00", "199.00", False),
        ("Troca de pastilhas traseiras", "Substituicao do jogo traseiro com conferencia do sistema.", 65, "75.00", "179.00", False),
        ("Sangria do sistema de freio", "Remocao de ar do circuito hidraulico.", 45, "35.00", "109.00", False),
        ("Troca do fluido de freio", "Renovacao total do fluido do sistema.", 35, "25.00", "79.00", False),
        ("Limpeza de bicos injetores", "Servico de limpeza com aplicacao de produto especifico.", 80, "95.00", "249.00", False),
        ("Descarbonizacao do motor", "Limpeza interna preventiva em motores com uso severo.", 90, "120.00", "329.00", False),
        ("Troca de velas de ignicao", "Substituicao das velas com torque adequado.", 50, "45.00", "119.00", False),
        ("Troca de cabos de vela", "Troca do jogo com conferencia de resistencia.", 60, "50.00", "139.00", False),
        ("Revisao do sistema de arrefecimento", "Inspecao de mangueiras, bomba, ventoinha e nivel.", 80, "90.00", "239.00", False),
        ("Troca do liquido de arrefecimento", "Substituicao do liquido com sangria do sistema.", 40, "35.00", "99.00", False),
        ("Recarga de gas do ar-condicionado", "Vacuo e recarga do sistema com conferencia de vedacao.", 60, "85.00", "229.00", True),
        ("Troca da correia de acessorios", "Substituicao da correia poli-V e inspecao dos tensores.", 75, "95.00", "229.00", False),
        ("Troca da correia dentada", "Servico completo com sincronismo do motor.", 240, "380.00", "890.00", False),
        ("Troca do kit de embreagem", "Substituicao de disco, plato e rolamento.", 300, "520.00", "1290.00", False),
        ("Troca de amortecedores dianteiros", "Substituicao do par dianteiro com conferencia de batente.", 180, "240.00", "649.00", False),
        ("Troca de amortecedores traseiros", "Substituicao do par traseiro e teste de assentamento.", 150, "210.00", "579.00", False),
        ("Troca de bandeja dianteira", "Troca da bandeja completa com reaperto final.", 150, "185.00", "489.00", False),
        ("Troca de bieleta estabilizadora", "Substituicao do elo da barra estabilizadora.", 50, "55.00", "149.00", False),
        ("Troca de terminal de direcao", "Substituicao do terminal e ajuste basico para alinhamento.", 70, "80.00", "189.00", False),
        ("Geometria completa", "Ajuste de alinhamento com foco em rodagem e estabilidade.", 70, "50.00", "149.00", False),
        ("Carga de bateria", "Recuperacao lenta com monitoramento de carga.", 30, "20.00", "49.00", False),
        ("Teste de alternador e bateria", "Diagnostico de partida, carga e queda de tensao.", 35, "22.00", "59.00", False),
        ("Troca de bateria", "Substituicao com limpeza dos terminais e reset de memoria.", 25, "18.00", "45.00", False),
        ("Instalacao de lampadas LED", "Instalacao e ajuste de foco em conjunto frontal.", 30, "25.00", "69.00", False),
        ("Scanner e diagnostico eletronico", "Leitura de falhas com orientacao tecnica inicial.", 50, "45.00", "139.00", False),
        ("Troca de oleo do cambio manual", "Troca do lubrificante com vedacao e conferencia de nivel.", 45, "55.00", "149.00", False),
        ("Troca de oleo do cambio automatico", "Substituicao parcial com conferencia de temperatura e nivel.", 180, "260.00", "790.00", False),
        ("Troca de palhetas do limpador", "Instalacao do jogo dianteiro com teste de varredura.", 15, "10.00", "29.00", False),
        ("Cristalizacao do para-brisa", "Aplicacao hidrofobica no vidro dianteiro.", 40, "45.00", "109.00", False),
        ("Lavagem tecnica do motor", "Limpeza controlada de cofre com protecao de conectores.", 60, "65.00", "169.00", False),
        ("Polimento de farois", "Recuperacao de transparencia com acabamento protetivo.", 50, "55.00", "149.00", False),
        ("Revisao pre-viagem", "Checklist preventivo para uso rodoviario e urbano.", 90, "85.00", "229.00", False),
    )

    return [
        ServiceSpec(
            name=name,
            description=description,
            duration=timedelta(minutes=minutes),
            suggested_cost=_decimal(suggested_cost),
            selling_price=_decimal(selling_price),
            is_third_party=is_third_party,
        )
        for name, description, minutes, suggested_cost, selling_price, is_third_party in raw_services
    ]


def _build_kit_specs() -> list[KitSpec]:
    return [
        KitSpec(
            name="Kit Revisao 5.000 km Flex",
            description="Pacote basico para troca de oleo e filtros de uso urbano.",
            products=(
                KitProductSpec("PRD-1001", 4),
                KitProductSpec("PRD-1005"),
                KitProductSpec("PRD-1006"),
                KitProductSpec("PRD-1007"),
            ),
            services=(
                KitServiceSpec("Troca de oleo do motor"),
                KitServiceSpec("Troca do filtro de oleo"),
                KitServiceSpec("Troca do filtro de ar do motor"),
                KitServiceSpec("Troca do filtro de cabine"),
            ),
        ),
        KitSpec(
            name="Kit Revisao 10.000 km Sedan",
            description="Revisao preventiva com fluido de freio e higienizacao do sistema interno.",
            products=(
                KitProductSpec("PRD-1001", 4),
                KitProductSpec("PRD-1003"),
                KitProductSpec("PRD-1005"),
                KitProductSpec("PRD-1006"),
                KitProductSpec("PRD-1007"),
            ),
            services=(
                KitServiceSpec("Troca de oleo do motor"),
                KitServiceSpec("Troca do filtro de oleo"),
                KitServiceSpec("Troca do fluido de freio"),
                KitServiceSpec("Higienizacao do ar-condicionado"),
            ),
        ),
        KitSpec(
            name="Kit Revisao 20.000 km Compacto",
            description="Combo para manutencao completa de fluidos, filtros e ignicao.",
            products=(
                KitProductSpec("PRD-1001", 4),
                KitProductSpec("PRD-1003"),
                KitProductSpec("PRD-1005"),
                KitProductSpec("PRD-1006"),
                KitProductSpec("PRD-1007"),
                KitProductSpec("PRD-1021", 4),
            ),
            services=(
                KitServiceSpec("Troca de oleo do motor"),
                KitServiceSpec("Troca do filtro de oleo"),
                KitServiceSpec("Troca do filtro de ar do motor"),
                KitServiceSpec("Troca do filtro de cabine"),
                KitServiceSpec("Troca de velas de ignicao"),
                KitServiceSpec("Troca do fluido de freio"),
            ),
        ),
        KitSpec(
            name="Kit Freio Dianteiro Urbano",
            description="Pacote para recuperacao do conjunto dianteiro de freio.",
            products=(
                KitProductSpec("PRD-1003"),
                KitProductSpec("PRD-1009"),
                KitProductSpec("PRD-1011", 2),
            ),
            services=(
                KitServiceSpec("Troca de pastilhas dianteiras"),
                KitServiceSpec("Sangria do sistema de freio"),
                KitServiceSpec("Troca do fluido de freio"),
            ),
        ),
        KitSpec(
            name="Kit Freio Completo Premium",
            description="Pacote para revisao completa de freio dianteiro e traseiro.",
            products=(
                KitProductSpec("PRD-1003"),
                KitProductSpec("PRD-1009"),
                KitProductSpec("PRD-1010"),
                KitProductSpec("PRD-1011", 2),
                KitProductSpec("PRD-1012"),
            ),
            services=(
                KitServiceSpec("Troca de pastilhas dianteiras"),
                KitServiceSpec("Troca de pastilhas traseiras"),
                KitServiceSpec("Sangria do sistema de freio"),
                KitServiceSpec("Troca do fluido de freio"),
            ),
        ),
        KitSpec(
            name="Kit Suspensao Dianteira Estavel",
            description="Pacote para eliminar folgas e melhorar estabilidade dianteira.",
            products=(
                KitProductSpec("PRD-1013", 2),
                KitProductSpec("PRD-1015", 2),
                KitProductSpec("PRD-1016", 2),
            ),
            services=(
                KitServiceSpec("Troca de amortecedores dianteiros"),
                KitServiceSpec("Troca de bieleta estabilizadora"),
                KitServiceSpec("Troca de bandeja dianteira"),
                KitServiceSpec("Geometria completa"),
            ),
        ),
        KitSpec(
            name="Kit Suspensao Traseira Conforto",
            description="Conjunto para restaurar conforto e reduzir batidas na traseira.",
            products=(
                KitProductSpec("PRD-1014", 2),
                KitProductSpec("PRD-1015", 2),
            ),
            services=(
                KitServiceSpec("Troca de amortecedores traseiros"),
                KitServiceSpec("Geometria completa"),
            ),
        ),
        KitSpec(
            name="Kit Arrefecimento Preventivo",
            description="Pacote para evitar superaquecimento em uso diario.",
            products=(
                KitProductSpec("PRD-1004"),
                KitProductSpec("PRD-1017"),
                KitProductSpec("PRD-1018"),
                KitProductSpec("PRD-1019"),
            ),
            services=(
                KitServiceSpec("Revisao do sistema de arrefecimento"),
                KitServiceSpec("Troca do liquido de arrefecimento"),
            ),
        ),
        KitSpec(
            name="Kit Ar-Condicionado Higiene",
            description="Higienizacao e recarga para melhorar conforto da cabine.",
            products=(
                KitProductSpec("PRD-1007"),
                KitProductSpec("PRD-1036"),
            ),
            services=(
                KitServiceSpec("Higienizacao do ar-condicionado"),
                KitServiceSpec("Recarga de gas do ar-condicionado"),
            ),
        ),
        KitSpec(
            name="Kit Ignicao Partida Rapida",
            description="Pacote para eliminar falhas de partida e oscilacao em marcha lenta.",
            products=(
                KitProductSpec("PRD-1021", 4),
                KitProductSpec("PRD-1022"),
                KitProductSpec("PRD-1023"),
            ),
            services=(
                KitServiceSpec("Troca de velas de ignicao"),
                KitServiceSpec("Troca de cabos de vela"),
                KitServiceSpec("Scanner e diagnostico eletronico"),
            ),
        ),
        KitSpec(
            name="Kit Bateria e Carga",
            description="Servico rapido para recuperar ou substituir bateria.",
            products=(
                KitProductSpec("PRD-1024"),
                KitProductSpec("PRD-1034"),
            ),
            services=(
                KitServiceSpec("Teste de alternador e bateria"),
                KitServiceSpec("Troca de bateria"),
                KitServiceSpec("Carga de bateria"),
            ),
        ),
        KitSpec(
            name="Kit Cambio Manual Leve",
            description="Pacote para manutencao preventiva do cambio mecanico.",
            products=(
                KitProductSpec("PRD-1028", 2),
                KitProductSpec("PRD-1026"),
            ),
            services=(
                KitServiceSpec("Troca de oleo do cambio manual"),
                KitServiceSpec("Scanner e diagnostico eletronico"),
            ),
        ),
        KitSpec(
            name="Kit Embreagem Oficina",
            description="Troca do conjunto de embreagem com conferencia final de funcionamento.",
            products=(
                KitProductSpec("PRD-1025"),
                KitProductSpec("PRD-1026"),
            ),
            services=(
                KitServiceSpec("Troca do kit de embreagem"),
                KitServiceSpec("Scanner e diagnostico eletronico"),
            ),
        ),
        KitSpec(
            name="Kit Direcao e Geometria",
            description="Pacote para eliminar folga de direcao e corrigir alinhamento.",
            products=(
                KitProductSpec("PRD-1015", 2),
                KitProductSpec("PRD-1016"),
            ),
            services=(
                KitServiceSpec("Troca de terminal de direcao"),
                KitServiceSpec("Geometria completa"),
            ),
        ),
        KitSpec(
            name="Kit Vistoria Pre-Viagem",
            description="Pacote preventivo para clientes que vao pegar estrada.",
            products=(
                KitProductSpec("PRD-1003"),
                KitProductSpec("PRD-1033", 2),
                KitProductSpec("PRD-1037"),
            ),
            services=(
                KitServiceSpec("Revisao pre-viagem"),
                KitServiceSpec("Balanceamento das 4 rodas"),
                KitServiceSpec("Alinhamento dianteiro"),
            ),
        ),
        KitSpec(
            name="Kit Cuidado para Chuva",
            description="Melhora visibilidade em dias chuvosos e uso noturno.",
            products=(
                KitProductSpec("PRD-1029", 2),
                KitProductSpec("PRD-1033", 2),
            ),
            services=(
                KitServiceSpec("Troca de palhetas do limpador"),
                KitServiceSpec("Cristalizacao do para-brisa"),
                KitServiceSpec("Polimento de farois"),
            ),
        ),
        KitSpec(
            name="Kit Motor Limpo e Eficiente",
            description="Pacote para melhorar consumo e resposta em aceleracao.",
            products=(
                KitProductSpec("PRD-1035"),
                KitProductSpec("PRD-1037"),
            ),
            services=(
                KitServiceSpec("Limpeza de bicos injetores"),
                KitServiceSpec("Descarbonizacao do motor"),
                KitServiceSpec("Lavagem tecnica do motor"),
            ),
        ),
        KitSpec(
            name="Kit Freio Traseiro de Revisao",
            description="Servico voltado ao eixo traseiro em revisoes corretivas.",
            products=(
                KitProductSpec("PRD-1003"),
                KitProductSpec("PRD-1010"),
                KitProductSpec("PRD-1012"),
            ),
            services=(
                KitServiceSpec("Troca de pastilhas traseiras"),
                KitServiceSpec("Sangria do sistema de freio"),
            ),
        ),
        KitSpec(
            name="Kit Conforto de Cabine",
            description="Melhora qualidade do ar e visual interno para entrega ao cliente.",
            products=(
                KitProductSpec("PRD-1007"),
                KitProductSpec("PRD-1036"),
                KitProductSpec("PRD-1039"),
                KitProductSpec("PRD-1040"),
            ),
            services=(KitServiceSpec("Higienizacao do ar-condicionado"),),
        ),
        KitSpec(
            name="Kit Rodas Alinhadas",
            description="Pacote rapido para pneus, rodagem reta e desgaste uniforme.",
            products=(KitProductSpec("PRD-1038"),),
            services=(
                KitServiceSpec("Alinhamento dianteiro"),
                KitServiceSpec("Balanceamento das 4 rodas"),
                KitServiceSpec("Rodizio de pneus"),
            ),
        ),
        KitSpec(
            name="Kit Arrefecimento e Correia",
            description="Troca preventiva de componentes antes de superaquecimento.",
            products=(
                KitProductSpec("PRD-1004"),
                KitProductSpec("PRD-1018"),
                KitProductSpec("PRD-1019"),
            ),
            services=(
                KitServiceSpec("Revisao do sistema de arrefecimento"),
                KitServiceSpec("Troca do liquido de arrefecimento"),
                KitServiceSpec("Troca da correia de acessorios"),
            ),
        ),
        KitSpec(
            name="Kit Cambio Automatico Limpo",
            description="Pacote para troca de ATF e leitura de funcionamento do cambio.",
            products=(KitProductSpec("PRD-1027", 6),),
            services=(
                KitServiceSpec("Troca de oleo do cambio automatico"),
                KitServiceSpec("Scanner e diagnostico eletronico"),
            ),
        ),
    ]


CHECKLIST_ITEM_BANK: dict[str, tuple[tuple[str, str], ...]] = {
    "Exterior": (
        ("Estado da pintura e para-choques", CHECKLIST_RESPONSE_BRR),
        ("Trincas ou lascas no para-brisa", CHECKLIST_RESPONSE_SIM_NAO),
        ("Condicao das palhetas", CHECKLIST_RESPONSE_BRR),
        ("Lanternas e farois sem avarias", CHECKLIST_RESPONSE_SIM_NAO),
        ("Avarias em portas e tampas", CHECKLIST_RESPONSE_TEXT),
        ("Placas bem fixadas", CHECKLIST_RESPONSE_SIM_NAO),
    ),
    "Interior": (
        ("Luzes de advertencia no painel", CHECKLIST_RESPONSE_SIM_NAO),
        ("Funcionamento do ar quente e ventilacao", CHECKLIST_RESPONSE_BRR),
        ("Odor interno ao ligar o ar", CHECKLIST_RESPONSE_TEXT),
        ("Estado dos cintos e travas", CHECKLIST_RESPONSE_BRR),
        ("Funcionamento dos vidros eletricos", CHECKLIST_RESPONSE_SIM_NAO),
        ("Nivel geral de limpeza interna", CHECKLIST_RESPONSE_BRR),
    ),
    "Fluidos": (
        ("Nivel do oleo do motor", CHECKLIST_RESPONSE_LEVEL),
        ("Nivel do fluido de freio", CHECKLIST_RESPONSE_LEVEL),
        ("Nivel do liquido de arrefecimento", CHECKLIST_RESPONSE_LEVEL),
        ("Indicio de vazamento visivel", CHECKLIST_RESPONSE_SIM_NAO),
        ("Estado da tampa do reservatorio", CHECKLIST_RESPONSE_BRR),
        ("Condicao do fluido de direcao", CHECKLIST_RESPONSE_BRR),
    ),
    "Freios": (
        ("Espessura aparente das pastilhas", CHECKLIST_RESPONSE_BRR),
        ("Pedal com curso regular", CHECKLIST_RESPONSE_SIM_NAO),
        ("Ruido de freio em baixa velocidade", CHECKLIST_RESPONSE_TEXT),
        ("Freio de estacionamento funcional", CHECKLIST_RESPONSE_SIM_NAO),
        ("Discos sem sulcos profundos", CHECKLIST_RESPONSE_BRR),
        ("Balanceamento de frenagem percebido", CHECKLIST_RESPONSE_BRR),
    ),
    "Suspensao": (
        ("Folga em bieletas e links", CHECKLIST_RESPONSE_BRR),
        ("Batidas ao passar em valetas", CHECKLIST_RESPONSE_TEXT),
        ("Amortecedores com vazamento", CHECKLIST_RESPONSE_SIM_NAO),
        ("Buchas com desgaste aparente", CHECKLIST_RESPONSE_BRR),
        ("Altura do veiculo uniforme", CHECKLIST_RESPONSE_SIM_NAO),
        ("Ruido em esterco total", CHECKLIST_RESPONSE_TEXT),
    ),
    "Pneus": (
        ("Desgaste uniforme dos pneus", CHECKLIST_RESPONSE_BRR),
        ("Pressao adequada na entrada", CHECKLIST_RESPONSE_SIM_NAO),
        ("Estado do estepe", CHECKLIST_RESPONSE_BRR),
        ("Profundidade dos sulcos", CHECKLIST_RESPONSE_BRR),
        ("Rodas com amassados", CHECKLIST_RESPONSE_SIM_NAO),
        ("Necessidade de alinhamento", CHECKLIST_RESPONSE_SIM_NAO),
    ),
    "Eletrica": (
        ("Bateria fixada corretamente", CHECKLIST_RESPONSE_SIM_NAO),
        ("Terminais sem oxidacao", CHECKLIST_RESPONSE_BRR),
        ("Carga do alternador dentro do esperado", CHECKLIST_RESPONSE_SIM_NAO),
        ("Lampadas de farol funcionando", CHECKLIST_RESPONSE_SIM_NAO),
        ("Lanterna de freio operacional", CHECKLIST_RESPONSE_SIM_NAO),
        ("Falha eletrica relatada", CHECKLIST_RESPONSE_TEXT),
    ),
    "Arrefecimento": (
        ("Mangueiras sem ressecamento", CHECKLIST_RESPONSE_BRR),
        ("Ventoinha acionando corretamente", CHECKLIST_RESPONSE_SIM_NAO),
        ("Temperatura estabiliza em uso", CHECKLIST_RESPONSE_SIM_NAO),
        ("Reservatorio sem trinca", CHECKLIST_RESPONSE_BRR),
        ("Tampa do reservatorio vedando", CHECKLIST_RESPONSE_BRR),
        ("Historico de aquecimento recente", CHECKLIST_RESPONSE_TEXT),
    ),
    "Motor": (
        ("Marcha lenta estavel", CHECKLIST_RESPONSE_BRR),
        ("Ruido metalico ao acelerar", CHECKLIST_RESPONSE_TEXT),
        ("Resposta do acelerador", CHECKLIST_RESPONSE_BRR),
        ("Presenca de fumaca no escape", CHECKLIST_RESPONSE_SIM_NAO),
        ("Suportes do motor sem folga", CHECKLIST_RESPONSE_BRR),
        ("Falhas intermitentes relatadas", CHECKLIST_RESPONSE_TEXT),
    ),
    "Ar-condicionado": (
        ("Ar frio atingindo a cabine", CHECKLIST_RESPONSE_BRR),
        ("Ruido no compressor", CHECKLIST_RESPONSE_TEXT),
        ("Vazao nas saidas do painel", CHECKLIST_RESPONSE_BRR),
        ("Cheiro forte ao ligar o ar", CHECKLIST_RESPONSE_SIM_NAO),
        ("Filtro de cabine em dia", CHECKLIST_RESPONSE_SIM_NAO),
        ("Compressor aciona normalmente", CHECKLIST_RESPONSE_SIM_NAO),
    ),
    "Entrega": (
        ("Ferramentas retiradas do veiculo", CHECKLIST_RESPONSE_SIM_NAO),
        ("Tapetes e capas removidos", CHECKLIST_RESPONSE_SIM_NAO),
        ("Itens trocados apresentados ao cliente", CHECKLIST_RESPONSE_SIM_NAO),
        ("Observacoes finais registradas", CHECKLIST_RESPONSE_TEXT),
        ("Teste rapido apos servico", CHECKLIST_RESPONSE_SIM_NAO),
        ("Veiculo limpo para entrega", CHECKLIST_RESPONSE_BRR),
    ),
}

CHECKLIST_BLUEPRINTS: tuple[ChecklistBlueprint, ...] = (
    ChecklistBlueprint("Recepcao rapida de revisao", ("Exterior", "Interior", "Fluidos", "Pneus"), 10),
    ChecklistBlueprint("Vistoria de freios", ("Freios", "Pneus", "Fluidos"), 9),
    ChecklistBlueprint("Vistoria de suspensao", ("Suspensao", "Pneus", "Exterior"), 9),
    ChecklistBlueprint("Entrega tecnica do veiculo", ("Entrega", "Interior", "Exterior"), 8),
    ChecklistBlueprint("Check de ar-condicionado", ("Ar-condicionado", "Interior", "Eletrica"), 8),
    ChecklistBlueprint("Revisao de viagem", ("Fluidos", "Pneus", "Eletrica", "Motor"), 10),
    ChecklistBlueprint("Inspecao eletrica basica", ("Eletrica", "Interior", "Exterior"), 8),
    ChecklistBlueprint("Diagnostico de arrefecimento", ("Arrefecimento", "Fluidos", "Motor"), 9),
    ChecklistBlueprint("Pre-compra urbana", ("Exterior", "Interior", "Freios", "Suspensao", "Motor"), 12),
    ChecklistBlueprint("Manutencao de oleo e filtros", ("Fluidos", "Motor", "Ar-condicionado"), 8),
    ChecklistBlueprint("Vistoria de pneus e rodas", ("Pneus", "Suspensao", "Exterior"), 8),
    ChecklistBlueprint("Inspecao de luzes e sinalizacao", ("Eletrica", "Exterior", "Interior"), 8),
    ChecklistBlueprint("Inspecao de motor e ignicao", ("Motor", "Eletrica", "Fluidos"), 9),
    ChecklistBlueprint("Avaliacao de ruido e vibracao", ("Motor", "Suspensao", "Pneus"), 9),
    ChecklistBlueprint("Conferencia final pos-servico", ("Entrega", "Exterior", "Interior", "Motor"), 10),
)


def _build_question_specs() -> list[QuestionSpec]:
    response_type = InvestigativeQuestion.ResponseType
    return [
        QuestionSpec("Qual e o principal uso do veiculo?", response_type.MULTIPLE_CHOICE, ("Uso particular", "Aplicativo", "Frota leve", "Entrega urbana", "Uso misto")),
        QuestionSpec("O veiculo roda mais em cidade ou estrada?", response_type.MULTIPLE_CHOICE, ("Cidade", "Estrada", "Uso equilibrado")),
        QuestionSpec("Existe algum ruido especifico que mais incomoda hoje?", response_type.FREE_TEXT),
        QuestionSpec("Em uma escala de 1 a 10, quanto o conforto de rodagem precisa melhorar?", response_type.SCALE),
        QuestionSpec("O cliente percebe aumento no consumo de combustivel?", response_type.BOOLEAN),
        QuestionSpec("Qual foi a ultima manutencao relevante feita no veiculo?", response_type.FREE_TEXT),
        QuestionSpec("Ha interesse em priorizar pecas com maior durabilidade?", response_type.BOOLEAN),
        QuestionSpec("Qual e a urgencia esperada para a entrega?", response_type.MULTIPLE_CHOICE, ("Mesmo dia", "Em ate 24 horas", "Em ate 48 horas", "Sem urgencia")),
        QuestionSpec("Em uma escala de 1 a 10, quanto o ruido do motor incomoda?", response_type.SCALE),
        QuestionSpec("O veiculo costuma transportar carga ou peso acima da media?", response_type.BOOLEAN),
        QuestionSpec("Existe historico recente de superaquecimento?", response_type.BOOLEAN),
        QuestionSpec("Quais situacoes costumam reproduzir o problema relatado?", response_type.FREE_TEXT),
        QuestionSpec("Em uma escala de 1 a 10, qual a importancia de manter o custo total mais enxuto?", response_type.SCALE),
        QuestionSpec("O veiculo fica parado por longos periodos?", response_type.BOOLEAN),
        QuestionSpec("Qual combustivel o cliente usa com mais frequencia?", response_type.MULTIPLE_CHOICE, ("Gasolina", "Etanol", "Diesel", "Flex sem preferencia")),
        QuestionSpec("Ha vibracao em frenagens fortes?", response_type.BOOLEAN),
        QuestionSpec("Em uma escala de 1 a 10, qual o nivel de exigencia do cliente com acabamento e limpeza?", response_type.SCALE),
        QuestionSpec("O cliente prefere pecas originais, premium ou custo-beneficio?", response_type.MULTIPLE_CHOICE, ("Original", "Premium", "Custo-beneficio")),
        QuestionSpec("Existe dificuldade para partidas pela manha?", response_type.BOOLEAN),
        QuestionSpec("Que melhoria faria o cliente sentir mais valor neste atendimento?", response_type.FREE_TEXT),
        QuestionSpec("Em uma escala de 1 a 10, quanto a estabilidade em estrada e importante para este cliente?", response_type.SCALE),
        QuestionSpec("O cliente autoriza contato para manutencoes preventivas futuras?", response_type.BOOLEAN),
        QuestionSpec("Qual a media de quilometragem mensal do veiculo?", response_type.MULTIPLE_CHOICE, ("Ate 500 km", "500 a 1.500 km", "1.500 a 3.000 km", "Acima de 3.000 km")),
        QuestionSpec("Existe alguma observacao comercial importante para esta venda?", response_type.FREE_TEXT),
        QuestionSpec("Em uma escala de 1 a 10, quanto a rapidez no atendimento pesa na decisao de retorno?", response_type.SCALE),
    ]


PRODUCT_SPECS = _build_product_specs()
SERVICE_SPECS = _build_service_specs()
KIT_SPECS = _build_kit_specs()
QUESTION_SPECS = _build_question_specs()


class Command(BaseCommand):
    help = "Popula a oficina 1 com dados de demonstracao realistas e deterministas."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--seed",
            type=int,
            default=DEFAULT_SEED,
            help="Seed deterministica para datas, enderecos e pequenas variacoes.",
        )

    def handle(self, *args, **options) -> None:
        seed = int(options["seed"])
        workshop = Workshop.objects.filter(pk=WORKSHOP_ID).first()
        if workshop is None:
            raise CommandError(f"A oficina fixa de ID {WORKSHOP_ID} nao foi encontrada.")

        rng = random.Random(seed)

        with transaction.atomic():
            monthly_costs = self._ensure_monthly_costs(workshop=workshop)
            groups = self._ensure_catalog_groups(workshop=workshop)
            suppliers = self._seed_suppliers(workshop=workshop)
            products = self._seed_products(workshop=workshop, groups=groups, suppliers=suppliers)
            services = self._seed_services(workshop=workshop)
            self._seed_kits(workshop=workshop, products=products, services=services)
            self._seed_customers(workshop=workshop)
            collaborators = self._seed_collaborators(workshop=workshop)
            self._seed_checklists(workshop=workshop)
            self._seed_questions(workshop=workshop)
            self._seed_workshop_costs(workshop=workshop, monthly_costs=monthly_costs, collaborators=collaborators, rng=rng)

        self.stdout.write(self.style.SUCCESS(f"Seed concluido para a oficina {WORKSHOP_ID} com seed {seed}."))
        self.stdout.write(
            " | ".join(
                (
                    f"produtos: {workshop.products.count()}",
                    f"servicos: {workshop.services.count()}",
                    f"kits: {workshop.kits.count()}",
                    f"clientes: {workshop.customers.count()}",
                    f"fornecedores: {workshop.suppliers.count()}",
                    f"checklists: {workshop.checklists.count()}",
                    f"colaboradores: {workshop.collaborators.count()}",
                    f"perguntas: {workshop.investigative_questions.count()}",
                    f"custos: {workshop.workshop_costs.count()}",
                )
            )
        )

    def _ensure_monthly_costs(self, *, workshop: Workshop) -> dict[str, MonthlyCost]:
        costs: dict[str, MonthlyCost] = {}
        for name in DEFAULT_MONTHLY_COSTS:
            monthly_cost, _ = MonthlyCost.objects.get_or_create(
                workshop=workshop,
                name=name,
                defaults={"is_active": True, "is_editable": False},
            )
            costs[name] = monthly_cost
        return costs

    def _ensure_catalog_groups(self, *, workshop: Workshop) -> dict[str, CatalogGroup]:
        groups: dict[str, CatalogGroup] = {}
        for group_name in sorted({spec.group_name for spec in PRODUCT_SPECS}):
            group, _ = CatalogGroup.objects.get_or_create(workshop=workshop, name=group_name)
            groups[group_name] = group
        return groups

    def _seed_suppliers(self, *, workshop: Workshop) -> list[Supplier]:
        suppliers: list[Supplier] = []
        for index, (name, contact_person, email) in enumerate(SUPPLIER_SPECS, start=1):
            defaults: dict[str, object] = {
                "name": name,
                "contact_person": contact_person,
                "phone": _landline_phone(index),
                "mobile": _mobile_phone(index),
                "email": email,
                "registration_date": date(2023 + (index % 2), ((index * 2) % 12) + 1, ((index * 3) % 28) + 1),
                "is_active": True,
                **_address(index + 20),
            }
            supplier, _ = Supplier.objects.update_or_create(workshop=workshop, cnpj=_generate_cnpj(500 + index), defaults=defaults)
            suppliers.append(supplier)
        return suppliers

    def _seed_products(self, *, workshop: Workshop, groups: dict[str, CatalogGroup], suppliers: Sequence[Supplier]) -> dict[str, Product]:
        products: dict[str, Product] = {}
        for index, spec in enumerate(PRODUCT_SPECS, start=1):
            product, _ = Product.objects.update_or_create(
                workshop=workshop,
                code=spec.code,
                defaults={
                    "name": spec.name,
                    "description": spec.description,
                    "unit": spec.unit,
                    "group": groups[spec.group_name],
                    "brand": spec.brand,
                    "model": spec.model,
                    "sku": f"SKU-{spec.code}",
                    "barcode": "",
                    "location": spec.location,
                    "cost_price": _money(spec.cost_price),
                    "selling_price": _money(spec.selling_price),
                    "profit_margin": _margin(spec.cost_price, spec.selling_price),
                    "ncm": "",
                    "cest": "",
                    "application": spec.application,
                    "is_active": True,
                },
            )
            stock_product, _ = StockProduct.objects.get_or_create(workshop=workshop, product=product)
            stock_product.supplier = suppliers[(index - 1) % len(suppliers)]
            stock_product.current_quantity = 6 + ((index * 3) % 28)
            stock_product.minimum_quantity = 2 + (index % 4)
            stock_product.restock_quantity = 4 + (index % 6)
            stock_product.last_nf = f"NF-{202500 + index:06d}"
            stock_product.save(update_fields=["supplier", "current_quantity", "minimum_quantity", "restock_quantity", "last_nf"])
            products[spec.code] = product
        return products

    def _seed_services(self, *, workshop: Workshop) -> dict[str, Service]:
        services: dict[str, Service] = {}
        for spec in SERVICE_SPECS:
            service, _ = Service.objects.update_or_create(
                workshop=workshop,
                name=spec.name,
                defaults={
                    "description": spec.description,
                    "duration": spec.duration,
                    "suggested_cost": _money(spec.suggested_cost),
                    "selling_price": _money(spec.selling_price),
                    "is_third_party": spec.is_third_party,
                    "is_active": True,
                },
            )
            services[spec.name] = service
        return services

    def _seed_kits(self, *, workshop: Workshop, products: dict[str, Product], services: dict[str, Service]) -> None:
        for spec in KIT_SPECS:
            kit, _ = Kit.objects.update_or_create(
                workshop=workshop,
                name=spec.name,
                defaults={"description": spec.description, "is_active": True},
            )

            KitProduct.objects.filter(kit=kit).delete()
            KitService.objects.filter(kit=kit).delete()

            total_price = Decimal("0.00")
            total_duration = timedelta()

            kit_products: list[KitProduct] = []
            for item in spec.products:
                product = products[item.code]
                kit_products.append(KitProduct(kit=kit, product=product, quantity=item.quantity))
                total_price += product.selling_price.amount * item.quantity

            kit_services: list[KitService] = []
            for item in spec.services:
                service = services[item.name]
                row_duration = item.duration if item.duration is not None else service.duration
                kit_services.append(KitService(kit=kit, service=service, quantity=item.quantity, duration=row_duration))
                total_price += service.selling_price.amount * item.quantity
                total_duration += row_duration * item.quantity

            KitProduct.objects.bulk_create(kit_products)
            KitService.objects.bulk_create(kit_services)

            kit.total_price = _money(total_price)
            kit.total_duration = total_duration
            kit.save(update_fields=["description", "is_active", "total_price", "total_duration"])

    def _seed_customers(self, *, workshop: Workshop) -> None:
        for index, (name, sex) in enumerate(PF_CUSTOMERS, start=1):
            defaults: dict[str, object] = {
                "customer_type": "PF",
                "name": name,
                "phone": _mobile_phone(index + 100),
                "email": _email_from_name(name, index),
                "is_active": True,
                "rg": f"{120000000 + index:09d}",
                "birth_date": date(1980 + (index % 14), ((index * 2) % 12) + 1, ((index * 5) % 28) + 1),
                "sex": sex,
                "fantasy_name": None,
                "state_registration": None,
                "municipal_registration": None,
                "foundation_date": None,
                **_address(index + 40),
            }
            Customer.objects.update_or_create(workshop=workshop, cpf_or_cnpj=_generate_cpf(index), defaults=defaults)

        for index, (name, fantasy_name) in enumerate(PJ_CUSTOMERS, start=1):
            defaults = {
                "customer_type": "PJ",
                "name": name,
                "phone": _mobile_phone(index + 200),
                "email": f"financeiro@{_slugify(fantasy_name).replace('.', '')}.com.br",
                "is_active": True,
                "rg": None,
                "birth_date": None,
                "sex": None,
                "fantasy_name": fantasy_name,
                "state_registration": f"{310000000 + index * 23}",
                "municipal_registration": f"{810000 + index * 7}",
                "foundation_date": date(2008 + (index % 10), ((index * 3) % 12) + 1, ((index * 2) % 28) + 1),
                **_address(index + 60),
            }
            Customer.objects.update_or_create(workshop=workshop, cpf_or_cnpj=_generate_cnpj(800 + index), defaults=defaults)

    def _seed_collaborators(self, *, workshop: Workshop) -> list[WorkshopCollaborator]:
        collaborators: list[WorkshopCollaborator] = []
        for index, (name, sex) in enumerate(COLLABORATOR_NAMES, start=1):
            if index <= 15:
                collaborator_type = WorkshopCollaborator.CollaboratorType.PRODUCTIVE
                position = PRODUCTIVE_POSITIONS[(index - 1) % len(PRODUCTIVE_POSITIONS)]
                salary_base = Decimal("2650") + Decimal((index - 1) % 6) * Decimal("280")
                receives_commission = index in {3, 6, 9, 12, 15}
                commission_percentage = Decimal("0.040000") + Decimal(index % 3) * Decimal("0.010000") if receives_commission else None
            else:
                collaborator_type = WorkshopCollaborator.CollaboratorType.ADMINISTRATIVE
                position = ADMINISTRATIVE_POSITIONS[(index - 16) % len(ADMINISTRATIVE_POSITIONS)]
                salary_base = Decimal("2400") + Decimal((index - 16) % 5) * Decimal("350")
                receives_commission = position == "Consultor tecnico"
                commission_percentage = Decimal("0.025000") if receives_commission else None

            defaults: dict[str, object] = {
                "name": name,
                "rg": f"{220000000 + index:09d}",
                "birth_date": date(1979 + (index % 18), ((index * 4) % 12) + 1, ((index * 6) % 28) + 1),
                "sex": sex,
                "phone": _mobile_phone(index + 300),
                "email": f"{_slugify(name)}@oficina-demo.local",
                "position": position,
                "salary": _money(salary_base),
                "admission_date": date(2020 + (index % 5), ((index * 2) % 12) + 1, ((index * 3) % 28) + 1),
                "termination_date": None,
                "collaborator_type": collaborator_type,
                "receives_commission": receives_commission,
                "commission_percentage": commission_percentage,
                "is_active": True,
            }
            collaborator, _ = WorkshopCollaborator.objects.update_or_create(workshop=workshop, cpf=_generate_cpf(2000 + index), defaults=defaults)
            collaborators.append(collaborator)
        return collaborators

    def _seed_checklists(self, *, workshop: Workshop) -> None:
        for index, blueprint in enumerate(CHECKLIST_BLUEPRINTS):
            checklist = Checklist.objects.filter(workshop=workshop, name=blueprint.name).order_by("pk").first()
            if checklist is None:
                checklist = Checklist.objects.create(workshop=workshop, name=blueprint.name)
            elif checklist.name != blueprint.name:
                checklist.name = blueprint.name
                checklist.save(update_fields=["name"])

            checklist.items.all().delete()
            items = self._build_checklist_items(blueprint=blueprint, seed_index=index)
            ChecklistItem.objects.bulk_create(
                [
                    ChecklistItem(
                        checklist=checklist,
                        group=group,
                        description=description,
                        response_type=response_type,
                        order=order,
                    )
                    for order, (group, description, response_type) in enumerate(items)
                ]
            )

    def _build_checklist_items(self, *, blueprint: ChecklistBlueprint, seed_index: int) -> list[tuple[str, str, str]]:
        grouped_positions = {group: seed_index % len(CHECKLIST_ITEM_BANK[group]) for group in blueprint.groups}
        items: list[tuple[str, str, str]] = []
        seen: set[tuple[str, str]] = set()
        group_cycle = cycle(blueprint.groups)

        while len(items) < blueprint.item_count:
            group = next(group_cycle)
            bank = CHECKLIST_ITEM_BANK[group]
            start = grouped_positions[group]
            selected = False

            for offset in range(len(bank)):
                description, response_type = bank[(start + offset) % len(bank)]
                key = (group, description)
                if key in seen:
                    continue
                items.append((group, description, response_type))
                seen.add(key)
                grouped_positions[group] = (start + offset + 1) % len(bank)
                selected = True
                break

            if not selected:
                break

        return items

    def _seed_questions(self, *, workshop: Workshop) -> None:
        for order, spec in enumerate(QUESTION_SPECS):
            question = InvestigativeQuestion.objects.filter(workshop=workshop, text=spec.text).order_by("pk").first()
            if question is None:
                question = InvestigativeQuestion.objects.create(
                    workshop=workshop,
                    text=spec.text,
                    response_type=spec.response_type,
                    options=list(spec.options),
                    order=order,
                    is_active=True,
                )
                continue

            question.response_type = spec.response_type
            question.options = list(spec.options)
            question.order = order
            question.is_active = True
            question.save(update_fields=["response_type", "options", "order", "is_active"])

    def _seed_workshop_costs(self, *, workshop: Workshop, monthly_costs: dict[str, MonthlyCost], collaborators: Sequence[WorkshopCollaborator], rng: random.Random) -> None:
        active_productive = [collaborator for collaborator in collaborators if collaborator.is_active and collaborator.collaborator_type == WorkshopCollaborator.CollaboratorType.PRODUCTIVE]
        active_administrative = [collaborator for collaborator in collaborators if collaborator.is_active and collaborator.collaborator_type == WorkshopCollaborator.CollaboratorType.ADMINISTRATIVE]

        productive_salary_total = sum((collaborator.salary.amount for collaborator in active_productive), Decimal("0.00"))
        administrative_salary_total = sum((collaborator.salary.amount for collaborator in active_administrative), Decimal("0.00"))

        reference_date = timezone.localdate()
        for offset in range(6):
            month, year = _reference_month(reference_date, offset)
            factor = Decimal("0.97") + Decimal(5 - offset) * Decimal("0.01") + Decimal(rng.randint(0, 2)) * Decimal("0.005")

            workshop_cost, _ = WorkshopCost.objects.update_or_create(
                workshop=workshop,
                month=month,
                year=year,
                defaults={
                    "mechanic_quantity": len(active_productive),
                    "work_hours_per_day": timedelta(hours=8),
                    "work_days_per_month": 21 + ((offset + 1) % 3),
                    "productivity_average": Decimal("0.64") + Decimal(offset % 3) * Decimal("0.02"),
                    "card_rate": Decimal("0.034") + Decimal(offset) * Decimal("0.001"),
                    "tax_rate": Decimal("0.068"),
                    "profit_margin": Decimal("0.22"),
                    "commission_rate": Decimal("0.035"),
                    "risk_coefficient": Decimal("1.08") + Decimal(offset % 2) * Decimal("0.02"),
                    "parts_purchase_cap": _money(23500 * factor),
                    "freight_cost": _money(620 * factor),
                    "third_party_service_cap": _money(3900 * factor),
                },
            )

            for monthly_cost in monthly_costs.values():
                amount = self._monthly_cost_amount(
                    name=monthly_cost.name,
                    productive_salary_total=productive_salary_total,
                    administrative_salary_total=administrative_salary_total,
                    factor=factor,
                )
                WorkshopCostItem.objects.update_or_create(
                    workshop_cost=workshop_cost,
                    monthly_cost=monthly_cost,
                    defaults={"amount": amount},
                )

            workshop_cost.calculate_all()
            workshop_cost.save()

    def _monthly_cost_amount(self, *, name: str, productive_salary_total: Decimal, administrative_salary_total: Decimal, factor: Decimal) -> Money:
        normalized_name = _normalize_text(name)
        normalized_mechanic_salary = _normalize_text(MECHANIC_SALARY_MONTHLY_COST_NAME)

        if normalized_name == normalized_mechanic_salary:
            base_amount = productive_salary_total or Decimal("18000.00")
            return _money(base_amount * factor)
        if "administrativo" in normalized_name:
            base_amount = administrative_salary_total or Decimal("12000.00")
            return _money(base_amount * factor)

        base_amounts = {
            "aluguel": Decimal("6800.00"),
            "agua": Decimal("320.00"),
            "pro labore": Decimal("4800.00"),
            "taxas bancarias": Decimal("420.00"),
            "emprestimo": Decimal("1850.00"),
            "treinamentos": Decimal("380.00"),
            "contabilidade": Decimal("690.00"),
            "luz": Decimal("1280.00"),
            "internet": Decimal("189.00"),
            "seguro": Decimal("970.00"),
            "iptu": Decimal("610.00"),
        }
        base_amount = base_amounts.get(normalized_name, Decimal("250.00"))
        return _money(base_amount * factor)
