from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, SimpleTestCase

from apps.finance.views.request_workflow import render_emission_preview_modal


class EmissionPreviewModalTests(SimpleTestCase):
    def test_allows_a_custom_transmission_target_and_label(self) -> None:
        request = RequestFactory().get("/")
        request.user = AnonymousUser()
        response = render_emission_preview_modal(
            request=request,
            title="Prévia da Nota de Devolução",
            previews=[],
            transmit_url="/finance/nfe/devolucao/1/transmitir/",
            hidden_fields=[],
            transmit_target="#modal-container",
            transmit_label="Transmitir NF-e",
        )

        self.assertContains(response, 'hx-target="#modal-container"')
        self.assertContains(response, "Transmitir NF-e")
