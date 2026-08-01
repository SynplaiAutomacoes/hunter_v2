from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Account, User
from apps.budget.models import Budget, BudgetStatus
from apps.collaborators.models import WorkshopMember
from apps.customer.models import Customer
from apps.finance.models.finance import NfeItem, NfeRequest
from apps.iam.models import WorkshopRole
from apps.workorder.models import WorkOrder, WorkOrderStatus
from apps.workshops.models.workshops import Workshop


class FiscalPhaseFourNfeDedicatedPermissionTests(TestCase):
    def setUp(self) -> None:
        self.account = Account.objects.create(name="Conta NF-e Permissoes")
        self.workshop = Workshop.objects.create(account=self.account, name="Oficina NF-e", cnpj="12.345.678/0001-90", phone="+5511999999999", address="Rua NF-e, 1")
        self.other_workshop = Workshop.objects.create(account=self.account, name="Outra Oficina NF-e", cnpj="12.345.678/0001-91", phone="+5511888888888", address="Rua NF-e, 2")
        self.nfe_request = self._create_nfe_request(workshop=self.workshop, suffix=1, item_status="aprovado")
        self.invalidatable_request = self._create_nfe_request(workshop=self.workshop, suffix=2, item_status="reprovado")
        self.other_request = self._create_nfe_request(workshop=self.other_workshop, suffix=3, item_status="aprovado")

    def _create_nfe_request(self, *, workshop: Workshop, suffix: int, item_status: str) -> NfeRequest:
        customer = Customer.objects.create(workshop=workshop, customer_type="PF", name=f"Cliente NF-e {suffix}", cpf_or_cnpj=f"1234567890{suffix}", email=f"nfe{suffix}@example.test", logradouro="Rua Teste", numero="123", bairro="Centro", cidade="São Paulo", estado="SP", cep="01001-000")
        budget = Budget.objects.create(workshop=workshop, entry_date="2026-07-08", status=BudgetStatus.APPROVED, customer=customer)
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget, status=WorkOrderStatus.APPROVED)
        nfe_request = NfeRequest.objects.create(workshop=workshop, workorder=workorder, reserved_number=1000 + suffix, reserved_series=1)
        NfeItem.objects.create(
            workshop=workshop,
            workorder=workorder,
            request=nfe_request,
            uuid=uuid4(),
            status=item_status,
            access_key=f"35{suffix:042d}"[-44:],
            xml_url=f"https://example.test/nfe-{suffix}.xml",
            danfe_url=f"https://example.test/nfe-{suffix}.pdf",
            danfe_simple_url=f"https://example.test/nfe-{suffix}-simples.pdf",
            danfe_label_url=f"https://example.test/nfe-{suffix}-etiqueta.pdf",
            raw_payload={"modelo": 1, "token": "secret"},
            log_payload={"status": item_status},
        )
        return nfe_request

    def _permission(self, codename: str) -> Permission:
        model = "nfserequest" if codename.endswith("_nfserequest") else "nferequest"
        return Permission.objects.get(content_type__app_label="finance", content_type__model=model, codename=codename)

    def _user_with_permissions(self, *codenames: str, workshop: Workshop | None = None, suffix: str = "") -> User:
        user = User.objects.create_user(username=f"nfe-perm-{suffix or len(codenames)}-{User.objects.count()}", password="test", cpf=f"9876543{User.objects.count():04d}")
        user.account = self.account
        user.save(update_fields=["account"])
        role = WorkshopRole.objects.create(account=self.account, name=f"Fiscal NF-e {suffix or User.objects.count()}")
        if codenames:
            role.permissions.add(*(self._permission(codename) for codename in codenames))
        WorkshopMember.objects.create(user=user, workshop=workshop or self.workshop, role=role)
        return user

    def _login(self, user: User, *, workshop: Workshop | None = None) -> None:
        self.client.force_login(user)
        session = self.client.session
        session["active_workshop_id"] = (workshop or self.workshop).pk
        session.save()

    def test_cancel_permission_controls_button_and_post(self) -> None:
        user = self._user_with_permissions("view_nferequest", "cancel_nferequest", suffix="cancel")
        self._login(user)
        detail_response = self.client.get(reverse("finance:nfe_detail", args=[self.nfe_request.pk]))
        self.assertContains(detail_response, "Cancelar Nota Fiscal de Produto")

        service = Mock()
        service.cancel_nfe.return_value = {"motivo": "Cancelamento operacional válido", "xml": "https://example.test/cancel.xml"}
        with patch("apps.finance.views.nfe.get_fiscal_service", return_value=service):
            response = self.client.post(reverse("finance:nfe_cancel", args=[self.nfe_request.pk]), {"reason": "Cancelamento operacional válido"})
        self.assertEqual(response.status_code, 302)
        service.cancel_nfe.assert_called_once()

    def test_cancel_is_blocked_without_dedicated_or_legacy_permission(self) -> None:
        user = self._user_with_permissions("view_nferequest", suffix="view-only")
        self._login(user)
        detail_response = self.client.get(reverse("finance:nfe_detail", args=[self.nfe_request.pk]))
        self.assertNotContains(detail_response, "Cancelar Nota Fiscal de Produto")

        with patch("apps.finance.views.nfe.get_fiscal_service") as service_factory:
            response = self.client.post(reverse("finance:nfe_cancel", args=[self.nfe_request.pk]), {"reason": "Cancelamento operacional válido"})
        self.assertEqual(response.status_code, 403)
        service_factory.assert_not_called()

    def test_cancel_legacy_fallbacks_still_work(self) -> None:
        for index, codename in enumerate(("change_nferequest", "change_nfserequest"), start=10):
            with self.subTest(codename=codename):
                nfe_request = self._create_nfe_request(workshop=self.workshop, suffix=index, item_status="aprovado")
                user = self._user_with_permissions("view_nferequest", codename, suffix=codename)
                self._login(user)
                service = Mock()
                service.cancel_nfe.return_value = {"motivo": "Cancelamento operacional válido"}
                with patch("apps.finance.views.nfe.get_fiscal_service", return_value=service):
                    response = self.client.post(reverse("finance:nfe_cancel", args=[nfe_request.pk]), {"reason": "Cancelamento operacional válido"})
                self.assertEqual(response.status_code, 302)
                service.cancel_nfe.assert_called_once()

    def test_invalidate_permission_does_not_allow_cancel(self) -> None:
        user = self._user_with_permissions("view_nferequest", "invalidate_nferequest_numbering", suffix="invalidate-only")
        self._login(user)
        with patch("apps.finance.views.nfe.get_fiscal_service") as service_factory:
            response = self.client.post(reverse("finance:nfe_cancel", args=[self.nfe_request.pk]), {"reason": "Cancelamento operacional válido"})
        self.assertEqual(response.status_code, 403)
        service_factory.assert_not_called()

    def test_invalidate_permission_controls_button_and_post(self) -> None:
        user = self._user_with_permissions("view_nferequest", "invalidate_nferequest_numbering", suffix="invalidate")
        self._login(user)
        detail_response = self.client.get(reverse("finance:nfe_detail", args=[self.invalidatable_request.pk]))
        self.assertContains(detail_response, "Inutilizar numeração")

        service = Mock()
        service.invalidate_nfe_number.return_value = {"motivo": "Inutilização operacional válida", "xml": "https://example.test/inutilizacao.xml", "log": {"ok": True}}
        with patch("apps.finance.views.nfe.get_fiscal_service", return_value=service):
            response = self.client.post(reverse("finance:nfe_invalidate", args=[self.invalidatable_request.pk]), {"reason": "Inutilização operacional válida"})
        self.assertEqual(response.status_code, 302)
        service.invalidate_nfe_number.assert_called_once()

    def test_invalidate_is_blocked_without_dedicated_or_legacy_permission(self) -> None:
        user = self._user_with_permissions("view_nferequest", suffix="view-only-invalidate")
        self._login(user)
        detail_response = self.client.get(reverse("finance:nfe_detail", args=[self.invalidatable_request.pk]))
        self.assertNotContains(detail_response, "Inutilizar numeração")

        with patch("apps.finance.views.nfe.get_fiscal_service") as service_factory:
            response = self.client.post(reverse("finance:nfe_invalidate", args=[self.invalidatable_request.pk]), {"reason": "Inutilização operacional válida"})
        self.assertEqual(response.status_code, 403)
        service_factory.assert_not_called()

    def test_invalidate_legacy_fallbacks_still_work(self) -> None:
        for index, codename in enumerate(("change_nferequest", "change_nfserequest"), start=20):
            with self.subTest(codename=codename):
                nfe_request = self._create_nfe_request(workshop=self.workshop, suffix=index, item_status="reprovado")
                user = self._user_with_permissions("view_nferequest", codename, suffix=f"invalidate-{codename}")
                self._login(user)
                service = Mock()
                service.invalidate_nfe_number.return_value = {"motivo": "Inutilização operacional válida"}
                with patch("apps.finance.views.nfe.get_fiscal_service", return_value=service):
                    response = self.client.post(reverse("finance:nfe_invalidate", args=[nfe_request.pk]), {"reason": "Inutilização operacional válida"})
                self.assertEqual(response.status_code, 302)
                service.invalidate_nfe_number.assert_called_once()

    def test_cancel_permission_does_not_allow_invalidate(self) -> None:
        user = self._user_with_permissions("view_nferequest", "cancel_nferequest", suffix="cancel-only")
        self._login(user)
        with patch("apps.finance.views.nfe.get_fiscal_service") as service_factory:
            response = self.client.post(reverse("finance:nfe_invalidate", args=[self.invalidatable_request.pk]), {"reason": "Inutilização operacional válida"})
        self.assertEqual(response.status_code, 403)
        service_factory.assert_not_called()

    def test_download_permissions_and_fallbacks_are_enforced(self) -> None:
        for codename, document, expected_name in (
            ("download_nferequest_xml", "xml", "nfe-xml"),
            ("download_nferequest_pdf", "danfe", "nfe-danfe"),
            ("view_nferequest", "xml", "nfe-xml"),
            ("change_nferequest", "danfe", "nfe-danfe"),
        ):
            with self.subTest(codename=codename, document=document):
                user = self._user_with_permissions(codename, suffix=f"download-{codename}-{document}")
                self._login(user)
                service = Mock()
                service.download_document.return_value = SimpleNamespace(content=b"document", content_type="application/octet-stream")
                with patch("apps.finance.views.nfe.get_fiscal_service", return_value=service):
                    response = self.client.get(reverse("finance:nfe_document_download", args=[self.nfe_request.pk, document]))
                self.assertEqual(response.status_code, 200)
                self.assertIn(expected_name, response["Content-Disposition"])
                service.download_document.assert_called_once()

    def test_download_is_blocked_without_permission_and_cross_workshop_is_scoped(self) -> None:
        user = self._user_with_permissions(suffix="no-download")
        self._login(user)
        with patch("apps.finance.views.nfe.get_fiscal_service") as service_factory:
            response = self.client.get(reverse("finance:nfe_document_download", args=[self.nfe_request.pk, "xml"]))
        self.assertEqual(response.status_code, 403)
        service_factory.assert_not_called()

        allowed_user = self._user_with_permissions("download_nferequest_xml", suffix="cross")
        self._login(allowed_user, workshop=self.workshop)
        with patch("apps.finance.views.nfe.get_fiscal_service") as service_factory:
            response = self.client.get(reverse("finance:nfe_document_download", args=[self.other_request.pk, "xml"]))
        self.assertEqual(response.status_code, 404)
        service_factory.assert_not_called()

    def test_future_payload_and_remote_response_permissions_exist_without_new_views(self) -> None:
        self.assertIsNotNone(self._permission("view_nferequest_payload"))
        self.assertIsNotNone(self._permission("view_nferequest_remote_response"))
