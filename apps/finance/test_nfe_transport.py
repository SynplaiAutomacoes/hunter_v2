from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from apps.core.infrastructure.services.webmania.nfe_emission import build_nfe_payload, emit_nfe_request, preview_nfe_request
from apps.finance.forms.emission import EmissionNfeConfigForm
from apps.finance.forms.nfe import NfeRequestStep3Form
from apps.finance.models.finance import NfeFreightMode, NfeRequest
from apps.finance.nfe_transport import build_nfe_transport_snapshot


TRANSPORT_SNAPSHOT = {
    "modalidade": 2,
    "transportador": {
        "tipo_pessoa": "pj",
        "cnpj": "11222333000181",
        "razao_social": "Transportadora teste",
        "ie": "123456789",
        "endereco": "Rua do transporte, 10",
        "uf": "SP",
        "cidade": "Sao paulo",
        "cep": "01001000",
        "placa": "ABC1D23",
        "uf_veiculo": "SP",
        "rntc": "12345678",
    },
    "volumes": {
        "volume": 2,
        "especie": "Caixas",
        "peso_bruto": "12.500",
        "peso_liquido": "11.750",
        "marca": "Hunter",
        "numeracao": "1-2",
        "lacres": "L123",
    },
}


class NfeTransportFormTests(SimpleTestCase):
    def _form_data(self) -> dict[str, str]:
        return {
            "pricing_slider": "0",
            "tax_class": "REF-NFE",
            "additional_information": "",
            "freight_mode": "2",
            "transport_person_type": "pj",
            "transport_document": "11.222.333/0001-81",
            "transport_name": "Transportadora Teste",
            "transport_state_registration": "123456789",
            "transport_address": "Rua do Transporte, 10",
            "transport_state": "SP",
            "transport_city": "Sao Paulo",
            "transport_postal_code": "01001-000",
            "transport_vehicle_plate": "ABC1D23",
            "transport_vehicle_state": "SP",
            "transport_rntc": "12345678",
            "transport_volume_quantity": "2",
            "transport_volume_species": "Caixas",
            "transport_gross_weight": "12.500",
            "transport_net_weight": "11.750",
            "transport_volume_brand": "Hunter",
            "transport_volume_numbering": "1-2",
            "transport_seals": "L123",
        }

    def test_legacy_and_unified_forms_build_the_same_snapshot(self) -> None:
        data = self._form_data()
        legacy_form = NfeRequestStep3Form(
            data=data,
            instance=NfeRequest(),
            tax_class_choices=[("REF-NFE", "Classe NF-e")],
        )
        unified_form = EmissionNfeConfigForm(
            data=data,
            tax_class_choices=[("REF-NFE", "Classe NF-e")],
        )

        self.assertTrue(legacy_form.is_valid(), legacy_form.errors)
        self.assertTrue(unified_form.is_valid(), unified_form.errors)
        self.assertEqual(legacy_form.cleaned_data["transport_snapshot"], TRANSPORT_SNAPSHOT)
        self.assertEqual(unified_form.cleaned_data["transport_snapshot"], TRANSPORT_SNAPSHOT)

        request = legacy_form.save(commit=False)
        self.assertEqual(request.freight_mode, 2)
        self.assertEqual(request.transport_snapshot, TRANSPORT_SNAPSHOT)

    def test_default_mode_keeps_transport_snapshot_empty(self) -> None:
        form = EmissionNfeConfigForm(
            data={
                "tax_class": "REF-NFE",
                "additional_information": "",
                "freight_mode": "9",
            },
            tax_class_choices=[("REF-NFE", "Classe NF-e")],
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["transport_snapshot"], {})

    def test_transport_details_are_rejected_with_no_transport_mode(self) -> None:
        form = EmissionNfeConfigForm(
            data={
                "tax_class": "REF-NFE",
                "additional_information": "",
                "freight_mode": "9",
                "transport_volume_quantity": "1",
            },
            tax_class_choices=[("REF-NFE", "Classe NF-e")],
        )

        self.assertFalse(form.is_valid())
        self.assertIn("Selecione uma modalidade com transporte", form.non_field_errors()[0])

    def test_complete_individual_carrier_uses_cpf_and_full_address(self) -> None:
        data = self._form_data()
        data.update(
            {
                "transport_person_type": "pf",
                "transport_document": "529.982.247-25",
                "transport_name": "Transportador Autonomo",
                "transport_state_registration": "",
            }
        )
        form = EmissionNfeConfigForm(data=data, tax_class_choices=[("REF-NFE", "Classe NF-e")])

        self.assertTrue(form.is_valid(), form.errors)
        carrier = form.cleaned_data["transport_snapshot"]["transportador"]
        self.assertEqual(
            carrier,
            {
                "tipo_pessoa": "pf",
                "cpf": "52998224725",
                "nome_completo": "Transportador autonomo",
                "endereco": "Rua do transporte, 10",
                "uf": "SP",
                "cidade": "Sao paulo",
                "cep": "01001000",
                "rntc": "12345678",
                "placa": "ABC1D23",
                "uf_veiculo": "SP",
            },
        )

    def test_state_registration_requires_state_and_accepts_exempt_marker(self) -> None:
        missing_state = self._form_data()
        missing_state["transport_state"] = ""
        invalid_form = EmissionNfeConfigForm(data=missing_state, tax_class_choices=[("REF-NFE", "Classe NF-e")])
        self.assertFalse(invalid_form.is_valid())
        self.assertIn("Informe a UF da transportadora", invalid_form.non_field_errors()[0])

        exempt = self._form_data()
        exempt["transport_state_registration"] = "0"
        valid_form = EmissionNfeConfigForm(data=exempt, tax_class_choices=[("REF-NFE", "Classe NF-e")])
        self.assertTrue(valid_form.is_valid(), valid_form.errors)
        self.assertEqual(valid_form.cleaned_data["transport_snapshot"]["transportador"]["ie"], "0")

    def test_vehicle_accepts_webmania_legacy_formats_and_exterior_state(self) -> None:
        for plate in ("ABC123", "AB1234", "ABCD123"):
            with self.subTest(plate=plate):
                snapshot = build_nfe_transport_snapshot(
                    {
                        "freight_mode": "3",
                        "transport_vehicle_plate": plate,
                        "transport_vehicle_state": "EX",
                        "transport_rntc": "12345678901234567890",
                    }
                )
                self.assertEqual(
                    snapshot["transportador"],
                    {
                        "placa": plate,
                        "uf_veiculo": "EX",
                        "rntc": "12345678901234567890",
                    },
                )

    def test_volume_quantity_uses_fifteen_digit_contract_limit(self) -> None:
        data = {
            "tax_class": "REF-NFE",
            "additional_information": "",
            "freight_mode": "3",
            "transport_volume_quantity": "999999999999999",
            "transport_volume_species": "CAIXAS",
            "transport_volume_brand": "HUNTER",
            "transport_volume_numbering": "1-999",
            "transport_seals": "LACRE-1",
            "transport_gross_weight": "12.500",
            "transport_net_weight": "11.750",
        }
        form = EmissionNfeConfigForm(data=data, tax_class_choices=[("REF-NFE", "Classe NF-e")])

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["transport_snapshot"]["volumes"]["volume"], 999999999999999)


