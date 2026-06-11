from __future__ import annotations

from datetime import date
from typing import Any, cast

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView, UpdateView

from apps.core.infrastructure.services.webmania.webmania import is_webmania_homolog_environment
from apps.finance.forms import WebmaniaCompanyUpdateForm
from apps.finance.models.finance import WebmaniaCompany
from apps.core.infrastructure.services.webmania.webmania_b2b import (
    WebmaniaB2BServiceError,
    get_b2b_requests,
    list_local_b2b_companies,
    sync_b2b_companies_to_database,
    update_webmania_company,
)
from apps.core.infrastructure.services.webmania.webmania_secrets import decrypt_secret
from .common import DirectorWorkshopAccessMixin, _format_cnpj, _format_cpf, _format_tax_type, _format_unit
from apps.workshops.util.workshops import has_workshop_perm


def _is_webmania_homolog_environment() -> bool:
    return is_webmania_homolog_environment()


def _to_public_integration_message(raw_message: object) -> str:
    normalized_message = str(raw_message or "").strip()
    if not normalized_message:
        return "Nao foi possivel concluir a operacao de integracao."

    return normalized_message.replace("WEBMANIA", "integracao").replace("Webmania", "integracao").replace("webmania", "integracao")


class WebmaniaCompanyListView(LoginRequiredMixin, DirectorWorkshopAccessMixin, TemplateView):
    template_name = "finance/webmania_company_list.html"
    required_webmania_permission_codename = "view_webmaniacompany"

    @staticmethod
    def _latest_sync_error(companies: list[WebmaniaCompany]) -> str:
        companies_with_error = [company for company in companies if str(company.last_sync_error or "").strip()]
        if not companies_with_error:
            return ""

        latest_error_company = max(
            companies_with_error,
            key=lambda company: company.last_sync_at or company.atualizado_em or company.criado_em,
        )
        return str(latest_error_company.last_sync_error or "").strip()

    @staticmethod
    def _build_company_row(company: WebmaniaCompany) -> dict[str, object]:
        formatted_document = _format_cnpj(company.cnpj)

        return {
            "pk": company.pk,
            "id": company.webmania_company_id or "-",
            "name": company.razao_social or company.nome_completo or "-",
            "document": formatted_document,
            "ie": company.ie or "-",
            "city": company.cidade or "-",
            "state": company.uf or "-",
            "unit": _format_unit(company.unidade_empresa),
            "tax_type": _format_tax_type(company.tipo_tributacao),
        }

    def get_context_data(self, **kwargs: object) -> dict[str, object]:
        context = super().get_context_data(**kwargs)

        local_companies = list_local_b2b_companies(workshop=self.workshop)
        company_rows = [self._build_company_row(company) for company in local_companies]
        sync_candidates = [company.last_sync_at for company in local_companies if company.last_sync_at is not None]
        latest_sync_at = max(sync_candidates) if sync_candidates else None

        user = cast(Any, self.request.user)
        can_sync_webmania_companies = has_workshop_perm(
            user=user,
            workshop=self.workshop,
            app_label=WebmaniaCompany._meta.app_label,
            model=str(WebmaniaCompany._meta.model_name),
            codename="change_webmaniacompany",
            request=self.request,
        )  # type: ignore[arg-type]
        is_webmania_homolog_environment = _is_webmania_homolog_environment()
        latest_sync_error = self._latest_sync_error(local_companies)

        context.update(
            {
                "webmania_companies": company_rows,
                "webmania_company_count": len(company_rows),
                "webmania_last_sync_at": latest_sync_at,
                "webmania_last_sync_error": _to_public_integration_message(latest_sync_error) if latest_sync_error else "",
                "can_sync_webmania_companies": can_sync_webmania_companies and is_webmania_homolog_environment,
                "is_webmania_homolog_environment": is_webmania_homolog_environment,
            }
        )
        return context


class WebmaniaCompanySyncView(LoginRequiredMixin, DirectorWorkshopAccessMixin, View):
    required_webmania_permission_codename = "change_webmaniacompany"

    def post(self, request, *args, **kwargs):
        if not _is_webmania_homolog_environment():
            messages.error(request, "A sincronizacao manual esta disponivel apenas em ambiente de homologacao.")
            return redirect("finance:webmania_company_list")

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

        return redirect("finance:webmania_company_list")


