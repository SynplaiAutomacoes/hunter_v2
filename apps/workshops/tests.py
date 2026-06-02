from __future__ import annotations

import base64
import io
from datetime import date
from decimal import Decimal
from unittest.mock import Mock, patch

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
import holidays
from PIL import Image

from apps.accounts.models import Account, User
from apps.collaborators.models import WorkshopMember
from apps.finance.models.finance import WebmaniaCompany
from apps.iam.models import WorkshopRole
from apps.iam.utils import get_or_create_director_role
from apps.workshops.forms.workshop_costs import WorkshopCostForm
from apps.workshops.models.workshop_costs import WorkshopCost, WorkshopCostWorkDay
from apps.workshops.models.workshops import Workshop
from apps.workshops.services.files import StoredWorkshopFile, WorkshopFileSyncError
from apps.workshops.util.workshops import is_workshop_director, is_workshop_manager


def create_account_owner_user(*, suffix: int = 1) -> User:
    user = User.objects.create_user(username=f"workshop_owner{suffix}", password="123", cpf=f"11122233{suffix:03d}")
    account = Account.objects.create(name=f"Conta Owner {suffix}", owner=user)
    user.account = account
    user.is_account_owner = True
    user.save(update_fields=["account", "is_account_owner"])
    return user


def create_director_user_with_workshop(*, suffix: int = 1) -> tuple[User, Workshop]:
    user = User.objects.create_user(username=f"workshop_director{suffix}", password="123", cpf=f"22233344{suffix:03d}")
    account = Account.objects.create(name=f"Conta Workshop {suffix}", owner=user)
    user.account = account
    user.is_account_owner = True
    user.save(update_fields=["account", "is_account_owner"])

    workshop = Workshop.objects.create(
        account=account,
        name=f"Oficina Workshop {suffix}",
        cnpj=f"21.222.444/0001-{suffix:02d}",
        phone="+5511988887777",
        address="Rua Oficina, 10",
        uf="SP",
    )

    director_role = get_or_create_director_role(account=account, with_all_permissions=True)
    WorkshopMember.objects.create(user=user, workshop=workshop, role=director_role, is_active=True)

    return user, workshop


class FakeWorkshopFileService:
    def __init__(self) -> None:
        self._counter = 0
        self.files: dict[str, dict[str, StoredWorkshopFile]] = {
            "certificate": {},
            "logo": {},
        }

    def save_file(self, *, kind: str, content: bytes, filename: str, content_type: str, workshop_id: int) -> StoredWorkshopFile:
        self._counter += 1
        stored_file = StoredWorkshopFile(
            file_id=f"{kind}-{self._counter}",
            filename=filename,
            content_type=content_type,
            content=content,
            uploaded_at=timezone.now(),
        )
        self.files[kind][stored_file.file_id] = stored_file
        return stored_file

    def read_file(self, *, kind: str, file_id: str) -> StoredWorkshopFile:
        return self.files[kind][file_id]

    def delete_file(self, *, kind: str, file_id: str) -> None:
        self.files[kind].pop(file_id, None)


class WorkshopWebmaniaIntegrationTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=11)
        self.client.force_login(self.user)

        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

    def test_finance_requests_url_redirects_to_management_history(self) -> None:
        response = self.client.get(reverse("finance:webmania_requests"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers.get("Location"), reverse("workshops:emission_history"))

    @override_settings(WEBMANIA_AMBIENT="1")
    def test_sync_endpoint_blocks_outside_homolog_environment(self) -> None:
        with patch("apps.workshops.views.workshops.sync_b2b_companies_to_database") as sync_mock:
            response = self.client.post(reverse("workshops:webmania_company_sync"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers.get("Location"), reverse("workshops:list"))
        sync_mock.assert_not_called()

    @override_settings(WEBMANIA_AMBIENT="2")
    def test_create_page_shows_sync_button_for_first_workshop_owner(self) -> None:
        create_director_user_with_workshop(suffix=12)

        owner_user = create_account_owner_user(suffix=13)
        self.client.force_login(owner_user)
        session = self.client.session
        session.pop("active_workshop_id", None)
        session.save()

        response = self.client.get(reverse("workshops:create"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sincronizar empresas")

    @override_settings(WEBMANIA_AMBIENT="2")
    def test_sync_endpoint_allows_first_workshop_owner_without_active_workshop(self) -> None:
        owner_user = create_account_owner_user(suffix=14)
        self.client.force_login(owner_user)
        session = self.client.session
        session.pop("active_workshop_id", None)
        session.save()

        with patch(
            "apps.workshops.views.workshops.sync_b2b_companies_to_database",
            return_value=[Mock(workshop_id=999)],
        ) as sync_mock:
            response = self.client.post(reverse("workshops:webmania_company_sync"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers.get("Location"), reverse("workshops:create"))
        sync_mock.assert_called_once_with(
            workshop=None,
            actor_user=owner_user,
            force_global_auth=True,
        )
        self.assertEqual(self.client.session.get("active_workshop_id"), 999)

    def test_workshop_update_page_renders_tabs_and_updates_company_data(self) -> None:
        response = self.client.get(f"{reverse('workshops:update', kwargs={'pk': self.workshop.pk})}?tab=certificado")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Empresa")
        self.assertContains(response, "Endereco")
        self.assertContains(response, "Nota Fiscal")
        self.assertContains(response, "Certificados")
        self.assertContains(response, "Opcionais")
        self.assertContains(response, "Credenciais")
        self.assertContains(response, "Nenhum arquivo de certificado foi enviado ainda.")
        self.assertContains(response, "Formatos aceitos: .pfx e .p12.")
        self.assertNotContains(response, "Atualmente:")

        with patch("apps.workshops.views.workshops.update_webmania_company", return_value={"success": True}) as update_mock:
            post_response = self.client.post(
                reverse("workshops:update", kwargs={"pk": self.workshop.pk}),
                data={
                    "tab": "empresa",
                    "nf_tab": "nfe",
                    "tipo_tributacao": "simples_nacional",
                    "regime_tributario": "",
                    "cnpj": "11.222.333/0001-81",
                    "razao_social": "Empresa Integrada",
                    "cpf": "",
                    "nome_completo": "",
                    "nome_fantasia": "Empresa Integrada",
                    "ie": "",
                    "im": "",
                    "unidade_empresa": "matriz",
                    "email": "fiscal@empresa.com",
                    "telefone": "",
                    "contabilidade": "",
                    "logomarca": "",
                    "workshop_is_active": "on",
                },
            )

        self.assertEqual(post_response.status_code, 302)
        update_mock.assert_called_once()

        self.workshop.refresh_from_db()
        self.assertEqual(self.workshop.name, "Empresa Integrada")

    def test_credentials_tab_is_read_only_without_editable_fields(self) -> None:
        response = self.client.get(reverse("workshops:update", kwargs={"pk": self.workshop.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="consumer_key"')
        self.assertNotContains(response, 'name="consumer_secret"')
        self.assertNotContains(response, 'name="access_token"')
        self.assertNotContains(response, 'name="nfse_password"')
        self.assertNotContains(response, 'name="nfse_token"')

    def test_certificate_save_updates_workshop_and_syncs_integration(self) -> None:
        certificate_bytes = b"certificado-a1-binario"
        certificate_file = SimpleUploadedFile(
            "certificado.pfx",
            certificate_bytes,
            content_type="application/x-pkcs12",
        )
        file_service = FakeWorkshopFileService()

        with (
            patch("apps.workshops.services.files.get_workshop_file_service", return_value=file_service),
            patch("apps.workshops.services.files.wait_for_public_logo_url"),
            patch("apps.workshops.services.files.update_webmania_company", return_value={"success": True}) as update_mock,
        ):
            response = self.client.post(
                reverse("workshops:update", kwargs={"pk": self.workshop.pk}),
                data={
                    "tab": "certificado",
                    "nf_tab": "nfe",
                    "pfx_certificate": certificate_file,
                    "certificate_password": "senha-certificado",
                },
            )

        self.assertEqual(response.status_code, 302)
        update_mock.assert_called_once()
        payload = update_mock.call_args.kwargs["payload"]
        self.assertEqual(payload.get("certificado"), base64.b64encode(certificate_bytes).decode())
        self.assertEqual(payload.get("certificado_senha"), "senha-certificado")

        company = WebmaniaCompany.objects.get(workshop=self.workshop)
        self.assertEqual(company.certificado, "")

        self.workshop.refresh_from_db()
        self.assertEqual(self.workshop.certificate_password, "senha-certificado")
        self.assertTrue(self.workshop.certificate_file_key)
        self.assertEqual(self.workshop.certificate_file_name, "certificado.pfx")

        stored_certificate = file_service.files["certificate"][self.workshop.certificate_file_key]
        self.assertEqual(stored_certificate.content, certificate_bytes)

        page_response = self.client.get(f"{reverse('workshops:update', kwargs={'pk': self.workshop.pk})}?tab=certificado")
        self.assertEqual(page_response.status_code, 200)
        self.assertContains(page_response, "Arquivo atual do certificado")
        self.assertContains(page_response, ".pfx")
        self.assertNotContains(page_response, "certificados/")
        self.assertNotContains(page_response, "Atualmente:")

    @override_settings(APP_BASE_URL="https://app.example.com")
    def test_logo_autoupload_saves_logo_in_bucket_and_syncs_public_url(self) -> None:
        logo_bytes = self._build_png(width=320, height=160)
        logo_file = SimpleUploadedFile(
            "logo.png",
            logo_bytes,
            content_type="image/png",
        )
        file_service = FakeWorkshopFileService()

        with (
            patch("apps.workshops.services.files.get_workshop_file_service", return_value=file_service),
            patch("apps.workshops.services.files.ensure_logo_is_readable_from_storage"),
            patch("apps.workshops.services.files.update_webmania_company", return_value={"success": True}) as update_mock,
        ):
            response = self.client.post(
                reverse("workshops:update", kwargs={"pk": self.workshop.pk}),
                data={
                    "tab": "logo_autoupload",
                    "logo": logo_file,
                },
            )

            self.assertEqual(response.status_code, 200)
            self.assertJSONEqual(response.content, {"ok": True, "message": "Logo da oficina atualizada."})

            self.workshop.refresh_from_db()
            self.assertTrue(self.workshop.logo_file_key)
            self.assertEqual(self.workshop.logo_file_name, "logo.jpg")

            company = WebmaniaCompany.objects.get(workshop=self.workshop)
            public_logo_path = reverse("workshops:logo_public", kwargs={"token": self.workshop.logo_public_token})
            self.assertTrue(company.logomarca.endswith(public_logo_path))
            update_mock.assert_called_once_with(company=company, payload={"logomarca": company.logomarca})

            preview_response = self.client.get(reverse("workshops:logo", kwargs={"pk": self.workshop.pk}))
            self.client.logout()
            public_response = self.client.get(reverse("workshops:logo_public", kwargs={"token": self.workshop.logo_public_token}))

        self.assertEqual(preview_response.status_code, 200)
        self.assertEqual(preview_response["Content-Type"], "image/jpeg")
        self.assertEqual(preview_response.content[:2], b"\xff\xd8")
        self.assertEqual(public_response.status_code, 200)
        self.assertEqual(public_response["Content-Type"], "image/jpeg")
        self.assertEqual(public_response.content[:2], b"\xff\xd8")

        normalized_logo = file_service.files["logo"][self.workshop.logo_file_key]
        self.assertEqual(normalized_logo.filename, "logo.jpg")
        self.assertEqual(normalized_logo.content_type, "image/jpeg")
        with Image.open(io.BytesIO(normalized_logo.content)) as image:
            self.assertLessEqual(image.width, 120)
            self.assertLessEqual(image.height, 65)

    @override_settings(APP_BASE_URL="https://app.example.com")
    def test_logo_autoupload_converts_svg_to_jpeg_with_size_limit(self) -> None:
        logo_file = SimpleUploadedFile(
            "logo.svg",
            b"""<?xml version="1.0" encoding="UTF-8"?><svg xmlns="http://www.w3.org/2000/svg" width="320" height="160"><rect width="320" height="160" fill="#ff0000"/></svg>""",
            content_type="image/svg+xml",
        )
        file_service = FakeWorkshopFileService()
        rasterized_png = self._build_png(width=320, height=160)

        with (
            patch("apps.workshops.services.files.get_workshop_file_service", return_value=file_service),
            patch("apps.workshops.services.files.ensure_logo_is_readable_from_storage"),
            patch("apps.workshops.services.files.update_webmania_company", return_value={"success": True}),
            patch("apps.workshops.services.files._rasterize_svg_to_png", return_value=rasterized_png),
        ):
            response = self.client.post(
                reverse("workshops:update", kwargs={"pk": self.workshop.pk}),
                data={
                    "tab": "logo_autoupload",
                    "logo": logo_file,
                },
            )

        self.assertEqual(response.status_code, 200)
        self.workshop.refresh_from_db()
        self.assertEqual(self.workshop.logo_file_name, "logo.jpg")

        normalized_logo = file_service.files["logo"][self.workshop.logo_file_key]
        self.assertEqual(normalized_logo.filename, "logo.jpg")
        self.assertEqual(normalized_logo.content_type, "image/jpeg")
        with Image.open(io.BytesIO(normalized_logo.content)) as image:
            self.assertLessEqual(image.width, 120)
            self.assertLessEqual(image.height, 65)

    def test_logo_autoupload_rejects_non_supported_logo_format(self) -> None:
        logo_file = SimpleUploadedFile(
            "logo.gif",
            b"GIF89a",
            content_type="image/gif",
        )

        response = self.client.post(
            reverse("workshops:update", kwargs={"pk": self.workshop.pk}),
            data={
                "tab": "logo_autoupload",
                "logo": logo_file,
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertJSONEqual(response.content, {"ok": False, "message": "Permitido logomarca somente nos formatos JPEG, PNG, WEBP ou SVG."})

    @override_settings(APP_BASE_URL="https://app.example.com")
    def test_logo_autoupload_checks_storage_readiness_before_sync(self) -> None:
        logo_file = SimpleUploadedFile(
            "logo.png",
            self._build_png(width=320, height=160),
            content_type="image/png",
        )
        file_service = FakeWorkshopFileService()

        with (
            patch("apps.workshops.services.files.get_workshop_file_service", return_value=file_service),
            patch("apps.workshops.services.files.ensure_logo_is_readable_from_storage") as readiness_mock,
            patch("apps.workshops.services.files.update_webmania_company", return_value={"success": True}) as update_mock,
        ):
            response = self.client.post(
                reverse("workshops:update", kwargs={"pk": self.workshop.pk}),
                data={"tab": "logo_autoupload", "logo": logo_file},
            )

        self.assertEqual(response.status_code, 200)
        readiness_mock.assert_called_once_with(file_id=self.workshop.logo_file_key)
        update_mock.assert_called_once()
        self.assertTrue(update_mock.call_args.kwargs["payload"]["logomarca"].endswith(reverse("workshops:logo_public", kwargs={"token": self.workshop.logo_public_token})))

    @override_settings(APP_BASE_URL="https://app.example.com")
    def test_logo_autoupload_rolls_back_when_storage_readiness_fails(self) -> None:
        logo_file = SimpleUploadedFile(
            "logo.png",
            self._build_png(width=320, height=160),
            content_type="image/png",
        )
        file_service = FakeWorkshopFileService()

        with (
            patch("apps.workshops.services.files.get_workshop_file_service", return_value=file_service),
            patch("apps.workshops.services.files.ensure_logo_is_readable_from_storage", side_effect=WorkshopFileSyncError("A logomarca salva ainda nao ficou disponivel no bucket. Tente novamente em instantes.")),
            patch("apps.workshops.services.files.update_webmania_company") as update_mock,
        ):
            response = self.client.post(
                reverse("workshops:update", kwargs={"pk": self.workshop.pk}),
                data={"tab": "logo_autoupload", "logo": logo_file},
            )

        self.assertEqual(response.status_code, 400)
        self.assertJSONEqual(response.content, {"ok": False, "message": "A logomarca salva ainda nao ficou disponivel no bucket. Tente novamente em instantes."})
        self.workshop.refresh_from_db()
        self.assertEqual(self.workshop.logo_file_key, "")
        self.assertEqual(self.workshop.logo_file_name, "")
        update_mock.assert_not_called()

    @staticmethod
    def _build_png(*, width: int, height: int) -> bytes:
        image = Image.new("RGBA", (width, height), color=(255, 0, 0, 255))
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()

    def test_delete_workshop_removes_local_records_only(self) -> None:
        company = WebmaniaCompany.objects.create(workshop=self.workshop, webmania_company_id="DEL-01")

        with patch("apps.workshops.views.workshops.update_webmania_company") as update_mock:
            response = self.client.post(
                reverse("workshops:delete", kwargs={"pk": self.workshop.pk}),
                HTTP_HX_REQUEST="true",
            )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Workshop.objects.filter(pk=self.workshop.pk).exists())
        self.assertFalse(WebmaniaCompany.objects.filter(pk=company.pk).exists())
        update_mock.assert_not_called()

        self.assertNotIn("active_workshop_id", self.client.session)


class WorkshopPdfPhoneTests(TestCase):
    def test_pdf_phone_prefers_webmania_company_phone_when_available(self) -> None:
        _, workshop = create_director_user_with_workshop(suffix=21)
        WebmaniaCompany.objects.create(workshop=workshop, telefone="+5511988880001")

        self.assertEqual(workshop.pdf_phone, "+5511988880001")

    def test_pdf_phone_falls_back_to_workshop_phone(self) -> None:
        _, workshop = create_director_user_with_workshop(suffix=22)

        self.assertEqual(workshop.pdf_phone, "(11) 98888-7777")


def create_manager_user_with_workshop(*, suffix: int = 1) -> tuple[User, Workshop, WorkshopRole]:
    """Create a user with a Gerente role on a workshop (not account owner)."""
    owner = User.objects.create_user(username=f"mgr_owner{suffix}", password="123", cpf=f"33344455{suffix:03d}")
    account = Account.objects.create(name=f"Conta Gerente {suffix}", owner=owner)
    owner.account = account
    owner.is_account_owner = True
    owner.save(update_fields=["account", "is_account_owner"])

    workshop = Workshop.objects.create(
        account=account,
        name=f"Oficina Gerente {suffix}",
        cnpj=f"33.444.555/0001-{suffix:02d}",
        phone="+5511977776666",
        address="Rua Gerente, 20",
        uf="SP",
    )

    manager_role = WorkshopRole.objects.create(
        account=account,
        name="Gerente",
        is_system=True,
        is_editable=False,
    )

    manager_user = User.objects.create_user(username=f"mgr_user{suffix}", password="123", cpf=f"44455566{suffix:03d}")
    manager_user.account = account
    manager_user.save(update_fields=["account"])
    WorkshopMember.objects.create(user=manager_user, workshop=workshop, role=manager_role, is_active=True)

    return manager_user, workshop, manager_role


class IsWorkshopManagerTests(TestCase):
    def setUp(self) -> None:
        self.manager_user, self.workshop, self.manager_role = create_manager_user_with_workshop(suffix=20)

    def test_is_workshop_manager_returns_true_for_gerente_role(self) -> None:
        result = is_workshop_manager(user=self.manager_user, workshop=self.workshop)
        self.assertTrue(result)

    def test_is_workshop_manager_returns_false_for_non_member(self) -> None:
        other_user = User.objects.create_user(username="non_member_mgr", password="123", cpf="99988877766")
        other_user.account = self.manager_user.account
        other_user.save(update_fields=["account"])
        result = is_workshop_manager(user=other_user, workshop=self.workshop)
        self.assertFalse(result)

    def test_is_workshop_director_returns_false_for_gerente_role(self) -> None:
        result = is_workshop_director(user=self.manager_user, workshop=self.workshop)
        self.assertFalse(result)

    def test_is_workshop_manager_returns_false_for_different_account(self) -> None:
        other_owner = User.objects.create_user(username="other_acc_owner_mgr", password="123", cpf="77766655544")
        other_account = Account.objects.create(name="Outra Conta Mgr", owner=other_owner)
        other_workshop = Workshop.objects.create(
            account=other_account,
            name="Outra Oficina Mgr",
            cnpj="77.666.555/0001-99",
            phone="+5511911112222",
            address="Outra Rua, 1",
            uf="RJ",
        )
        result = is_workshop_manager(user=self.manager_user, workshop=other_workshop)
        self.assertFalse(result)


class WorkshopManagerAccessTests(TestCase):
    def setUp(self) -> None:
        self.manager_user, self.workshop, self.manager_role = create_manager_user_with_workshop(suffix=21)
        self.client.force_login(self.manager_user)
        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

    def test_manager_can_list_own_active_workshop(self) -> None:
        response = self.client.get(reverse("workshops:list"))
        self.assertEqual(response.status_code, 200)
        workshop_names = [w.name for w in response.context["workshops"]]
        self.assertIn(self.workshop.name, workshop_names)
        self.assertEqual(len(workshop_names), 1)

    def test_manager_sees_only_active_workshop_not_others_in_account(self) -> None:
        # Create a second workshop in the same account — manager is NOT a member
        second_workshop = Workshop.objects.create(
            account=self.workshop.account,
            name="Segunda Oficina",
            cnpj="55.444.333/0001-22",
            phone="+5511966665555",
            address="Rua Segunda, 5",
            uf="MG",
        )
        response = self.client.get(reverse("workshops:list"))
        self.assertEqual(response.status_code, 200)
        workshop_names = [w.name for w in response.context["workshops"]]
        self.assertIn(self.workshop.name, workshop_names)
        self.assertNotIn(second_workshop.name, workshop_names)

    def test_manager_can_access_update_view_for_active_workshop(self) -> None:
        response = self.client.get(reverse("workshops:update", kwargs={"pk": self.workshop.pk}))
        self.assertEqual(response.status_code, 200)

    def test_manager_cannot_delete_workshop(self) -> None:
        response = self.client.post(
            reverse("workshops:delete", kwargs={"pk": self.workshop.pk}),
            HTTP_HX_REQUEST="true",
        )
        # Manager should get 404 (not in allowed queryset for delete)
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Workshop.objects.filter(pk=self.workshop.pk).exists())

    def test_manager_can_access_emission_history(self) -> None:
        with patch("apps.workshops.views.workshops.get_b2b_requests", return_value={"total_notas_processadas": 0, "empresas": []}):
            response = self.client.get(reverse("workshops:emission_history"))
        self.assertEqual(response.status_code, 200)

    def test_manager_cannot_create_workshop(self) -> None:
        response = self.client.get(reverse("workshops:create"))
        self.assertEqual(response.status_code, 403)


class WorkshopRoleFormReservedNameTests(TestCase):
    def setUp(self) -> None:
        from apps.iam.forms import WorkshopRoleForm

        self.form_class = WorkshopRoleForm

    def test_reserved_name_diretor_is_rejected(self) -> None:
        form = self.form_class(data={"name": "Diretor", "permissions": []})
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)

    def test_reserved_name_gerente_is_rejected(self) -> None:
        form = self.form_class(data={"name": "Gerente", "permissions": []})
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)

    def test_reserved_name_case_insensitive_diretor(self) -> None:
        form = self.form_class(data={"name": "DIRETOR", "permissions": []})
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)

    def test_reserved_name_case_insensitive_gerente(self) -> None:
        form = self.form_class(data={"name": "gerente", "permissions": []})
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)

    def test_non_reserved_name_is_accepted(self) -> None:
        form = self.form_class(data={"name": "Mecânico", "permissions": []})
        # May fail for other reasons (account FK) but not on name field
        if not form.is_valid():
            self.assertNotIn("name", form.errors)


class WorkshopCostWorkDayTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=90)
        self.client.force_login(self.user)

        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

        self.workshop_cost = WorkshopCost.objects.create(
            workshop=self.workshop,
            month=5,
            year=2026,
            mechanic_quantity=1,
            work_days_per_month=22,
            productivity_average=Decimal("0.60"),
        )

    def test_work_day_count_returns_correct_value(self) -> None:
        WorkshopCostWorkDay.objects.create(workshop_cost=self.workshop_cost, date=date(2026, 5, 1))
        WorkshopCostWorkDay.objects.create(workshop_cost=self.workshop_cost, date=date(2026, 5, 4))

        self.assertEqual(self.workshop_cost.get_work_day_count(), 2)

    def test_work_day_validation_rejects_date_outside_reference_month(self) -> None:
        work_day = WorkshopCostWorkDay(workshop_cost=self.workshop_cost, date=date(2026, 6, 1))

        with self.assertRaises(ValidationError):
            work_day.full_clean()

    def test_workshop_cost_create_page_renders_work_day_calendar(self) -> None:
        response = self.client.get(reverse("workshops:workshop_cost_create"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Calendário de Dias Trabalhados")
        self.assertContains(response, "work-day-calendar")

    def test_workshop_cost_form_preloads_work_days_and_calculates_work_days_per_month(self) -> None:
        form = WorkshopCostForm(workshop=self.workshop, initial={"month": 1, "year": 2026})
        work_day_dates = [date.fromisoformat(raw) for raw in str(form.initial.get("work_day_dates") or "").split(",") if raw]
        expected_sp_holidays = sorted(holiday_date for holiday_date in holidays.Brazil(state="SP", years=2026).keys() if holiday_date.month == 1 and holiday_date.weekday() < 5)
        expected_work_days = sorted(date(2026, 1, day) for day in range(1, 32) if date(2026, 1, day).weekday() < 5 and date(2026, 1, day) not in expected_sp_holidays)
        self.assertEqual(work_day_dates, expected_work_days)

        no_holiday_month = next(month for month in range(1, 13) if not [holiday_date for holiday_date in holidays.Brazil(state="SP", years=2026).keys() if holiday_date.month == month and holiday_date.weekday() < 5])
        form_no_holiday = WorkshopCostForm(
            data={
                "month": str(no_holiday_month),
                "year": "2026",
                "mechanic_quantity": "1",
                "work_hours_per_day": "08:00",
                "work_days_per_month": "99",
                "productivity_average": "0.60",
                "work_day_dates": "",
                "state": "SP",
            },
            workshop=self.workshop,
        )
        self.assertTrue(form_no_holiday.is_valid(), form_no_holiday.errors)
        self.assertEqual(form_no_holiday.cleaned_data["work_days_per_month"], 0)

        all_work_days_jan = sorted(date(2026, 1, day) for day in range(1, 32) if date(2026, 1, day).weekday() < 5)
        work_day_dates_str = ",".join(d.isoformat() for d in all_work_days_jan[:20])
        form_manual = WorkshopCostForm(
            data={
                "month": "1",
                "year": "2026",
                "mechanic_quantity": "1",
                "work_hours_per_day": "08:00",
                "work_days_per_month": "99",
                "productivity_average": "0.60",
                "work_day_dates": work_day_dates_str,
                "state": "SP",
            },
            workshop=self.workshop,
        )
        self.assertTrue(form_manual.is_valid(), form_manual.errors)
        self.assertEqual(form_manual.cleaned_data["work_days_per_month"], 20)
