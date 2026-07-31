from __future__ import annotations

from django.template import Context, Template
from django.test import RequestFactory, TestCase, override_settings

from apps.customer.models import Customer
from apps.workshops.models.workshops import Workshop

TABLE_TEMPLATE = """
{% load table_tags %}
{% render_table customers fields table_id='row-id-table' checkbox_name='row_selection' %}
"""


@override_settings(USE_THOUSAND_SEPARATOR=True, LANGUAGE_CODE="pt-br")
class TableRowIdLocalizationTests(TestCase):
    """Row ids feed JS/POST parsing, so they must never be thousand-separated."""

    def setUp(self) -> None:
        self.workshop = Workshop.objects.create(
            name="Oficina Row Id",
            cnpj="51.222.333/0001-01",
            phone="+5511999999999",
            address="Rua Teste, 123",
        )
        self.customer = Customer.objects.create(
            pk=3712,
            workshop=self.workshop,
            name="Cliente Id Grande",
            cpf_or_cnpj="52998224725",
            email="idgrande@example.com",
            phone="+5511988887777",
        )

    def _render(self) -> str:
        from apps.core.templatetags.table_tags import TableColumn

        request = RequestFactory().get("/")
        context = Context(
            {
                "request": request,
                "customers": Customer.objects.filter(pk=self.customer.pk),
                "fields": [TableColumn("Nome", attr="name")],
            }
        )
        return Template(TABLE_TEMPLATE).render(context)

    def test_row_checkbox_uses_raw_primary_key(self) -> None:
        html = self._render()

        self.assertIn('value="3712"', html)
        self.assertIn('data-row-id="3712"', html)
        self.assertNotIn("3.712", html)
