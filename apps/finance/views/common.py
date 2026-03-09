from __future__ import annotations

from typing import Any, cast

from django.core.exceptions import PermissionDenied
from django.views import View

from apps.finance.models.finance import WebmaniaCompany, WebmaniaCompanyTaxType
from apps.workshops.util.workshops import get_active_workshop_or_404, has_workshop_perm, is_workshop_director


def _only_digits(value: object) -> str:
    return "".join(char for char in str(value or "") if char.isdigit())


def _format_cnpj(value: object) -> str:
    digits = _only_digits(value)
    if len(digits) != 14:
        return str(value or "").strip() or "-"
    return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"


def _format_cpf(value: object) -> str:
    digits = _only_digits(value)
    if len(digits) != 11:
        return str(value or "").strip() or "-"
    return f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}"


def _format_unit(value: object) -> str:
    normalized = str(value or "").strip().replace("_", " ")
    if not normalized:
        return "-"
    return normalized.title()


def _format_tax_type(value: object) -> str:
    normalized = str(value or "").strip().lower()
    if normalized == WebmaniaCompanyTaxType.SIMPLES_NACIONAL:
        return str(WebmaniaCompanyTaxType.SIMPLES_NACIONAL.label)
    if normalized == WebmaniaCompanyTaxType.LUCRO_NORMAL:
        return str(WebmaniaCompanyTaxType.LUCRO_NORMAL.label)
    return str(value or "-").strip() or "-"


class DirectorWorkshopAccessMixin(View):
    required_webmania_permission_codename: str | None = None

    def _has_required_webmania_permission(self, request) -> bool:
        codename = self.required_webmania_permission_codename
        if not codename:
            return True

        model_name = str(WebmaniaCompany._meta.model_name)

        return has_workshop_perm(
            user=request.user,
            workshop=self.workshop,
            app_label=WebmaniaCompany._meta.app_label,
            model=model_name,
            codename=codename,
            request=request,
        )

    def dispatch(self, request, *args, **kwargs):
        self.workshop = get_active_workshop_or_404(request)
        if not request.user.is_authenticated:
            raise PermissionDenied
        user = cast(Any, request.user)
        if not is_workshop_director(user=user, workshop=self.workshop, request=request):
            raise PermissionDenied
        if not self._has_required_webmania_permission(request):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)