@override_settings(WEBMANIA_NFE_NATUREZA_OPERACAO="Venda de mercadoria", WEBMANIA_AMBIENT="2")
class NfeTransportPayloadTests(SimpleTestCase):
    def _nfe_request(self, *, freight_mode: int = 9, transport_snapshot: dict | None = None) -> SimpleNamespace:
        payments = Mock()
        payments.order_by.return_value.first.return_value = None
        workorder = SimpleNamespace(
            pk=22,
            payments=payments,
            discount_type="products",
        )
        return SimpleNamespace(
            pk=11,
            workshop=SimpleNamespace(pk=33),
            workorder=workorder,
            tax_class="REF-NFE",
            additional_information="",
            freight_mode=freight_mode,
            transport_snapshot=deepcopy(transport_snapshot or {}),
        )

    def _build_payload(self, nfe_request: SimpleNamespace) -> dict:
        allocation = SimpleNamespace(
            products_target=Decimal("100.00"),
            services_target=Decimal("0.00"),
            slider=0,
        )
        with (
            patch(
                "apps.core.infrastructure.services.webmania.nfe_emission._build_nfe_products_payload",
                return_value=([{"codigo": "P1"}], Decimal("100.00"), allocation, Decimal("0.00")),
            ),
            patch(
                "apps.core.infrastructure.services.webmania.nfe_emission._build_customer_payload",
                return_value={"cpf": "52998224725"},
            ),
            patch(
                "apps.core.infrastructure.services.webmania.nfe_emission.build_webmania_webhook_url",
                return_value="https://example.test/webhook",
            ),
        ):
            return build_nfe_payload(nfe_request=nfe_request)

    def test_nfe_without_transport_keeps_existing_payload_shape(self) -> None:
        field = NfeRequest._meta.get_field("freight_mode")
        self.assertEqual(field.get_default(), NfeFreightMode.NO_TRANSPORT)

        payload = self._build_payload(self._nfe_request())

        self.assertNotIn("transporte", payload)
        self.assertEqual(
            payload["pedido"],
            {
                "pagamento": 0,
                "presenca": 2,
                "modalidade_frete": 9,
                "desconto": "0.00",
                "total": "100.00",
            },
        )

    def test_nfe_with_carrier_and_volumes_adds_only_transport_extension(self) -> None:
        payload = self._build_payload(self._nfe_request(freight_mode=2, transport_snapshot=TRANSPORT_SNAPSHOT))

        self.assertEqual(payload["pedido"]["modalidade_frete"], 2)
        self.assertEqual(
            payload["transporte"],
            {
                "cnpj": "11222333000181",
                "razao_social": "Transportadora teste",
                "ie": "123456789",
                "endereco": "Rua do transporte, 10",
                "uf": "SP",
                "cidade": "Sao paulo",
                "cep": "01001000",
                "placa": "ABC1D23",
                "uf_veiculo": "SP",
                "rntc": "12345678",
                "volume": 2,
                "especie": "Caixas",
                "peso_bruto": "12.500",
                "peso_liquido": "11.750",
                "marca": "Hunter",
                "numeracao": "1-2",
                "lacres": "L123",
            },
        )
        self.assertNotIn("tipo_pessoa", payload["transporte"])
        self.assertNotIn("frete", payload["pedido"])

    def test_nfe_can_send_volumes_without_carrier(self) -> None:
        snapshot = {
            "modalidade": 3,
            "transportador": {},
            "volumes": {"volume": 1, "especie": "Pacote", "peso_bruto": "2.500"},
        }

        payload = self._build_payload(self._nfe_request(freight_mode=3, transport_snapshot=snapshot))

        self.assertEqual(payload["pedido"]["modalidade_frete"], 3)
        self.assertEqual(payload["transporte"], {"volume": 1, "especie": "Pacote", "peso_bruto": "2.500"})

    def test_preview_emission_and_attempt_use_same_frozen_transport(self) -> None:
        nfe_request = self._nfe_request(freight_mode=2, transport_snapshot=TRANSPORT_SNAPSHOT)
        allocation = SimpleNamespace(products_target=Decimal("100.00"), services_target=Decimal("0.00"), slider=0)
        preview_response = Mock()
        preview_response.raise_for_status.return_value = None
        preview_response.json.return_value = {"danfe": "https://example.test/preview.pdf"}
        emission_response = Mock()
        emission_response.raise_for_status.return_value = None
        emission_response.json.return_value = {"uuid": "12345678-1234-4234-8234-123456789012", "modelo": "nfe"}
        attempt = Mock()

        common_patches = (
            patch("apps.core.infrastructure.services.webmania.nfe_emission._build_headers", return_value={"X": "Y"}),
            patch("apps.core.infrastructure.services.webmania.nfe_emission._build_emit_url", return_value="https://example.test/emissao"),
            patch("apps.core.infrastructure.services.webmania.nfe_emission._validate_nfe_tax_class"),
            patch("apps.core.infrastructure.services.webmania.nfe_emission._validate_local_ibs_cbs_tax_class"),
            patch("apps.core.infrastructure.services.webmania.nfe_emission._build_nfe_products_payload", return_value=([{"codigo": "P1"}], Decimal("100.00"), allocation, Decimal("0.00"))),
            patch("apps.core.infrastructure.services.webmania.nfe_emission._build_customer_payload", return_value={"cpf": "52998224725"}),
            patch("apps.core.infrastructure.services.webmania.nfe_emission.build_webmania_webhook_url", return_value="https://example.test/webhook"),
        )
        with common_patches[0], common_patches[1], common_patches[2], common_patches[3], common_patches[4], common_patches[5], common_patches[6]:
            with patch("apps.core.infrastructure.services.webmania.nfe_emission.requests.post", return_value=preview_response) as preview_post:
                preview_nfe_request(nfe_request=nfe_request)

            with (
                patch("apps.core.infrastructure.services.webmania.nfe_emission.reserve_nfe_request_number"),
                patch("apps.core.infrastructure.services.webmania.nfe_emission.begin_emission_attempt", return_value=attempt) as begin_attempt,
                patch("apps.core.infrastructure.services.webmania.nfe_emission.mark_attempt_sent"),
                patch("apps.core.infrastructure.services.webmania.nfe_emission.mark_attempt_succeeded"),
                patch("apps.core.infrastructure.services.webmania.nfe_emission.requests.post", return_value=emission_response) as emission_post,
            ):
                emit_nfe_request(nfe_request=nfe_request)

        preview_payload = preview_post.call_args.kwargs["json"]
        emission_payload = emission_post.call_args.kwargs["json"]
        attempted_payload = begin_attempt.call_args.kwargs["request_payload"]
        self.assertEqual(preview_payload["transporte"], emission_payload["transporte"])
        self.assertEqual(emission_payload["transporte"], attempted_payload["transporte"])
        self.assertEqual(preview_payload["pedido"]["modalidade_frete"], emission_payload["pedido"]["modalidade_frete"])

        nfe_request.transport_snapshot["transportador"]["razao_social"] = "Alterada depois"
        self.assertEqual(attempted_payload["transporte"]["razao_social"], "Transportadora teste")
