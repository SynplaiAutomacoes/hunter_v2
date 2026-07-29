from __future__ import annotations

from datetime import date
import logging
from typing import Any, cast

from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView, TemplateView

from apps.collaborators.models import WorkshopMember
from apps.core.infrastructure.query_filters import apply_is_active_filter
from apps.core.presentation.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.core.presentation.mixins import HtmxDeleteResponseMixin, HtmxTemplateResponseMixin
from apps.core.infrastructure.services.webmania.webmania import to_public_integration_message, latest_sync_error, has_webmania_change_perm
from apps.core.infrastructure.providers import get_fiscal_service
from apps.core.domain.contracts.fiscal import FiscalServiceError
from apps.finance.models.finance import WebmaniaCompany
from apps.core.infrastructure.services.webmania.webmania_secrets import decrypt_secret
from apps.finance.views.common import DirectorWorkshopAccessMixin
from apps.iam.utils import get_or_create_director_role
from apps.workshops.forms.workshops import (
    BaseWebmaniaCompanySectionForm,
    WorkshopAddressSectionForm,
    WorkshopCertificateSectionForm,
    WorkshopCompanySectionForm,
    WorkshopFiscalSectionForm,
    WorkshopForm,
    WorkshopLogoForm,
    WorkshopOptionalsSectionForm,
    WorkshopPdfObservationSectionForm,
)
from apps.workshops.models.workshops import Workshop
from apps.workshops.services.files import (
    WorkshopFileStorageError,
    WorkshopFileSyncError,
    get_workshop_logo_file,
    schedule_workshop_files_cleanup,
)
from apps.workshops.usecases.upload_file_usecase import UploadWorkshopFileUseCase
from apps.workshops.util.default_setup import create_default_workshop_setup
from apps.workshops.util.monthly_costs import create_default_monthly_costs
from apps.workshops.util.workshops import has_workshop_perm, is_workshop_director, is_workshop_manager


logger = logging.getLogger(__name__)


def _get_user_workshop_queryset(request):
    user = cast(Any, request.user)
    account_id = getattr(user, "account_id", None)
    base_qs = Workshop.objects.select_related("webmania_company").filter(account_id=account_id)

    active_workshop_id = request.session.get("active_workshop_id")
    active_workshop = base_qs.filter(pk=active_workshop_id, is_active=True, members__user=user, members__is_active=True).distinct().first() if active_workshop_id else None

    if active_workshop is not None and is_workshop_director(user=user, workshop=active_workshop, request=request):
        return base_qs.filter(members__user=user, members__is_active=True).distinct()

    if active_workshop is not None and is_workshop_manager(user=user, workshop=active_workshop, request=request):
        return base_qs.filter(pk=active_workshop.pk)

    return base_qs.filter(
        members__user=user,
        members__is_active=True,
        members__role__permissions__content_type__app_label="workshops",
        members__role__permissions__content_type__model="workshop",
        members__role__permissions__codename="change_workshop",
    ).distinct()


