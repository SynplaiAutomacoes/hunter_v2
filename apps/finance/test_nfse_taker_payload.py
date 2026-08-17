from __future__ import annotations

from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.core.infrastructure.services.webmania.emission import NfseEmissionError, _build_taker_payload


def _customer(**overrides: object) -> SimpleNamespace:
    data: dict[str, object] = {
        "cpf_or_cnpj": "390.533.447-05",
        "name": "Cliente Teste",
        "logradouro": "Rua das Oficinas",
        "numero": 123,
        "complemento": "",
        "bairro": "Centro",
        "cidade": "Betim",
        "estado": "MG",
        "cep": "32600-000",
        "email": "",
        "phone": "",
        "municipal_registration": "",
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def _nfse_request(customer: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(workorder=SimpleNamespace(budget=SimpleNamespace(customer=customer)))


class BuildTakerPayloadTests(SimpleTestCase):
    def test_pf_payload_includes_complete_address(self) -> None:
        payload = _build_taker_payload(_nfse_request(_customer()))

        self.assertEqual(payload["cpf"], "390.533.447-05")
        self.assertEqual(payload["nome_completo"], "Cliente Teste")
        self.assertEqual(payload["endereco"], "Rua das Oficinas")
        self.assertEqual(payload["numero"], "123")
        self.assertEqual(payload["bairro"], "Centro")
        self.assertEqual(payload["cidade"], "Betim")
        self.assertEqual(payload["uf"], "MG")
        self.assertEqual(payload["cep"], "32600000")
        self.assertNotIn("complemento", payload)

    def test_pj_payload_includes_complete_address(self) -> None:
        customer = _customer(
            cpf_or_cnpj="11.222.333/0001-81",
            name="Oficina Betim LTDA",
            complemento="Sala 2",
            municipal_registration="123456",
        )
        payload = _build_taker_payload(_nfse_request(customer))

        self.assertEqual(payload["cnpj"], "11.222.333/0001-81")
        self.assertEqual(payload["razao_social"], "Oficina Betim LTDA")
        self.assertEqual(payload["endereco"], "Rua das Oficinas")
        self.assertEqual(payload["numero"], "123")
        self.assertEqual(payload["complemento"], "Sala 2")
        self.assertEqual(payload["bairro"], "Centro")
        self.assertEqual(payload["cidade"], "Betim")
        self.assertEqual(payload["uf"], "MG")
        self.assertEqual(payload["cep"], "32600000")
        self.assertEqual(payload["im"], "123456")

    def test_incomplete_address_is_omitted(self) -> None:
        payload = _build_taker_payload(_nfse_request(_customer(logradouro="", bairro="", cidade="", cep="")))

        self.assertEqual(payload, {"cpf": "390.533.447-05", "nome_completo": "Cliente Teste"})
        self.assertNotIn("endereco", payload)
        self.assertNotIn("numero", payload)
        self.assertNotIn("bairro", payload)
        self.assertNotIn("cidade", payload)
        self.assertNotIn("uf", payload)
        self.assertNotIn("cep", payload)

    def test_complemento_is_omitted_when_blank(self) -> None:
        payload = _build_taker_payload(_nfse_request(_customer(complemento="   ")))

        self.assertNotIn("complemento", payload)
        self.assertEqual(payload["endereco"], "Rua das Oficinas")

    def test_address_fields_are_truncated_to_api_limit(self) -> None:
        payload = _build_taker_payload(
            _nfse_request(
                _customer(
                    logradouro="A" * 60,
                    bairro="B" * 50,
                    complemento="C" * 45,
                )
            )
        )

        self.assertEqual(payload["endereco"], "A" * 40)
        self.assertEqual(payload["bairro"], "B" * 40)
        self.assertEqual(payload["complemento"], "C" * 40)

    def test_missing_customer_raises(self) -> None:
        nfse_request = SimpleNamespace(workorder=SimpleNamespace(budget=SimpleNamespace(customer=None)))
        with self.assertRaises(NfseEmissionError):
            _build_taker_payload(nfse_request)
