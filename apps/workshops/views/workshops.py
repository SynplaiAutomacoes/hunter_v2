from __future__ import annotations

import base64
from datetime import date
import logging
from typing import Any, cast

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView, TemplateView

from apps.collaborators.models import WorkshopMember
from apps.core.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.core.views import HtmxDeleteResponseMixin, HtmxTemplateResponseMixin
from apps.finance.models import WebmaniaCompany
from apps.finance.services.webmania_b2b import (
    WebmaniaB2BServiceError,
    get_b2b_requests,
    provision_webmania_company_for_workshop,
    sync_b2b_companies_to_database,
    update_webmania_company,
)
from apps.finance.services.webmania_secrets import decrypt_secret, encrypt_secret
from apps.finance.views.common import DirectorWorkshopAccessMixin
from apps.iam.utils import get_or_create_director_role
from apps.workshops.forms.workshops import (
    BaseWebmaniaCompanySectionForm,
    WorkshopAddressSectionForm,
    WorkshopCertificateSectionForm,
    WorkshopCompanySectionForm,
    WorkshopFiscalSectionForm,
    WorkshopForm,
    WorkshopOptionalsSectionForm,
)
from apps.workshops.models.workshops import Workshop
from apps.workshops.util.monthly_costs import create_default_monthly_costs
from apps.workshops.util.workshops import has_workshop_perm


logger = logging.getLogger(__name__)


def _is_webmania_homolog_environment() -> bool:
    raw_value = getattr(settings, "WEBMANIA_AMBIENT", "2")
    try:
        return int(str(raw_value).strip()) == 2
    except (TypeError, ValueError):
        return False


def _to_public_integration_message(raw_message: object) -> str:
    normalized_message = str(raw_message or "").strip()
    if not normalized_message:
        return "Nao foi possivel concluir a operacao de integracao."

    return normalized_message.replace("WEBMANIA", "integracao").replace("Webmania", "integracao").replace("webmania", "integracao")


# TODO: Não permitir nome igual de oficina
class WorkshopCreateView(LoginRequiredMixin, CreateView):
    model = Workshop
    form_class = WorkshopForm
    template_name = "workshops/workshop_create.html"
    success_url = reverse_lazy("workshops:list")

    @staticmethod
    def _latest_sync_error(companies: list[WebmaniaCompany]) -> str:
        candidates = [company for company in companies if str(company.last_sync_error or "").strip()]
        if not candidates:
            return ""

        latest = max(
            candidates,
            key=lambda company: company.last_sync_at or company.atualizado_em or company.criado_em,
        )
        return str(latest.last_sync_error or "").strip()

    def _reference_workshop_for_permission(self):
        user_account_id = getattr(self.request.user, "account_id", None)
        active_workshop_id = self.request.session.get("active_workshop_id")
        if active_workshop_id and user_account_id is not None:
            workshop = Workshop.objects.filter(pk=active_workshop_id, account_id=user_account_id).first()
            if workshop is not None:
                return workshop

        return self.get_queryset().first()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        user_account_id = getattr(self.request.user, "account_id", None)
        account_companies = []
        if user_account_id is not None:
            account_companies = list(WebmaniaCompany.objects.filter(workshop__account_id=user_account_id).exclude(webmania_company_id="").select_related("workshop"))
        sync_candidates = [company.last_sync_at for company in account_companies if company.last_sync_at is not None]
        latest_sync_at = max(sync_candidates) if sync_candidates else None

        reference_workshop = self._reference_workshop_for_permission()
        user = cast(Any, self.request.user)
        can_sync_webmania_companies = bool(reference_workshop) and has_workshop_perm(
            user=user,
            workshop=reference_workshop,
            app_label=WebmaniaCompany._meta.app_label,
            model=str(WebmaniaCompany._meta.model_name),
            codename="change_webmaniacompany",
            request=self.request,
        )

        is_webmania_homolog_environment = _is_webmania_homolog_environment()
        latest_sync_error = self._latest_sync_error(account_companies)

        context.update(
            {
                "webmania_company_count": len(account_companies),
                "webmania_last_sync_at": latest_sync_at,
                "webmania_last_sync_error": _to_public_integration_message(latest_sync_error) if latest_sync_error else "",
                "can_sync_webmania_companies": can_sync_webmania_companies and is_webmania_homolog_environment,
                "is_webmania_homolog_environment": is_webmania_homolog_environment,
            }
        )

        return context

    def dispatch(self, request, *args, **kwargs):
        user = cast(Any, request.user)
        user_account = getattr(user, "account", None)
        if user_account is None:
            raise PermissionDenied

        if getattr(user_account, "owner_id", None) != getattr(user, "id", None):
            raise PermissionDenied

        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        user = cast(Any, self.request.user)
        user_account = getattr(user, "account", None)
        if user_account is None:
            raise PermissionDenied

        logger.info(
            "workshop_create_started user_id=%s account_id=%s",
            getattr(user, "id", None),
            getattr(user_account, "id", None),
        )

        try:
            with transaction.atomic():
                workshop = form.save(commit=False)
                workshop.account = user_account
                workshop.save()

                provision_webmania_company_for_workshop(workshop=workshop)

                director_role = get_or_create_director_role(account=user_account)
                WorkshopMember.objects.get_or_create(
                    user=self.request.user,
                    workshop=workshop,
                    defaults={
                        "role": director_role,
                        "is_active": True,
                    },
                )

                create_default_monthly_costs(workshop=workshop)

                self.object = workshop
                logger.info(
                    "workshop_create_succeeded workshop_id=%s account_id=%s user_id=%s",
                    getattr(workshop, "pk", None),
                    getattr(user_account, "id", None),
                    getattr(user, "id", None),
                )
        except WebmaniaB2BServiceError as exc:
            logger.exception(
                "workshop_create_failed_integration user_id=%s account_id=%s",
                getattr(user, "id", None),
                getattr(user_account, "id", None),
            )
            form.add_error(None, _to_public_integration_message(str(exc)))
            self.object = None
            return self.form_invalid(form)

        return redirect(self.get_success_url())


