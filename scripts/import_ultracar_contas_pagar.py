#!/usr/bin/env python3
"""Script to import Accounts Payable (Contas a Pagar) from Ultracar into Hunter v2.

Features:
- Configurable database connection parameters (DB_CONFIG or CLI args).
- Target workshop allocation (default: ID 25 - Lube Car Embu das Artes).
- Automatic remapping of Ultracar 'Plano de Contas' to Hunter v2 'FinancialGroup' (Plano Orçamentário).
- Automatic association with Suppliers, Collaborators, and Payment Methods.
- Accurate financial discount / surcharge handling (MoneyField/Decimal).
- Deduplication support to avoid double imports.
- Dry-run mode by default, requires --commit to persist changes.
"""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime
from decimal import Decimal
from io import StringIO
import os
import re
import sys
from typing import Any

# Ensure project root is on sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# ---------------------------------------------------------------------------
# 1. DATABASE CONFIGURATION (can be configured here or overridden via CLI/env)
# ---------------------------------------------------------------------------
DB_CONFIG: dict[str, str | int | None] = {
    "NAME": "railway",
    "USER": "postgres",
    "PASSWORD": "DUTbVebExfoQWpjyrIuupizAGZLTELbC",
    "HOST": "switchyard.proxy.rlwy.net",
    "PORT": "15758"
}

DEFAULT_WORKSHOP_ID = int("25")

# ---------------------------------------------------------------------------
# 2. BUDGET PLAN (Plano Orçamentário) MAPPING FOR WORKSHOP 25
# ---------------------------------------------------------------------------
# Maps Ultracar "Plano de Contas" string to Hunter v2 FinancialGroup (code & name).
BUDGET_PLAN_MAPPING: dict[str, dict[str, str]] = {
    "2100.0001 - Aluguel": {"code": "4.1", "name": "Aluguel Imovel"},
    "2100.0002 - Energia": {"code": "4.2.1", "name": "Agua/ Luz/ Telefone Internet"},
    "2100.0003 - Agua e Saneamento": {"code": "4.2.1", "name": "Agua/ Luz/ Telefone Internet"},
    "2100.0004 - Telefonia": {"code": "4.2.1", "name": "Agua/ Luz/ Telefone Internet"},
    "2100.0005 - Contabilidade": {"code": "6.1.6", "name": "Contabilidade"},
    "2100.0006 - Sistema  Gestão": {"code": "4.7", "name": "Sistemas"},
    "2200.0020 - Hora Extra": {"code": "6.1.9", "name": "Horas Extras Mensais"},
    "2300.0001 - Fornecedores de Peças": {"code": "5.1", "name": "Fornecedores de Peças"},
    "2300.0008 - Reforma e Melhoria Predial": {"code": "3.3", "name": "Reforma e Melhorias Prediais"},
    "2500.0007 - Fornecedor de serviços": {"code": "5.2", "name": "Fornecedores de Serviços"},
    "2500.0011 - MARKETING": {"code": "4.5", "name": "Marketing e Propaganda"},
    "2500.0013 - ATIVO IMOBILIZADO/MOBILIA/EQUIPAMENTO": {"code": "3.1", "name": "Equipamentos e Mobiliario (Ativos)"},
}

# Granular overrides based on description or beneficiary keyword
BUDGET_PLAN_OVERRIDES: list[dict[str, Any]] = [
    {"field": "description", "keyword": "SINDICATO", "code": "4.4.5", "name": "Sindicato"},
    {"field": "beneficiary", "keyword": "VERISURI", "code": "4.2.2", "name": "Monitoramento e Segurança"},
    {"field": "beneficiary", "keyword": "YAPAY", "code": "6.1.12", "name": "Segurança e Saude Ocupacional"},
    {"field": "beneficiary", "keyword": "PANORAM", "code": "4.5", "name": "Marketing e Propaganda"},
]

# ---------------------------------------------------------------------------
# 3. PAYMENT METHOD MAPPING (Doc. -> PaymentMethod.description)
# ---------------------------------------------------------------------------
PAYMENT_METHOD_MAPPING: dict[str, str] = {
    "BL": "Boleto",
    "TR": "Transferencia bancaria ou pix",
    "CCI": "Cartão de crédito itau",
}

# ---------------------------------------------------------------------------
# 4. BENEFICIARY ALIASES TO AID SUPPLIER LOOKUP
# ---------------------------------------------------------------------------
BENEFICIARY_ALIASES: dict[str, str] = {
    "VERISURI": "Verisure",
    "DANILO ANTONIO FURLAN": "Danilo Antonio Furlan",
    "TELEFONICA VIVO": "Telefonica Brasil S.A.",
    "ELETROPAULO": "Eletropaulo",
    "SABESP": "Sabesp",
    "LUBE CAR MINUTO/EURO REPAR": "Lube Car Minuto",
}

