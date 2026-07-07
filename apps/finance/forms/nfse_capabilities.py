from __future__ import annotations

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Field, HTML, Layout, Submit
from django.urls import reverse

from apps.core.presentation.forms import CoreModelForm
from apps.finance.models.finance import NfseMunicipalCapability, WebmaniaCompany


class NfseMunicipalCapabilityForm(CoreModelForm):
    class Meta:
        model = NfseMunicipalCapability
        fields = [
            "city_code",
            "city_name",
            "state",
            "provider",
            "provider_version",
            "is_active",
            "national_standard_enabled",
            "legacy_municipal_enabled",
            "emission_enabled",
            "manual_emission_enabled",
            "query_enabled",
            "cancellation_enabled",
            "substitution_enabled",
            "manifestation_enabled",
            "batch_required",
            "rps_required",
            "synchronous_emission",
            "xml_download_enabled",
            "pdf_download_enabled",
            "rps_pdf_enabled",
            "requires_municipal_registration",
            "requires_service_code",
            "requires_cnae",
            "requires_iss_rate",
            "notes",
        ]

    def __init__(self, *args: object, workshop=None, company: WebmaniaCompany | None = None, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.workshop = workshop
        self.company = company
        if workshop is not None:
            self.instance.workshop = workshop
        if company is not None:
            self.instance.company = company
        self.helper = FormHelper()
        field_names = list(self.fields)
        self.helper.layout = Layout(
            Div(*(Field(name, wrapper_class="col-span-12 md:col-span-6") for name in field_names), css_class="grid grid-cols-12 gap-4"),
            HTML('<div class="divider"></div>'),
            Div(
                HTML(f'<a href="{reverse("finance:nfse_capability_list")}" class="btn-form-cancel">Cancelar</a>'),
                Submit("submit", "Salvar", css_class="btn-form-save"),
                css_class="flex items-center justify-end gap-2",
            ),
        )

    def clean(self) -> dict[str, object]:
        cleaned_data = super().clean() or {}
        city_code = str(cleaned_data.get("city_code") or "").strip()
        if self.workshop is not None and self.company is not None and city_code:
            duplicate = NfseMunicipalCapability.objects.filter(workshop=self.workshop, company=self.company, city_code=city_code)
            if self.instance.pk:
                duplicate = duplicate.exclude(pk=self.instance.pk)
            if duplicate.exists():
                self.add_error("city_code", "Ja existe uma capacidade para este municipio nesta oficina.")
        return cleaned_data
