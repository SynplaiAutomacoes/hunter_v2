from __future__ import annotations

import secrets
from datetime import timedelta

from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.db.models import CharField, BooleanField
from django.utils import timezone
from localflavor.br.models import BRCNPJField
from phonenumber_field.modelfields import PhoneNumberField

from apps.core.infrastructure.models import TimeStampedModel


def generate_workshop_logo_public_token() -> str:
    return secrets.token_hex(16)


class Workshop(TimeStampedModel):
    account = models.ForeignKey(
        "accounts.Account",
        on_delete=models.PROTECT,
        related_name="workshops",
        null=True,
        blank=True,
    )
    name = CharField(verbose_name="Nome", max_length=255, null=False, blank=False)
    cnpj = BRCNPJField(verbose_name="CNPJ", null=False, blank=False, unique=True)
    phone = PhoneNumberField(region="BR", verbose_name="Telefone", max_length=20, blank=False)
    address = CharField(verbose_name="Endereço", max_length=255, null=False, blank=False)
    uf = models.CharField(verbose_name="UF", max_length=2, null=False, blank=False, default="SP")
    pdf_observation = models.TextField(verbose_name="Observação", null=False, blank=False, default="")
    logo_file_key = models.CharField(max_length=512, blank=True, default="")
    logo_file_name = models.CharField(max_length=255, blank=True, default="")
    logo_content_type = models.CharField(max_length=100, blank=True, default="")
    logo_uploaded_at = models.DateTimeField(null=True, blank=True)
    logo_public_token = models.CharField(max_length=32, unique=True, default=generate_workshop_logo_public_token, editable=False)
    is_active = BooleanField(verbose_name="Ativa", default=True)
    # Sefaz
    certificate_file_key = models.CharField(max_length=512, blank=True, default="")
    certificate_file_name = models.CharField(max_length=255, blank=True, default="")
    certificate_content_type = models.CharField(max_length=100, blank=True, default="")
    certificate_uploaded_at = models.DateTimeField(null=True, blank=True)
    certificate_password = models.CharField(verbose_name="Senha do Certificado", max_length=255, null=True, blank=True)
    last_nsu_sefaz = models.CharField(null=True, blank=True, default="0")
    last_sefaz_search_date = models.DateTimeField(null=True, blank=True)
    whatsapp_phone = CharField(
        verbose_name="Telefone Assistente Virtual",
        max_length=20,
        blank=True,
        default="",
    )
    whatsapp_instance_name = CharField(
        verbose_name="Nome da instância WhatsApp",
        max_length=64,
        blank=True,
        default="",
    )

    class Meta:
        verbose_name = "Oficina"
        verbose_name_plural = "Oficinas"

    @property
    def can_search_sefaz(self) -> bool:
        if not self.last_sefaz_search_date:
            return True
        return timezone.now() > self.last_sefaz_search_date + timedelta(hours=1)

    @staticmethod
    def _extract_file_name(raw_name: object) -> str:
        normalized_name = str(raw_name or "").replace("\\", "/")
        if not normalized_name:
            return ""
        return normalized_name.split("/")[-1]

    @property
    def has_logo_file(self) -> bool:
        return bool(self.logo_file_key)

    @property
    def current_logo_file_name(self) -> str:
        return self.logo_file_name

    @property
    def has_certificate_file(self) -> bool:
        return bool(self.certificate_file_key)

    @property
    def current_certificate_file_name(self) -> str:
        return self.certificate_file_name

    def _get_webmania_company(self) -> object | None:
        cache_attr = "_cached_webmania_company"
        if hasattr(self, cache_attr):
            return getattr(self, cache_attr)

        company = None
        try:
            company = self.webmania_company
        except ObjectDoesNotExist:
            company = None

        setattr(self, cache_attr, company)
        return company

    @staticmethod
    def _format_document(*, cnpj: object, cpf: object) -> str:
        cnpj_digits = "".join(ch for ch in str(cnpj or "") if ch.isdigit())
        if len(cnpj_digits) == 14:
            return f"{cnpj_digits[:2]}.{cnpj_digits[2:5]}.{cnpj_digits[5:8]}/{cnpj_digits[8:12]}-{cnpj_digits[12:]}"

        cpf_digits = "".join(ch for ch in str(cpf or "") if ch.isdigit())
        if len(cpf_digits) == 11:
            return f"{cpf_digits[:3]}.{cpf_digits[3:6]}.{cpf_digits[6:9]}-{cpf_digits[9:]}"

        return "-"

    @property
    def webmania_company_pk(self) -> int | None:
        company = self._get_webmania_company()
        if company is None:
            return None
        return int(getattr(company, "pk", None)) if getattr(company, "pk", None) is not None else None

    @property
    def webmania_company_name_display(self) -> str:
        company = self._get_webmania_company()
        if company is None:
            return "-"
        return str(company.razao_social or company.nome_completo or "").strip() or "-"

    @property
    def nome_fantasia_display(self) -> str:
        company = self._get_webmania_company()
        if company is not None:
            nome = str(company.nome_fantasia or "").strip()
            if nome:
                return nome
        workshop_name = str(self.name or "").strip()
        if workshop_name:
            return workshop_name
        return "-"

    @property
    def razao_social_display(self) -> str:
        company = self._get_webmania_company()
        if company is not None:
            razao = str(company.razao_social or company.nome_completo or "").strip()
            if razao:
                return razao
        workshop_name = str(self.name or "").strip()
        return workshop_name or "-"

    @property
    def webmania_company_document_display(self) -> str:
        company = self._get_webmania_company()
        if company is None:
            return "-"
        return self._format_document(cnpj=company.cnpj, cpf=company.cpf)

    @property
    def webmania_company_ie_display(self) -> str:
        company = self._get_webmania_company()
        if company is None:
            return "-"
        return str(company.ie or "").strip() or "-"

    @property
    def webmania_company_city_state_display(self) -> str:
        company = self._get_webmania_company()
        if company is None:
            return "-"

        city = str(company.cidade or "").strip()
        state = str(company.uf or "").strip()
        if city and state:
            return f"{city} / {state}"
        if city:
            return city
        if state:
            return state
        return "-"

    @property
    def pdf_phone(self) -> str:
        company = self._get_webmania_company()
        if company is not None:
            company_phone = str(company.telefone or "").strip()
            if company_phone:
                return company_phone
        return str(self.phone or "").strip()

    @property
    def webmania_company_unit_display(self) -> str:
        company = self._get_webmania_company()
        if company is None:
            return "-"
        return str(company.unidade_empresa or "").strip().replace("_", " ").title() or "-"

    @property
    def webmania_company_tax_type_display(self) -> str:
        company = self._get_webmania_company()
        if company is None:
            return "-"

        tax_type = str(company.get_tipo_tributacao_display() or company.tipo_tributacao or "").strip()
        return tax_type or "-"

    def __str__(self) -> str:
        return self.name
