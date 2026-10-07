from __future__ import annotations

from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.template.loader import get_template
from django.test import SimpleTestCase

from apps.stock.services.sefaz_distribution import synchronize_workshop_sefaz_documents


def _sefaz_response(status: str, *, current_nsu: str | None = None, max_nsu: str | None = None) -> bytes:
    nsu_fields = ""
    if current_nsu is not None and max_nsu is not None:
        nsu_fields = f"<ultNSU>{current_nsu}</ultNSU><maxNSU>{max_nsu}</maxNSU>"
    return f'<?xml version="1.0"?><retDistDFeInt xmlns="http://www.portalfiscal.inf.br/nfe"><cStat>{status}</cStat>{nsu_fields}</retDistDFeInt>'.encode()


class SefazDistributionSynchronizationTests(SimpleTestCase):
    def setUp(self) -> None:
        self.workshop = SimpleNamespace(
            cnpj="12.345.678/0001-90",
            certificate_password="secret",
            uf="SP",
            last_nsu_sefaz="0",
            last_sefaz_search_date=None,
            can_search_sefaz=True,
            save=Mock(),
        )

    @patch("apps.stock.services.sefaz_distribution.workshop_has_certificate", return_value=True)
    @patch("apps.stock.services.sefaz_distribution.workshop_certificate_temp_path", return_value=nullcontext("certificate.pfx"))
    @patch("apps.stock.services.sefaz_distribution.get_sefaz_service")
    def test_consumes_all_pending_nsu_batches_before_cooldown(self, get_service: Mock, _certificate_path: Mock, _has_certificate: Mock) -> None:
        service = Mock()
        service.consultar_distribuicao.side_effect = [
            _sefaz_response("138", current_nsu="000000000000001", max_nsu="000000000000002"),
            _sefaz_response("138", current_nsu="000000000000002", max_nsu="000000000000002"),
        ]
        get_service.return_value = service

        result = synchronize_workshop_sefaz_documents(workshop=self.workshop)

        self.assertTrue(result.success)
        self.assertEqual(result.requests, 2)
        self.assertEqual(self.workshop.last_nsu_sefaz, "000000000000002")
        self.assertIsNotNone(self.workshop.last_sefaz_search_date)
        self.assertEqual(service.consultar_distribuicao.call_count, 2)

    @patch("apps.stock.services.sefaz_distribution.workshop_has_certificate", return_value=True)
    @patch("apps.stock.services.sefaz_distribution.workshop_certificate_temp_path", return_value=nullcontext("certificate.pfx"))
    @patch("apps.stock.services.sefaz_distribution.get_sefaz_service")
    def test_sefaz_rejection_is_not_reported_as_success(self, get_service: Mock, _certificate_path: Mock, _has_certificate: Mock) -> None:
        service = Mock()
        service.consultar_distribuicao.return_value = _sefaz_response("108")
        get_service.return_value = service

        result = synchronize_workshop_sefaz_documents(workshop=self.workshop)

        self.assertFalse(result.success)
        self.assertIn("108", result.message)
        self.assertIsNone(self.workshop.last_sefaz_search_date)


class SefazTablePaginationLocalizationTests(SimpleTestCase):
    def test_pagination_keeps_primary_key_unlocalized(self) -> None:
        class Notes(list):
            has_other_pages = True
            has_previous = True
            has_next = True
            previous_page_number = 51
            next_page_number = 53
            number = 52
            paginator = SimpleNamespace(num_pages=90)
            object_list: list[object] = []

        form = SimpleNamespace(
            notas=Notes(),
            workshop=SimpleNamespace(last_sefaz_search_date=None, can_search_sefaz=True),
        )
        rendered = get_template("stock/partials/sefaz_table.html").render(
            {"form": form, "object": SimpleNamespace(pk=1286), "current_step": 2}
        )

        self.assertIn("pk=1286", rendered)
        self.assertNotIn("pk=1.286", rendered)
