"""
core/presentation/mixins.py

Reusable Django view mixins for HTMX-based interactions and page favorites.
"""
from __future__ import annotations

import json
from typing import Any

from django.http import HttpResponse
from django.template.response import TemplateResponse

from apps.core.presentation.favorites import FavoritePageLimitError, InvalidFavoritePageError
from apps.core.presentation.navigation import build_favoritable_page

__all__ = [
    "HtmxTemplateResponseMixin",
    "HtmxDeleteResponseMixin",
    "BaseModalFormView",
    "PageFavoriteMixin",
]


class HtmxTemplateResponseMixin:
    """Returns an alternative template when the request is HTMX."""

    htmx_template_name: str | None = None

    def render_to_response(self, context: dict[str, Any], **response_kwargs: Any) -> Any:
        if bool(getattr(self.request, "htmx", False)) and self.htmx_template_name:  # type: ignore[attr-defined]
            return TemplateResponse(self.request, self.htmx_template_name, context, **response_kwargs)  # type: ignore[attr-defined]

        return super().render_to_response(context, **response_kwargs)  # type: ignore[misc]


class HtmxDeleteResponseMixin:
    """Standardises the HTMX delete flow (opens modal on GET, deletes on POST)."""

    htmx_template_name: str | None = "crud/delete_modal.html"
    htmx_trigger: str | None = None

    def get_template_names(self) -> list[str]:
        if bool(getattr(self.request, "htmx", False)) and self.htmx_template_name:  # type: ignore[attr-defined]
            return [self.htmx_template_name]

        return super().get_template_names()  # type: ignore[misc]

    def form_valid(self, form: Any) -> HttpResponse:
        if bool(getattr(self.request, "htmx", False)):  # type: ignore[attr-defined]
            self.object.delete()  # type: ignore[attr-defined]
            response = HttpResponse()
            if self.htmx_trigger:
                response["HX-Trigger"] = self.htmx_trigger
            return response

        return super().form_valid(form)  # type: ignore[misc]


class BaseModalFormView:
    """Mixin for handling forms inside HTMX Modals."""

    template_name = "partials/modal_form.html"

    def form_valid(self, form: Any) -> HttpResponse:
        form.instance.workshop = self.workshop  # type: ignore[attr-defined]
        self.object = form.save()  # type: ignore[attr-defined]

        if self.request.htmx:  # type: ignore[attr-defined]
            response = HttpResponse(status=204)
            response["HX-Refresh"] = "true"
            return response

        return super().form_valid(form)  # type: ignore[misc]


class PageFavoriteMixin:
    favorite_page_definition: dict[str, Any] | None = None

    def get_page_favorite(self) -> dict[str, Any] | None:
        if self.favorite_page_definition is None:
            return None
        return build_favoritable_page(self.favorite_page_definition)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context: dict[str, Any] = super().get_context_data(**kwargs)  # type: ignore[misc]
        context["page_favorite"] = self.get_page_favorite()
        return context
