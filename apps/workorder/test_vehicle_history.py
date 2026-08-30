from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase


TEMPLATES_DIR = Path(__file__).resolve().parent / "templates" / "workorder" / "partials"


class WorkOrderVehicleHistoryTemplateTests(SimpleTestCase):
    def test_history_uses_sorted_workorders_and_shows_km_fields(self) -> None:
        template = (TEMPLATES_DIR / "vehicle_history_section.html").read_text(encoding="utf-8")
        self.assertIn("{% for wo in vehicle_history %}", template)
        self.assertIn("KM de entrada", template)
        self.assertIn("KM de saída", template)
        self.assertIn("wo.budget.current_km", template)
        self.assertIn("wo.km_final", template)
        self.assertNotIn("workorder.budget.vehicle.budgets.all", template)
