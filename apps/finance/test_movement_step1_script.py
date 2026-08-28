from __future__ import annotations

from crispy_forms.layout import HTML
from django.test import SimpleTestCase

from apps.finance.forms.financial_movement import MovementStep1Form
from apps.finance.models import FinancialMovement


class MovementStep1FormScriptTests(SimpleTestCase):
    def test_step1_loads_entities_via_alpine_set_options(self) -> None:
        form = MovementStep1Form()
        script_html = form.helper.layout.fields[0]
        self.assertIsInstance(script_html, HTML)

        script = script_html.html
        self.assertIn("setSearchableOptions", script)
        self.assertIn("setOptions", script)
        self.assertNotIn("optionsList.innerHTML", script)
        self.assertNotIn('li.setAttribute("x-show"', script)
        self.assertNotIn('li.setAttribute("@click"', script)
        self.assertIn("getSearchableData", script)
        self.assertIn("setSearchableOptions", script)
        self.assertIn("loadEntities(entityField.value ? { id: entityField.value } : null)", script)

    def test_step1_restores_supplier_fields_from_saved_movement(self) -> None:
        movement = FinancialMovement(supplier_id=123)

        form = MovementStep1Form(instance=movement)

        self.assertEqual(form.initial["person_type"], "supplier")
        self.assertEqual(form.initial["entity"], "123")

    def test_step1_restores_collaborator_fields_from_saved_movement(self) -> None:
        movement = FinancialMovement(collaborator_id=456)

        form = MovementStep1Form(instance=movement)

        self.assertEqual(form.initial["person_type"], "collaborator")
        self.assertEqual(form.initial["entity"], "456")
