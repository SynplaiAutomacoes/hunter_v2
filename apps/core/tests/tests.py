import calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from django.contrib.auth import get_user_model
from django.db import connection
from django.db.models import F, Func, IntegerField, Value
from django.db.models.functions import Cast, NullIf
from django.template import Context, Template
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from phonenumber_field.phonenumber import PhoneNumber
from djmoney.money import Money

from apps.accounts.models import Account
from apps.budget.models import Budget, BudgetItem, BudgetStatus, BudgetType
from apps.collaborators.models import WorkshopMember
from apps.core.documents.signature import SIGNATURE_POSITION, build_absolute_app_url, normalize_signature_phone_number
from apps.core.templatetags.table_tags import TableColumn, render_table
from apps.finance.models.financial_movement import FinancialMovement
from apps.iam.utils import get_or_create_director_role
from apps.workshops.models.workshop_costs import WorkshopCost, WorkshopCostHoliday
from apps.workshops.models.workshops import Workshop
from apps.workorder.models import WorkOrder, WorkOrderItem, WorkOrderPaymentMethod, WorkOrderSignatureStatus, WorkOrderStatus


def create_workshop(**kwargs):
    data = {
        "name": "Oficina",
        "phone": "+5511999999999",
        "address": "Não informado",
    }
    data.update(kwargs)
    return Workshop.objects.create(**data)


class SignatureHelpersTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_signature_position_matches_current_budget_coordinates(self):
        self.assertEqual(
            SIGNATURE_POSITION,
            {
                "x": 443.0,
                "y": 95.0,
                "width": 120.0,
                "height": 38.0,
            },
        )

    def test_normalize_signature_phone_number_returns_empty_for_blank_values(self):
        self.assertEqual(normalize_signature_phone_number(None), "")
        self.assertEqual(normalize_signature_phone_number(""), "")
        self.assertEqual(normalize_signature_phone_number("   "), "")

    def test_normalize_signature_phone_number_keeps_plus_and_digits(self):
        self.assertEqual(normalize_signature_phone_number("+55 (11) 99888-7777"), "+5511998887777")

    def test_normalize_signature_phone_number_adds_plus_when_missing(self):
        self.assertEqual(normalize_signature_phone_number("(11) 99888-7777"), "+5511998887777")

    def test_normalize_signature_phone_number_uses_e164_from_phone_object(self):
        phone = PhoneNumber.from_string("11989472983", region="BR")

        self.assertEqual(normalize_signature_phone_number(phone), "+5511989472983")

    @override_settings(APP_BASE_URL="https://app.example.com")
    def test_build_absolute_app_url_prefers_request_when_available(self):
        request = self.factory.get("/origem/")

        self.assertEqual(build_absolute_app_url(path="/destino/", request=request), "http://testserver/destino/")

    @override_settings(APP_BASE_URL="https://app.example.com")
    def test_build_absolute_app_url_uses_app_base_url_without_request(self):
        self.assertEqual(build_absolute_app_url(path="/destino/"), "https://app.example.com/destino/")

    @override_settings(APP_BASE_URL="")
    def test_build_absolute_app_url_falls_back_to_localhost(self):
        self.assertEqual(build_absolute_app_url(path="/destino/"), "http://localhost:8000/destino/")


class CrudWrapperTemplateTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_list_page_wrapper_only_syncs_query_params_for_its_own_requests(self):
        request = self.factory.get("/workshops/?q=Oficina&page=2")
        template = Template(
            """
            {% extends 'crud/list_page.html' %}
            {% block crud_title %}Oficinas{% endblock %}
            {% block crud_subtitle %}Subtitulo{% endblock %}
            {% block crud_table %}<div>Conteudo</div>{% endblock %}
            """
        )

        html = template.render(Context({"request": request, "active_workshops": [], "active_workshop_is_director": False}))

        self.assertNotIn('hx-vals="js:{', html)
        self.assertIn("document.currentScript.previousElementSibling", html)
        self.assertIn("wrapper.addEventListener('htmx:configRequest'", html)
        self.assertIn("if (!event.detail || event.detail.elt !== wrapper) return;", html)
        self.assertIn("new URLSearchParams(window.location.search)", html)
        self.assertIn("event.detail.parameters = parameters;", html)

    def test_page_wrapper_renders_clickable_favorite_button_in_navbar(self):
        request = self.factory.get("/workshops/")
        template = Template(
            """
            {% extends 'crud/page.html' %}
            {% block crud_content %}<div>Conteudo</div>{% endblock %}
            """
        )

        html = template.render(
            Context(
                {
                    "request": request,
                    "active_workshops": [],
                    "active_workshop_is_director": False,
                    "navbar_menus": [
                        {"label": "Cadastros", "children": [{"label": "Cliente", "href": "/customer/", "favoritable": True}]},
                        {"label": "Orcamentos", "href": "/budget/", "favoritable": False},
                    ],
                    "navbar_favorites": [{"id": 1, "label": "Cliente", "href": "/customer/"}],
                    "navbar_favorite_urls": {"/customer/"},
                }
            )
        )

        self.assertIn(reverse("core:favorite_page_toggle"), html)
        self.assertIn("favorite-pages-limit-modal", html)
        self.assertIn('x-sort="reorderFavorites()"', html)
        self.assertIn('data-favorite-id="1"', html)
        self.assertIn("Remover Cliente dos favoritos", html)
        self.assertNotIn("Adicionar Orcamentos aos favoritos", html)

    def test_form_page_does_not_render_page_favorite_button_when_present(self):
        request = self.factory.get("/customer/create/")
        template = Template(
            """
            {% extends 'crud/form_page.html' %}
            {% block crud_title %}Criar cliente{% endblock %}
            {% block crud_subtitle %}Cadastro{% endblock %}
            {% block crud_back_url %}/clientes/{% endblock %}
            {% block crud_form %}<div>Formulario</div>{% endblock %}
            """
        )

        html = template.render(
            Context(
                {
                    "request": request,
                    "active_workshops": [],
                    "active_workshop_is_director": False,
                    "page_favorite": {"label": "Criar Cliente", "href": reverse("customer:customer_create"), "favoritable": True},
                    "navbar_favorite_urls": {reverse("customer:customer_create")},
                }
            )
        )

        self.assertNotIn("Remover Criar Cliente dos favoritos", html)

    def test_favoritable_action_link_renders_embedded_star_button(self):
        request = self.factory.get("/customer/")
        template = Template("{% include 'favorites/partials/favoritable_action_link.html' with action_url='/customer/create/' action_label='Criar Cliente' favorite_url='/customer/create/' favorite_label='Criar Cliente' %}")

        html = template.render(Context({"request": request, "navbar_favorite_urls": {"/customer/create/"}}))

        self.assertIn("btn btn-primary pr-11", html)
        self.assertIn(reverse("core:favorite_page_toggle"), html)
        self.assertIn("Remover Criar Cliente dos favoritos", html)

    def test_detail_wrapper_only_syncs_query_params_for_its_own_requests(self):
        request = self.factory.get("/workshops/1/?q=Oficina&page=2")
        template = Template(
            """
            {% extends 'crud/detail.html' %}
            {% block crud_title %}Oficina{% endblock %}
            {% block crud_subtitle %}Detalhes{% endblock %}
            {% block crud_back_url %}/workshops/{% endblock %}
            {% block crud_card_title %}Tabela{% endblock %}
            {% block crud_table %}<div>Conteudo</div>{% endblock %}
            """
        )

        html = template.render(Context({"request": request, "active_workshops": [], "active_workshop_is_director": False}))

        self.assertNotIn('hx-vals="js:{', html)
        self.assertIn("document.currentScript.previousElementSibling", html)
        self.assertIn("wrapper.addEventListener('htmx:configRequest'", html)
        self.assertIn("if (!event.detail || event.detail.elt !== wrapper) return;", html)
        self.assertIn("new URLSearchParams(window.location.search)", html)
        self.assertIn("event.detail.parameters = parameters;", html)


