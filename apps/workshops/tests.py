from __future__ import annotations

import base64
from unittest.mock import Mock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Account, User
from apps.collaborators.models import WorkshopMember
from apps.finance.models.finance import WebmaniaCompany
from apps.finance.services.webmania_secrets import decrypt_secret
from apps.iam.models import WorkshopRole
from apps.iam.utils import get_or_create_director_role
from apps.workshops.services.files import StoredWorkshopFile
from apps.workshops.models.workshops import Workshop
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
        self.assertEqual(decrypt_secret(company.certificado), base64.b64encode(certificate_bytes).decode())
        self.assertEqual(decrypt_secret(company.certificado_senha), "senha-certificado")

        self.workshop.refresh_from_db()
        self.assertEqual(self.workshop.certificate_password, "senha-certificado")
        self.assertTrue(self.workshop.certificate_mongo_file_id)
        self.assertEqual(self.workshop.certificate_file_name, "certificado.pfx")
        self.assertFalse(bool(self.workshop.pfx_certificate))

        stored_certificate = file_service.files["certificate"][self.workshop.certificate_mongo_file_id]
        self.assertEqual(stored_certificate.content, certificate_bytes)

        page_response = self.client.get(f"{reverse('workshops:update', kwargs={'pk': self.workshop.pk})}?tab=certificado")
        self.assertEqual(page_response.status_code, 200)
        self.assertContains(page_response, "Arquivo atual do certificado")
        self.assertContains(page_response, ".pfx")
        self.assertNotContains(page_response, "certificados/")
        self.assertNotContains(page_response, "Atualmente:")

    def test_logo_autoupload_saves_logo_in_mongo_and_serves_preview(self) -> None:
        logo_bytes = b"fake-logo-bytes"
        logo_file = SimpleUploadedFile(
            "logo.png",
            logo_bytes,
            content_type="image/png",
        )
        file_service = FakeWorkshopFileService()

        with patch("apps.workshops.services.files.get_workshop_file_service", return_value=file_service):
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
            self.assertTrue(self.workshop.logo_mongo_file_id)
            self.assertEqual(self.workshop.logo_file_name, "logo.png")
            self.assertFalse(bool(self.workshop.logo))

            preview_response = self.client.get(reverse("workshops:logo", kwargs={"pk": self.workshop.pk}))

        self.assertEqual(preview_response.status_code, 200)
        self.assertEqual(preview_response["Content-Type"], "image/png")
        self.assertEqual(preview_response.content, logo_bytes)

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