class WebmaniaCompanyDetailView(LoginRequiredMixin, DirectorWorkshopAccessMixin, TemplateView):
    template_name = "finance/webmania_company_detail.html"
    required_webmania_permission_codename = "view_webmaniacompany"

    @staticmethod
    def _secret_field(label: str, value: object) -> dict[str, object]:
        decrypted_value = decrypt_secret(value)
        has_value = bool(decrypted_value.strip())
        return {
            "label": label,
            "value": decrypted_value,
            "has_value": has_value,
        }

    @staticmethod
    def _regular_field(label: str, value: object) -> dict[str, str]:
        if isinstance(value, bool):
            normalized_value = "Sim" if value else "Não"
        else:
            normalized_value = str(value or "-").strip() or "-"

        return {
            "label": label,
            "value": normalized_value,
        }

    def _get_company(self) -> WebmaniaCompany:
        workshop_account_id = getattr(self.workshop, "account_id", None)
        return get_object_or_404(
            WebmaniaCompany.objects.select_related("workshop").filter(workshop__account_id=workshop_account_id),
            pk=self.kwargs.get("pk"),
        )

    def get_context_data(self, **kwargs: object) -> dict[str, object]:
        context = super().get_context_data(**kwargs)
        company = self._get_company()
        is_homolog_environment = _is_webmania_homolog_environment()

        fiscal_fields = [
            self._regular_field("Informações ao Fisco", company.informacoes_fisco),
            self._regular_field("NFS-e Login", company.nfse_login),
            self._regular_field("NFS-e RPS Série", company.nfse_rps_serie),
            self._regular_field("NFS-e RPS Número", company.nfse_rps_numero),
            self._regular_field("NFS-e Lote RPS Número", company.nfse_lote_rps_numero),
            self._regular_field("Regime Apuração SN", company.regime_apuracao_sn),
            self._regular_field("Regime Especial Nacional", company.regime_especial_nacional),
            self._regular_field("Regime Especial Municipal", company.regime_especial_municipal),
            self._regular_field("NF-e Série", company.nfe_serie),
            self._regular_field("NF-e Número", company.nfe_numero),
            self._regular_field("NFC-e Série", company.nfce_serie),
            self._regular_field("NFC-e Número", company.nfce_numero),
            self._regular_field("NFC-e ID CSC", company.nfce_id_csc),
            self._regular_field("NFC-e Código CSC", company.nfce_codigo_csc),
            self._regular_field("CNAE", company.cnae),
            self._regular_field("CNAE ISSQN", company.cnae_issqn),
            self._regular_field("Partilha ICMS contribuinte", company.partilha_icms_contribuinte),
            self._regular_field("Partilha ICMS isento", company.partilha_icms_isento),
            self._regular_field("Orientação DANFE", company.orientacao_danfe),
            self._regular_field("Microcervejaria", company.microcervejaria),
            self._regular_field("ICMS refeição SP", company.icms_ref_sp),
            self._regular_field("Regime refeições SP", company.refeicoes_sp),
            self._regular_field("ICMS refeição DF", company.icms_ref_df),
            self._regular_field("Exclusão ICMS PIS/COFINS", company.exclusao_icms_pis_cofins),
            self._regular_field("Exclusão DIFAL PIS/COFINS", company.exclusao_difal_pis_cofins),
            self._regular_field("Deduzir desconto IPI", company.deduzir_desconto_ipi),
            self._regular_field("E-mail automático NFS-e", company.email_automatico_nfse),
            self._regular_field("Desativar EPEC", company.desativar_epec),
            self._regular_field("Ocultar total etiqueta", company.ocultar_total_etiqueta),
            self._regular_field("Última sincronização", company.last_sync_at),
            self._regular_field("Último erro de sincronização", company.last_sync_error),
        ]
        if is_homolog_environment:
            fiscal_fields[5:5] = [self._regular_field("NFS-e RPS Número Homologação", company.nfse_rps_numero_dev)]
            fiscal_fields[11:11] = [self._regular_field("NF-e Número Homologação", company.nfe_numero_dev)]
            fiscal_fields[15:15] = [
                self._regular_field("NFC-e Número Homologação", company.nfce_numero_dev),
                self._regular_field("NFC-e ID CSC Homologação", company.nfce_id_csc_dev),
                self._regular_field("NFC-e Código CSC Homologação", company.nfce_codigo_csc_dev),
            ]

        context.update(
            {
                "company": company,
                "identity_fields": [
                    self._regular_field("ID da integracao", company.webmania_company_id),
                    self._regular_field("Razão Social", company.razao_social),
                    self._regular_field("CNPJ", _format_cnpj(company.cnpj)),
                    self._regular_field("CPF", _format_cpf(company.cpf)),
                    self._regular_field("Nome Fantasia", company.nome_fantasia),
                    self._regular_field("Nome Completo", company.nome_completo),
                    self._regular_field("Inscrição Estadual", company.ie),
                    self._regular_field("Inscrição Municipal", company.im),
                    self._regular_field("Unidade", _format_unit(company.unidade_empresa)),
                    self._regular_field("Tipo Tributação", _format_tax_type(company.tipo_tributacao)),
                    self._regular_field("Regime Tributário", company.regime_tributario),
                ],
                "contact_fields": [
                    self._regular_field("E-mail", company.email),
                    self._regular_field("Telefone", company.telefone),
                    self._regular_field("Banco", company.conta_bancaria_banco),
                    self._regular_field("Agência", company.conta_bancaria_agencia),
                    self._regular_field("Conta", company.conta_bancaria_numero),
                    self._regular_field("Dígito da conta", company.conta_bancaria_digito),
                    self._regular_field("Contabilidade", company.contabilidade),
                    self._regular_field("CEP", company.cep),
                    self._regular_field("Endereço", company.endereco),
                    self._regular_field("Número", company.numero),
                    self._regular_field("Complemento", company.complemento),
                    self._regular_field("Bairro", company.bairro),
                    self._regular_field("Cidade", company.cidade),
                    self._regular_field("UF", company.uf),
                    self._regular_field("URL Notificação", company.url_notificacao),
                    self._regular_field("Logomarca", company.logomarca),
                ],
                "credential_fields": [
                    self._secret_field("Consumer Key", company.consumer_key),
                    self._secret_field("Consumer Secret", company.consumer_secret),
                    self._secret_field("Access Token", company.access_token),
                    self._secret_field("Access Token Secret", company.access_token_secret),
                    self._secret_field("Bearer Access Token", company.bearer_access_token),
                    self._secret_field("Senha NFS-e", company.nfse_password),
                    self._secret_field("Token NFS-e", company.nfse_token),
                    self._secret_field("Senha Certificado A1", company.certificado_senha),
                ],
                "fiscal_fields": fiscal_fields,
                "is_webmania_homolog_environment": is_homolog_environment,
            }
        )
        return context


