from __future__ import annotations

from types import SimpleNamespace

from django.test import RequestFactory, SimpleTestCase
from django.urls import reverse

from apps.stock.views import StockImportCreateView, StockImportUpdateView


class StockImportFinalStepRedirectTests(SimpleTestCase):
    def _build_view(self, view_class):
        request = RequestFactory().post("/stock/import/", HTTP_HX_REQUEST="true")
        request.htmx = True
        request.user = object()

        instance = SimpleNamespace(workshop=None, user=None)
        saved_import = SimpleNamespace(pk=123, current_step=2, save=lambda **kwargs: None)
        form = SimpleNamespace(instance=instance, save=lambda: saved_import)

        view = view_class()
        view.request = request
        view.workshop = object()
        view.get_current_step = lambda: 2
        view.get_steps_config = lambda: [{}, {}]
        return view, form

    def test_create_final_step_uses_full_page_hx_redirect(self) -> None:
        view, form = self._build_view(StockImportCreateView)

        response = view.form_valid(form)

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response["HX-Redirect"], reverse("stock:stock_list"))
        self.assertNotIn("HX-Push-Url", response)

    def test_update_final_step_uses_full_page_hx_redirect(self) -> None:
        view, form = self._build_view(StockImportUpdateView)

        response = view.form_valid(form)

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response["HX-Redirect"], reverse("stock:stock_list"))
        self.assertNotIn("HX-Push-Url", response)
