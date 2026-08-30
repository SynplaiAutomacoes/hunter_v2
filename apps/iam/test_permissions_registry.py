from __future__ import annotations

from django.test import SimpleTestCase

from apps.iam.permissions_registry import is_visible


class FiscalEmissionPermissionsRegistryTests(SimpleTestCase):
    def test_all_fiscal_emission_models_are_hidden_like_nfserequest(self) -> None:
        """Emission uses auto-granted view_nfserequest; no per-note IAM toggles."""
        self.assertFalse(is_visible("finance", "nfserequest"))
        self.assertFalse(is_visible("finance", "nferequest"))
        self.assertFalse(is_visible("finance", "fiscaldocument"))
        self.assertFalse(is_visible("finance", "fiscaldocumentevent"))
        self.assertFalse(is_visible("finance", "purchasereturnrequest"))
