from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase, TestCase

from apps.catalog.forms.kits import KitForm
from apps.workshops.models.workshops import Workshop


class KitFormLayoutSourceTests(SimpleTestCase):
    def test_apply_updated_product_does_not_use_python_fstring_payload(self) -> None:
        source = (Path(__file__).resolve().parent / "forms" / "kits.py").read_text(encoding="utf-8")
        self.assertNotIn("${payload.code}", source)
        self.assertNotIn("${payload.name}", source)


class KitFormLayoutBuildTests(TestCase):
    def test_kit_form_layout_builds_without_nameerror(self) -> None:
        workshop = Workshop.objects.create(
            name="Oficina Kit Form",
            cnpj="12.345.678/0001-95",
            phone="+5511999999995",
            address="Rua Kit Form, 1",
        )
        form = KitForm(workshop=workshop)
        self.assertIsNotNone(form.helper.layout)
