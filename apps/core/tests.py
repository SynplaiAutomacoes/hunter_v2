from django.template import Context, Template
from django.test import RequestFactory, TestCase
from django.db import connection
from django.db.models import F, Func, IntegerField, Value
from django.db.models.functions import Cast, NullIf

from apps.workshops.models import Workshop


class TestRenderTableTag(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_renders_and_paginates(self):
        for i in range(1, 13):
            Workshop.objects.create(name=f"Oficina {i:02d}")

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
        Workshop.objects.create(name="Oficina 01")
        Workshop.objects.create(name="Oficina 02")
        Workshop.objects.create(name="Oficina 03")

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
        Workshop.objects.create(name="Oficina 01", is_active=True)
        Workshop.objects.create(name="Oficina 02", is_active=False)

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

    def test_third_click_clears_sort(self):
        # Não criar paginação (mantém apenas o link do cabeçalho como hx-get no HTML).
        Workshop.objects.create(name="Oficina 01")
        Workshop.objects.create(name="Oficina 02")
        Workshop.objects.create(name="Oficina 03")

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
        Workshop.objects.create(name="Alpha")
        Workshop.objects.create(name="Beta")

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
            Workshop.objects.create(name=f"Oficina {i:02d}")

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

    def test_numeric_sort_by_name_with_custom_sort_by_expression(self):
        # REGEXP_REPLACE é específico do PostgreSQL; em outros bancos esse teste não se aplica.
        if connection.vendor != "postgresql":
            self.skipTest("Ordenação numérica via REGEXP_REPLACE é suportada apenas no PostgreSQL.")

        # Mistura valores numéricos (como strings) e nomes com prefixo.
        for name in ["10", "11", "4", "5", "6", "7", "8", "9", "Oficina 1", "Oficina 2", "Oficina 3"]:
            Workshop.objects.create(name=name)

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
