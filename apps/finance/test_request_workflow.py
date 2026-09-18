from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, SimpleTestCase

from apps.finance.forms.nfse import NfseRequestStep3Form
from apps.finance.views.request_workflow import build_preview_hidden_fields, render_emission_preview_modal


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


class BuildPreviewHiddenFieldsTests(SimpleTestCase):
    def test_serializes_booleans_as_true_false_strings(self) -> None:
        fields = {
            item["name"]: item["value"]
            for item in build_preview_hidden_fields(
                cleaned_data={"consumidor_final": True, "other_flag": False, "tax_class": "REF1"}
            )
        }
        self.assertEqual(fields["consumidor_final"], "True")
        self.assertEqual(fields["other_flag"], "False")
        self.assertEqual(fields["tax_class"], "REF1")

    def test_consumidor_final_hidden_values_round_trip_step3_form(self) -> None:
        for raw_value, expected in (("True", True), ("False", False)):
            form = NfseRequestStep3Form(
                data={
                    "tax_class": "REF1",
                    "codigo_nbs": "123456789",
                    "consumidor_final": raw_value,
                    "service_description": "Prestacao de servico",
                    "additional_information": "",
                    "pricing_slider": 0,
                },
                tax_class_choices=[("REF1", "Classe 1")],
            )
            self.assertTrue(form.is_valid(), form.errors)
            self.assertIs(form.cleaned_data["consumidor_final"], expected)

    def test_legacy_checkbox_style_bool_encoding_is_rejected_by_step3_form(self) -> None:
        form = NfseRequestStep3Form(
            data={
                "tax_class": "REF1",
                "codigo_nbs": "123456789",
                "consumidor_final": "1",
                "service_description": "Prestacao de servico",
                "additional_information": "",
                "pricing_slider": 0,
            },
            tax_class_choices=[("REF1", "Classe 1")],
        )
        self.assertFalse(form.is_valid())
        self.assertIn("consumidor_final", form.errors)
