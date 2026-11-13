"""Tests for map-extent loading, attribute-only layers, and Cortex helpers.

Follows the source-inspection style used by test_plugin_improvements.py.
"""

import os
import sys
import unittest

_plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _plugin_root not in sys.path:
    sys.path.insert(0, _plugin_root)


def _read(filename: str) -> str:
    path = os.path.join(_plugin_root, filename)
    with open(path) as f:
        return f.read()


class TestExtentModeUri(unittest.TestCase):
    """URI parsing and provider wiring for extent_mode (#106)."""

    def test_decode_uri_supports_extent_mode(self):
        utils = _read("helpers/utils.py")
        self.assertIn('"extent_mode"', utils)

    def test_parse_uri_returns_extent_mode(self):
        wrapper = _read("helpers/wrapper.py")
        self.assertIn(
            'extent_mode = parsed_uri.get("extent_mode", "") == "1"',
            wrapper,
        )
        self.assertIn("extent_mode,", wrapper)

    def test_provider_parses_extent_mode(self):
        provider = _read("providers/sf_vector_data_provider.py")
        self.assertIn("self._extent_mode", provider)
        self.assertIn("self._extent_cache_key", provider)
        self.assertIn("self._extent_cache_features", provider)

    def test_provider_skips_row_probe_in_extent_mode(self):
        provider = _read("providers/sf_vector_data_provider.py")
        self.assertIn(
            "if self._load_all_rows or self._extent_mode:",
            provider,
        )

    def test_reload_clears_extent_cache(self):
        provider = _read("providers/sf_vector_data_provider.py")
        reload_idx = provider.index("def reloadData(self):")
        reload_block = provider[reload_idx : reload_idx + 500]
        self.assertIn("self._extent_cache_key = None", reload_block)
        self.assertIn("self._extent_cache_features = []", reload_block)

    def test_uri_token_keys_include_extent_mode(self):
        provider = _read("providers/sf_vector_data_provider.py")
        self.assertIn('"extent_mode"', provider)

    def test_parse_uri_callers_unpack_extent_mode(self):
        for path in (
            "entities/sf_dynamic_connection_combo_box_widget.py",
            "qgis_snowflake_connector_algorithm.py",
            "providers/sf_vector_data_provider.py",
        ):
            content = _read(path)
            self.assertIn(
                "_extent_mode" if path != "providers/sf_vector_data_provider.py"
                else "self._extent_mode",
                content,
                f"{path} must unpack extent_mode from parse_uri",
            )


class TestExtentModeIterator(unittest.TestCase):
    """Feature iterator behaviour for map-extent loading."""

    def test_extent_mode_uses_limit_not_sample(self):
        iterator = _read("providers/sf_feature_iterator.py")
        self.assertIn("if self._extent_mode:", iterator)
        self.assertIn("LIMIT {int(limit_n)}", iterator)
        # SAMPLE remains for the non-extent limited path.
        self.assertIn("SAMPLE ({sample_n} ROWS)", iterator)

    def test_extent_mode_never_writes_shared_cache(self):
        iterator = _read("providers/sf_feature_iterator.py")
        self.assertIn("not self._extent_mode", iterator)
        self.assertIn("_populate_extent_cache", iterator)
        self.assertIn("_serving_extent_cache", iterator)

    def test_extent_cache_key_helper_exists(self):
        iterator = _read("providers/sf_feature_iterator.py")
        self.assertIn("def _build_extent_cache_key", iterator)


class TestExtentModeBrowserAction(unittest.TestCase):
    """Browser context menu entry for map-extent loading."""

    def test_browser_action_exists(self):
        data_item = _read("entities/sf_data_item.py")
        self.assertIn("Add with map-extent loading", data_item)
        self.assertIn("on_add_with_extent_mode_triggered", data_item)
        self.assertIn("extent_mode=True", data_item)

    def test_convert_task_accepts_extent_mode(self):
        task = _read("tasks/sf_convert_column_to_layer_task.py")
        self.assertIn("extent_mode: bool = False", task)
        self.assertIn('uri += " extent_mode=1"', task)


class TestAttributeOnlyLayers(unittest.TestCase):
    """Tables without geometry load as attribute-only layers (#105)."""

    def test_iterator_skips_st_for_no_geometry(self):
        iterator = _read("providers/sf_feature_iterator.py")
        self.assertIn("has_geometry = bool(geom_column)", iterator)
        self.assertIn("Attribute-only table (#105)", iterator)

    def test_base_provider_counts_attribute_rows(self):
        provider = _read("providers/sf_vector_data_provider.py")
        # Base provider featureCount no longer hard-codes 0.
        self.assertIn(
            "Row count for attribute-only (no geometry) table layers (#105).",
            provider,
        )

    def test_browser_loads_attribute_table(self):
        data_item = _read("entities/sf_data_item.py")
        self.assertIn("_start_add_attribute_table_layer", data_item)
        self.assertIn('geom_column= geometry_type= geo_column_type=', data_item)
        self.assertNotIn("cannot be displayed on the map", data_item)