# TODO: Não permitir nome igual de oficina
class WorkshopCreateView(LoginRequiredMixin, CreateView):
    model = Workshop
    form_class = WorkshopForm
    template_name = "workshops/workshop_create.html"
    success_url = reverse_lazy("workshops:list")

    def _reference_workshop_for_permission(self):
        user_account_id = getattr(self.request.user, "account_id", None)
        active_workshop_id = self.request.session.get("active_workshop_id")
        if active_workshop_id and user_account_id is not None:
            workshop = Workshop.objects.filter(pk=active_workshop_id, account_id=user_account_id).first()
            if workshop is not None:
                return workshop

        if user_account_id is None:
            return None

        return Workshop.objects.filter(account_id=user_account_id).order_by("criado_em", "pk").first()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        u_acc_id = getattr(self.request.user, "account_id", None)

        context.update(get_fiscal_service().get_context_meta(u_acc_id))

        ref_w = self._reference_workshop_for_permission()
        context.update({"can_sync_webmania_companies": has_webmania_change_perm(self.request.user, ref_w, self.request) and get_fiscal_service().is_homolog_environment(), "is_webmania_homolog_environment": get_fiscal_service().is_homolog_environment()})
        return context

    def dispatch(self, request, *args, **kwargs):
        user = cast(Any, request.user)
        user_account = getattr(user, "account", None)
        if user_account is None:
            raise PermissionDenied

        if user.is_superuser:
            return super().dispatch(request, *args, **kwargs)

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

                get_fiscal_service().provision_webmania_company_for_workshop(workshop=workshop)

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
                create_default_workshop_setup(workshop=workshop)

                self.object = workshop
                logger.info(
                    "workshop_create_succeeded workshop_id=%s account_id=%s user_id=%s",
                    getattr(workshop, "pk", None),
                    getattr(user_account, "id", None),
                    getattr(user, "id", None),
                )
        except FiscalServiceError as exc:
            logger.exception(
                "workshop_create_failed_integration user_id=%s account_id=%s",
                getattr(user, "id", None),
                getattr(user_account, "id", None),
            )
            form.add_error(None, to_public_integration_message(str(exc)))
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
    TAB_PDF_OBSERVATION = "pdf_observation"
    TAB_LOGO_AUTOUPLOAD = "logo_autoupload"
    TABS = {
        TAB_EMPRESA,
        TAB_ENDERECO,
        TAB_NOTA_FISCAL,
        TAB_CERTIFICADO,
        TAB_OPCIONAIS,
        TAB_CREDENCIAIS,
        TAB_PDF_OBSERVATION,
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

    def _get_workshop(self) -> Workshop:
        return get_object_or_404(_get_user_workshop_queryset(self.request), pk=self.kwargs.get("pk"))

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
            self.TAB_PDF_OBSERVATION: WorkshopPdfObservationSectionForm(instance=self.object),
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
        elif active_tab == self.TAB_PDF_OBSERVATION:
            form_map[self.TAB_PDF_OBSERVATION] = WorkshopPdfObservationSectionForm(data=data, files=files, instance=self.object)

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

    def _logo_preview_url(self) -> str:
        if not self.object.has_logo_file:
            return ""
        return reverse("workshops:logo", kwargs={"pk": self.object.pk})

    def _current_certificate_name(self) -> str:
        return self.object.current_certificate_file_name

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
        can_change_workshop = has_workshop_perm(
            user=self.request.user,
            workshop=self.object,
            app_label=Workshop._meta.app_label,
            model=str(Workshop._meta.model_name),
            codename="change_workshop",
            request=self.request,
        )
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
            "pdf_observation_form": forms_map[self.TAB_PDF_OBSERVATION],
            "credential_preview_fields": self._credential_preview_fields(),
            "certificate_status": self._certificate_status(),
            "has_certificate_file": self.object.has_certificate_file,
            "has_certificate_password": bool(str(self.object.certificate_password or "").strip()),
            "can_change_webmania_company": can_change_webmania_company,
            "can_change_workshop": can_change_workshop,
            "logo_form": WorkshopLogoForm(instance=self.object, preview_url=self._logo_preview_url()),
        }

    def _build_update_url(self, *, tab: str, nf_subtab: str) -> str:
        return f"{reverse('workshops:update', kwargs={'pk': self.object.pk})}?tab={tab}&nf_tab={nf_subtab}"

    def _save_company_sync_metadata(self, *, error: str = "") -> None:
        normalized_error = to_public_integration_message(error) if str(error or "").strip() else ""
        self.company.last_sync_at = timezone.now() if not error else self.company.last_sync_at
        self.company.last_sync_error = normalized_error

        update_fields = ["last_sync_error"]
        if not error:
            update_fields.append("last_sync_at")

        self.company.save(update_fields=update_fields)

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
                get_fiscal_service().update_webmania_company(company=self.company, payload=payload)
        except FiscalServiceError as exc:
            public_message = to_public_integration_message(str(exc))
            get_fiscal_service().save_sync_metadata(company=self.company, error=str(exc))
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
            get_fiscal_service().save_sync_metadata(company=self.company, error="")
            get_fiscal_service().sync_workshop_from_company(self.object, self.company, sync_name=sync_name, sync_address=sync_address)

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

        try:
            UploadWorkshopFileUseCase(request=self.request).upload_certificate(
                workshop=self.object,
                company=self.company,
                uploaded_file=form.cleaned_data.get("pfx_certificate"),
                certificate_password=str(form.cleaned_data.get("certificate_password") or ""),
            )
        except (FiscalServiceError, WorkshopFileStorageError, WorkshopFileSyncError) as exc:
            public_message = to_public_integration_message(str(exc)) if isinstance(exc, FiscalServiceError) else str(exc)
            self._save_company_sync_metadata(error=public_message)
            logger.warning(
                "workshop_certificate_sync_failed workshop_id=%s error=%s user_id=%s",
                getattr(self.object, "pk", None),
                public_message,
                getattr(self.request.user, "id", None),
            )
            form.add_error(None, public_message)
            forms_map = self._build_forms(active_tab=tab)
            forms_map[tab] = form
            context = self._build_context(forms_map=forms_map, active_tab=tab, active_nf_subtab=nf_subtab)
            return TemplateResponse(self.request, self.template_name, context)

        self._save_company_sync_metadata(error="")
        messages.success(self.request, "Certificado atualizado e sincronizado com sucesso.")
        logger.info(
            "workshop_certificate_sync_succeeded workshop_id=%s user_id=%s",
            getattr(self.object, "pk", None),
            getattr(self.request.user, "id", None),
        )
        return redirect(self._build_update_url(tab=tab, nf_subtab=nf_subtab))

    def _save_workshop_tab_form(self, *, form: forms.ModelForm, tab: str, nf_subtab: str, success_message: str):
        if not form.changed_data:
            logger.info(
                "workshop_update_tab_no_changes workshop_id=%s tab=%s user_id=%s",
                getattr(self.object, "pk", None),
                tab,
                getattr(self.request.user, "id", None),
            )
            messages.info(self.request, "Nenhuma alteracao detectada.")
            return redirect(self._build_update_url(tab=tab, nf_subtab=nf_subtab))

        form.save()
        messages.success(self.request, success_message)
        logger.info(
            "workshop_update_tab_save_succeeded workshop_id=%s tab=%s user_id=%s",
            getattr(self.object, "pk", None),
            tab,
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
        if request.POST.get("tab") == self.TAB_LOGO_AUTOUPLOAD:
            logo_form = WorkshopLogoForm(data=request.POST, files=request.FILES, instance=self.object, preview_url=self._logo_preview_url())
            if not logo_form.is_valid():
                first_error = "Erro ao salvar logo da oficina."
                if logo_form.errors:
                    first_key = next(iter(logo_form.errors), None)
                    if first_key and logo_form.errors.get(first_key):
                        first_error = str(logo_form.errors[first_key][0])
                return JsonResponse({"ok": False, "message": first_error}, status=400)

            if not logo_form.changed_data:
                return JsonResponse({"ok": True, "message": "Nenhuma alteracao na logo."})

            upload_usecase = UploadWorkshopFileUseCase(request=request)
            try:
                if logo_form.should_clear():
                    upload_usecase.clear_logo(workshop=self.object, company=self.company)
                    return JsonResponse({"ok": True, "message": "Logo da oficina removida."})

                if logo_form.has_new_upload():
                    uploaded_logo = logo_form.cleaned_data.get("logo")
                    if uploaded_logo is None or uploaded_logo is False:
                        return JsonResponse({"ok": True, "message": "Nenhuma alteracao na logo."})
                    upload_usecase.upload_logo(workshop=self.object, company=self.company, uploaded_file=uploaded_logo)
                    return JsonResponse({"ok": True, "message": "Logo da oficina atualizada."})
            except (FiscalServiceError, WorkshopFileStorageError, WorkshopFileSyncError) as exc:
                message = to_public_integration_message(str(exc)) if isinstance(exc, FiscalServiceError) else str(exc)
                return JsonResponse({"ok": False, "message": message}, status=400)

            return JsonResponse({"ok": True, "message": "Nenhuma alteracao na logo."})

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
            self.TAB_CERTIFICADO,
            self.TAB_OPCIONAIS,
        }
        restricted_workshop_tabs = {
            self.TAB_PDF_OBSERVATION,
        }

        if active_tab in restricted_webmania_tabs and not self._can_change_webmania_company():
            raise PermissionDenied

        if active_tab in restricted_workshop_tabs and not has_workshop_perm(
            user=request.user,
            workshop=self.object,
            app_label=Workshop._meta.app_label,
            model=str(Workshop._meta.model_name),
            codename="change_workshop",
            request=request,
        ):
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
        elif active_tab == self.TAB_PDF_OBSERVATION:
            pdf_observation_form = cast(WorkshopPdfObservationSectionForm, forms_map[self.TAB_PDF_OBSERVATION])
            if pdf_observation_form.is_valid():
                return self._save_workshop_tab_form(
                    form=pdf_observation_form,
                    tab=active_tab,
                    nf_subtab=active_nf_subtab,
                    success_message="Observacao do PDF atualizada com sucesso.",
                )
        elif active_tab == self.TAB_CREDENCIAIS:
            messages.info(request, "As credenciais dessa aba sao apenas para visualizacao.")
            return redirect(self._build_update_url(tab=active_tab, nf_subtab=active_nf_subtab))

        context = self._build_context(forms_map=forms_map, active_tab=active_tab, active_nf_subtab=active_nf_subtab)
        return TemplateResponse(request, self.template_name, context)


