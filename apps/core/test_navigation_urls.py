from __future__ import annotations

from django.test import SimpleTestCase
from django.urls import NoReverseMatch, reverse

from apps.core.presentation.navigation import EXTRA_FAVORITABLE_PAGE_DEFINITIONS, NAVBAR_MENU_DEFINITIONS


class NavbarUrlIntegrityTests(SimpleTestCase):
    def test_all_navbar_view_names_reverse(self) -> None:
        failures: list[str] = []

        def collect(entry: dict) -> None:
            view_name = entry.get("view_name")
            if not view_name:
                return
            try:
                reverse(view_name)
            except NoReverseMatch as exc:
                failures.append(f"{entry.get('label')}: {exc}")

        for menu in NAVBAR_MENU_DEFINITIONS:
            collect(menu)
            for item in menu.get("items") or ():
                collect(item)

        for page in EXTRA_FAVORITABLE_PAGE_DEFINITIONS:
            collect(page)

        self.assertEqual(failures, [], msg="; ".join(failures))
