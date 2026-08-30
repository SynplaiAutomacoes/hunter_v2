from __future__ import annotations

from typing import Any


def default_vehicle_receipt_content() -> dict[str, Any]:
    return {
        "sections": [
            {
                "id": "sec-1",
                "title": "TERMO DE RECEBIMENTO DE VEÍCULO",
                "subtitle": "Informações importantes para diagnóstico e manutenção",
                "show_vehicle_banner": True,
                "topics": [
                    {
                        "id": "topic-1",
                        "number": "01",
                        "title": "TESTES E CONSUMO DE COMBUSTÍVEL",
                        "paragraphs": [
                            "Durante o diagnóstico e a manutenção, poderá ser necessário realizar deslocamentos em via pública. Caso o veículo esteja com baixo nível de combustível, será realizado abastecimento por nossa equipe, e o valor será lançado na ordem de serviço.",
                            "Em diagnósticos intermitentes ou manutenção de câmbio automático, o consumo pode ser mais elevado. Em reparos de transmissão, poderá ser necessário rodar no mínimo 100 km.",
                        ],
                        "bullets": [],
                    },
                    {
                        "id": "topic-2",
                        "number": "02",
                        "title": "SEGURO E RESTRIÇÕES",
                        "paragraphs": [
                            "Caso o veículo não possua seguro, essa condição deverá ser informada no ato da assinatura deste termo.",
                            "Eventual restrição judicial ou bloqueio administrativo que possa levar à apreensão do veículo em blitz ou fiscalização deverá ser obrigatoriamente comunicado à oficina no ato da assinatura.",
                        ],
                        "bullets": [],
                    },
                    {
                        "id": "topic-3",
                        "number": "03",
                        "title": "PRAZOS DE DIAGNÓSTICO",
                        "paragraphs": [
                            "Para diagnósticos, é necessário deixar o veículo por no mínimo 2 dias úteis. O prazo poderá se estender conforme a complexidade do defeito.",
                            "Após o diagnóstico, será elaborado orçamento detalhado com valores e prazos. Nenhum serviço será executado sem a aprovação do cliente.",
                        ],
                        "bullets": [],
                    },
                    {
                        "id": "topic-4",
                        "number": "04",
                        "title": "TAXA DE DIAGNÓSTICO",
                        "paragraphs": [
                            "Caso o cliente não aprove o orçamento, será cobrada taxa mínima de R$ 380,00.",
                            "Em casos de difícil diagnóstico, a taxa poderá ser maior, proporcionalmente à complexidade, e será informada no envio do orçamento.",
                            "A taxa poderá ser abatida integralmente do valor do serviço caso o cliente retorne em até 90 dias corridos para executar o orçamento fornecido.",
                        ],
                        "bullets": [],
                    },
                ],
            },
            {
                "id": "sec-2",
                "title": "CONDIÇÕES COMPLEMENTARES",
                "subtitle": "Leia atentamente antes de assinar",
                "show_vehicle_banner": False,
                "topics": [
                    {
                        "id": "topic-5",
                        "number": "05",
                        "title": "PEÇAS E GARANTIA",
                        "paragraphs": [
                            "A oficina não se responsabiliza por defeitos de peças fornecidas pelo cliente. Havendo necessidade de retrabalho, a mão de obra será cobrada novamente.",
                            "Para peças sob encomenda em concessionárias, será solicitado pagamento antecipado. Se o veículo puder circular, poderá ser liberado até a chegada da peça, com novo agendamento para instalação.",
                        ],
                        "bullets": [],
                    },
                    {
                        "id": "topic-6",
                        "number": "06",
                        "title": "PRAZO PARA RETIRADA DO VEÍCULO",
                        "paragraphs": [
                            "Em caso de não aprovação do orçamento, o cliente terá prazo máximo de 48 horas para retirar o veículo.",
                            "Após esse prazo, será cobrada taxa de permanência de R$ 50,00 por dia de ocupação na oficina.",
                        ],
                        "bullets": [],
                    },
                    {
                        "id": "topic-7",
                        "number": "07",
                        "title": "CONDIÇÕES GERAIS",
                        "paragraphs": [],
                        "bullets": [
                            "Todos os serviços são realizados por profissionais capacitados, visando segurança e qualidade.",
                            "O cliente declara estar ciente das condições descritas neste termo e concorda com os termos apresentados.",
                        ],
                    },
                ],
                "include_signature_block": True,
            },
        ],
    }


def default_warranty_content() -> dict[str, Any]:
    return {
        "sections": [
            {
                "id": "sec-1",
                "title": "TERMO DE GARANTIA",
                "subtitle": "Condições de cobertura dos serviços executados",
                "show_vehicle_banner": True,
                "topics": [
                    {
                        "id": "topic-1",
                        "number": "01",
                        "title": "COBERTURA",
                        "paragraphs": [
                            "A garantia cobre exclusivamente os serviços e peças descritos na ordem de serviço vinculada a este documento, pelo prazo informado na entrega do veículo.",
                        ],
                        "bullets": [],
                    },
                    {
                        "id": "topic-2",
                        "number": "02",
                        "title": "EXCLUSÕES",
                        "paragraphs": [],
                        "bullets": [
                            "Desgaste natural de componentes.",
                            "Danos causados por mau uso, acidentes ou alterações não autorizadas.",
                            "Peças fornecidas pelo cliente.",
                        ],
                    },
                ],
            },
            {
                "id": "sec-2",
                "title": "CIÊNCIA DO CLIENTE",
                "subtitle": "Declaração de concordância",
                "show_vehicle_banner": False,
                "topics": [
                    {
                        "id": "topic-3",
                        "number": "03",
                        "title": "DECLARAÇÃO",
                        "paragraphs": [
                            "Declaro que recebi o veículo e estou ciente das condições de garantia descritas neste termo.",
                        ],
                        "bullets": [],
                    },
                ],
                "include_signature_block": True,
            },
        ],
    }
