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