class WebmaniaCompanyUpdateView(LoginRequiredMixin, DirectorWorkshopAccessMixin, UpdateView):
    template_name = "finance/webmania_company_update.html"
    model = WebmaniaCompany
    form_class = WebmaniaCompanyUpdateForm
    required_webmania_permission_codename = "change_webmaniacompany"

    def get_object(self, queryset=None) -> WebmaniaCompany:
        workshop_account_id = getattr(self.workshop, "account_id", None)
        scoped_queryset = WebmaniaCompany.objects.select_related("workshop").filter(workshop__account_id=workshop_account_id)
        return get_object_or_404(scoped_queryset, pk=self.kwargs.get("pk"))

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        return super().post(request, *args, **kwargs)

    def form_valid(self, form: WebmaniaCompanyUpdateForm):
        payload = form.build_api_payload()
        if not payload:
            messages.info(self.request, "Nenhuma alteracao detectada para sincronizar.")
            return redirect("finance:webmania_company_detail", pk=self.object.pk)

        try:
            update_webmania_company(company=self.object, payload=payload)
        except WebmaniaB2BServiceError as exc:
            self.object.last_sync_error = _to_public_integration_message(str(exc))
            self.object.save(update_fields=["last_sync_error"])
            messages.error(self.request, _to_public_integration_message(str(exc)))
            return self.form_invalid(form)

        self.object = form.save(commit=False)
        self.object.last_sync_at = timezone.now()
        self.object.last_sync_error = ""
        self.object.save()
        messages.success(self.request, "Empresa atualizada com sucesso.")
        return redirect("finance:webmania_company_detail", pk=self.object.pk)


class WebmaniaRequestsView(LoginRequiredMixin, DirectorWorkshopAccessMixin, TemplateView):
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
            empresas_payload = empresas_payload_raw if isinstance(empresas_payload_raw, list) else []

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