class WorkshopLogoView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        workshop = get_object_or_404(_get_user_workshop_queryset(request), pk=self.kwargs.get("pk"))

        try:
            stored_logo = get_workshop_logo_file(workshop)
        except WorkshopFileStorageError as exc:
            raise Http404(str(exc)) from exc

        if stored_logo is None:
            raise Http404("Logo nao encontrada.")

        response = HttpResponse(stored_logo.content, content_type=stored_logo.content_type)
        response["Content-Disposition"] = f'inline; filename="{stored_logo.filename}"'
        return response


class PublicWorkshopLogoView(View):
    def get(self, request, *args, **kwargs):
        workshop = get_object_or_404(Workshop.objects.only("id", "logo_file_key", "logo_file_name", "logo_content_type", "logo_uploaded_at"), logo_public_token=self.kwargs.get("token"))

        try:
            stored_logo = get_workshop_logo_file(workshop)
        except WorkshopFileStorageError as exc:
            raise Http404(str(exc)) from exc

        if stored_logo is None:
            raise Http404("Logo nao encontrada.")

        response = HttpResponse(stored_logo.content, content_type=stored_logo.content_type)
        response["Content-Disposition"] = f'inline; filename="{stored_logo.filename}"'
        response["Cache-Control"] = "public, max-age=300"
        return response

    def head(self, request, *args, **kwargs):
        return self.get(request, *args, **kwargs)


