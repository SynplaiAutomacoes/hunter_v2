from __future__ import annotations

DEFAULT_INTRO_TEXT = "Prezado Cliente, para que possamos dar andamento no diagnóstico ou manutenção do seu veículo, apresentamos abaixo informações importantes sobre o atendimento."

DEFAULT_CLOSING_TEXT = "Declaro que li, compreendi e concordo com as condições apresentadas neste Termo de Recebimento de Veículo."

DEFAULT_RECEIPT_SECTIONS: tuple[dict[str, object], ...] = (
    {
        "title": "Condições gerais",
        "items": [
            "O cliente declara estar ciente das condições descritas neste termo e concorda com os termos apresentados.",
        ],
    },
)