class WorkshopUpdateView(LoginRequiredMixin, View):
    template_name = "workshops/workshop_update.html"

    TAB_EMPRESA = "empresa"
    TAB_ENDERECO = "endereco"
    TAB_NOTA_FISCAL = "nota_fiscal"
    TAB_CERTIFICADO = "certificado"
    TAB_OPCIONAIS = "opcionais"
    TAB_CREDENCIAIS = "credenciais"
    TABS = {
        TAB_EMPRESA,
        TAB_ENDERECO,
        TAB_NOTA_FISCAL,
        TAB_CERTIFICADO,
        TAB_OPCIONAIS,
        TAB_CREDENCIAIS,
    }

    NF_SUBTAB_NFE = "nfe"
    NF_SUBTAB_NFCE = "nfce"
    NF_SUBTAB_NFSE = "nfse"
    NF_SUBTABS = {
        NF_SUBTAB_NFE,
        NF_SUBTAB_NFCE,
        NF_SUBTAB_NFSE,
    }

    def dispatch(self, request, *args, **kwargs):
        self.object = self._get_workshop()
        self.company = self._get_or_create_company()
        return super().dispatch(request, *args, **kwargs)

    def _get_workshop_queryset(self):
        return (
            Workshop.objects.filter(
                members__user=self.request.user,
                members__is_active=True,
                members__role__permissions__content_type__app_label="workshops",
                members__role__permissions__content_type__model="workshop",
                members__role__permissions__codename="change_workshop",
            )
            .select_related("webmania_company")
            .distinct()
        )

    def _get_workshop(self) -> Workshop:
        return get_object_or_404(self._get_workshop_queryset(), pk=self.kwargs.get("pk"))

    def _get_or_create_company(self) -> WebmaniaCompany:
        company = getattr(self.object, "webmania_company", None)
        if company is None:
            company = WebmaniaCompany.objects.create(workshop=self.object)
        return company

    @staticmethod
    def _normalize_tab(value: object) -> str:
        tab = str(value or "").strip().lower()
        if tab in WorkshopUpdateView.TABS:
            return tab
        return WorkshopUpdateView.TAB_EMPRESA

    @staticmethod
    def _normalize_nf_subtab(value: object) -> str:
        subtab = str(value or "").strip().lower()
        if subtab in WorkshopUpdateView.NF_SUBTABS:
            return subtab
        return WorkshopUpdateView.NF_SUBTAB_NFE

    def _can_change_webmania_company(self) -> bool:
        user = cast(Any, self.request.user)
        return has_workshop_perm(
            user=user,
            workshop=self.object,
            app_label=WebmaniaCompany._meta.app_label,
            model=str(WebmaniaCompany._meta.model_name),
            codename="change_webmaniacompany",
            request=self.request,
        )

    def _build_forms(
        self,
        *,
        active_tab: str,
        data=None,
        files=None,
    ) -> dict[str, forms.BaseForm]:
        form_map: dict[str, forms.BaseForm] = {
            self.TAB_EMPRESA: WorkshopCompanySectionForm(instance=self.company, workshop=self.object),
            self.TAB_ENDERECO: WorkshopAddressSectionForm(instance=self.company, workshop=self.object),
            self.TAB_NOTA_FISCAL: WorkshopFiscalSectionForm(instance=self.company, workshop=self.object),
            self.TAB_CERTIFICADO: WorkshopCertificateSectionForm(instance=self.object),
            self.TAB_OPCIONAIS: WorkshopOptionalsSectionForm(instance=self.company, workshop=self.object),
        }

        if data is None and files is None:
            return form_map

        if active_tab == self.TAB_EMPRESA:
            form_map[self.TAB_EMPRESA] = WorkshopCompanySectionForm(data=data, files=files, instance=self.company, workshop=self.object)
        elif active_tab == self.TAB_ENDERECO:
            form_map[self.TAB_ENDERECO] = WorkshopAddressSectionForm(data=data, files=files, instance=self.company, workshop=self.object)
        elif active_tab == self.TAB_NOTA_FISCAL:
            form_map[self.TAB_NOTA_FISCAL] = WorkshopFiscalSectionForm(data=data, files=files, instance=self.company, workshop=self.object)
        elif active_tab == self.TAB_CERTIFICADO:
            form_map[self.TAB_CERTIFICADO] = WorkshopCertificateSectionForm(data=data, files=files, instance=self.object)
        elif active_tab == self.TAB_OPCIONAIS:
            form_map[self.TAB_OPCIONAIS] = WorkshopOptionalsSectionForm(data=data, files=files, instance=self.company, workshop=self.object)

        return form_map

    def _credential_preview_fields(self) -> list[dict[str, object]]:
        fields = [
            ("Consumer Key", self.company.consumer_key),
            ("Consumer Secret", self.company.consumer_secret),
            ("Access Token", self.company.access_token),
            ("Access Token Secret", self.company.access_token_secret),
            ("Bearer Access Token", self.company.bearer_access_token),
            ("Login NFS-e", self.company.nfse_login),
            ("Senha NFS-e", self.company.nfse_password),
            ("Token NFS-e", self.company.nfse_token),
        ]

        payload: list[dict[str, object]] = []
        for label, value in fields:
            decrypted_value = decrypt_secret(value)
            payload.append(
                {
                    "label": label,
                    "value": decrypted_value,
                    "has_value": bool(decrypted_value.strip()),
                }
            )

        return payload

    def _current_certificate_name(self) -> str:
        if not self.object.pfx_certificate:
            return ""

        raw_name = str(self.object.pfx_certificate.name or "")
        if not raw_name:
            return ""

        normalized = raw_name.replace("\\", "/")
        return normalized.split("/")[-1]

    def _certificate_status(self) -> dict[str, str]:
        certificate_name = self._current_certificate_name()

        password = str(self.object.certificate_password or "").strip()
        has_certificate_file = bool(certificate_name)
        has_password = bool(password)

        if has_certificate_file and has_password:
            return {
                "label": "Certificado A1 configurado",
                "description": "Arquivo e senha configurados para emissao fiscal.",
            }
        if has_certificate_file:
            return {
                "label": "Certificado A1 parcial",
                "description": "Arquivo enviado, mas falta a senha para completar a configuracao.",
            }
        if has_password:
            return {
                "label": "Certificado A1 parcial",
                "description": "Senha cadastrada sem arquivo de certificado. Envie o arquivo .pfx ou .p12.",
            }

        return {
            "label": "Certificado A1 nao cadastrado",
            "description": "Envie um certificado .pfx ou .p12 para consultas da SEFAZ e emissao fiscal.",
        }

    def _build_context(self, *, forms_map: dict[str, forms.BaseForm], active_tab: str, active_nf_subtab: str) -> dict[str, object]:
        can_change_webmania_company = self._can_change_webmania_company()
        return {
            "object": self.object,
            "workshop": self.object,
            "active_tab": active_tab,
            "active_nf_subtab": active_nf_subtab,
            "current_certificate_name": self._current_certificate_name(),
            "company_form": forms_map[self.TAB_EMPRESA],
            "address_form": forms_map[self.TAB_ENDERECO],
            "fiscal_form": forms_map[self.TAB_NOTA_FISCAL],
            "certificate_form": forms_map[self.TAB_CERTIFICADO],
            "optionals_form": forms_map[self.TAB_OPCIONAIS],
            "credential_preview_fields": self._credential_preview_fields(),
            "certificate_status": self._certificate_status(),
            "can_change_webmania_company": can_change_webmania_company,
        }

    def _build_update_url(self, *, tab: str, nf_subtab: str) -> str:
        return f"{reverse('workshops:update', kwargs={'pk': self.object.pk})}?tab={tab}&nf_tab={nf_subtab}"

    def _save_company_sync_metadata(self, *, error: str = "") -> None:
        normalized_error = _to_public_integration_message(error) if str(error or "").strip() else ""
        self.company.last_sync_at = timezone.now() if not error else self.company.last_sync_at
        self.company.last_sync_error = normalized_error

        update_fields = ["last_sync_error"]
        if not error:
            update_fields.append("last_sync_at")

        self.company.save(update_fields=update_fields)

    def _sync_workshop_summary_from_company(self, *, sync_name: bool = False, sync_address: bool = False) -> None:
        update_fields: list[str] = []

        if sync_name:
            workshop_name = str(self.company.razao_social or self.company.nome_completo or "").strip()
            if workshop_name and self.object.name != workshop_name:
                self.object.name = workshop_name
                update_fields.append("name")

        if sync_address:
            address_parts = [
                str(self.company.endereco or "").strip(),
                str(self.company.numero or "").strip(),
                str(self.company.complemento or "").strip(),
            ]
            normalized_address = ", ".join(part for part in address_parts if part)
            if normalized_address and self.object.address != normalized_address:
                self.object.address = normalized_address
                update_fields.append("address")

            normalized_uf = str(self.company.uf or "").strip().upper()
            if len(normalized_uf) == 2 and self.object.uf != normalized_uf:
                self.object.uf = normalized_uf
                update_fields.append("uf")

        if update_fields:
            self.object.save(update_fields=update_fields)

    def _save_company_tab_form(
        self,
        *,
        form: BaseWebmaniaCompanySectionForm,
        tab: str,
        nf_subtab: str,
        sync_name: bool = False,
        sync_address: bool = False,
        form_key: str | None = None,
    ):
        if not form.changed_data:
            logger.info(
                "workshop_update_tab_no_changes workshop_id=%s tab=%s user_id=%s",
                getattr(self.object, "pk", None),
                tab,
                getattr(self.request.user, "id", None),
            )
            messages.info(self.request, "Nenhuma alteracao detectada.")
            return redirect(self._build_update_url(tab=tab, nf_subtab=nf_subtab))

        payload = form.build_api_payload()
        logger.info(
            "workshop_update_tab_save_started workshop_id=%s tab=%s has_sync_payload=%s user_id=%s",
            getattr(self.object, "pk", None),
            tab,
            bool(payload),
            getattr(self.request.user, "id", None),
        )

        try:
            if payload:
                update_webmania_company(company=self.company, payload=payload)
        except WebmaniaB2BServiceError as exc:
            public_message = _to_public_integration_message(str(exc))
            self._save_company_sync_metadata(error=public_message)
            logger.warning(
                "workshop_update_tab_sync_failed workshop_id=%s tab=%s error=%s user_id=%s",
                getattr(self.object, "pk", None),
                tab,
                public_message,
                getattr(self.request.user, "id", None),
            )
            form.add_error(None, public_message)
            forms_map = self._build_forms(active_tab=tab)
            forms_map[form_key or tab] = form
            context = self._build_context(forms_map=forms_map, active_tab=tab, active_nf_subtab=nf_subtab)
            return TemplateResponse(self.request, self.template_name, context)

        with transaction.atomic():
            self.company = form.save(commit=True)
            self.company.last_sync_error = ""
            self.company.last_sync_at = timezone.now()
            self.company.save(update_fields=["last_sync_error", "last_sync_at"])
            self._sync_workshop_summary_from_company(sync_name=sync_name, sync_address=sync_address)

        if not payload:
            messages.success(self.request, "Dados locais atualizados com sucesso.")
        else:
            messages.success(self.request, "Dados sincronizados com sucesso.")

        logger.info(
            "workshop_update_tab_save_succeeded workshop_id=%s tab=%s synced=%s user_id=%s",
            getattr(self.object, "pk", None),
            tab,
            bool(payload),
            getattr(self.request.user, "id", None),
        )

        return redirect(self._build_update_url(tab=tab, nf_subtab=nf_subtab))

    @staticmethod
    def _encode_workshop_certificate(workshop: Workshop) -> str:
        if not workshop.pfx_certificate:
            return ""

        try:
            workshop.pfx_certificate.open("rb")
            try:
                raw_bytes = workshop.pfx_certificate.read()
            finally:
                workshop.pfx_certificate.close()
        except OSError:
            return ""

        if not raw_bytes:
            return ""

        return base64.b64encode(raw_bytes).decode()

    def _update_company_certificate_snapshot(self, *, encoded_certificate: str, certificate_password: str) -> None:
        update_fields: list[str] = []

        new_certificate_value = encrypt_secret(encoded_certificate) if encoded_certificate else ""
        if self.company.certificado != new_certificate_value:
            self.company.certificado = new_certificate_value
            update_fields.append("certificado")

        new_password_value = encrypt_secret(certificate_password) if certificate_password else ""
        if self.company.certificado_senha != new_password_value:
            self.company.certificado_senha = new_password_value
            update_fields.append("certificado_senha")

        if update_fields:
            self.company.save(update_fields=update_fields)

    def _save_certificate_form(self, *, form: WorkshopCertificateSectionForm, tab: str, nf_subtab: str):
        if not form.changed_data:
            logger.info(
                "workshop_certificate_no_changes workshop_id=%s user_id=%s",
                getattr(self.object, "pk", None),
                getattr(self.request.user, "id", None),
            )
            messages.info(self.request, "Nenhuma alteracao detectada.")
            return redirect(self._build_update_url(tab=tab, nf_subtab=nf_subtab))

        logger.info(
            "workshop_certificate_save_started workshop_id=%s user_id=%s",
            getattr(self.object, "pk", None),
            getattr(self.request.user, "id", None),
        )

        with transaction.atomic():
            self.object = form.save()

        encoded_certificate = self._encode_workshop_certificate(self.object)
        certificate_password = str(self.object.certificate_password or "").strip()
        self._update_company_certificate_snapshot(encoded_certificate=encoded_certificate, certificate_password=certificate_password)

        payload: dict[str, str] = {}
        if encoded_certificate:
            payload["certificado"] = encoded_certificate
        if certificate_password:
            payload["certificado_senha"] = certificate_password

        if not payload:
            messages.success(self.request, "Certificados locais atualizados com sucesso.")
            logger.info(
                "workshop_certificate_saved_local_only workshop_id=%s reason=no_payload user_id=%s",
                getattr(self.object, "pk", None),
                getattr(self.request.user, "id", None),
            )
            return redirect(self._build_update_url(tab=tab, nf_subtab=nf_subtab))

        if not self._can_change_webmania_company():
            messages.warning(self.request, "Certificados locais atualizados. Sem permissao para sincronizar na integracao.")
            logger.warning(
                "workshop_certificate_saved_without_sync_permission workshop_id=%s user_id=%s",
                getattr(self.object, "pk", None),
                getattr(self.request.user, "id", None),
            )
            return redirect(self._build_update_url(tab=tab, nf_subtab=nf_subtab))

        try:
            update_webmania_company(company=self.company, payload=payload)
        except WebmaniaB2BServiceError as exc:
            public_message = _to_public_integration_message(str(exc))
            self._save_company_sync_metadata(error=public_message)
            logger.warning(
                "workshop_certificate_sync_failed workshop_id=%s error=%s user_id=%s",
                getattr(self.object, "pk", None),
                public_message,
                getattr(self.request.user, "id", None),
            )
            messages.warning(self.request, f"Certificados locais atualizados, mas a sincronizacao falhou: {public_message}")
            return redirect(self._build_update_url(tab=tab, nf_subtab=nf_subtab))

        self._save_company_sync_metadata(error="")
        messages.success(self.request, "Certificados atualizados e sincronizados com sucesso.")
        logger.info(
            "workshop_certificate_sync_succeeded workshop_id=%s user_id=%s",
            getattr(self.object, "pk", None),
            getattr(self.request.user, "id", None),
        )
        return redirect(self._build_update_url(tab=tab, nf_subtab=nf_subtab))

    def get(self, request, *args, **kwargs):
        active_tab = self._normalize_tab(request.GET.get("tab"))
        active_nf_subtab = self._normalize_nf_subtab(request.GET.get("nf_tab"))

        forms_map = self._build_forms(active_tab=active_tab)
        context = self._build_context(forms_map=forms_map, active_tab=active_tab, active_nf_subtab=active_nf_subtab)
        return TemplateResponse(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        active_tab = self._normalize_tab(request.POST.get("tab"))
        active_nf_subtab = self._normalize_nf_subtab(request.POST.get("nf_tab"))

        logger.info(
            "workshop_update_post_started workshop_id=%s tab=%s nf_tab=%s user_id=%s",
            getattr(self.object, "pk", None),
            active_tab,
            active_nf_subtab,
            getattr(request.user, "id", None),
        )

        forms_map = self._build_forms(active_tab=active_tab, data=request.POST, files=request.FILES)

        restricted_webmania_tabs = {
            self.TAB_EMPRESA,
            self.TAB_ENDERECO,
            self.TAB_NOTA_FISCAL,
            self.TAB_OPCIONAIS,
        }
        if active_tab in restricted_webmania_tabs and not self._can_change_webmania_company():
            raise PermissionDenied

        if active_tab == self.TAB_EMPRESA:
            company_form = cast(WorkshopCompanySectionForm, forms_map[self.TAB_EMPRESA])
            if company_form.is_valid():
                return self._save_company_tab_form(form=company_form, tab=active_tab, nf_subtab=active_nf_subtab, sync_name=True)
        elif active_tab == self.TAB_ENDERECO:
            address_form = cast(WorkshopAddressSectionForm, forms_map[self.TAB_ENDERECO])
            if address_form.is_valid():
                return self._save_company_tab_form(form=address_form, tab=active_tab, nf_subtab=active_nf_subtab, sync_address=True)
        elif active_tab == self.TAB_NOTA_FISCAL:
            fiscal_form = cast(WorkshopFiscalSectionForm, forms_map[self.TAB_NOTA_FISCAL])
            if fiscal_form.is_valid():
                return self._save_company_tab_form(form=fiscal_form, tab=active_tab, nf_subtab=active_nf_subtab)
        elif active_tab == self.TAB_CERTIFICADO:
            certificate_form = cast(WorkshopCertificateSectionForm, forms_map[self.TAB_CERTIFICADO])
            if certificate_form.is_valid():
                return self._save_certificate_form(form=certificate_form, tab=active_tab, nf_subtab=active_nf_subtab)
        elif active_tab == self.TAB_OPCIONAIS:
            optionals_form = cast(WorkshopOptionalsSectionForm, forms_map[self.TAB_OPCIONAIS])
            if optionals_form.is_valid():
                return self._save_company_tab_form(form=optionals_form, tab=active_tab, nf_subtab=active_nf_subtab)
        elif active_tab == self.TAB_CREDENCIAIS:
            messages.info(request, "As credenciais dessa aba sao apenas para visualizacao.")
            return redirect(self._build_update_url(tab=active_tab, nf_subtab=active_nf_subtab))

        context = self._build_context(forms_map=forms_map, active_tab=active_tab, active_nf_subtab=active_nf_subtab)
        return TemplateResponse(request, self.template_name, context)


class WorkshopDeleteView(LoginRequiredMixin, HtmxDeleteResponseMixin, DeleteView):
    model = Workshop
    success_url = reverse_lazy("workshops:list")

    htmx_template_name = "workshops/partials/workshop_delete_modal.html"
    htmx_trigger = "workshops-table-refresh"

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .filter(
                members__user=self.request.user,
                members__is_active=True,
                members__role__permissions__content_type__app_label="workshops",
                members__role__permissions__content_type__model="workshop",
                members__role__permissions__codename="delete_workshop",
            )
            .distinct()
        )

    def form_valid(self, form):
        workshop_pk = self.object.pk

        logger.info(
            "workshop_delete_started workshop_id=%s user_id=%s",
            workshop_pk,
            getattr(self.request.user, "id", None),
        )

        with transaction.atomic():
            self.object.delete()

        if self.request.session.get("active_workshop_id") == workshop_pk:
            self.request.session.pop("active_workshop_id", None)

        if bool(getattr(self.request, "htmx", False)):
            response = HttpResponse()
            if self.htmx_trigger:
                response["HX-Trigger"] = self.htmx_trigger
            logger.info(
                "workshop_delete_succeeded_htmx workshop_id=%s user_id=%s",
                workshop_pk,
                getattr(self.request.user, "id", None),
            )
            return response

        messages.success(self.request, "Oficina excluida com sucesso no sistema.")
        logger.info(
            "workshop_delete_succeeded workshop_id=%s user_id=%s",
            workshop_pk,
            getattr(self.request.user, "id", None),
        )
        return redirect(self.get_success_url())