class WorkshopDeleteView(LoginRequiredMixin, HtmxDeleteResponseMixin, DeleteView):
    model = Workshop
    success_url = reverse_lazy("workshops:list")

    htmx_template_name = "workshops/partials/workshop_delete_modal.html"
    htmx_trigger = "workshops-table-refresh"

    def get_queryset(self):
        user = cast(Any, self.request.user)
        account_id = getattr(user, "account_id", None)
        base_qs = super().get_queryset().filter(account_id=account_id)

        active_workshop_id = self.request.session.get("active_workshop_id")
        active_workshop = base_qs.filter(pk=active_workshop_id, is_active=True, members__user=user, members__is_active=True).distinct().first() if active_workshop_id else None

        if active_workshop is not None and is_workshop_director(user=user, workshop=active_workshop, request=self.request):
            return base_qs.filter(members__user=user, members__is_active=True).distinct()

        return base_qs.filter(
            members__user=user,
            members__is_active=True,
            members__role__permissions__content_type__app_label="workshops",
            members__role__permissions__content_type__model="workshop",
            members__role__permissions__codename="delete_workshop",
        ).distinct()

    def form_valid(self, form):
        workshop_pk = self.object.pk

        logger.info(
            "workshop_delete_started workshop_id=%s user_id=%s",
            workshop_pk,
            getattr(self.request.user, "id", None),
        )

        with transaction.atomic():
            schedule_workshop_files_cleanup(self.object)
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
        user = cast(Any, self.request.user)
        account_id = getattr(user, "account_id", None)
        base_qs = Workshop.objects.filter(account_id=account_id).select_related("webmania_company").order_by("-criado_em")

        active_workshop_id = self.request.session.get("active_workshop_id")
        active_workshop = base_qs.filter(pk=active_workshop_id, is_active=True, members__user=user, members__is_active=True).distinct().first() if active_workshop_id else None

        if active_workshop is not None and is_workshop_director(user=user, workshop=active_workshop, request=self.request):
            queryset = base_qs.filter(members__user=user, members__is_active=True).distinct()
        elif active_workshop is not None and is_workshop_manager(user=user, workshop=active_workshop, request=self.request):
            queryset = base_qs.filter(pk=active_workshop.pk)
        else:
            queryset = base_qs.filter(
                members__user=user,
                members__is_active=True,
                members__role__permissions__content_type__app_label="workshops",
                members__role__permissions__content_type__model="workshop",
                members__role__permissions__codename="view_workshop",
            ).distinct()

        return apply_is_active_filter(queryset, params=self.request.GET)

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

        context.update(
            {
                "webmania_company_count": len(account_companies),
                "webmania_last_sync_at": latest_sync_at,
                "webmania_last_sync_error": to_public_integration_message(latest_sync_error(account_companies)) if latest_sync_error(account_companies) else "",
                "can_sync_webmania_companies": can_sync_webmania_companies and get_fiscal_service().is_homolog_environment(),
                "is_webmania_homolog_environment": get_fiscal_service().is_homolog_environment(),
            }
        )

        return context


