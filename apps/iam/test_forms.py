from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.iam.forms import _iter_live_permissions


class WorkshopRoleFormPermissionTests(SimpleTestCase):
    @patch("apps.iam.forms.Permission.objects")
    def test_iter_live_permissions_skips_stale_content_types(self, permission_manager) -> None:
        live_permission = SimpleNamespace(content_type=SimpleNamespace(model_class=lambda: object()))
        stale_permission = SimpleNamespace(content_type=SimpleNamespace(model_class=lambda: None))
        permission_manager.select_related.return_value.order_by.return_value = [live_permission, stale_permission]

        permissions = list(_iter_live_permissions())

        self.assertEqual(permissions, [live_permission])
