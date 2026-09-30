from django.test import SimpleTestCase

from apps.core.infrastructure.services.webmania.webmania_errors import extract_webmania_error_message


class ExtractWebmaniaErrorMessageTests(SimpleTestCase):
    def test_prefers_motivo_from_nfe_rejection_payload(self) -> None:
        message = extract_webmania_error_message(
            {"status": "reprovado", "modelo": "nfe", "motivo": "Rejeicao: CFOP de entrada para NF-e de saida [nItem:1]"},
            scope="nfe",
        )

        self.assertEqual(message, "Rejeicao: CFOP de entrada para NF-e de saida [nItem:1]")

    def test_skips_generic_error_token_and_reads_nested_xmotivo(self) -> None:
        message = extract_webmania_error_message(
            {"error": "erro", "status": "reprovado", "log": {"cStat": "778", "xMotivo": "Rejeicao: Informar a NF-e referenciada"}},
            scope="nfe",
        )

        self.assertEqual(message, "Rejeicao: Informar a NF-e referenciada")