class WorkshopListView(LoginRequiredMixin, HtmxTemplateResponseMixin, ListView):
    model = Workshop
    template_name = "workshops/workshop_list.html"
    context_object_name = "workshops"

    htmx_template_name = "workshops/partials/workshop_table.html"

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .filter(
                members__user=self.request.user,
                members__is_active=True,
                members__role__permissions__content_type__app_label="workshops",
                members__role__permissions__content_type__model="workshop",
                members__role__permissions__codename="view_workshop",
            )
            .select_related("webmania_company")
            .distinct()
            .order_by("-criado_em")
        )

    @staticmethod
    def _latest_sync_error(companies: list[WebmaniaCompany]) -> str:
        candidates = [company for company in companies if str(company.last_sync_error or "").strip()]
        if not candidates:
            return ""

        latest = max(
            candidates,
            key=lambda company: company.last_sync_at or company.atualizado_em or company.criado_em,
        )
        return str(latest.last_sync_error or "").strip()

    def _reference_workshop_for_permission(self):
        user_account_id = getattr(self.request.user, "account_id", None)
        active_workshop_id = self.request.session.get("active_workshop_id")
        if active_workshop_id and user_account_id is not None:
            workshop = Workshop.objects.filter(pk=active_workshop_id, account_id=user_account_id).first()
            if workshop is not None:
                return workshop

        return self.get_queryset().first()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["fields"] = [
            TableColumn(label="Oficina", attr=Workshop.name.field.name),
            TableColumn(label="Empresa", attr="webmania_company_name_display", sortable=False, searchable=False),
            TableColumn(label="Documento", attr="webmania_company_document_display", sortable=False, searchable=False),
            TableColumn(label="IE", attr="webmania_company_ie_display", sortable=False, searchable=False),
            TableColumn(label="Cidade/UF", attr="webmania_company_city_state_display", sortable=False, searchable=False),
            TableColumn(label="Unidade", attr="webmania_company_unit_display", sortable=False, searchable=False),
            TableColumn(label="Tributacao", attr="webmania_company_tax_type_display", sortable=False, searchable=False),
            TableColumn(label=str(Workshop.is_active.field.verbose_name), attr=Workshop.is_active.field.name),
        ]

        context["actions"] = [
            TableActionDefaults.view("finance:webmania_company_detail", kwargs={"pk": "webmania_company_pk"}),
            TableActionDefaults.edit("workshops:update"),
            TableActionDefaults.delete("workshops:delete"),
        ]

        user_account_id = getattr(self.request.user, "account_id", None)
        account_companies = []
        if user_account_id is not None:
            account_companies = list(WebmaniaCompany.objects.filter(workshop__account_id=user_account_id).exclude(webmania_company_id="").select_related("workshop"))
        sync_candidates = [company.last_sync_at for company in account_companies if company.last_sync_at is not None]
        latest_sync_at = max(sync_candidates) if sync_candidates else None

        reference_workshop = self._reference_workshop_for_permission()
        user = cast(Any, self.request.user)
        can_sync_webmania_companies = bool(reference_workshop) and has_workshop_perm(
            user=user,
            workshop=reference_workshop,
            app_label=WebmaniaCompany._meta.app_label,
            model=str(WebmaniaCompany._meta.model_name),
            codename="change_webmaniacompany",
            request=self.request,
        )

        is_webmania_homolog_environment = _is_webmania_homolog_environment()
        latest_sync_error = self._latest_sync_error(account_companies)

        context.update(
            {
                "webmania_company_count": len(account_companies),
                "webmania_last_sync_at": latest_sync_at,
                "webmania_last_sync_error": _to_public_integration_message(latest_sync_error) if latest_sync_error else "",
                "can_sync_webmania_companies": can_sync_webmania_companies and is_webmania_homolog_environment,
                "is_webmania_homolog_environment": is_webmania_homolog_environment,
            }
        )

        return context


