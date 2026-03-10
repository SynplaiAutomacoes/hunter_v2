import json
from itertools import zip_longest

from apps.checklist.models import ChecklistItem

VALID_RESPONSE_TYPES = {choice[0] for choice in ChecklistItem.TIPO_RESPOSTA_CHOICES}

def extract_checklist_items(post_data):
    agrupamentos = post_data.getlist("agrupamento")
    descricoes = post_data.getlist("descricao")
    tipos = post_data.getlist("tipo_resposta")

    parsed_items = []
    for group, description, response_type in zip_longest(agrupamentos, descricoes, tipos, fillvalue=""):
        cleaned_group = (group or "").strip()
        cleaned_description = (description or "").strip()
        cleaned_response_type = (response_type or "").strip()

        if not cleaned_description:
            continue
        if not cleaned_group:
            raise ValueError("Todos os itens devem possuir um agrupamento.")
        if cleaned_response_type not in VALID_RESPONSE_TYPES:
            continue

        parsed_items.append(
            {
                "group": cleaned_group,
                "description": cleaned_description,
                "response_type": cleaned_response_type,
            }
        )

    return parsed_items


def build_showtoast_trigger(toast_type: str, message: str) -> str:
    return json.dumps(
        {
            "showToast": {
                "type": toast_type,
                "message": message,
            }
        }
    )