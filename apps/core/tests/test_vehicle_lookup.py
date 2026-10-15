from __future__ import annotations

from decimal import Decimal

from django.test import SimpleTestCase

from apps.core.infrastructure.services.vehicle_lookup.fipe_matching import (
    parse_fipe_valor,
    select_fipe_item,
)
from apps.core.infrastructure.services.vehicle_lookup.service import VehiclePlateLookupService


FIPE_ITEMS = [
    {
        "ano_modelo": "2023",
        "codigo_fipe": "017070-4",
        "combustivel": "Flex",
        "score": 77,
        "texto_marca": "Jeep",
        "texto_modelo": "COMPASS LIMITED T270 1.3 TB 4x2 Flex Aut",
        "texto_valor": "R$ 131.646,00",
        "mes_referencia": "outubro de 2026",
    },
    {
        "ano_modelo": "2023",
        "codigo_fipe": "017077-1",
        "combustivel": "Diesel",
        "score": 51,
        "texto_marca": "Jeep",
        "texto_modelo": "COMPASS LIMITED TD 350 2.0 4x4 Die. Aut.",
        "texto_valor": "R$ 142.723,00",
        "mes_referencia": "outubro de 2026",
    },
]


class StubWdService:
    def __init__(self, payload):
        self._payload = payload

    def fetch_raw(self, plate):
        return self._payload


class StubBuscarsService:
    def __init__(self, payload):
        self._payload = payload

    def fetch_raw(self, plate):
        return self._payload


def _wd_payload(**overrides):
    payload = {
        "brand": "JEEP",
        "model": "COMPASS LIMITED TF",
        "version": "TF",
        "year_fabrication": "2023",
        "year_model": "2023",
        "color": "BRANCA",
        "fuel": None,
        "engine": None,
        "engine_extra": None,
        "fuel_extra": None,
        "type": None,
        "chassi": "*****15322",
        "renavam": None,
        "extra_year_fabrication": None,
        "extra_year_model": None,
        "fipe_items": FIPE_ITEMS,
        "marca_modelo": "JEEP/COMPASS LIMITED TF",
    }
    payload.update(overrides)
    return payload


BUSCARS_PAYLOAD = {
    "placa": "SUC4J28",
    "renavam": "01371747161",
    "chassi": "98867516MPKM15322",
    "motor": "463536590325631",
    "marcaModelo": "JEEP/COMPASS LIMITED TF",
    "anoFabricacao": 2023,
    "anoModelo": 2023,
    "cor": "BRANCA",
}


class FipeMatchingTests(SimpleTestCase):
    def test_selects_matching_item_by_fuel_and_displacement(self) -> None:
        item, _score = select_fipe_item(
            candidates=FIPE_ITEMS,
            brand="JEEP",
            model="COMPASS LIMITED TF",
            version="TF",
            year_model="2023",
            fuel="Alcool / Gasolina",
            engine_displacement="1.3",
        )
        self.assertEqual(item["codigo_fipe"], "017070-4")

    def test_selects_diesel_item_for_diesel_vehicle(self) -> None:
        item, _score = select_fipe_item(
            candidates=FIPE_ITEMS,
            brand="JEEP",
            model="COMPASS LIMITED TF",
            version="TF",
            year_model="2023",
            fuel="Diesel",
            engine_displacement="2.0",
        )
        self.assertEqual(item["codigo_fipe"], "017077-1")

    def test_tiebreak_selects_first_item(self) -> None:
        twins = [dict(FIPE_ITEMS[0]), dict(FIPE_ITEMS[0], codigo_fipe="OTHER")]
        item, _score = select_fipe_item(candidates=twins, brand="JEEP", model="COMPASS LIMITED TF", year_model="2023")
        self.assertEqual(item["codigo_fipe"], "017070-4")

    def test_parse_fipe_valor(self) -> None:
        self.assertEqual(parse_fipe_valor("R$ 131.646,00"), Decimal("131646.00"))
        self.assertIsNone(parse_fipe_valor(""))
        self.assertIsNone(parse_fipe_valor(None))


class VehicleLookupMergeTests(SimpleTestCase):
    def _lookup(self, wd_payload, buscars_payload):
        service = VehiclePlateLookupService(
            wd_service=StubWdService(wd_payload),
            buscars_service=StubBuscarsService(buscars_payload),
        )
        return service.lookup_plate("SUC4J28")

    def test_critical_fields_come_from_buscars(self) -> None:
        result = self._lookup(_wd_payload(), BUSCARS_PAYLOAD)
        self.assertEqual(result.chassi, "98867516MPKM15322")
        self.assertEqual(result.renavam, "01371747161")
        self.assertEqual(result.motor_registry, "463536590325631")
        self.assertEqual(result.sources.get("chassi"), "buscars")
        self.assertEqual(result.sources.get("renavam"), "buscars")
        self.assertEqual(result.sources.get("motor_registry"), "buscars")

    def test_engine_serial_does_not_override_engine_choice(self) -> None:
        result = self._lookup(_wd_payload(engine="1.3"), BUSCARS_PAYLOAD)
        self.assertEqual(result.engine, "1.3")
        self.assertNotIn("engine", result.sources)

    def test_fuel_falls_back_to_selected_fipe_item(self) -> None:
        result = self._lookup(_wd_payload(), BUSCARS_PAYLOAD)
        self.assertEqual(result.fuel, "Flex")
        self.assertEqual(result.fipe_value, Decimal("131646.00"))

    def test_returns_none_when_both_sources_fail(self) -> None:
        service = VehiclePlateLookupService(wd_service=StubWdService(None), buscars_service=StubBuscarsService(None))
        self.assertIsNone(service.lookup_plate("SUC4J28"))
        self.assertIsNone(service.lookup_plate(""))

    def test_wd_only_result_has_no_fipe_value_without_candidates(self) -> None:
        result = self._lookup(_wd_payload(fipe_items=[]), None)
        self.assertIsNone(result.fipe_value)
        self.assertIsNone(result.fipe)
        self.assertEqual(result.brand, "JEEP")
