"""Ids em atributos alimentam JS e POST: com USE_THOUSAND_SEPARATOR eles precisam de |unlocalize."""

from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

ATTRIBUTE_ID_PATTERN = re.compile(r"""(?:value|data-[\w-]+|hx-vals)\s*=\s*['"][^'"]*\{\{\s*(?P<expression>[\w.]*(?:\bpk\b|\bid\b|_id))\s*\}\}""")
QUERYSTRING_ID_PATTERN = re.compile(
    r"""(?:hx-get|hx-post)\s*=\s*['"][^'"]*[?&](?:pk|id|_id|appointment_id)=\{\{\s*(?P<expression>[\w.]*(?:\bpk\b|\bid\b|_id))\s*\}\}"""
)

# Expressoes textuais (slug, UUID): a localizacao numerica nunca as altera.
ALLOWED_EXPRESSIONS = frozenset(
    {
        "app_id",
        "log.client_message_id",
    }
)


class TemplateIdLocalizationTests(SimpleTestCase):
    def _template_files(self) -> list[Path]:
        base = Path(settings.BASE_DIR)
        roots = [base / "apps", base / "templates"]
        return sorted(path for root in roots if root.is_dir() for path in root.rglob("*.html"))

    def test_ids_rendered_in_attributes_are_unlocalized(self) -> None:
        base = Path(settings.BASE_DIR)
        offenders: list[str] = []

        for path in self._template_files():
            content = path.read_text(encoding="utf-8")
            for pattern in (ATTRIBUTE_ID_PATTERN, QUERYSTRING_ID_PATTERN):
                for match in pattern.finditer(content):
                    expression = match.group("expression")
                    if expression in ALLOWED_EXPRESSIONS:
                        continue
                    line_number = content.count("\n", 0, match.start()) + 1
                    offenders.append(f"{path.relative_to(base)}:{line_number} -> {{{{ {expression} }}}}")

        self.assertEqual(offenders, [], "Ids renderizados em atributos precisam de |unlocalize (ou |stringformat:'d'):\n" + "\n".join(offenders))
