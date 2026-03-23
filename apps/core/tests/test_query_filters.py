from __future__ import annotations

from datetime import timedelta

from django.http import QueryDict
from django.test import TestCase
from django.utils import timezone

from apps.core.query_filters import QueryParamFilter, apply_query_param_filters
from apps.workshops.models.workshops import Workshop


def create_workshop(*, suffix: int) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina Query Filter {suffix}",
        cnpj=f"19.222.333/0001-{suffix:02d}",
        phone="+5511999999999",
        address="Rua Query Filter, 123",
    )


class QueryParamFiltersDateTests(TestCase):
    def test_apply_query_param_filters_supports_date_range_filters(self) -> None:
        older_workshop = create_workshop(suffix=1)
        in_range_workshop = create_workshop(suffix=2)
        newer_workshop = create_workshop(suffix=3)

        now = timezone.now()
        Workshop.objects.filter(pk=older_workshop.pk).update(criado_em=now - timedelta(days=7))
        Workshop.objects.filter(pk=in_range_workshop.pk).update(criado_em=now - timedelta(days=3))
        Workshop.objects.filter(pk=newer_workshop.pk).update(criado_em=now)

        filtered = apply_query_param_filters(
            Workshop.objects.all(),
            params=QueryDict(f"data_inicial={(now - timedelta(days=4)).date().isoformat()}&data_final={(now - timedelta(days=2)).date().isoformat()}"),
            filter_configs=(
                QueryParamFilter(param_name="data_inicial", lookup="criado_em__date", kind="date_gte"),
                QueryParamFilter(param_name="data_final", lookup="criado_em__date", kind="date_lte"),
            ),
        )

        self.assertQuerySetEqual(filtered.order_by("pk"), [in_range_workshop], transform=lambda obj: obj)

    def test_apply_query_param_filters_ignores_invalid_date_values(self) -> None:
        first_workshop = create_workshop(suffix=4)
        second_workshop = create_workshop(suffix=5)

        filtered = apply_query_param_filters(
            Workshop.objects.all(),
            params=QueryDict("data_inicial=invalid-date&data_final=2026-99-99"),
            filter_configs=(
                QueryParamFilter(param_name="data_inicial", lookup="criado_em__date", kind="date_gte"),
                QueryParamFilter(param_name="data_final", lookup="criado_em__date", kind="date_lte"),
            ),
        )

        self.assertQuerySetEqual(filtered.order_by("pk"), [first_workshop, second_workshop], transform=lambda obj: obj)
