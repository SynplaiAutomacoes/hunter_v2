from __future__ import annotations

from typing import Any

from django.http import HttpResponse
from django.template.response import TemplateResponse
from django.shortcuts import render
import requests


class HtmxTemplateResponseMixin:
    """Retorna um template alternativo quando a requisição é HTMX."""

    htmx_template_name: str | None = None

    def render_to_response(self, context: dict[str, Any], **response_kwargs: Any):
        if bool(getattr(self.request, "htmx", False)) and self.htmx_template_name:
            return TemplateResponse(self.request, self.htmx_template_name, context, **response_kwargs)

        return super().render_to_response(context, **response_kwargs)


class HtmxDeleteResponseMixin:
    """Padroniza o fluxo de exclusão via HTMX (abre modal no GET e deleta no POST)."""

    htmx_template_name: str | None = "crud/delete_modal.html"
    htmx_trigger: str | None = None

    def get_template_names(self):
        if bool(getattr(self.request, "htmx", False)) and self.htmx_template_name:
            return [self.htmx_template_name]

        return super().get_template_names()

    def form_valid(self, form):
        if bool(getattr(self.request, "htmx", False)):
            self.object.delete()
            response = HttpResponse()
            if self.htmx_trigger:
                response["HX-Trigger"] = self.htmx_trigger
            return response

        return super().form_valid(form)


def cep_lookup(request):
    cep = request.GET.get("cep", "").replace("-", "").replace(".", "")
    updates = {
        "id_logradouro": "",
        "id_bairro": "",
        "id_cidade": "",
        "readonly": True
    }
    if len(cep) == 8:
        try:
            response = requests.get(f"https://viacep.com.br/ws/{cep}/json/", timeout=5)
            data = response.json()
            if "erro" not in data:
                updates.update(
                    {
                        "id_logradouro": data.get("logradouro", ""),
                        "id_bairro": data.get("bairro", ""),
                        "id_cidade": data.get("localidade", ""),
                        "readonly": False,
                    }
                )
            else:
                updates.update({"readonly": False})
        except Exception:
            updates.update({"readonly": False})

    return render(request, "partials/address_fields.html", {"updates": updates})