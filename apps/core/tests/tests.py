from django.contrib.auth import get_user_model
from dataclasses import dataclass
from django.db import connection
from django.db.models import F, Func, IntegerField, Value
from django.db.models.functions import Cast, NullIf
from django.template import Context, Template
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from phonenumber_field.phonenumber import PhoneNumber

from apps.core.documents.signature import SIGNATURE_POSITION, build_absolute_app_url, normalize_signature_phone_number
from apps.core.templatetags.table_tags import TableColumn, render_table
from apps.workshops.models.workshops import Workshop


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
                        {"label": "Cadastros", "children": [{"label": "Cliente", "href": "/customer/"}]},
                        {"label": "Orcamentos", "href": "/budget/"},
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
        self.assertIn("Adicionar Orcamentos aos favoritos", html)
        self.assertIn("Favoritos", html)

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
                        ("draft", "Em Aberto"),
                        ("approved", "Aprovado"),
                    ],
                }
            )
        )

        self.assertIn('value="draft"', html)
        self.assertIn("Em Aberto", html)
        self.assertIn('value="approved"', html)
        self.assertIn("Aprovado", html)

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
                        ("draft", "Em Aberto"),
                        ("approved", "Aprovado"),
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
        user = User.objects.create_user(username="u", password="p", cpf="11144477735")
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