# ---------------------------------------------------------------------------
# 5. EMBEDDED CSV DATA (Fallback if no external file is provided)
# ---------------------------------------------------------------------------
DEFAULT_CSV_DATA = """Vencimento;Código;Parc.;Beneficiado;CPF/CNPJ;Descrição;Numero doc.;Doc.;Plano de Contas;Sit.;Emissão;Pagamento;Atraso;Valor;Acresc./Desc.;Total;C.Custo
01/09/2026;21658;9;ELETROPAULO;;CONTA DE ENERGIA ;;BL;2100.0002 - Energia;A;07/01/2026;;;500;0;500;
01/09/2026;21659;8;SABESP;;CONTA DE AGUA;;BL;2100.0003 - Agua e Saneamento;A;07/01/2026;;;300;0;300;
01/09/2026;21660;9;TELEFONICA VIVO;;TELEFONE/INTERNET;;BL;2100.0004 - Telefonia;A;07/01/2026;;;150;0;150;
01/09/2026;21661;9;TELEFONICA VIVO;;INTERNET CELULAR;;BL;2100.0004 - Telefonia;A;07/01/2026;;;58,33;0;58,33;
01/09/2026;23036;3;SIM LUBRIFICANTES E PRODUTOS AUTOMOTIVOS LTDA;35.080.137/0003-40;Compra 6689/3 - 131433;;BL;2300.0001 - Fornecedores de Peças;A;09/07/2026;;;536;0;536;
01/09/2026;23268;1;LEAUTO AUTO PEÇAS;07.862.095/0001-00;PASTILHA HB20;;BL;2300.0001 - Fornecedores de Peças;A;04/08/2026;;;80,7;0;80,7;
01/09/2026;23271;1;LEAUTO AUTO PEÇAS;07.862.095/0001-00;RETENTORES VECTRA;;BL;2300.0001 - Fornecedores de Peças;A;04/08/2026;;;64,11;0;64,11;
02/09/2026;22827;3;PE NA TABUA AUTO PECAS LTDA.;13.958.849/0001-14;3ª Parcela PE NA TABUA;;BL;2300.0001 - Fornecedores de Peças;A;05/06/2026;;;447,1;-16,75;430,35;
03/09/2026;23045;2;PE NA TABUA AUTO PECAS LTDA.;13.958.849/0001-14;1ª Parcela;;BL;2300.0001 - Fornecedores de Peças;A;13/07/2026;;;266,14;-54,94;211,2;
04/09/2026;21672;9;RAYSSA NASCIMENTO SILVA;538.229.718-55;HORA EXTRA MENSAL;;TR;2200.0020 - Hora Extra;A;07/01/2026;;;400;0;400;
04/09/2026;21674;9;MATEUS DE JESUS OLIVEIRA;485.522.098-10;HORA EXTRA MENSAL ;;TR;2200.0020 - Hora Extra;A;07/01/2026;;;500;0;500;
04/09/2026;21678;9;PABLO ENRIQUE IBANEZ ARAGON;712.835.992-36;HORA EXTRA MENSAL;;TR;2200.0020 - Hora Extra;A;07/01/2026;;;400;0;400;
04/09/2026;21682;9;CARLOS EDUARDO ALVES FERREIRA DA SILVA;546.794.668-47;HORA EXTRA MENSAL;;TR;2200.0020 - Hora Extra;A;07/01/2026;;;400;0;400;
04/09/2026;23037;2;ABSOLUTA DISTRIBUIDORA DE AUTOMOVEIS LTDA;01.197.867/0001-41;Compra 6690/2 - 597979;;BL;2300.0001 - Fornecedores de Peças;A;09/07/2026;;;370,8;0;370,8;
05/09/2026;21703;9;VERISURI;;ALARME LOJA;;BL;2500.0007 - Fornecedor de serviços;A;08/01/2026;;;224,98;0;224,98;
06/09/2026;21662;9;DANILO ANTONIO FURLAN;;ALUGUEL+IMPOSTO - Renegociada;;TR;2100.0001 - Aluguel;A;07/01/2026;;;8.500,00;0;8.500,00;
06/09/2026;21665;9;CAMIS CONTABILIDADE;13.104.437/0001-17;MENSALIDADE CONTABILIDADE - Renegociada;;BL;2100.0005 - Contabilidade;A;07/01/2026;;;733;0;733;
06/09/2026;23044;2;PJ CAR AUTO PEÇAS LTDA;46.466.780/0001-60;2ª Parcela;2º PARCELA PJ;BL;2300.0001 - Fornecedores de Peças;A;10/07/2026;;;439,2;0;439,2;
06/09/2026;23283;1;PE NA TABUA AUTO PECAS LTDA.;13.958.849/0001-14;1ª Parcela PE NA TABUA;;BL;2300.0001 - Fornecedores de Peças;A;11/08/2026;;;385,79;-19,29;366,5;
07/09/2026;22174;7;MAHOVI INDUSTRIA E COMERCIO DE EQUIPAMENTOS LTDA;32.554.486/0002-87;Compra 6306/7 - 1386;;BL;2500.0013 - ATIVO IMOBILIZADO/MOBILIA/EQUIPAMENTO;A;11/03/2026;;;1.572,44;0;1.572,44;
08/09/2026;21962;8;CAMIS CONTABILIDADE;13.104.437/0001-17;SINDICATO;;TR;2100.0005 - Contabilidade;A;10/02/2026;;;119,47;0;119,47;
08/09/2026;23235;3;BRIDA LUBRIFICANTES LTDA;00.846.804/0001-06;Compra 6759/3 - 1435582;1435582;BL;2300.0001 - Fornecedores de Peças;A;31/07/2026;;;1.542,35;0;1.542,35;
13/09/2026;23172;2;FIRST DISTRIBUIDORA LTDA;51.328.675/0001-03;Compra 6755/2 - 107750;107750;BL;2300.0001 - Fornecedores de Peças;A;30/07/2026;;;255,15;0;255,15;
16/09/2026;22882;3;PE NA TABUA AUTO PECAS LTDA.;13.958.849/0001-14;1ª Parcela;;BL;2300.0001 - Fornecedores de Peças;A;16/06/2026;;;664,01;-12,97;651,04;
17/09/2026;21798;9;YAPAY PAGAMENTOS ONLINE LTDA;14.338.304/0001-78;PLANO DE SAUDE;;BL;2500.0007 - Fornecedor de serviços;A;20/01/2026;;;3.163,02;0;3.163,02;
17/09/2026;21834;8;PANORAM DIGITAL MARKETING LTDA;28.271.509/0001-98;TRAFEGO PAGO;;BL;2500.0011 - MARKETING;A;23/01/2026;;;897;0;897;
18/09/2026;23235;4;BRIDA LUBRIFICANTES LTDA;00.846.804/0001-06;Compra 6759/4 - 1435582;1435582;BL;2300.0001 - Fornecedores de Peças;A;31/07/2026;;;1.542,35;0;1.542,35;
20/09/2026;21354;10;PANORAM DIGITAL MARKETING LTDA;28.271.509/0001-98;TRAFEGO PAGO (MENSALIDADE);;BL;2500.0007 - Fornecedor de serviços;A;25/11/2025;;;997;0;997;
20/09/2026;22703;5;USETINTAS COMERCIO DE TINTAS E ACESSORIOS LTDA.;05.841.962/0001-97;Compra 6552/1 - 62600;62600;CCI;2300.0008 - Reforma e Melhoria Predial;A;20/05/2026;;;479,1;0;479,1;
20/09/2026;23117;3;TECNOLUZ MATERIAIS ELETR, PROJT E INSTALACOES LTDA;60.950.748/0001-87;Compra 6732/3 - 21667;;CCI;2500.0013 - ATIVO IMOBILIZADO/MOBILIA/EQUIPAMENTO;A;23/07/2026;;;280,18;0;280,18;
21/09/2026;21666;9;LUBE CAR MINUTO/EURO REPAR;;APP PONTO - Renegociada;;TR;2100.0006 - Sistema  Gestão;A;07/01/2026;;;80;0;80;
26/09/2026;23170;2;ITAPECAS PARA VEICULOS COMERCIO E SERVICOS LTDA;06.352.893/0003-82;Compra 6753/2 - 853540;853540;BL;2300.0001 - Fornecedores de Peças;A;29/07/2026;;;265,75;0;265,75;
28/09/2026;23172;3;FIRST DISTRIBUIDORA LTDA;51.328.675/0001-03;Compra 6755/3 - 107750;107750;BL;2300.0001 - Fornecedores de Peças;A;30/07/2026;;;255,15;0;255,15;
01/10/2026;21658;10;ELETROPAULO;;CONTA DE ENERGIA ;;BL;2100.0002 - Energia;A;07/01/2026;;;500;0;500;
01/10/2026;21659;9;SABESP;;CONTA DE AGUA;;BL;2100.0003 - Agua e Saneamento;A;07/01/2026;;;300;0;300;
01/10/2026;21660;10;TELEFONICA VIVO;;TELEFONE/INTERNET;;BL;2100.0004 - Telefonia;A;07/01/2026;;;150;0;150;
01/10/2026;21661;10;TELEFONICA VIVO;;INTERNET CELULAR;;BL;2100.0004 - Telefonia;A;07/01/2026;;;58,33;0;58,33;
04/10/2026;21672;10;RAYSSA NASCIMENTO SILVA;538.229.718-55;HORA EXTRA MENSAL;;TR;2200.0020 - Hora Extra;A;07/01/2026;;;400;0;400;
04/10/2026;21674;10;MATEUS DE JESUS OLIVEIRA;485.522.098-10;HORA EXTRA MENSAL ;;TR;2200.0020 - Hora Extra;A;07/01/2026;;;500;0;500;
04/10/2026;21678;10;PABLO ENRIQUE IBANEZ ARAGON;712.835.992-36;HORA EXTRA MENSAL;;TR;2200.0020 - Hora Extra;A;07/01/2026;;;400;0;400;
04/10/2026;21682;10;CARLOS EDUARDO ALVES FERREIRA DA SILVA;546.794.668-47;HORA EXTRA MENSAL;;TR;2200.0020 - Hora Extra;A;07/01/2026;;;400;0;400;
05/10/2026;21703;10;VERISURI;;ALARME LOJA;;BL;2500.0007 - Fornecedor de serviços;A;08/01/2026;;;224,98;0;224,98;
06/10/2026;21662;10;DANILO ANTONIO FURLAN;;ALUGUEL+IMPOSTO - Renegociada;;TR;2100.0001 - Aluguel;A;07/01/2026;;;8.500,00;0;8.500,00;
06/10/2026;21665;10;CAMIS CONTABILIDADE;13.104.437/0001-17;MENSALIDADE CONTABILIDADE - Renegociada;;BL;2100.0005 - Contabilidade;A;07/01/2026;;;733;0;733;
06/10/2026;23283;2;PE NA TABUA AUTO PECAS LTDA.;13.958.849/0001-14;1ª Parcela PE NA TABUA;;BL;2300.0001 - Fornecedores de Peças;A;11/08/2026;;;385,79;-19,29;366,5;
07/10/2026;22174;8;MAHOVI INDUSTRIA E COMERCIO DE EQUIPAMENTOS LTDA;32.554.486/0002-87;Compra 6306/8 - 1386;;BL;2500.0013 - ATIVO IMOBILIZADO/MOBILIA/EQUIPAMENTO;A;11/03/2026;;;1.572,44;0;1.572,44;
08/10/2026;21962;9;CAMIS CONTABILIDADE;13.104.437/0001-17;SINDICATO;;TR;2100.0005 - Contabilidade;A;10/02/2026;;;119,47;0;119,47;
13/10/2026;23172;4;FIRST DISTRIBUIDORA LTDA;51.328.675/0001-03;Compra 6755/4 - 107750;107750;BL;2300.0001 - Fornecedores de Peças;A;30/07/2026;;;255,15;0;255,15;
17/10/2026;21798;10;YAPAY PAGAMENTOS ONLINE LTDA;14.338.304/0001-78;PLANO DE SAUDE;;BL;2500.0007 - Fornecedor de serviços;A;20/01/2026;;;3.163,02;0;3.163,02;
17/10/2026;21834;9;PANORAM DIGITAL MARKETING LTDA;28.271.509/0001-98;TRAFEGO PAGO;;BL;2500.0011 - MARKETING;A;23/01/2026;;;897;0;897;
20/10/2026;21354;11;PANORAM DIGITAL MARKETING LTDA;28.271.509/0001-98;TRAFEGO PAGO (MENSALIDADE);;BL;2500.0007 - Fornecedor de serviços;A;25/11/2025;;;997;0;997;
21/10/2026;21666;10;LUBE CAR MINUTO/EURO REPAR;;APP PONTO - Renegociada;;TR;2100.0006 - Sistema  Gestão;A;07/01/2026;;;80;0;80;
26/10/2026;23170;3;ITAPECAS PARA VEICULOS COMERCIO E SERVICOS LTDA;06.352.893/0003-82;Compra 6753/3 - 853540;853540;BL;2300.0001 - Fornecedores de Peças;A;29/07/2026;;;265,75;0;265,75;
28/10/2026;23172;5;FIRST DISTRIBUIDORA LTDA;51.328.675/0001-03;Compra 6755/5 - 107750;107750;BL;2300.0001 - Fornecedores de Peças;A;30/07/2026;;;255,14;0;255,14;
31/10/2026;21658;11;ELETROPAULO;;CONTA DE ENERGIA ;;BL;2100.0002 - Energia;A;07/01/2026;;;500;0;500;
31/10/2026;21659;10;SABESP;;CONTA DE AGUA;;BL;2100.0003 - Agua e Saneamento;A;07/01/2026;;;300;0;300;
31/10/2026;21660;11;TELEFONICA VIVO;;TELEFONE/INTERNET;;BL;2100.0004 - Telefonia;A;07/01/2026;;;150;0;150;
31/10/2026;21661;11;TELEFONICA VIVO;;INTERNET CELULAR;;BL;2100.0004 - Telefonia;A;07/01/2026;;;58,33;0;58,33;
03/11/2026;21672;11;RAYSSA NASCIMENTO SILVA;538.229.718-55;HORA EXTRA MENSAL;;TR;2200.0020 - Hora Extra;A;07/01/2026;;;400;0;400;
03/11/2026;21674;11;MATEUS DE JESUS OLIVEIRA;485.522.098-10;HORA EXTRA MENSAL ;;TR;2200.0020 - Hora Extra;A;07/01/2026;;;500;0;500;
03/11/2026;21678;11;PABLO ENRIQUE IBANEZ ARAGON;712.835.992-36;HORA EXTRA MENSAL;;TR;2200.0020 - Hora Extra;A;07/01/2026;;;400;0;400;
03/11/2026;21682;11;CARLOS EDUARDO ALVES FERREIRA DA SILVA;546.794.668-47;HORA EXTRA MENSAL;;TR;2200.0020 - Hora Extra;A;07/01/2026;;;400;0;400;
04/11/2026;21703;11;VERISURI;;ALARME LOJA;;BL;2500.0007 - Fornecedor de serviços;A;08/01/2026;;;224,98;0;224,98;
05/11/2026;21662;11;DANILO ANTONIO FURLAN;;ALUGUEL+IMPOSTO - Renegociada;;TR;2100.0001 - Aluguel;A;07/01/2026;;;8.500,00;0;8.500,00;
05/11/2026;21665;11;CAMIS CONTABILIDADE;13.104.437/0001-17;MENSALIDADE CONTABILIDADE - Renegociada;;BL;2100.0005 - Contabilidade;A;07/01/2026;;;733;0;733;
06/11/2026;22174;9;MAHOVI INDUSTRIA E COMERCIO DE EQUIPAMENTOS LTDA;32.554.486/0002-87;Compra 6306/9 - 1386;;BL;2500.0013 - ATIVO IMOBILIZADO/MOBILIA/EQUIPAMENTO;A;11/03/2026;;;1.572,44;0;1.572,44;
07/11/2026;21962;10;CAMIS CONTABILIDADE;13.104.437/0001-17;SINDICATO;;TR;2100.0005 - Contabilidade;A;10/02/2026;;;119,47;0;119,47;
16/11/2026;21798;11;YAPAY PAGAMENTOS ONLINE LTDA;14.338.304/0001-78;PLANO DE SAUDE;;BL;2500.0007 - Fornecedor de serviços;A;20/01/2026;;;3.163,02;0;3.163,02;
16/11/2026;21834;10;PANORAM DIGITAL MARKETING LTDA;28.271.509/0001-98;TRAFEGO PAGO;;BL;2500.0011 - MARKETING;A;23/01/2026;;;897;0;897;
20/11/2026;21666;11;LUBE CAR MINUTO/EURO REPAR;;APP PONTO - Renegociada;;TR;2100.0006 - Sistema  Gestão;A;07/01/2026;;;80;0;80;
30/11/2026;21658;12;ELETROPAULO;;CONTA DE ENERGIA ;;BL;2100.0002 - Energia;A;07/01/2026;;;500;0;500;
30/11/2026;21659;11;SABESP;;CONTA DE AGUA;;BL;2100.0003 - Agua e Saneamento;A;07/01/2026;;;300;0;300;
30/11/2026;21660;12;TELEFONICA VIVO;;TELEFONE/INTERNET;;BL;2100.0004 - Telefonia;A;07/01/2026;;;150;0;150;
30/11/2026;21661;12;TELEFONICA VIVO;;INTERNET CELULAR;;BL;2100.0004 - Telefonia;A;07/01/2026;;;58,33;0;58,33;
03/12/2026;21672;12;RAYSSA NASCIMENTO SILVA;538.229.718-55;HORA EXTRA MENSAL;;TR;2200.0020 - Hora Extra;A;07/01/2026;;;400;0;400;
03/12/2026;21674;12;MATEUS DE JESUS OLIVEIRA;485.522.098-10;HORA EXTRA MENSAL ;;TR;2200.0020 - Hora Extra;A;07/01/2026;;;500;0;500;
03/12/2026;21678;12;PABLO ENRIQUE IBANEZ ARAGON;712.835.992-36;HORA EXTRA MENSAL;;TR;2200.0020 - Hora Extra;A;07/01/2026;;;400;0;400;
03/12/2026;21682;12;CARLOS EDUARDO ALVES FERREIRA DA SILVA;546.794.668-47;HORA EXTRA MENSAL;;TR;2200.0020 - Hora Extra;A;07/01/2026;;;400;0;400;
04/12/2026;21703;12;VERISURI;;ALARME LOJA;;BL;2500.0007 - Fornecedor de serviços;A;08/01/2026;;;224,98;0;224,98;
05/12/2026;21662;12;DANILO ANTONIO FURLAN;;ALUGUEL+IMPOSTO - Renegociada;;TR;2100.0001 - Aluguel;A;07/01/2026;;;8.500,00;0;8.500,00;
05/12/2026;21665;12;CAMIS CONTABILIDADE;13.104.437/0001-17;MENSALIDADE CONTABILIDADE - Renegociada;;BL;2100.0005 - Contabilidade;A;07/01/2026;;;733;0;733;
06/12/2026;22174;10;MAHOVI INDUSTRIA E COMERCIO DE EQUIPAMENTOS LTDA;32.554.486/0002-87;Compra 6306/10 - 1386;;BL;2500.0013 - ATIVO IMOBILIZADO/MOBILIA/EQUIPAMENTO;A;11/03/2026;;;1.572,44;0;1.572,44;
07/12/2026;21962;11;CAMIS CONTABILIDADE;13.104.437/0001-17;SINDICATO;;TR;2100.0005 - Contabilidade;A;10/02/2026;;;119,47;0;119,47;
16/12/2026;21798;12;YAPAY PAGAMENTOS ONLINE LTDA;14.338.304/0001-78;PLANO DE SAUDE;;BL;2500.0007 - Fornecedor de serviços;A;20/01/2026;;;3.163,02;0;3.163,02;
16/12/2026;21834;11;PANORAM DIGITAL MARKETING LTDA;28.271.509/0001-98;TRAFEGO PAGO;;BL;2500.0011 - MARKETING;A;23/01/2026;;;897;0;897;
20/12/2026;21666;12;LUBE CAR MINUTO/EURO REPAR;;APP PONTO - Renegociada;;TR;2100.0006 - Sistema  Gestão;A;07/01/2026;;;80;0;80;"""