class WorkshopWebmaniaSyncView(LoginRequiredMixin, DirectorWorkshopAccessMixin, View):
    required_webmania_permission_codename = "change_webmaniacompany"

    def post(self, request, *args, **kwargs):
        if not _is_webmania_homolog_environment():
            messages.error(request, "A sincronizacao manual esta disponivel apenas em ambiente de homologacao.")
            return redirect("workshops:list")

        try:
            synced_companies = sync_b2b_companies_to_database(
                workshop=self.workshop,
                actor_user=request.user,
                force_global_auth=True,
            )
        except WebmaniaB2BServiceError as exc:
            messages.error(request, _to_public_integration_message(str(exc)))
        else:
            synced_count = len(synced_companies)
            if synced_count <= 0:
                messages.warning(request, "Sincronizacao concluida, mas nenhuma empresa foi retornada.")
            elif synced_count == 1:
                messages.success(request, "Sincronizacao concluida com sucesso. 1 empresa atualizada.")
            else:
                messages.success(request, f"Sincronizacao concluida com sucesso. {synced_count} empresas atualizadas.")

        return redirect("workshops:list")


class WorkshopEmissionHistoryView(LoginRequiredMixin, DirectorWorkshopAccessMixin, TemplateView):
    template_name = "finance/webmania_requests_list.html"
    required_webmania_permission_codename = "view_webmaniacompany"

    @staticmethod
    def _parse_competencia(value: str | None) -> tuple[int, int] | None:
        raw_value = str(value or "").strip()
        if not raw_value:
            return None

        parts = raw_value.split("-")
        if len(parts) != 2:
            return None

        year_str, month_str = parts
        try:
            year = int(year_str)
            month = int(month_str)
        except ValueError:
            return None

        if year < 2000 or year > 9999:
            return None
        if month < 1 or month > 12:
            return None

        return month, year

    @staticmethod
    def _normalize_month(value: str | None) -> int:
        try:
            month = int(str(value or "").strip())
        except ValueError:
            month = date.today().month
        if month < 1 or month > 12:
            return date.today().month
        return month

    @staticmethod
    def _normalize_year(value: str | None) -> int:
        try:
            year = int(str(value or "").strip())
        except ValueError:
            year = date.today().year
        if year < 2000 or year > 9999:
            return date.today().year
        return year

    def get_context_data(self, **kwargs: object) -> dict[str, object]:
        context = super().get_context_data(**kwargs)

        competencia = self._parse_competencia(self.request.GET.get("competencia"))
        if competencia is not None:
            month, year = competencia
        else:
            month = self._normalize_month(self.request.GET.get("mes"))
            year = self._normalize_year(self.request.GET.get("ano"))

        try:
            request_payload = get_b2b_requests(month=month, year=year, workshop=self.workshop)
        except WebmaniaB2BServiceError as exc:
            messages.error(self.request, _to_public_integration_message(str(exc)))
            total_notas_processadas = 0
            request_rows: list[dict[str, str]] = []
        else:
            total_notas_processadas = int(request_payload.get("total_notas_processadas") or 0)
            empresas_payload_raw = request_payload.get("empresas")
            empresas_payload: list[object] = empresas_payload_raw if isinstance(empresas_payload_raw, list) else []

            request_rows = []
            for item in empresas_payload:
                if not isinstance(item, dict):
                    continue
                request_rows.append(
                    {
                        "name": str(item.get("razao_social") or item.get("nome_completo") or "-"),
                        "document": str(item.get("cnpj") or item.get("cpf") or "-"),
                        "ie": str(item.get("ie") or "-"),
                        "notas_processadas": str(item.get("notas_processadas") or 0),
                    }
                )

        context.update(
            {
                "selected_month": month,
                "selected_year": year,
                "selected_month_str": f"{month:02d}",
                "selected_year_str": f"{year:04d}",
                "selected_competencia": f"{year:04d}-{month:02d}",
                "total_notas_processadas": total_notas_processadas,
                "request_rows": request_rows,
            }
        )
        return context


class NavbarWorkshopSelectView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        workshop_id = request.POST.get("workshop_id")
        user = cast(Any, request.user)

        if workshop_id:
            try:
                workshop_id_int = int(workshop_id)
            except (TypeError, ValueError):
                workshop_id_int = None

            if workshop_id_int is not None and Workshop.objects.filter(pk=workshop_id_int, account=getattr(user, "account", None), is_active=True).exists():
                if not WorkshopMember.objects.filter(user=request.user, workshop_id=workshop_id_int, is_active=True, workshop__is_active=True).exists():
                    request.session.pop("active_workshop_id", None)
                    return TemplateResponse(request, "navbar/partials/workshop_select.html", {})

                request.session["active_workshop_id"] = workshop_id_int
            else:
                request.session.pop("active_workshop_id", None)

        redirect_url = reverse("budget:budget_list")
        if request.headers.get("HX-Request"):
            response = HttpResponse()
            response["HX-Redirect"] = redirect_url
            return response
        return redirect(redirect_url)