class WorkshopWebmaniaSyncView(LoginRequiredMixin, View):
    required_webmania_permission_codename = "change_webmaniacompany"

    def _resolve_workshop_for_sync(self, request):
        user_account_id = getattr(request.user, "account_id", None)
        active_workshop_id = request.session.get("active_workshop_id")
        if active_workshop_id and user_account_id is not None:
            workshop = Workshop.objects.filter(pk=active_workshop_id, account_id=user_account_id, is_active=True).first()
            if workshop is not None:
                return workshop

        if user_account_id is None:
            return None

        return Workshop.objects.filter(account_id=user_account_id, is_active=True).order_by("criado_em", "pk").first()

    def _has_sync_permission(self, request, workshop: Workshop) -> bool:
        user = cast(Any, request.user)
        return is_workshop_director(user=user, workshop=workshop, request=request) and has_workshop_perm(
            user=user,
            workshop=workshop,
            app_label=WebmaniaCompany._meta.app_label,
            model=str(WebmaniaCompany._meta.model_name),
            codename=self.required_webmania_permission_codename,
            request=request,
        )

    def _redirect_after_sync(self, request):
        user_account_id = getattr(request.user, "account_id", None)
        has_active_workshop = bool(user_account_id) and Workshop.objects.filter(account_id=user_account_id, is_active=True).exists()
        if not has_active_workshop:
            return redirect("workshops:create")
        return redirect("workshops:list")

    @staticmethod
    def _set_active_workshop_from_synced_companies(*, request, synced_companies: list[WebmaniaCompany]) -> None:
        if request.session.get("active_workshop_id"):
            return

        for company in synced_companies:
            workshop_id = getattr(company, "workshop_id", None)
            if workshop_id is not None:
                request.session["active_workshop_id"] = workshop_id
                break

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        user = cast(Any, request.user)
        user_account = getattr(user, "account", None)
        if user_account is None:
            raise PermissionDenied

        self.workshop = self._resolve_workshop_for_sync(request)
        is_account_owner = getattr(user_account, "owner_id", None) == getattr(user, "id", None)

        if self.workshop is not None:
            if not (is_account_owner or self._has_sync_permission(request, self.workshop)):
                raise PermissionDenied
        elif not is_account_owner:
            raise PermissionDenied

        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        if not get_fiscal_service().is_homolog_environment():
            messages.error(request, "A sincronizacao manual esta disponivel apenas em ambiente de homologacao.")
            return self._redirect_after_sync(request)

        try:
            synced_companies = get_fiscal_service().sync_b2b_companies_to_database(
                workshop=self.workshop,
                actor_user=request.user,
                force_global_auth=True,
            )
        except FiscalServiceError as exc:
            messages.error(request, to_public_integration_message(str(exc)))
        else:
            self._set_active_workshop_from_synced_companies(request=request, synced_companies=synced_companies)
            synced_count = len(synced_companies)
            if synced_count <= 0:
                messages.warning(request, "Sincronizacao concluida, mas nenhuma empresa foi retornada.")
            elif synced_count == 1:
                messages.success(request, "Sincronizacao concluida com sucesso. 1 empresa atualizada.")
            else:
                messages.success(request, f"Sincronizacao concluida com sucesso. {synced_count} empresas atualizadas.")

        return self._redirect_after_sync(request)


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
            request_payload = get_fiscal_service().get_b2b_requests(month=month, year=year, workshop=self.workshop)
        except FiscalServiceError as exc:
            messages.error(self.request, to_public_integration_message(str(exc)))
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
                    return TemplateResponse(request, "navbar/partials/workshop_select.html", {})

                request.session["active_workshop_id"] = workshop_id_int

        redirect_url = reverse("budget:budget_list")
        if request.headers.get("HX-Request"):
            response = HttpResponse()
            response["HX-Redirect"] = redirect_url
            return response
        return redirect(redirect_url)