class TestToolbarHelpers(unittest.TestCase):
    """Pure helpers for the Snowflake toolbar."""

    def test_toggle_extent_mode_uri(self):
        from helpers.toolbar import toggle_extent_mode_uri, uri_has_extent_mode

        base = "connection_name=c schema_name=s table_name=t"
        on = toggle_extent_mode_uri(base)
        self.assertTrue(uri_has_extent_mode(on))
        self.assertIn("extent_mode=1", on)
        off = toggle_extent_mode_uri(on)
        self.assertFalse(uri_has_extent_mode(off))
        self.assertNotIn("extent_mode=1", off)

    def test_plugin_registers_toolbar_actions(self):
        plugin = _read("qgis_snowflake_connector.py")
        self.assertIn("_init_toolbar", plugin)
        self.assertIn("Execute SQL...", plugin)
        self.assertIn("Reload from Snowflake", plugin)
        self.assertIn("Toggle map-extent loading", plugin)
        self.assertIn("Ask Snowflake (Cortex)...", plugin)
        self.assertIn("Describe map (Cortex)...", plugin)
        self.assertIn("on_reload_from_snowflake", plugin)
        self.assertIn("toolbar.deleteLater", plugin)


class TestCortexSqlHelpers(unittest.TestCase):
    """Pure Cortex SQL prompt / extract helpers."""

    def test_build_schema_context(self):
        from helpers.cortex import build_schema_context

        text = build_schema_context(
            [
                ("CITIES", "ID", "NUMBER"),
                ("CITIES", "GEOM", "GEOGRAPHY"),
                ("ROADS", "NAME", "TEXT"),
            ]
        )
        self.assertIn("CITIES(ID NUMBER, GEOM GEOGRAPHY)", text)
        self.assertIn("ROADS(NAME TEXT)", text)

    def test_build_schema_context_respects_max_tables(self):
        from helpers.cortex import build_schema_context

        rows = [(f"T{i}", "C", "TEXT") for i in range(5)]
        text = build_schema_context(rows, max_tables=2)
        self.assertEqual(text.count("("), 2)

    def test_build_sql_prompt_mentions_rules(self):
        from helpers.cortex import build_sql_prompt

        prompt = build_sql_prompt(
            "find parks", "PARKS(GEOM GEOGRAPHY)", "DB", "PUBLIC"
        )
        self.assertIn("read-only SELECT", prompt)
        self.assertIn("PARKS(GEOM GEOGRAPHY)", prompt)
        self.assertIn("find parks", prompt)

    def test_extract_sql_fenced(self):
        from helpers.cortex import extract_sql

        sql = extract_sql("Sure.\n```sql\nSELECT 1;\n```\nDone.")
        self.assertEqual(sql, "SELECT 1")

    def test_extract_sql_unfenced(self):
        from helpers.cortex import extract_sql

        sql = extract_sql("Here you go:\nSELECT * FROM T")
        self.assertEqual(sql, "SELECT * FROM T")

    def test_extract_sql_keeps_first_statement(self):
        from helpers.cortex import extract_sql

        sql = extract_sql("SELECT 1; DELETE FROM T;")
        self.assertEqual(sql, "SELECT 1")

    def test_ask_dialog_and_task_exist(self):
        self.assertIn("class SFAskDialog", _read("dialogs/sf_ask_dialog.py"))
        self.assertIn(
            "class SFCortexCompleteTask",
            _read("tasks/sf_cortex_complete_task.py"),
        )
        self.assertIn("def set_query", _read("dialogs/sf_sql_query_dialog.py"))
        self.assertIn("sql_statement_is_read_only", _read("dialogs/sf_ask_dialog.py"))


class TestDescribeMapHelpers(unittest.TestCase):
    """Map description helpers and dialog wiring."""

    def test_summarize_renderer_graduated(self):
        from helpers.cortex import summarize_renderer

        class _Range:
            def __init__(self, label):
                self._label = label

            def label(self):
                return self._label

        class _Renderer:
            def type(self):
                return "graduatedSymbol"

            def classAttribute(self):
                return "CRASHES"

            def ranges(self):
                return [_Range("0-10"), _Range("10-50")]

        summary = summarize_renderer(_Renderer())
        self.assertIn("renderer=graduatedSymbol", summary)
        self.assertIn("field=CRASHES", summary)
        self.assertIn("0-10", summary)

    def test_build_map_context_truncates(self):
        from helpers.cortex import build_map_context

        text = build_map_context(
            extent_wkt="POLYGON((0 0,1 0,1 1,0 1,0 0))",
            scale=10000,
            crs_authid="EPSG:4326",
            layer_summaries=["layer " + ("x" * 200)] * 50,
            max_chars=500,
        )
        self.assertLessEqual(len(text), 500)
        self.assertIn("[truncated]", text)

    def test_describe_dialog_and_task_exist(self):
        dialog = _read("dialogs/sf_describe_map_dialog.py")
        task = _read("tasks/sf_describe_map_task.py")
        self.assertIn("class SFDescribeMapDialog", dialog)
        self.assertIn("CREATE TEMPORARY STAGE IF NOT EXISTS", task)
        self.assertIn("SNOWFLAKE_SSE", task)
        self.assertIn("TO_FILE", task)
        self.assertIn("REMOVE", task)
        capture = _read("helpers/map_capture.py")
        self.assertIn("def render_canvas_png", capture)
        self.assertIn("def build_canvas_map_context", capture)


if __name__ == "__main__":
    unittest.main()



