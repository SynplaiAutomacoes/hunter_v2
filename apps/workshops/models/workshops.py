from __future__ import annotations

from datetime import timedelta

from django.core.exceptions import ObjectDoesNotExist
from django.core.validators import FileExtensionValidator
from django.db import models
from django.db.models import CharField, BooleanField
from django.utils import timezone
from localflavor.br.models import BRCNPJField
from phonenumber_field.modelfields import PhoneNumberField

from apps.core.models import TimeStampedModel


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
    pdf_observation = CharField(verbose_name="Observação", max_length=250, null=False, blank=False, default="")
    logo = models.FileField(
        verbose_name="Logo da oficina",
        upload_to="workshops/logos/",
        null=True,
        blank=True,
        validators=[FileExtensionValidator(allowed_extensions=["png", "jpg", "jpeg", "gif", "webp", "svg"])],
    )
    is_active = BooleanField(verbose_name="Ativa", default=True)
    # Sefaz
    pfx_certificate = models.FileField(verbose_name="Certificado PFX", upload_to="certificados/", null=True, blank=True)
    certificate_password = models.CharField(verbose_name="Senha do Certificado", max_length=255, null=True, blank=True)
    last_nsu_sefaz = models.CharField(null=True, blank=True, default="0")
    last_sefaz_search_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Oficina"
        verbose_name_plural = "Oficinas"

    @property
    def can_search_sefaz(self):
        if not self.last_sefaz_search_date:
            return True
        return timezone.now() > self.last_sefaz_search_date + timedelta(hours=1)

    def _get_webmania_company(self):
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
    def webmania_company_pk(self):
        company = self._get_webmania_company()
        if company is None:
            return None
        return company.pk

    @property
    def webmania_company_name_display(self) -> str:
        company = self._get_webmania_company()
        if company is None:
            return "-"
        return str(company.razao_social or company.nome_completo or "").strip() or "-"

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

    def __str__(self):
        return self.name
