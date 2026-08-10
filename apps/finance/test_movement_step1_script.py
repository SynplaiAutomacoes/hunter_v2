from __future__ import annotations

from crispy_forms.layout import HTML
from django.test import SimpleTestCase

from apps.finance.forms.financial_movement import MovementStep1Form


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
