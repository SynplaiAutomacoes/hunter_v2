from __future__ import annotations

import re
import uuid

from django import forms

EMPLOYEE_OPTIONS = (
    "Somente eu",
    "2 a 5",
    "6 a 10",
    "11 a 20",
    "Mais de 20",
)
REVENUE_OPTIONS = (
    "Até R$ 20 mil",
    "De R$ 20 mil a R$ 50 mil",
    "De R$ 50 mil a R$ 100 mil",
    "De R$ 100 mil a R$ 200 mil",
    "Acima de R$ 200 mil",
    "Prefiro não informar",
)
CONSENT_TEXT = "Autorizo a equipe Hunter Auto a entrar em contato comigo por WhatsApp ou e-mail para apresentar o sistema."
WHATSAPP_RE = re.compile(r"^[1-9][0-9]9[0-9]{8}$")


class MarketingLeadForm(forms.Form):
    submission_id = forms.UUIDField(required=False)
    name = forms.CharField(min_length=3, max_length=120)
    workshop = forms.CharField(min_length=2, max_length=160)
    email = forms.EmailField(max_length=254)
    whatsapp = forms.CharField(max_length=20)
    employees = forms.ChoiceField(choices=[(value, value) for value in EMPLOYEE_OPTIONS])
    revenue = forms.ChoiceField(choices=[(value, value) for value in REVENUE_OPTIONS])
    consent = forms.BooleanField()
    source = forms.CharField(required=False, max_length=2048)
    utm_source = forms.CharField(required=False, max_length=500)
    utm_medium = forms.CharField(required=False, max_length=500)
    utm_campaign = forms.CharField(required=False, max_length=500)
    utm_term = forms.CharField(required=False, max_length=500)
    utm_content = forms.CharField(required=False, max_length=500)

    def clean_name(self) -> str:
        return str(self.cleaned_data["name"]).strip()

    def clean_workshop(self) -> str:
        return str(self.cleaned_data["workshop"]).strip()

    def clean_email(self) -> str:
        return str(self.cleaned_data["email"]).strip().lower()

    def clean_whatsapp(self) -> str:
        digits = re.sub(r"\D", "", str(self.cleaned_data.get("whatsapp") or ""))
        if not WHATSAPP_RE.match(digits):
            raise forms.ValidationError("Informe um WhatsApp com DDD e 9 dígitos.")
        return digits

    def clean_consent(self) -> bool:
        if not self.cleaned_data.get("consent"):
            raise forms.ValidationError("Autorize o contato para continuar.")
        return True

    def clean_submission_id(self) -> uuid.UUID:
        value = self.cleaned_data.get("submission_id")
        return value if value else uuid.uuid4()

    def build_utm(self) -> dict[str, str]:
        utm: dict[str, str] = {}
        for key in ("utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"):
            value = str(self.cleaned_data.get(key) or "").strip()
            if value:
                utm[key] = value[:500]
        return utm
