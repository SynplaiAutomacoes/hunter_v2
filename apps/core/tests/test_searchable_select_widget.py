from __future__ import annotations

from django.test import SimpleTestCase

from apps.core.presentation.widgets import SearchableSelectInput


class SearchableSelectInputTests(SimpleTestCase):
    def test_render_includes_constructor_data_source_url_in_alpine_source_url(self) -> None:
        widget = SearchableSelectInput(
            choices=(),
            attrs={"data-source-url": "/scheduling/get-customers/"},
        )

        html = widget.render("customer", None, attrs={"id": "id_customer"})

        # escapejs encodes '-' as \u002D in the Alpine sourceUrl string.
        self.assertIn("sourceUrl: '/scheduling/get\\u002Dcustomers/'", html)
        self.assertIn('data-source-url="/scheduling/get-customers/"', html)

    def test_render_includes_constructor_min_search_length(self) -> None:
        widget = SearchableSelectInput(
            choices=(),
            attrs={
                "data-source-url": "/scheduling/get-customers/",
                "data-min-search-length": "2",
            },
        )

        html = widget.render("customer", None, attrs={"id": "id_customer"})

        self.assertIn("minSearchLength: Number('2'", html)

    def test_render_preserves_search_query_while_dropdown_is_open(self) -> None:
        """Empty value must not clear search while open (remote fetch race)."""
        widget = SearchableSelectInput(choices=(), attrs={"data-source-url": "/scheduling/get-customers/"})

        html = widget.render("customer", None, attrs={"id": "id_customer"})

        self.assertIn("if (!this.value)", html)
        self.assertIn("if (!this.open)", html)
        self.assertNotIn(
            "if (!this.value) {\n                this.label = '';\n                this.search = '';",
            html,
        )

    def test_render_uses_x_model_instead_of_controlled_open_value_binding(self) -> None:
        """Safari/WebKit breaks on :value=open?search:label controlled binding while typing."""
        widget = SearchableSelectInput(choices=())

        html = widget.render("entity", None, attrs={"id": "id_entity"})

        self.assertIn('x-model="search"', html)
        self.assertNotIn(':value="open ? search : label"', html)

    def test_render_normalizes_name_as_label_fallback(self) -> None:
        widget = SearchableSelectInput(choices=())

        html = widget.render("entity", None, attrs={"id": "id_entity"})

        self.assertIn("option.name", html)
        self.assertIn("hasVisibleOptions", html)
        self.assertIn("pointer-events-none", html)
        self.assertIn("'ring-2 ring-primary': open", html)
        self.assertNotIn("border-primary': open", html)
        self.assertNotIn("style*='display: none'", html)