def parse_decimal(raw_val: str | None) -> Decimal:
    if not raw_val:
        return Decimal("0.00")
    cleaned = raw_val.strip().replace(".", "").replace(",", ".")
    try:
        return Decimal(cleaned).quantize(Decimal("0.01"))
    except Exception:
        return Decimal("0.00")


def parse_brazilian_date(raw_date: str | None) -> date | None:
    if not raw_date or not raw_date.strip():
        return None
    try:
        return datetime.strptime(raw_date.strip(), "%d/%m/%Y").date()
    except ValueError:
        return None


def clean_digits(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\D", "", value)


def resolve_budget_plan(
    workshop: Any,
    raw_plano: str,
    description: str,
    beneficiary: str,
    cache: dict[str, Any],
) -> Any | None:
    from apps.finance.models import FinancialGroup

    # 1. Check specific overrides first
    for override in BUDGET_PLAN_OVERRIDES:
        target_val = description if override["field"] == "description" else beneficiary
        if override["keyword"].upper() in target_val.upper():
            cache_key = f"code_{override['code']}"
            if cache_key not in cache:
                cache[cache_key] = FinancialGroup.objects.filter(workshop=workshop, code=override["code"]).first()
            if cache[cache_key]:
                return cache[cache_key]

    # 2. Check standard mapping table
    mapping = BUDGET_PLAN_MAPPING.get(raw_plano.strip())
    if mapping:
        cache_key = f"code_{mapping['code']}"
        if cache_key not in cache:
            cache[cache_key] = FinancialGroup.objects.filter(workshop=workshop, code=mapping["code"]).first()
        if cache[cache_key]:
            return cache[cache_key]

    # 3. Fallback: try by name match
    name_clean = raw_plano.split("-")[-1].strip()
    cache_key = f"name_{name_clean.lower()}"
    if cache_key not in cache:
        cache[cache_key] = FinancialGroup.objects.filter(workshop=workshop, name__icontains=name_clean).first()
    return cache.get(cache_key)


def resolve_payment_method(
    workshop: Any,
    doc_type: str,
    cache: dict[str, Any],
) -> Any | None:
    from apps.finance.models import PaymentMethod

    expected_name = PAYMENT_METHOD_MAPPING.get(doc_type.strip().upper(), "Boleto")
    cache_key = expected_name.lower()
    if cache_key not in cache:
        cache[cache_key] = PaymentMethod.objects.filter(
            workshop=workshop,
            description__iexact=expected_name,
        ).first()
        if not cache[cache_key]:
            cache[cache_key] = PaymentMethod.objects.filter(
                workshop=workshop,
                description__icontains=expected_name,
            ).first()
    return cache.get(cache_key)


def resolve_supplier_or_collaborator(
    workshop: Any,
    beneficiary: str,
    cpf_cnpj: str,
    is_payroll_expense: bool,
    supplier_cache: dict[str, Any],
    collaborator_cache: dict[str, Any],
) -> tuple[Any | None, Any | None]:
    from apps.collaborators.models import WorkshopCollaborator
    from apps.suppliers.models import Supplier

    clean_doc = clean_digits(cpf_cnpj)
    supplier = None
    collaborator = None

    # Collaborator check for Hora Extra / Payroll expenses
    if is_payroll_expense:
        if clean_doc:
            if clean_doc in collaborator_cache:
                collaborator = collaborator_cache[clean_doc]
            else:
                collaborator = WorkshopCollaborator.objects.filter(
                    workshop=workshop,
                    cpf=clean_doc,
                ).first()
                collaborator_cache[clean_doc] = collaborator

        if not collaborator and beneficiary:
            b_clean = beneficiary.strip()
            if b_clean in collaborator_cache:
                collaborator = collaborator_cache[b_clean]
            else:
                collaborator = WorkshopCollaborator.objects.filter(
                    workshop=workshop,
                    name__icontains=b_clean,
                ).first()
                collaborator_cache[b_clean] = collaborator

        if collaborator:
            return None, collaborator

    # Supplier lookup
    if clean_doc:
        if clean_doc in supplier_cache:
            supplier = supplier_cache[clean_doc]
        else:
            supplier = Supplier.objects.filter(workshop=workshop, cnpj=clean_doc).first()
            supplier_cache[clean_doc] = supplier

    if not supplier and beneficiary:
        search_name = BENEFICIARY_ALIASES.get(beneficiary.strip().upper(), beneficiary.strip())
        if search_name in supplier_cache:
            supplier = supplier_cache[search_name]
        else:
            supplier = Supplier.objects.filter(workshop=workshop, name__icontains=search_name).first()
            supplier_cache[search_name] = supplier

    return supplier, collaborator


def check_is_duplicate(
    workshop_id: int,
    due_date: date,
    amount: Decimal,
    description: str,
    supplier_id: int | None,
    collaborator_id: int | None,
    code: str,
) -> Any | None:
    from apps.finance.models import FinancialMovement

    # Check exact date and amount in workshop DEBITs
    qs = FinancialMovement.objects.filter(
        workshop_id=workshop_id,
        direction=FinancialMovement.MovementDirection.DEBIT,
        due_date=due_date,
        amount=amount,
    )

    if not qs.exists():
        return None

    # Refine matching: check if observation has Ultracar code, or description matches
    for movement in qs:
        # Match by Ultracar code in observation or description
        if code and code in (movement.financial_observation or ""):
            return movement
        if code and code in (movement.description or ""):
            return movement
        # Match by supplier or collaborator
        if supplier_id and movement.supplier_id == supplier_id:
            return movement
        if collaborator_id and movement.collaborator_id == collaborator_id:
            return movement
        # Match by description overlap
        if "ultracar" in (movement.description or "").lower():
            return movement

    return qs.first()


def setup_django_environment(db_config: dict[str, Any]) -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()

    # If custom database params provided, apply them dynamically
    from django.conf import settings
    from django.db import connections

    modified = False
    for k, v in db_config.items():
        if v is not None and settings.DATABASES["default"].get(k) != v:
            settings.DATABASES["default"][k] = v
            modified = True

    if modified:
        connections["default"].close()


def run_import(
    csv_file_path: str | None = None,
    workshop_id: int = DEFAULT_WORKSHOP_ID,
    commit: bool = False,
    skip_existing: bool = True,
) -> int:
    from django.db import transaction
    from djmoney.money import Money

    from apps.finance.models import FinancialMovement
    from apps.workshops.models.workshops import Workshop

    workshop = Workshop.objects.filter(id=workshop_id).first()
    if not workshop:
        print(f"[ERROR] Oficina com ID {workshop_id} não foi encontrada no banco!")
        return 1

    print("=" * 80)
    print(f"IMPORTAÇÃO DE CONTAS A PAGAR (ULTRACAR) -> OFICINA ID {workshop.id} ({workshop.name})")
    print(f"Modo de Execução: {'[GRAVAÇÃO NO BANCO - COMMIT]' if commit else '[SIMULAÇÃO SEGURA - DRY-RUN]'}")
    print(f"Pular Existentes (Deduplicação): {'Ativado' if skip_existing else 'Desativado'}")
    print("=" * 80)

    # Read CSV
    if csv_file_path and os.path.exists(csv_file_path):
        print(f"Lendo dados a partir do arquivo: {csv_file_path}")
        with open(csv_file_path, mode="r", encoding="utf-8-sig", errors="replace") as f:
            csv_content = f.read()
    else:
        print("Utilizando base de dados embutida (86 lançamentos Ultracar).")
        csv_content = DEFAULT_CSV_DATA

    reader = csv.DictReader(StringIO(csv_content), delimiter=";")

    budget_plan_cache: dict[str, Any] = {}
    payment_method_cache: dict[str, Any] = {}
    supplier_cache: dict[str, Any] = {}
    collaborator_cache: dict[str, Any] = {}

    total_rows = 0
    total_gross = Decimal("0.00")
    total_net = Decimal("0.00")
    total_discount = Decimal("0.00")

    skipped_duplicates = 0
    inserted_records = 0
    errors: list[str] = []

    movements_to_create: list[FinancialMovement] = []

    for index, row in enumerate(reader, start=1):
        total_rows += 1

        due_date = parse_brazilian_date(row.get("Vencimento"))
        entry_date = parse_brazilian_date(row.get("Emissão")) or due_date or date.today()
        code = (row.get("Código") or "").strip()
        installment_raw = (row.get("Parc.") or "").strip()
        beneficiary = (row.get("Beneficiado") or "").strip()
        cpf_cnpj = (row.get("CPF/CNPJ") or "").strip()
        description = (row.get("Descrição") or "").strip()
        doc_num = (row.get("Numero doc.") or "").strip()
        doc_type = (row.get("Doc.") or "").strip()
        plano_contas = (row.get("Plano de Contas") or "").strip()

        gross_val = parse_decimal(row.get("Valor"))
        adjustment_val = parse_decimal(row.get("Acresc./Desc."))
        net_val = parse_decimal(row.get("Total"))

        total_gross += gross_val
        total_discount += adjustment_val
        total_net += net_val

        if not due_date:
            errors.append(f"Linha {index} (Código {code}): Data de vencimento inválida '{row.get('Vencimento')}'.")
            continue

        # 1. Resolve Budget Plan
        budget_plan = resolve_budget_plan(
            workshop=workshop,
            raw_plano=plano_contas,
            description=description,
            beneficiary=beneficiary,
            cache=budget_plan_cache,
        )
        if not budget_plan:
            errors.append(f"Linha {index} (Código {code}): Não foi possível mapear o Plano Orçamentário para '{plano_contas}'.")

        # 2. Resolve Payment Method
        payment_method = resolve_payment_method(
            workshop=workshop,
            doc_type=doc_type,
            cache=payment_method_cache,
        )

        # 3. Resolve Supplier / Collaborator
        is_payroll = "Hora Extra" in plano_contas or "2200." in plano_contas
        supplier, collaborator = resolve_supplier_or_collaborator(
            workshop=workshop,
            beneficiary=beneficiary,
            cpf_cnpj=cpf_cnpj,
            is_payroll_expense=is_payroll,
            supplier_cache=supplier_cache,
            collaborator_cache=collaborator_cache,
        )

        # 4. Check for duplicate
        existing_fm = check_is_duplicate(
            workshop_id=workshop.id,
            due_date=due_date,
            amount=net_val,
            description=description,
            supplier_id=supplier.id if supplier else None,
            collaborator_id=collaborator.id if collaborator else None,
            code=code,
        )

        if existing_fm and skip_existing:
            skipped_duplicates += 1
            print(f"  [PULADO - DUPLICADO] Linha {index:02d} | Venc: {due_date.strftime('%d/%m/%Y')} | R$ {net_val:9.2f} | {beneficiary[:25]:<25} -> Já existe (FM ID {existing_fm.id})")
            continue

        # 5. Discount Mode & Values
        if adjustment_val < 0:
            discount_mode = FinancialMovement.DiscountMode.AMOUNT
            discount_value = abs(adjustment_val)
        elif adjustment_val > 0:
            discount_mode = FinancialMovement.DiscountMode.SURCHARGE
            discount_value = adjustment_val
        else:
            discount_mode = FinancialMovement.DiscountMode.NONE
            discount_value = Decimal("0.00")

        installment_number = int(installment_raw) if installment_raw.isdigit() else None

        # Build FinancialMovement instance
        movement = FinancialMovement(
            workshop=workshop,
            direction=FinancialMovement.MovementDirection.DEBIT,
            movement_kind=FinancialMovement.MovementKind.DEFAULT,
            description=f"{beneficiary} - {description}".strip(" -") if description else beneficiary,
            nf_number=doc_num or None,
            entry_date=entry_date,
            due_date=due_date,
            gross_amount=Money(gross_val, "BRL"),
            discount_mode=discount_mode,
            discount_value=Money(discount_value, "BRL"),
            amount=Money(net_val, "BRL"),
            is_paid=False,
            budget_plan=budget_plan,
            payment_method=payment_method,
            supplier=supplier,
            collaborator=collaborator,
            installment_number=installment_number,
            financial_observation=f"Importado Ultracar | Cód: {code} | Parc: {installment_raw} | Doc: {doc_type} | Plano Orig: {plano_contas}",
        )
        movements_to_create.append(movement)
        inserted_records += 1

        beneficiary_display = (supplier.name if supplier else (collaborator.name if collaborator else beneficiary))[:25]
        budget_display = budget_plan.code_label if budget_plan else "N/A"
        print(f"  [A IMPORTAR] Linha {index:02d} | Venc: {due_date.strftime('%d/%m/%Y')} | R$ {net_val:9.2f} | {beneficiary_display:<25} | Grupo: {budget_display}")

    # Print Summary Report
    print("\n" + "=" * 80)
    print("RESUMO DA ANÁLISE E IMPORTAÇÃO")
    print("=" * 80)
    print(f"Total de Linhas no Arquivo: {total_rows}")
    print(f"Total Bruto Analisado:      R$ {total_gross:12.2f}")
    print(f"Total Descontos / Ajustes:  R$ {total_discount:12.2f}")
    print(f"Total Líquido Analisado:    R$ {total_net:12.2f}")
    print("-" * 80)
    print(f"Registros Já Existentes:    {skipped_duplicates} (pulados para evitar duplicidade)")
    print(f"Novos Registros a Inserir:  {inserted_records}")
    print(f"Erros Encontrados:          {len(errors)}")

    if errors:
        print("\nLista de Alertas / Erros:")
        for err in errors[:10]:
            print(f"  - {err}")
        if len(errors) > 10:
            print(f"  ... e mais {len(errors) - 10} avisos.")

    if commit and movements_to_create:
        print("\nGravando registros no banco de dados...")
        with transaction.atomic():
            for mov in movements_to_create:
                mov.save()
        print(f"[SUCESSO] {len(movements_to_create)} movimentações financeiras foram criadas com sucesso na oficina {workshop.id}!")
    elif not commit:
        print("\n[AVISO] Nenhuma alteração foi gravada pois o script rodou em modo de simulação (--dry-run).")
        print("Para gravar permanentemente no banco, execute com o parâmetro: --commit")

    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Importação de Contas a Pagar Ultracar para Oficina 25.")
    parser.add_argument("--commit", action="store_true", help="Efetiva a gravação no banco de dados.")
    parser.add_argument("--dry-run", action="store_true", help="Modo de simulação (padrão).")
    parser.add_argument("--file", type=str, default=None, help="Caminho para arquivo CSV externo.")
    parser.add_argument("--workshop-id", type=int, default=DEFAULT_WORKSHOP_ID, help="ID da oficina (padrão: 25).")
    parser.add_argument("--force-all", action="store_true", help="Não pula registros já existentes.")

    # DB Config CLI overrides
    parser.add_argument("--db-name", type=str, default=None, help="Nome do banco de dados PostgreSQL.")
    parser.add_argument("--db-user", type=str, default=None, help="Usuário do banco de dados.")
    parser.add_argument("--db-password", type=str, default=None, help="Senha do banco de dados.")
    parser.add_argument("--db-host", type=str, default=None, help="Host do banco de dados.")
    parser.add_argument("--db-port", type=int, default=None, help="Porta do banco de dados.")

    args = parser.parse_args()

    # Merge CLI database options into DB_CONFIG
    if args.db_name:
        DB_CONFIG["NAME"] = args.db_name
    if args.db_user:
        DB_CONFIG["USER"] = args.db_user
    if args.db_password:
        DB_CONFIG["PASSWORD"] = args.db_password
    if args.db_host:
        DB_CONFIG["HOST"] = args.db_host
    if args.db_port:
        DB_CONFIG["PORT"] = args.db_port

    setup_django_environment(DB_CONFIG)

    exit_code = run_import(
        csv_file_path=args.file,
        workshop_id=args.workshop_id,
        commit=args.commit and not args.dry_run,
        skip_existing=not args.force_all,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