class TestRenderTableTag(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_render_table_supports_sequence_input(self):
        @dataclass(frozen=True)
        class Row:
            name: str

        request = self.factory.get("/workshops/?q=Beta")

        rendered = render_table(
            context={"request": request},
            queryset=[Row(name="Alfa"), Row(name="Beta")],
            fields=[TableColumn(label="Nome", attr="name")],
            table_id="t",
        )

        self.assertEqual(len(rendered["rows"]), 1)
        self.assertEqual(rendered["rows"][0]["cells"][0]["value"], "Beta")

    def test_renders_and_paginates(self):
        for i in range(1, 13):
            create_workshop(name=f"Oficina {i:02d}")

        request = self.factory.get("/workshops/?page=2")
        template = Template(
            """
            {% load table_tags %}
            {% render_table workshops fields table_id='t' %}
            """
        )
        html = template.render(
            Context(
                {
                    "request": request,
                    "workshops": Workshop.objects.all(),
                    "fields": [
                        {"label": "Nome", "attr": "name"},
                        {"label": "Ativa", "attr": "is_active"},
                    ],
                }
            )
        )

        # Página 2 com per_page=10 deve conter apenas os dois últimos itens.
        self.assertIn("Oficina 11", html)
        self.assertIn("Oficina 12", html)
        self.assertNotIn("Oficina 01", html)
        self.assertIn("Página 2 de", html)
        self.assertIn('id="t"', html)

    def test_sorts_desc_by_name(self):
        create_workshop(name="Oficina 01")
        create_workshop(name="Oficina 02")
        create_workshop(name="Oficina 03")

        request = self.factory.get("/workshops/?sort=-name")
        template = Template(
            """
            {% load table_tags %}
            {% render_table workshops fields table_id='t' per_page=10 %}
            """
        )
        html = template.render(
            Context(
                {
                    "request": request,
                    "workshops": Workshop.objects.all(),
                    "fields": [
                        {"label": "Nome", "attr": "name"},
                    ],
                }
            )
        )

        # Checa ordem pela primeira ocorrência no HTML.
        self.assertLess(html.find("Oficina 03"), html.find("Oficina 01"))
        # Deve renderizar controles de seleção.
        self.assertIn("Selecionar todos", html)

    def test_boolean_cells_render_as_sim_nao_with_badges(self):
        create_workshop(name="Oficina 01", is_active=True)
        create_workshop(name="Oficina 02", is_active=False)

        request = self.factory.get("/workshops/")
        template = Template(
            """
            {% load table_tags %}
            {% render_table workshops fields table_id='t' per_page=10 %}
            """
        )
        html = template.render(
            Context(
                {
                    "request": request,
                    "workshops": Workshop.objects.all(),
                    "fields": [
                        {"label": "Nome", "attr": "name"},
                        {"label": "Ativa", "attr": "is_active"},
                    ],
                }
            )
        )

        self.assertIn("badge-success", html)
        self.assertIn(">Sim<", html)
        self.assertIn("badge-error", html)
        self.assertIn(">Não<", html)

        # Não deve renderizar o literal Python dentro do <td>.
        self.assertNotIn(">True</td>", html)
        self.assertNotIn(">False</td>", html)

    def test_can_render_cell_with_frontend_format_hint(self):
        create_workshop(name="Oficina 01", cnpj="11.222.333/0001-81")

        request = self.factory.get("/workshops/")
        template = Template(
            """
            {% load table_tags %}
            {% render_table workshops fields table_id='t' per_page=10 %}
            """
        )
        html = template.render(
            Context(
                {
                    "request": request,
                    "workshops": Workshop.objects.all(),
                    "fields": [
                        {"label": "CNPJ", "attr": "cnpj", "format": "cnpj"},
                    ],
                }
            )
        )

        # A célula deve carregar o hint via data-attribute para o JS aplicar a máscara.
        self.assertIn('data-hf="cnpj"', html)

    def test_custom_cell_template_renders_preview_and_mobile_stack_layout(self):
        @dataclass(frozen=True)
        class ApplicationItem:
            title: str
            subtitle: str = ""

        @dataclass(frozen=True)
        class ApplicationValue:
            visible_items: list[ApplicationItem]
            hidden_items: list[ApplicationItem]
            hidden_count: int
            empty_label: str = "Sem aplicação cadastrada"

        @dataclass(frozen=True)
        class Row:
            applications: ApplicationValue

        request = self.factory.get("/workshops/")
        template = Template(
            """
            {% load table_tags %}
            {% render_table rows fields table_id='t' per_page=10 %}
            """
        )
        html = template.render(
            Context(
                {
                    "request": request,
                    "rows": [
                        Row(
                            applications=ApplicationValue(
                                visible_items=[
                                    ApplicationItem(title="Jeep Renegade", subtitle="2.0 Diesel | 2015 a 2021"),
                                    ApplicationItem(title="Fiat Toro", subtitle="2.0 Diesel | 2016 a 2022"),
                                ],
                                hidden_items=[ApplicationItem(title="Ram Rampage", subtitle="2.0 Diesel | 2024")],
                                hidden_count=1,
                            )
                        )
                    ],
                    "fields": [
                        TableColumn(label="Aplicações", attr="applications", cell_template="kits/partials/applications_cell.html", mobile_stack=True),
                    ],
                }
            )
        )

        self.assertIn("Jeep Renegade", html)
        self.assertIn("2.0 Diesel | 2015 a 2021", html)
        self.assertIn("Fiat Toro", html)
        self.assertIn("2.0 Diesel | 2016 a 2022", html)
        self.assertIn("Ram Rampage", html)
        self.assertIn("2.0 Diesel | 2024", html)
        self.assertIn("Ver mais", html)
        self.assertIn("Ver menos", html)
        self.assertIn("+1", html)
        self.assertIn('x-show="open"', html)
        self.assertIn("flex-col items-start", html)
        self.assertIn("w-full text-left", html)
        self.assertLess(html.find("Ram Rampage"), html.find("Ver menos"))

    def test_formatted_cell_with_none_renders_literal_none_and_no_hint(self):
        create_workshop(name="Oficina 01", cnpj=None)

        request = self.factory.get("/workshops/")
        template = Template(
            """
            {% load table_tags %}
            {% render_table workshops fields table_id='t' per_page=10 %}
            """
        )
        html = template.render(
            Context(
                {
                    "request": request,
                    "workshops": Workshop.objects.all(),
                    "fields": [
                        {"label": "CNPJ", "attr": "cnpj", "format": "cnpj"},
                    ],
                }
            )
        )

        compact_html = "".join(html.split())

        # Quando o valor é None, deve mostrar literalmente 'None' (não vazio) e não aplicar data-hf.
        self.assertIn(">None</", compact_html)
        self.assertNotIn('data-hf="cnpj"', compact_html)

    def test_action_column_renders_with_edit_and_delete_links(self):
        w = create_workshop(name="Oficina 01", is_active=True)

        request = self.factory.get("/workshops/")
        template = Template(
            """
            {% load table_tags %}
            {% render_table workshops fields actions=actions table_id='t' per_page=10 %}
            """
        )
        html = template.render(
            Context(
                {
                    "request": request,
                    "workshops": Workshop.objects.all(),
                    "fields": [
                        {"label": "Nome", "attr": "name"},
                        {"label": "Ativa", "attr": "is_active"},
                    ],
                    "actions": [
                        {"kind": "edit", "url_name": "workshops:update"},
                        {"kind": "delete", "url_name": "workshops:delete"},
                    ],
                }
            )
        )

        # Header deve incluir coluna de ações ao final.
        self.assertIn(">Ações<", html)
        self.assertLess(html.find(">Ativa<"), html.find(">Ações<"))

        self.assertIn(f'href="/workshops/{w.pk}/edit/"', html)
        self.assertIn(f'href="/workshops/{w.pk}/delete/"', html)

    def test_empty_state_colspan_includes_actions(self):
        request = self.factory.get("/workshops/")
        template = Template(
            """
            {% load table_tags %}
            {% render_table workshops fields actions=actions table_id='t' per_page=10 %}
            """
        )
        html = template.render(
            Context(
                {
                    "request": request,
                    "workshops": Workshop.objects.none(),
                    "fields": [
                        {"label": "Nome", "attr": "name"},
                    ],
                    "actions": [
                        {"kind": "edit", "url_name": "workshops:update"},
                    ],
                }
            )
        )

        # colunas: checkbox (1) + Nome (1) + Ações (1) = 3
        self.assertIn('colspan="3"', html)

    def test_third_click_clears_sort(self):
        # Não criar paginação (mantém apenas o link do cabeçalho como hx-get no HTML).
        create_workshop(name="Oficina 01")
        create_workshop(name="Oficina 02")
        create_workshop(name="Oficina 03")

        request = self.factory.get("/workshops/?sort=-name")
        template = Template(
            """
            {% load table_tags %}
            {% render_table workshops fields table_id='t' per_page=10 %}
            """
        )
        html = template.render(
            Context(
                {
                    "request": request,
                    "workshops": Workshop.objects.all(),
                    "fields": [
                        {"label": "Nome", "attr": "name"},
                    ],
                }
            )
        )

        # Quando já está em desc, o próximo clique deve remover o parâmetro `sort`.
        self.assertIn('hx-get="/workshops/?page=1"', html)
        # Deve indicar visualmente que está ordenado desc no estado atual.
        self.assertIn("▼", html)

    def test_search_filters_rows(self):
        create_workshop(name="Alpha", cnpj="10.000.000/0001-01")
        create_workshop(name="Beta", cnpj="10.000.000/0001-02")

        request = self.factory.get("/workshops/?q=Alp")
        template = Template(
            """
            {% load table_tags %}
            {% render_table workshops fields table_id='t' per_page=10 %}
            """
        )
        html = template.render(
            Context(
                {
                    "request": request,
                    "workshops": Workshop.objects.all(),
                    "fields": [
                        {"label": "Nome", "attr": "name"},
                    ],
                }
            )
        )

        self.assertIn("Alpha", html)
        self.assertNotIn("Beta", html)
        self.assertIn('name="q"', html)
        self.assertIn('id="t-search"', html)
        self.assertIn('value="Alp"', html)
        self.assertIn('type="submit"', html)
        self.assertIn("Buscar", html)
        self.assertIn('action="/workshops/"', html)
        self.assertIn('method="get"', html)
        self.assertIn('hx-trigger="submit, change from:#t-sort-ui"', html)
        self.assertIn('hx-disinherit="hx-vals"', html)
        self.assertIn('hx-vals="{}"', html)
        self.assertNotIn("keyup changed delay:500ms", html)
        self.assertIn("input.addEventListener('input'", html)
        self.assertIn("let hadSearchValue = input.value.trim() !== ''", html)
        self.assertIn("form.requestSubmit()", html)
        self.assertNotIn("window.htmx.trigger(form, 'submit')", html)

    def test_search_ignores_invalid_related_lookup_and_keeps_valid_columns(self):
        create_workshop(name="Alpha", cnpj="10.000.000/0001-01")
        create_workshop(name="Beta", cnpj="10.000.000/0001-02")

        request = self.factory.get("/workshops/?q=Alpha")
        template = Template(
            """
            {% load table_tags %}
            {% render_table workshops fields table_id='t' per_page=10 %}
            """
        )
        html = template.render(
            Context(
                {
                    "request": request,
                    "workshops": Workshop.objects.all(),
                    "fields": [
                        TableColumn(label="Nome", attr="name"),
                        TableColumn(label="Conta", attr="account"),
                    ],
                }
            )
        )

        self.assertIn("Alpha", html)
        self.assertNotIn("Beta", html)

    def test_search_supports_callable_display_with_multiple_search_by_lookups(self):
        create_workshop(name="Alpha", address="Rua Central", cnpj="10.000.000/0001-03")
        create_workshop(name="Beta", address="Avenida Industrial", cnpj="10.000.000/0001-04")

        request = self.factory.get("/workshops/?q=industrial")
        template = Template(
            """
            {% load table_tags %}
            {% render_table workshops fields table_id='t' per_page=10 %}
            """
        )
        html = template.render(
            Context(
                {
                    "request": request,
                    "workshops": Workshop.objects.all(),
                    "fields": [
                        TableColumn(label="Resumo", attr=lambda workshop: f"{workshop.name} - {workshop.address}", search_by=("name", "address")),
                    ],
                }
            )
        )

        self.assertIn("Beta - Avenida Industrial", html)
        self.assertNotIn("Alpha - Rua Central", html)

    def test_search_filters_queryset_rows_without_accents_and_case(self):
        create_workshop(name="Sao Bento", cnpj="10.000.000/0001-05")
        create_workshop(name="Alpha", cnpj="10.000.000/0001-06")

        request = self.factory.get("/workshops/?q=SÃO")
        template = Template(
            """
            {% load table_tags %}
            {% render_table workshops fields table_id='t' per_page=10 %}
            """
        )
        html = template.render(
            Context(
                {
                    "request": request,
                    "workshops": Workshop.objects.all(),
                    "fields": [
                        TableColumn(label="Nome", attr="name"),
                    ],
                }
            )
        )

        self.assertIn("Sao Bento", html)
        self.assertNotIn("Alpha", html)

    def test_search_filters_sequence_rows_without_accents_and_case(self):
        create_workshop(name="Sao Bento", cnpj="10.000.000/0001-07")
        create_workshop(name="Alpha", cnpj="10.000.000/0001-08")

        request = self.factory.get("/workshops/?q=são")
        template = Template(
            """
            {% load table_tags %}
            {% render_table workshops fields table_id='t' per_page=10 %}
            """
        )
        html = template.render(
            Context(
                {
                    "request": request,
                    "workshops": list(Workshop.objects.order_by("pk")),
                    "fields": [
                        TableColumn(label="Nome", attr="name"),
                    ],
                }
            )
        )

        self.assertIn("Sao Bento", html)
        self.assertNotIn("Alpha", html)

    def test_search_query_is_kept_in_pagination_links(self):
        for i in range(1, 26):
            create_workshop(name=f"Oficina {i:02d}")

        request = self.factory.get("/workshops/?q=Oficina&page=2")
        template = Template(
            """
            {% load table_tags %}
            {% render_table workshops fields table_id='t' per_page=10 %}
            """
        )
        html = template.render(
            Context(
                {
                    "request": request,
                    "workshops": Workshop.objects.all(),
                    "fields": [
                        {"label": "Nome", "attr": "name"},
                    ],
                }
            )
        )

        compact_html = "".join(html.split())

        # O input deve manter o valor atual.
        self.assertIn('name="q"', compact_html)
        self.assertIn('value="Oficina"', compact_html)

        # Links HTMX de paginação devem preservar o filtro.
        self.assertTrue(
            'hx-get="/workshops/?q=Oficina&amp;page=1"' in compact_html or 'hx-get="/workshops/?page=1&amp;q=Oficina"' in compact_html,
            compact_html,
        )
        self.assertTrue(
            'hx-get="/workshops/?q=Oficina&amp;page=3"' in compact_html or 'hx-get="/workshops/?page=3&amp;q=Oficina"' in compact_html,
            compact_html,
        )

    def test_filter_clear_button_is_not_rendered_without_active_filter_params(self):
        request = self.factory.get("/workshops/?q=Oficina")
        template = Template(
            """
            {% load table_tags %}
            {% render_table workshops fields table_id='t' per_page=10 filter_fields_template='tables/partials/_pagination.html' filter_param_names='city,state' %}
            """
        )
        html = template.render(
            Context(
                {
                    "request": request,
                    "workshops": Workshop.objects.none(),
                    "fields": [TableColumn(label="Nome", attr="name")],
                }
            )
        )

        self.assertNotIn("Limpar Filtro", html)

    def test_filter_clear_button_is_rendered_with_active_filter_params(self):
        request = self.factory.get("/workshops/?q=Oficina&city=Campinas")
        template = Template(
            """
            {% load table_tags %}
            {% render_table workshops fields table_id='t' per_page=10 filter_fields_template='tables/partials/_pagination.html' filter_param_names='city,state' %}
            """
        )
        html = template.render(
            Context(
                {
                    "request": request,
                    "workshops": Workshop.objects.none(),
                    "fields": [TableColumn(label="Nome", attr="name")],
                }
            )
        )

        self.assertIn("Limpar Filtro", html)
        self.assertIn("btn btn-error", html)
        self.assertIn('hx-params="none"', html)

    def test_filter_modal_uses_native_submit_flow(self):
        request = self.factory.get("/workshops/?q=Oficina")
        template = Template(
            """
            {% load table_tags %}
            {% render_table workshops fields table_id='t' per_page=10 filter_fields_template='tables/partials/_pagination.html' filter_param_names='city,state' %}
            """
        )
        html = template.render(
            Context(
                {
                    "request": request,
                    "workshops": Workshop.objects.none(),
                    "fields": [TableColumn(label="Nome", attr="name")],
                }
            )
        )

        self.assertIn('id="t-controls-form"', html)
        self.assertIn('type="submit"', html)
        self.assertIn('id="t"', html)
        self.assertIn('id="t-content"', html)
        self.assertIn('hx-disinherit="hx-vals"', html)
        self.assertIn('@htmx:after-swap.window="syncMasterCheckbox()"', html)
        self.assertNotIn("@htmx:afterSwap.window", html)
        self.assertIn('@htmx:before-request.window="if ($event.detail && $event.detail.elt && $event.detail.elt.id === controlsFormId && $refs.filterModal?.open) $refs.filterModal.close()"', html)
        self.assertNotIn("@htmx:beforeRequest.window", html)
        self.assertIn('id="t-filter-modal"', html)
        self.assertIn('class="modal"', html)
        self.assertIn('aria-controls="t-filter-modal"', html)
        self.assertIn('aria-haspopup="dialog"', html)
        self.assertIn('@click="$refs.filterModal.showModal()"', html)
        self.assertIn('x-ref="filterModal"', html)
        self.assertIn("modal-box w-11/12 max-w-2xl", html)
        self.assertIn("max-h-[65vh]", html)
        self.assertNotIn("@submit.window", html)

    def test_filter_overlay_template_receives_parent_context_variables(self):
        request = self.factory.get("/workshops/")
        template = Template(
            """
            {% load table_tags %}
            {% render_table workshops fields table_id='t' per_page=10 filter_fields_template='budget/partials/budget_filters_fields.html' filter_param_names='status' %}
            """
        )
        html = template.render(
            Context(
                {
                    "request": request,
                    "workshops": Workshop.objects.none(),
                    "fields": [TableColumn(label="Nome", attr="name")],
                    "status_choices": [
                        ("draft", "Aprovado"),
                        ("approved", "Veículo Entregue"),
                    ],
                }
            )
        )

        self.assertIn('value="draft"', html)
        self.assertIn("Aprovado", html)
        self.assertIn('value="approved"', html)
        self.assertIn("Veículo Entregue", html)

    def test_render_table_can_render_summary_template_inside_table_content(self):
        for i in range(1, 13):
            create_workshop(name=f"Oficina {i:02d}", cnpj=f"11.222.333/0001-{i:02d}")

        request = self.factory.get("/workshops/")
        template = Template(
            """
            {% load table_tags %}
            {% render_table workshops fields table_id='t' per_page=10 summary_template='tables/partials/_pagination.html' %}
            """
        )
        html = template.render(
            Context(
                {
                    "request": request,
                    "workshops": Workshop.objects.all(),
                    "fields": [TableColumn(label="Nome", attr="name")],
                }
            )
        )

        pagination_marker = 'class="flex items-center justify-between gap-3 pt-4"'
        self.assertEqual(html.count(pagination_marker), 2)
        self.assertLess(html.find(pagination_marker), html.find('id="t-controls-form"'))

    def test_render_table_can_render_footer_template_inside_table_content(self):
        for i in range(1, 13):
            create_workshop(name=f"Oficina Rodape {i:02d}", cnpj=f"22.333.444/0001-{i:02d}")

        request = self.factory.get("/workshops/")
        template = Template(
            """
            {% load table_tags %}
            {% render_table workshops fields table_id='t' per_page=10 footer_template='tables/partials/_pagination.html' %}
            """
        )
        html = template.render(
            Context(
                {
                    "request": request,
                    "workshops": Workshop.objects.all(),
                    "fields": [TableColumn(label="Nome", attr="name")],
                }
            )
        )

        pagination_marker = 'class="flex items-center justify-between gap-3 pt-4"'
        self.assertEqual(html.count(pagination_marker), 2)
        self.assertGreater(html.rfind(pagination_marker), html.find(pagination_marker))

    def test_render_table_can_render_controls_actions_template_inside_controls_row(self):
        for i in range(1, 13):
            create_workshop(name=f"Oficina Acoes {i:02d}", cnpj=f"33.444.555/0001-{i:02d}")

        request = self.factory.get("/workshops/")
        template = Template(
            """
            {% load table_tags %}
            {% render_table workshops fields table_id='t' per_page=10 filter_fields_template='budget/partials/budget_filters_fields.html' filter_button_label='Filtros' filter_param_names='status' controls_actions_template='tables/partials/_pagination.html' %}
            """
        )
        html = template.render(
            Context(
                {
                    "request": request,
                    "workshops": Workshop.objects.all(),
                    "fields": [TableColumn(label="Nome", attr="name")],
                    "status_choices": [
                        ("draft", "Aprovado"),
                        ("approved", "Veículo Entregue"),
                    ],
                }
            )
        )

        pagination_marker = 'class="flex items-center justify-between gap-3 pt-4"'
        first_pagination_index = html.find(pagination_marker)

        self.assertEqual(html.count(pagination_marker), 2)
        self.assertIn('aria-controls="t-filter-modal"', html)
        self.assertLess(html.find('aria-controls="t-filter-modal"'), first_pagination_index)
        self.assertLess(first_pagination_index, html.find("</form>"))

    def test_render_table_clear_filter_url_removes_only_filter_params(self):
        request = self.factory.get("/workshops/?q=Oficina&sort=name&page=3&city=Campinas&state=SP")

        rendered = render_table(
            context={"request": request},
            queryset=Workshop.objects.none(),
            fields=[TableColumn(label="Nome", attr="name")],
            table_id="t",
            filter_fields_template="tables/partials/_pagination.html",
            filter_param_names="city,state",
        )

        self.assertTrue(rendered["has_active_filters"])

        clear_filter_url = rendered["clear_filter_url"] or ""
        self.assertIn("q=Oficina", clear_filter_url)
        self.assertIn("sort=name", clear_filter_url)
        self.assertIn("page=1", clear_filter_url)
        self.assertNotIn("city=", clear_filter_url)
        self.assertNotIn("state=", clear_filter_url)

    def test_render_table_defaults_hierarchical_selection_to_false(self):
        request = self.factory.get("/workshops/")

        rendered = render_table(
            context={"request": request},
            queryset=Workshop.objects.none(),
            fields=[TableColumn(label="Nome", attr="name")],
            table_id="t",
        )

        self.assertFalse(rendered["hierarchical_selection"])

    def test_render_table_can_enable_hierarchical_selection(self):
        request = self.factory.get("/workshops/")

        rendered = render_table(
            context={"request": request},
            queryset=Workshop.objects.none(),
            fields=[TableColumn(label="Nome", attr="name")],
            table_id="t",
            hierarchical_selection=True,
        )

        self.assertTrue(rendered["hierarchical_selection"])

    def test_renders_mobile_cards_container(self):
        create_workshop(name="Oficina 01", is_active=True)

        request = self.factory.get("/workshops/")
        template = Template(
            """
            {% load table_tags %}
            {% render_table workshops fields table_id='t' per_page=10 %}
            """
        )
        html = template.render(
            Context(
                {
                    "request": request,
                    "workshops": Workshop.objects.all(),
                    "fields": [
                        {"label": "Nome", "attr": "name"},
                        {"label": "Ativa", "attr": "is_active"},
                    ],
                }
            )
        )

        # Container de cards (mobile)
        self.assertIn('class="md:hidden space-y-3"', html)
        # Card básico
        self.assertIn('class="card', html)

    def test_can_highlight_rows_from_context(self):
        highlighted_workshop = create_workshop(name="Oficina destaque", is_active=True, cnpj="11.111.111/0001-11")
        create_workshop(name="Oficina normal", is_active=True, cnpj="22.222.222/0001-22")

        request = self.factory.get("/workshops/")
        template = Template(
            """
            {% load table_tags %}
            {% render_table workshops fields table_id='t' per_page=10 %}
            """
        )
        html = template.render(
            Context(
                {
                    "request": request,
                    "workshops": Workshop.objects.order_by("pk"),
                    "fields": [
                        {"label": "Nome", "attr": "name"},
                    ],
                    "highlighted_row_ids": [highlighted_workshop.pk],
                }
            )
        )

        self.assertEqual(html.count("bg-success/10 hover:bg-success/20 transition-colors"), 1)
        self.assertEqual(html.count("border-success/30 bg-success/10"), 1)

    def test_renders_mobile_sort_dropdown_and_hidden_sort_input(self):
        create_workshop(name="Oficina 01", is_active=True)

        request = self.factory.get("/workshops/")
        template = Template(
            """
            {% load table_tags %}
            {% render_table workshops fields table_id='t' per_page=10 %}
            """
        )
        html = template.render(
            Context(
                {
                    "request": request,
                    "workshops": Workshop.objects.all(),
                    "fields": [
                        {"label": "Nome", "attr": "name"},
                    ],
                }
            )
        )

        # Dropdown (mobile) de ordenação.
        self.assertIn('id="t-sort-ui"', html)
        self.assertIn('name="sort"', html)
        # Deve oferecer opção asc/desc para a coluna.
        self.assertIn('value="name"', html)
        self.assertIn('value="-name"', html)

    def test_numeric_sort_by_name_with_custom_sort_by_expression(self):
        # REGEXP_REPLACE é específico do PostgreSQL; em outros bancos esse teste não se aplica.
        if connection.vendor != "postgresql":
            self.skipTest("Ordenação numérica via REGEXP_REPLACE é suportada apenas no PostgreSQL.")

        # Mistura valores numéricos (como strings) e nomes com prefixo.
        for name in ["10", "11", "4", "5", "6", "7", "8", "9", "Oficina 1", "Oficina 2", "Oficina 3"]:
            create_workshop(name=name)

        digits_only = Func(F("name"), Value(r"\D"), Value(""), Value("g"), function="REGEXP_REPLACE")
        numeric_name = Cast(NullIf(digits_only, Value("")), IntegerField())

        request = self.factory.get("/workshops/?sort=name&page=1")
        template = Template(
            """
            {% load table_tags %}
            {% render_table workshops fields table_id='t' per_page=10 %}
            """
        )
        html = template.render(
            Context(
                {
                    "request": request,
                    "workshops": Workshop.objects.all(),
                    "fields": [
                        {"label": "Nome", "attr": "name", "sort_by": [numeric_name, "name"]},
                    ],
                }
            )
        )

        # O template pode introduzir whitespace/novas linhas; normalize para asserts estáveis.
        compact_html = "".join(html.split())

        # Com sort numérico asc e per_page=10, o item "11" deve ficar na página 2.
        self.assertNotIn(">11</td>", compact_html)
        self.assertIn(">10</td>", compact_html)

        # Ordem esperada (numérica): 1,2,3,4,...,10.
        self.assertLess(compact_html.find("Oficina1"), compact_html.find(">4</td>"))
        self.assertLess(compact_html.find(">4</td>"), compact_html.find(">10</td>"))

    def test_delete_action_can_render_htmx_attributes_and_has_no_default_js_confirm(self):
        w = create_workshop(name="Oficina 01", is_active=True)

        request = self.factory.get("/workshops/")
        template = Template(
            """
            {% load table_tags %}
            {% render_table workshops fields actions=actions table_id='t' per_page=10 %}
            """
        )
        html = template.render(
            Context(
                {
                    "request": request,
                    "workshops": Workshop.objects.all(),
                    "fields": [
                        {"label": "Nome", "attr": "name"},
                    ],
                    "actions": [
                        {"kind": "delete", "url_name": "workshops:delete", "hx_target": "#modal-container", "hx_swap": "innerHTML", "hx_push_url": "false"},
                    ],
                }
            )
        )

        # Deve usar HTMX para abrir o modal (sem navegar) e NÃO deve ter confirm() por default.
        self.assertIn('hx-target="#modal-container"', html)
        self.assertIn(f'hx-get="/workshops/{w.pk}/delete/"', html)
        self.assertNotIn('onclick="return confirm(', html)

    def test_workshop_delete_view_htmx_get_renders_modal_and_post_triggers_refresh(self):
        w = create_workshop(name="Oficina 01", is_active=True)

        User = get_user_model()
        user = User.objects.create(username="u", cpf="11144477735")
        user.set_password("p")
        user.save(update_fields=["password"])
        self.client.force_login(user)

        url = reverse("workshops:delete", args=[w.pk])

        resp_get = self.client.get(url, HTTP_HX_REQUEST="true")
        self.assertEqual(resp_get.status_code, 200)
        self.assertIn('class="modal"', resp_get.content.decode("utf-8"))
        self.assertIn("Confirmar exclusão", resp_get.content.decode("utf-8"))

        resp_post = self.client.post(url, HTTP_HX_REQUEST="true")
        self.assertEqual(resp_post.status_code, 200)
        self.assertEqual(resp_post.get("HX-Trigger"), "workshops-table-refresh")
        self.assertFalse(Workshop.objects.filter(pk=w.pk).exists())


class DashboardMetricsTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.user = self.user_model.objects.create(username="dashboard-user", cpf="11144477735")
        self.user.set_password("123")
        self.user.save(update_fields=["password"])
        self.account = Account.objects.create(name="Conta Dashboard", owner=self.user)
        self.user = self.user_model.objects.get(pk=self.user.pk)
        typed_user_any: Any = self.user
        setattr(typed_user_any, "account", self.account)
        setattr(typed_user_any, "is_account_owner", True)
        self.user.save(update_fields=["account", "is_account_owner"])

        self.workshop = Workshop.objects.create(
            account=self.account,
            name="Oficina Dashboard",
            cnpj="11.222.333/0001-99",
            phone="+5511999999999",
            address="Rua Dashboard, 123",
        )
        director_role = get_or_create_director_role(account=self.account, with_all_permissions=True)
        WorkshopMember.objects.create(user=self.user, workshop=self.workshop, role=director_role, is_active=True)

        self.client.force_login(self.user)
        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

    def _create_budget(self, *, status: str, amount: str, entry_date) -> Budget:
        budget = Budget.objects.create(workshop=self.workshop, entry_date=entry_date, status=status)
        BudgetItem.objects.create(
            workshop=self.workshop,
            budget=budget,
            is_local=True,
            description=f"Item {status}",
            quantity=1,
            service_selling_price=Money(amount, "BRL"),
        )
        return budget

    def _create_workorder_receivable(
        self,
        *,
        workshop: Workshop,
        workorder_status: str,
        amount: str,
        due_date,
        is_paid: bool = False,
    ) -> WorkOrder:
        budget = Budget.objects.create(workshop=workshop, entry_date=due_date)
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget, status=workorder_status)
        WorkOrderItem.objects.create(
            workshop=workshop,
            workorder=workorder,
            description=f"Item OS {amount}",
            quantity=1,
            service_selling_price=Money(amount, "BRL"),
        )
        WorkOrder.objects.filter(pk=workorder.pk).update(
            criado_em=timezone.make_aware(datetime.combine(due_date, datetime.min.time())),
        )
        FinancialMovement.objects.create(
            workshop=workshop,
            workorder=workorder,
            direction=FinancialMovement.MovementDirection.CREDIT,
            amount=Money(amount, "BRL"),
            due_date=due_date,
            is_paid=is_paid,
        )
        return workorder

    def _create_workorder_payment(
        self,
        *,
        workshop: Workshop,
        amount: str,
        due_date,
        workorder: WorkOrder | None = None,
    ) -> WorkOrderPaymentMethod:
        if workorder is None:
            budget = Budget.objects.create(workshop=workshop, entry_date=due_date)
            workorder = WorkOrder.objects.create(workshop=workshop, budget=budget, status=WorkOrderStatus.DRAFT)

        return WorkOrderPaymentMethod.objects.create(
            workorder=workorder,
            first_installment_amount=Money(amount, "BRL"),
            remaining_installments_amount=Money("0.00", "BRL"),
            installments_count=1,
            due_date=due_date,
        )

    def _create_workshop_cost(self, *, reference_date: date, work_days_per_month: int, holiday_dates: list[date] | None = None) -> WorkshopCost:
        workshop_cost = WorkshopCost.objects.create(
            workshop=self.workshop,
            month=reference_date.month,
            year=reference_date.year,
            mechanic_quantity=1,
            work_days_per_month=work_days_per_month,
        )
        for holiday_date in holiday_dates or []:
            WorkshopCostHoliday.objects.create(workshop_cost=workshop_cost, date=holiday_date)
        return workshop_cost

    def _count_business_days(self, *, start_date: date, end_date: date, holiday_dates: set[date] | None = None) -> int:
        if end_date < start_date:
            return 0

        excluded_holidays = holiday_dates or set()
        return sum(1 for day in range(start_date.day, end_date.day + 1) if (current_date := date(start_date.year, start_date.month, day)).weekday() < 5 and current_date not in excluded_holidays)

    def test_dashboard_counts_open_budgets_from_all_open_statuses_even_from_previous_months(self):
        today = timezone.localdate()
        previous_month_date = today - timedelta(days=40)

        included_statuses = (
            BudgetStatus.DRAFT,
            BudgetStatus.WAITING_CLIENT,
            BudgetStatus.WAITING_DIAGNOSIS,
            BudgetStatus.WAITING_ITEMS,
            BudgetStatus.WAITING_PRICING,
            BudgetStatus.WAITING_REVIEW,
            BudgetStatus.WAITING_APPROVAL,
        )
        included_amounts = ["10.00", "20.00", "30.00", "40.00", "50.00", "60.00", "70.00"]

        for index, status in enumerate(included_statuses):
            entry_date = previous_month_date if index == 0 else today
            self._create_budget(status=status, amount=included_amounts[index], entry_date=entry_date)

        self._create_budget(status=BudgetStatus.APPROVED, amount="100.00", entry_date=today)
        self._create_budget(status=BudgetStatus.REJECTED, amount="200.00", entry_date=today)
        self._create_budget(status=BudgetStatus.CANCELLED, amount="300.00", entry_date=previous_month_date)

        response = self.client.get(reverse("core:dashboard"), {"mes": today.month, "ano": today.year})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_orcamentos_aguardando_aprovacao"], 280)
        self.assertContains(response, "R$ 280,00")

    def test_dashboard_counts_rejected_budgets_from_selected_month(self):
        today = timezone.localdate()
        previous_month_date = today - timedelta(days=40)

        self._create_budget(status=BudgetStatus.REJECTED, amount="200.00", entry_date=today)
        self._create_budget(status=BudgetStatus.REJECTED, amount="300.00", entry_date=previous_month_date)

        other_workshop = Workshop.objects.create(
            account=self.account,
            name="Oficina Externa Reprovados",
            cnpj="11.222.333/0001-66",
            phone="+5511666666666",
            address="Rua Externa, 321",
        )
        other_budget = Budget.objects.create(workshop=other_workshop, entry_date=today, status=BudgetStatus.REJECTED)
        BudgetItem.objects.create(
            workshop=other_workshop,
            budget=other_budget,
            is_local=True,
            description="Item externo reprovado",
            quantity=1,
            service_selling_price=Money("500.00", "BRL"),
        )

        response = self.client.get(reverse("core:dashboard"), {"mes": today.month, "ano": today.year})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_orcamentos_reprovados"], Decimal("200.00"))
        self.assertContains(response, "R$ 200,00")

    def test_dashboard_counts_legacy_rejected_status_values(self):
        today = timezone.localdate()

        self._create_budget(status="reprovado", amount="75.00", entry_date=today)
        self._create_budget(status="reproved", amount="25.00", entry_date=today)

        response = self.client.get(reverse("core:dashboard"), {"mes": today.month, "ano": today.year})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_orcamentos_reprovados"], Decimal("100.00"))

    def test_dashboard_counts_only_pending_values_from_draft_workorders_in_execution(self):
        today = timezone.localdate()
        previous_month_date = today - timedelta(days=40)

        previous_month_workorder = self._create_workorder_receivable(
            workshop=self.workshop,
            workorder_status=WorkOrderStatus.DRAFT,
            amount="1000.00",
            due_date=previous_month_date,
        )
        self._create_workorder_payment(
            workshop=self.workshop,
            amount="500.00",
            due_date=previous_month_date,
            workorder=previous_month_workorder,
        )

        self._create_workorder_receivable(
            workshop=self.workshop,
            workorder_status=WorkOrderStatus.DRAFT,
            amount="300.00",
            due_date=today,
        )

        fully_paid_workorder = self._create_workorder_receivable(
            workshop=self.workshop,
            workorder_status=WorkOrderStatus.DRAFT,
            amount="200.00",
            due_date=today,
        )
        self._create_workorder_payment(
            workshop=self.workshop,
            amount="200.00",
            due_date=today,
            workorder=fully_paid_workorder,
        )

        self._create_workorder_receivable(
            workshop=self.workshop,
            workorder_status=WorkOrderStatus.APPROVED,
            amount="999.00",
            due_date=today,
        )

        other_workshop = Workshop.objects.create(
            account=self.account,
            name="Oficina Externa Dashboard",
            cnpj="11.222.333/0001-88",
            phone="+5511888888888",
            address="Rua Externa, 456",
        )
        self._create_workorder_receivable(
            workshop=other_workshop,
            workorder_status=WorkOrderStatus.DRAFT,
            amount="500.00",
            due_date=today,
        )

        response = self.client.get(reverse("core:dashboard"), {"mes": today.month, "ano": today.year})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_os_a_receber_em_execucao"], Decimal("800.00"))
        self.assertEqual(response.context["total_mensal_os_a_receber_em_execucao"], Decimal("300.00"))
        self.assertEqual(response.context["total_meses_anteriores_os_a_receber_em_execucao"], Decimal("500.00"))
        self.assertContains(response, "R$ 800,00")

    def test_dashboard_total_vendido_sums_workorder_payment_plans_for_selected_month(self):
        today = timezone.localdate()
        previous_month_date = today - timedelta(days=40)

        self._create_workorder_payment(
            workshop=self.workshop,
            amount="100.00",
            due_date=today,
        )
        budget = Budget.objects.create(workshop=self.workshop, entry_date=today)
        workorder = WorkOrder.objects.create(workshop=self.workshop, budget=budget, status=WorkOrderStatus.DRAFT)
        WorkOrderPaymentMethod.objects.create(
            workorder=workorder,
            first_installment_amount=Money("50.00", "BRL"),
            remaining_installments_amount=Money("25.00", "BRL"),
            installments_count=3,
            due_date=today,
        )
        self._create_workorder_payment(
            workshop=self.workshop,
            amount="40.00",
            due_date=previous_month_date,
        )

        other_workshop = Workshop.objects.create(
            account=self.account,
            name="Oficina Externa Pagamentos",
            cnpj="11.222.333/0001-77",
            phone="+5511777777777",
            address="Rua Externa, 789",
        )
        self._create_workorder_payment(
            workshop=other_workshop,
            amount="300.00",
            due_date=today,
        )

        response = self.client.get(reverse("core:dashboard"), {"mes": today.month, "ano": today.year})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_vendido_ate_a_data"], Decimal("200.00"))
        self.assertContains(response, "R$ 200,00")

    def test_dashboard_total_vendido_ignores_financial_movements_without_workorder_payment_plan(self):
        today = timezone.localdate()

        FinancialMovement.objects.create(
            workshop=self.workshop,
            direction=FinancialMovement.MovementDirection.CREDIT,
            amount=Money("900.00", "BRL"),
            due_date=today,
            is_paid=True,
        )

        response = self.client.get(reverse("core:dashboard"), {"mes": today.month, "ano": today.year})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_vendido_ate_a_data"], Decimal("0.00"))
        self.assertContains(response, "R$ 0,00")

    def test_dashboard_ticket_medio_uses_paid_workorders_in_selected_month(self):
        today = timezone.localdate()
        self._create_workshop_cost(reference_date=today, work_days_per_month=22)

        budget = Budget.objects.create(workshop=self.workshop, entry_date=today)
        workorder = WorkOrder.objects.create(
            workshop=self.workshop,
            budget=budget,
            status=WorkOrderStatus.APPROVED,
            delivered_at=timezone.now(),
        )
        self._create_workorder_payment(
            workshop=self.workshop,
            amount="500.00",
            due_date=today,
            workorder=workorder,
        )

        response = self.client.get(reverse("core:dashboard"), {"mes": today.month, "ano": today.year})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["qtd_carros_mes"], 1)
        self.assertEqual(response.context["ticket_medio"], Decimal("500.00"))
        self.assertContains(response, "R$ 500,00")

    def test_dashboard_counts_approved_workorders_without_delivery_date_using_signature_date_fallback(self):
        today = timezone.localdate()
        self._create_workshop_cost(reference_date=today, work_days_per_month=22)

        budget = Budget.objects.create(workshop=self.workshop, entry_date=today)
        workorder = WorkOrder.objects.create(
            workshop=self.workshop,
            budget=budget,
            status=WorkOrderStatus.APPROVED,
            signature_request_status=WorkOrderSignatureStatus.APPROVED,
            delivered_at=None,
        )
        WorkOrder.objects.filter(pk=workorder.pk).update(
            atualizado_em=timezone.make_aware(datetime.combine(today, datetime.min.time())),
        )

        response = self.client.get(reverse("core:dashboard"), {"mes": today.month, "ano": today.year})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["qtd_carros_mes"], 1)

    def test_dashboard_does_not_count_child_workorders_in_vehicle_total(self):
        today = timezone.localdate()
        self._create_workshop_cost(reference_date=today, work_days_per_month=22)

        parent_budget = Budget.objects.create(workshop=self.workshop, entry_date=today)
        child_budget = Budget.objects.create(workshop=self.workshop, entry_date=today, reference_budget=parent_budget)

        WorkOrder.objects.create(
            workshop=self.workshop,
            budget=parent_budget,
            status=WorkOrderStatus.APPROVED,
            delivered_at=timezone.now(),
        )
        WorkOrder.objects.create(
            workshop=self.workshop,
            budget=child_budget,
            status=WorkOrderStatus.APPROVED,
            delivered_at=timezone.now(),
        )

        response = self.client.get(reverse("core:dashboard"), {"mes": today.month, "ano": today.year})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["qtd_carros_mes"], 1)

    def test_dashboard_projection_uses_elapsed_business_days_for_current_month(self):
        today = timezone.localdate()
        self._create_workshop_cost(reference_date=today, work_days_per_month=22)
        self._create_workorder_payment(workshop=self.workshop, amount="220.00", due_date=today)

        response = self.client.get(reverse("core:dashboard"), {"mes": today.month, "ano": today.year})

        elapsed_business_days = self._count_business_days(start_date=today.replace(day=1), end_date=today)
        remaining_business_days = max(22 - elapsed_business_days, 0)
        expected_projection = (Decimal("220.00") / Decimal(elapsed_business_days) * Decimal(remaining_business_days)) + Decimal("220.00")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["projecao"], expected_projection)

    def test_dashboard_projection_excludes_business_holidays_from_elapsed_and_effective_days(self):
        today = timezone.localdate()
        holiday_date = next(day for day in (today.replace(day=day_number) for day_number in range(1, today.day + 1)) if day.weekday() < 5)
        self._create_workshop_cost(reference_date=today, work_days_per_month=22, holiday_dates=[holiday_date])
        self._create_workorder_payment(workshop=self.workshop, amount="220.00", due_date=today)

        response = self.client.get(reverse("core:dashboard"), {"mes": today.month, "ano": today.year})

        elapsed_business_days = self._count_business_days(start_date=today.replace(day=1), end_date=today, holiday_dates={holiday_date})
        remaining_business_days = max(22 - elapsed_business_days, 0)
        expected_projection = (Decimal("220.00") / Decimal(elapsed_business_days) * Decimal(remaining_business_days)) + Decimal("220.00")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["dias_transcorridos"], elapsed_business_days)
        self.assertEqual(response.context["feriados_uteis"], 1)
        self.assertEqual(response.context["projecao"], expected_projection)

    def test_dashboard_projection_uses_zero_remaining_days_for_past_month(self):
        today = timezone.localdate()
        previous_month_anchor = today.replace(day=1) - timedelta(days=1)
        self._create_workshop_cost(reference_date=previous_month_anchor, work_days_per_month=22)
        self._create_workorder_payment(workshop=self.workshop, amount="150.00", due_date=previous_month_anchor)

        response = self.client.get(reverse("core:dashboard"), {"mes": previous_month_anchor.month, "ano": previous_month_anchor.year})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["projecao"], Decimal("150.00"))

    def test_dashboard_projection_is_blank_and_warns_without_workshop_cost(self):
        today = timezone.localdate()
        self._create_workorder_payment(workshop=self.workshop, amount="100.00", due_date=today)

        response = self.client.get(reverse("core:dashboard"), {"mes": today.month, "ano": today.year})

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["projecao"])
        self.assertEqual(response.context["projecao_warning"], "Para realizar o calculo, cadastre um custo mensal da oficina para o mes selecionado.")
        self.assertContains(response, "Estimativa para o fim do mês")
        self.assertContains(response, "showToast")

    def test_dashboard_projection_uses_total_sold_for_future_month_when_no_business_days_elapsed(self):
        today = timezone.localdate()
        year = today.year + 1 if today.month == 12 else today.year
        month = 1 if today.month == 12 else today.month + 1
        future_date = date(year, month, min(today.day, calendar.monthrange(year, month)[1]))
        self._create_workshop_cost(reference_date=future_date, work_days_per_month=22)
        self._create_workorder_payment(workshop=self.workshop, amount="180.00", due_date=future_date)

        response = self.client.get(reverse("core:dashboard"), {"mes": future_date.month, "ano": future_date.year})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["projecao"], Decimal("180.00"))

    def test_dashboard_taxa_aprovacao_ignores_warranty_and_courtesy_budgets(self):
        today = timezone.localdate()
        self._create_workshop_cost(reference_date=today, work_days_per_month=22)

        Budget.objects.create(
            workshop=self.workshop,
            entry_date=today,
            status=BudgetStatus.APPROVED,
            budget_type=BudgetType.SALE,
            is_warranty_budget=False,
        )
        Budget.objects.create(
            workshop=self.workshop,
            entry_date=today,
            status=BudgetStatus.DRAFT,
            budget_type=BudgetType.SALE,
            is_warranty_budget=False,
        )
        Budget.objects.create(
            workshop=self.workshop,
            entry_date=today,
            status=BudgetStatus.APPROVED,
            budget_type=BudgetType.COURTESY,
        )
        Budget.objects.create(
            workshop=self.workshop,
            entry_date=today,
            status=BudgetStatus.APPROVED,
            budget_type=BudgetType.SALE,
            is_warranty_budget=True,
        )

        response = self.client.get(reverse("core:dashboard"), {"mes": today.month, "ano": today.year})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["taxa_aprovacao"], 50)

    def test_dashboard_taxa_aprovacao_uses_approved_over_created_from_sale_budgets_only(self):
        today = timezone.localdate()

        Budget.objects.create(
            workshop=self.workshop,
            entry_date=today,
            status=BudgetStatus.APPROVED,
            budget_type=BudgetType.SALE,
            is_warranty_budget=False,
        )
        Budget.objects.create(
            workshop=self.workshop,
            entry_date=today,
            status=BudgetStatus.APPROVED,
            budget_type=BudgetType.SALE,
            is_warranty_budget=False,
        )
        Budget.objects.create(
            workshop=self.workshop,
            entry_date=today,
            status=BudgetStatus.DRAFT,
            budget_type=BudgetType.SALE,
            is_warranty_budget=False,
        )
        Budget.objects.create(
            workshop=self.workshop,
            entry_date=today,
            status=BudgetStatus.WAITING_APPROVAL,
            budget_type=BudgetType.SALE,
            is_warranty_budget=False,
        )
        Budget.objects.create(
            workshop=self.workshop,
            entry_date=today,
            status=BudgetStatus.REJECTED,
            budget_type=BudgetType.SALE,
            is_warranty_budget=False,
        )

        Budget.objects.create(
            workshop=self.workshop,
            entry_date=today,
            status=BudgetStatus.APPROVED,
            budget_type=BudgetType.COURTESY,
        )
        Budget.objects.create(
            workshop=self.workshop,
            entry_date=today,
            status=BudgetStatus.APPROVED,
            budget_type=BudgetType.SALE,
            is_warranty_budget=True,
        )

        response = self.client.get(reverse("core:dashboard"), {"mes": today.month, "ano": today.year})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["taxa_aprovacao"], 40)

    def test_dashboard_taxa_aprovacao_is_zero_when_no_sale_budgets_created_in_month(self):
        today = timezone.localdate()

        Budget.objects.create(
            workshop=self.workshop,
            entry_date=today,
            status=BudgetStatus.APPROVED,
            budget_type=BudgetType.COURTESY,
        )
        Budget.objects.create(
            workshop=self.workshop,
            entry_date=today,
            status=BudgetStatus.APPROVED,
            budget_type=BudgetType.SALE,
            is_warranty_budget=True,
        )

        response = self.client.get(reverse("core:dashboard"), {"mes": today.month, "ano": today.year})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["taxa_aprovacao"], 0)

    def test_dashboard_taxa_aprovacao_includes_parent_and_child_sale_budgets(self):
        today = timezone.localdate()

        parent_budget = Budget.objects.create(
            workshop=self.workshop,
            entry_date=today,
            status=BudgetStatus.DRAFT,
            budget_type=BudgetType.SALE,
            is_warranty_budget=False,
        )
        Budget.objects.create(
            workshop=self.workshop,
            entry_date=today,
            status=BudgetStatus.APPROVED,
            budget_type=BudgetType.SALE,
            is_warranty_budget=False,
            reference_budget=parent_budget,
        )

        response = self.client.get(reverse("core:dashboard"), {"mes": today.month, "ano": today.year})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["taxa_aprovacao"], 50)
