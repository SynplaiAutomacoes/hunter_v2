from django.contrib.auth import get_user_model
from django.db import connection
from django.db.models import F, Func, IntegerField, Value
from django.db.models.functions import Cast, NullIf
from django.template import Context, Template
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from phonenumber_field.phonenumber import PhoneNumber

from apps.core.documents.signature import SIGNATURE_POSITION, build_absolute_app_url, normalize_signature_phone_number
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


class TestRenderTableTag(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

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
        create_workshop(name="Alpha")
        create_workshop(name="Beta")

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
