import unittest
import sys
from pathlib import Path

# Dashboard modules use local imports (e.g. "from heatmap_filters import ...").
# Add dashboard/ to sys.path so tests can import modules consistently.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from heatmap_queries import (
    build_click_ranking_query,
    build_session_stats_query,
)


class Phase8QueryTests(unittest.TestCase):
    def test_session_stats_query_exact_url_scope(self):
        sql, params = build_session_stats_query("https://example.com/product/1")

        self.assertIn("page_url = %(page_url_exact)s", sql)
        self.assertEqual(params["page_url_exact"], "https://example.com/product/1")
        self.assertIn("countIf(event_type = 'page_view')", sql)
        self.assertIn("avg(ifNull(max_scroll_pct, 0.0))", sql)
        self.assertIn("FROM session_rollup", sql)

    def test_session_stats_query_wildcard_scope(self):
        sql, params = build_session_stats_query("/product/*")

        self.assertIn("page_url LIKE %(page_url_like)s", sql)
        self.assertEqual(params["page_url_like"], "/product/%")

    def test_click_ranking_query_defaults_to_top_10(self):
        sql, params = build_click_ranking_query("/product/*")

        self.assertIn("event_type = 'click'", sql)
        self.assertIn("GROUP BY element_selector", sql)
        self.assertIn("ORDER BY click_count DESC", sql)
        self.assertIn("LIMIT %(limit)s", sql)
        self.assertEqual(params["limit"], 10)
        self.assertEqual(params["page_url_like"], "/product/%")

    def test_click_ranking_query_custom_limit_is_parameterized(self):
        sql, params = build_click_ranking_query("https://example.com", limit=3)

        self.assertIn("page_url = %(page_url_exact)s", sql)
        self.assertEqual(params["page_url_exact"], "https://example.com")
        self.assertEqual(params["limit"], 3)


if __name__ == "__main__":
    unittest.main()
