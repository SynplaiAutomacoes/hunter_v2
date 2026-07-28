from django.test import SimpleTestCase

from apps.core.management.commands.collect_person_one_performance_baseline import (
    normalize_sql,
    percentile,
    rendered_desktop_rows,
)


class PersonOnePerformanceCollectorTests(SimpleTestCase):
    def test_normalize_sql_collapses_literals_and_whitespace(self) -> None:
        sql = "SELECT  *  FROM example WHERE id = 42 AND name = 'Alice'"
        self.assertEqual(normalize_sql(sql), "SELECT * FROM example WHERE id = ? AND name = ?")

    def test_percentile_uses_nearest_rank(self) -> None:
        self.assertEqual(percentile([1.0, 2.0, 3.0, 4.0, 5.0], 0.95), 5.0)

    def test_rendered_desktop_rows_counts_first_table_body(self) -> None:
        content = b"<table><tbody><tr><td>1</td></tr><tr><td>2</td></tr></tbody></table>"
        self.assertEqual(rendered_desktop_rows(content), 2)
