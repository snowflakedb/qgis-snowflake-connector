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
        self.assertIn("if self._use_extent_style_fetch:", iterator)
        self.assertIn("LIMIT {int(limit_n)}", iterator)
        # SAMPLE remains for the non-extent limited path.
        self.assertIn("SAMPLE ({sample_n} ROWS)", iterator)

    def test_extent_mode_never_writes_shared_cache(self):
        iterator = _read("providers/sf_feature_iterator.py")
        self.assertIn("not self._use_extent_style_fetch", iterator)
        self.assertIn("_populate_extent_cache", iterator)
        self.assertIn("_serving_extent_cache", iterator)

    def test_extent_cache_key_helper_exists(self):
        iterator = _read("providers/sf_feature_iterator.py")
        self.assertIn("def _build_extent_cache_key", iterator)

    def test_limited_viewport_uses_extent_style_fetch(self):
        """Oversized sampled layers re-fetch the canvas rect with LIMIT + cache."""
        iterator = _read("providers/sf_feature_iterator.py")
        self.assertIn("self._viewport_candidate", iterator)
        self.assertIn("self._use_extent_style_fetch", iterator)
        self.assertIn("self._limited_unordered", iterator)
        self.assertIn("or self._viewport_candidate", iterator)
        # Shared sample cache must not win over an active viewport SQL fetch.
        self.assertIn(
            "not getattr(self, \"_use_extent_style_fetch\", False)",
            iterator,
        )


class TestExtentModeBrowserAction(unittest.TestCase):
    """Browser context menu entry for map-extent loading."""

    def test_browser_action_exists(self):
        data_item = _read("entities/sf_data_item.py")
        self.assertIn("Add with map-extent loading", data_item)
        self.assertIn("on_add_with_extent_mode_triggered", data_item)
        self.assertIn("extent_mode=True", data_item)

    def test_spatial_filter_browser_action_exists(self):
        data_item = _read("entities/sf_data_item.py")
        self.assertIn("Download with spatial filter…", data_item)
        self.assertIn("on_download_with_spatial_filter_triggered", data_item)
        self.assertIn("SFSpatialFilterDialog", data_item)
        self.assertIn("SFConvertSQLQueryToLayerTask", data_item)

    def test_convert_task_accepts_extent_mode(self):
        task = _read("tasks/sf_convert_column_to_layer_task.py")
        self.assertIn("extent_mode: bool = False", task)
        self.assertIn('uri += " extent_mode=1"', task)

    def test_large_h3_auto_enables_extent_mode(self):
        data_item = _read("entities/sf_data_item.py")
        dsm = _read("dialogs/sf_data_source_manager_widget.py")
        for src, label in ((data_item, "Browser"), (dsm, "DSM")):
            self.assertIn("H3_COLUMN_TYPES", src, label)
            self.assertIn("enabling map-extent", src, label)
        self.assertIn("effective_extent_mode = True", data_item)
        self.assertIn("extent_mode=effective_extent_mode", data_item)
        self.assertIn("extent_mode=extent_mode", dsm)
        # Oversized H3 skips the sample/load-all dialog.
        self.assertIn("if self.geom_type in H3_COLUMN_TYPES:", data_item)
        self.assertIn("if data_type in H3_COLUMN_TYPES:", dsm)

    def test_convert_and_sql_tasks_report_progress_and_zoom(self):
        convert = _read("tasks/sf_convert_column_to_layer_task.py")
        sql_task = _read("tasks/sf_convert_sql_query_to_layer_task.py")
        for source in (convert, sql_task):
            self.assertIn("setProgress", source)
            self.assertIn("zoom_canvas_to_layers", source)
            self.assertIn("Layer download was canceled", source)
        self.assertIn("Empty result", sql_task)
        zoom = _read("helpers/map_zoom.py")
        self.assertIn("buffer_scale: float = 1.1", zoom)
        self.assertIn("setExtent", zoom)


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
        self.assertIn("Map brief (Cortex)...", plugin)
        self.assertIn("on_map_brief", plugin)
        self.assertIn("on_reload_from_snowflake", plugin)
        self.assertIn("toolbar.deleteLater", plugin)


class TestCortexSqlHelpers(unittest.TestCase):
    """Pure Cortex SQL prompt / extract helpers."""

    def test_build_schema_context(self):
        from helpers.cortex import build_schema_context

        text, omitted = build_schema_context(
            [
                ("CITIES", "ID", "NUMBER"),
                ("CITIES", "GEOM", "GEOGRAPHY"),
                ("ROADS", "NAME", "TEXT"),
            ]
        )
        self.assertIn("CITIES(ID NUMBER, GEOM GEOGRAPHY)", text)
        self.assertIn("ROADS(NAME TEXT)", text)
        self.assertEqual(omitted, 0)

    def test_build_schema_context_respects_max_tables(self):
        from helpers.cortex import build_schema_context

        rows = [(f"T{i}", "C", "TEXT") for i in range(5)]
        text, omitted = build_schema_context(rows, max_tables=2)
        self.assertEqual(text.count("("), 2)
        self.assertEqual(omitted, 3)

    def test_system_dollar_rejected_as_not_readonly(self):
        from helpers.sql import sql_statement_is_read_only

        self.assertTrue(sql_statement_is_read_only("SELECT 1"))
        self.assertFalse(
            sql_statement_is_read_only("SELECT SYSTEM$CANCEL_ALL_QUERIES()")
        )

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

    def test_extract_sql_strips_wrapping_quotes(self):
        from helpers.cortex import extract_sql

        self.assertEqual(extract_sql('"SELECT 1"'), "SELECT 1")
        self.assertEqual(extract_sql("'SELECT * FROM T'"), "SELECT * FROM T")

    def test_extract_sql_unescapes_literal_newlines(self):
        from helpers.cortex import extract_sql

        bn = "\\n"
        raw = (
            f'SELECT SEVERITY_DESCRIPTION, COUNT(*) AS ACCIDENT_COUNT{bn}'
            f'FROM "CARTO"."BRISTOL_TRAFFIC_ACCIDENTS"{bn}'
            f"GROUP BY SEVERITY_DESCRIPTION{bn}"
            f"ORDER BY ACCIDENT_COUNT DESC"
        )
        sql = extract_sql(raw)
        self.assertNotIn("\\n", sql)
        self.assertIn("\nFROM", sql)
        self.assertTrue(sql.upper().startswith("SELECT"))

    def test_extract_sql_unescapes_literal_quotes(self):
        from helpers.cortex import extract_sql

        # Ask SQL often returns \"identifiers\" with no literal newlines.
        bq = '\\"'
        raw = (
            "SELECT REF_NUMBER, SEVERITY_DESCRIPTION, CASUALTIES FROM "
            f"{bq}CARTO_ACADEMY__DATA_FOR_TUTORIALS{bq}.{bq}CARTO{bq}."
            f"{bq}BRISTOL_TRAFFIC_ACCIDENTS{bq} WHERE CASUALTIES > 2 LIMIT 100"
        )
        self.assertIn('\\"', raw)
        sql = extract_sql(raw)
        self.assertNotIn('\\"', sql)
        self.assertIn(
            '"CARTO_ACADEMY__DATA_FOR_TUTORIALS"."CARTO"."BRISTOL_TRAFFIC_ACCIDENTS"',
            sql,
        )

    def test_ask_dialog_and_task_exist(self):
        self.assertIn("class SFAskDialog", _read("dialogs/sf_ask_dialog.py"))
        self.assertIn(
            "class SFCortexCompleteTask",
            _read("tasks/sf_cortex_complete_task.py"),
        )
        self.assertIn("def set_query", _read("dialogs/sf_sql_query_dialog.py"))
        self.assertIn("sql_statement_is_read_only", _read("dialogs/sf_ask_dialog.py"))
        ask = _read("dialogs/sf_ask_dialog.py")
        self.assertIn("fetch_cortex_base_models", ask)
        self.assertIn("models_for_ask_snowflake", ask)

    def test_parse_cortex_base_model_rows_skips_eol(self):
        from helpers.cortex import parse_cortex_base_model_rows

        rows = [
            (None, "llama3.1-70b", "CORTEX_BASE", "SNOWFLAKE", "MODELS", None, "GA"),
            (None, "old-model", "CORTEX_BASE", "SNOWFLAKE", "MODELS", None, "EOL"),
            (None, "pixtral-large", "CORTEX_BASE", "SNOWFLAKE", "MODELS", None, "GA"),
            (
                None,
                "secret-preview",
                "CORTEX_BASE",
                "SNOWFLAKE",
                "MODELS",
                None,
                "PRIVATE PREVIEW",
            ),
        ]
        names = parse_cortex_base_model_rows(rows)
        self.assertEqual(names, ["llama3.1-70b", "pixtral-large"])
        self.assertNotIn("secret-preview", names)

    def test_parse_cortex_base_model_rows_uses_description(self):
        from helpers.cortex import parse_cortex_base_model_rows

        description = (
            ("created_on",),
            ("name",),
            ("lifecycle_status",),
        )
        rows = [
            ("ts", "claude-sonnet-4-5", "GA"),
            ("ts", "dead-model", "EOL"),
            ("ts", "private-model", "PRIVATE PREVIEW"),
        ]
        names = parse_cortex_base_model_rows(rows, description)
        self.assertEqual(names, ["claude-sonnet-4-5"])

    def test_models_for_ask_and_map_brief_filters(self):
        from helpers.cortex import (
            FALLBACK_MULTIMODAL_MODELS,
            FALLBACK_SQL_MODELS,
            choose_model,
            models_for_ask_snowflake,
            models_for_map_brief,
        )

        available = [
            "llama3.1-70b",
            "pixtral-large",
            "claude-sonnet-4-5",
            "multilingual-e5-large",
            "ARCTIC-EXTRACT",
            "snowflake-arctic",
        ]
        ask = models_for_ask_snowflake(available)
        self.assertIn("llama3.1-70b", ask)
        self.assertIn("snowflake-arctic", ask)
        self.assertNotIn("pixtral-large", ask)
        self.assertNotIn("claude-sonnet-4-5", ask)
        self.assertNotIn("multilingual-e5-large", ask)
        self.assertNotIn("ARCTIC-EXTRACT", ask)

        brief = models_for_map_brief(available)
        self.assertEqual(brief, ["pixtral-large", "claude-sonnet-4-5"])
        self.assertEqual(models_for_map_brief([]), list(FALLBACK_MULTIMODAL_MODELS))
        self.assertEqual(models_for_ask_snowflake([]), list(FALLBACK_SQL_MODELS))
        self.assertEqual(
            choose_model(ask, "llama3.1-8b", "llama3.1-70b"),
            "llama3.1-70b",
        )


class TestMapBriefHelpers(unittest.TestCase):
    """Map brief helpers, section parsing, staging, and dialog wiring."""

    def test_assess_view_warnings(self):
        from helpers.cortex import assess_view

        self.assertEqual(
            assess_view(0, False, False),
            ["No visible layers on the map canvas."],
        )
        warnings = assess_view(2, False, True)
        self.assertIn(
            "No visible layer extent intersects the current map view.",
            warnings,
        )
        self.assertIn(
            "The rendered map image looks nearly uniform (possibly empty).",
            warnings,
        )
        self.assertEqual(assess_view(1, True, False), [])

    def test_layer_context_budget_omits_lower_layers(self):
        from helpers.cortex import build_map_context, format_layer_block

        blocks = []
        for idx in range(8):
            blocks.append(
                format_layer_block(
                    {
                        "name": f"layer_{idx}",
                        "geometry_kind": "points",
                        "draw_order": idx,
                        "fields": ["a", "b", "c"],
                        "snowflake_table": f"PUBLIC.T{idx}",
                        "extent_mode": idx == 0,
                    }
                )
            )
        text = build_map_context(
            extent_wkt="POLYGON((0 0,1 0,1 1,0 1,0 0))",
            scale=10000,
            crs_authid="EPSG:4326",
            layer_blocks=blocks,
            max_chars=450,
        )
        self.assertIn("layer_0", text)
        self.assertIn("map_extent_loading: on", text)
        self.assertIn("lower layers omitted", text)
        self.assertNotIn("[truncated]", text)

    def test_split_brief_sections_variants(self):
        from helpers.cortex import BRIEF_SECTIONS, split_brief_sections

        ordered = "\n".join(
            f"## {title}\nBody for {title}" for title in BRIEF_SECTIONS
        )
        sections = split_brief_sections(ordered)
        for title in BRIEF_SECTIONS:
            self.assertIn(f"Body for {title}", sections[title])

        shuffled = (
            "## Suggested next steps\nDo X\n"
            "**Seen in the image**\nDots\n"
            "### From layer settings\nRoads\n"
            "Not determinable from this view:\nUnknown\n"
        )
        sections = split_brief_sections(shuffled)
        self.assertIn("Do X", sections["Suggested next steps"])
        self.assertIn("Dots", sections["Seen in the image"])
        self.assertIn("Roads", sections["From layer settings"])
        self.assertIn("Unknown", sections["Not determinable from this view"])

        partial = "## Seen in the image\nOnly this\n"
        sections = split_brief_sections(partial)
        self.assertEqual(sections["Seen in the image"], "Only this")
        self.assertEqual(sections["Suggested next steps"], "")

        quoted = (
            '" ## Seen in the image\nDots\n'
            "## From layer settings\nRoads\n"
            "## Not determinable from this view\nUnknown\n"
            '## Suggested next steps\nZoom in"'
        )
        from helpers.cortex import normalize_cortex_text

        cleaned = normalize_cortex_text(quoted)
        self.assertFalse(cleaned.startswith('"'))
        self.assertFalse(cleaned.endswith('"'))
        sections = split_brief_sections(quoted)
        self.assertIn("Dots", sections["Seen in the image"])
        self.assertIn("Roads", sections["From layer settings"])
        self.assertIn("Zoom in", sections["Suggested next steps"])
        self.assertEqual(sections["Other"], "")

        # AI_COMPLETE sometimes returns one line with literal \n escapes.
        bn = "\\n"
        escaped = (
            '"## Seen in the image'
            + bn
            + "- Dots"
            + bn
            + bn
            + "## From layer settings"
            + bn
            + "- Roads"
            + bn
            + bn
            + "## Not determinable from this view"
            + bn
            + "- Unknown"
            + bn
            + bn
            + "## Suggested next steps"
            + bn
            + '- Zoom in"'
        )
        self.assertNotIn("\n", escaped[1:-1])  # no real newlines inside quotes
        sections = split_brief_sections(escaped)
        self.assertIn("Dots", sections["Seen in the image"])
        self.assertIn("Roads", sections["From layer settings"])
        self.assertIn("Unknown", sections["Not determinable from this view"])
        self.assertIn("Zoom in", sections["Suggested next steps"])
        self.assertEqual(sections["Other"], "")

        # Mixed real newline + literal \n must still unescape (Map brief gap).
        bn = "\\n"
        mixed = (
            "## Seen in the image\n"
            "- Green circles"
            + bn
            + bn
            + "## From layer settings"
            + bn
            + "- bristol_ok"
            + bn
            + bn
            + "## Not determinable from this view"
            + bn
            + "- Place names"
            + bn
            + bn
            + "## Suggested next steps"
            + bn
            + "- Zoom in"
        )
        self.assertIn("\n", mixed)
        self.assertIn("\\n", mixed)
        sections = split_brief_sections(mixed)
        self.assertIn("Green circles", sections["Seen in the image"])
        self.assertIn("bristol_ok", sections["From layer settings"])
        self.assertIn("Place names", sections["Not determinable from this view"])
        self.assertIn("Zoom in", sections["Suggested next steps"])
        self.assertEqual(sections["Other"], "")

        # Double-encoded \\n (two backslashes + n) must fully collapse.
        bn2 = "\\\\n"
        doubled = (
            '"## Seen in the image'
            + bn2
            + "- Green circles"
            + bn2
            + bn2
            + "## From layer settings"
            + bn2
            + "- bristol_ok"
            + bn2
            + bn2
            + "## Not determinable from this view"
            + bn2
            + "- Place names"
            + bn2
            + bn2
            + "## Suggested next steps"
            + bn2
            + '- Zoom in"'
        )
        sections = split_brief_sections(doubled)
        self.assertIn("Green circles", sections["Seen in the image"])
        self.assertIn("bristol_ok", sections["From layer settings"])
        self.assertIn("Place names", sections["Not determinable from this view"])
        self.assertIn("Zoom in", sections["Suggested next steps"])
        self.assertEqual(sections["Other"], "")
        self.assertNotIn("\\n", sections["Seen in the image"])

        # Escaped dump left in Other while sections already filled → drop Other.
        bn = "\\n"
        escaped_dump = (
            "## Seen in the image"
            + bn
            + "- A collection of green markers"
            + bn
            + "## From layer settings"
            + bn
            + "- bristol_ok"
            + bn
            + "## Not determinable from this view"
            + bn
            + "- Place names"
            + bn
            + "## Suggested next steps"
            + bn
            + "- Zoom in"
        )
        hybrid = (
            "## Seen in the image\n"
            "- Dense green markers on beige\n\n"
            "## From layer settings\n"
            "- Layer name: bristol_ok\n\n"
            "## Not determinable from this view\n"
            "- City identity\n\n"
            "## Suggested next steps\n"
            "- Zoom to densest cluster\n\n"
            + escaped_dump
        )
        sections = split_brief_sections(hybrid)
        self.assertIn("Dense green markers", sections["Seen in the image"])
        self.assertIn("bristol_ok", sections["From layer settings"])
        self.assertEqual(sections["Other"], "")

    def test_build_brief_prompt_contains_headings_and_warnings(self):
        from helpers.cortex import (
            BRIEF_SECTIONS,
            build_brief_prompt,
            build_followup_prompt,
        )

        map_context = (
            "CRS: EPSG:4326\n"
            "Automatic checks:\n"
            "- No visible layers on the map canvas."
        )
        prompt = build_brief_prompt(
            "road safety",
            map_context,
            warnings=["No visible layers on the map canvas."],
        )
        for title in BRIEF_SECTIONS:
            self.assertIn(title, prompt)
        self.assertIn("automatic checks", prompt.lower())
        self.assertIn("No visible layers", prompt)
        self.assertIn("road safety", prompt)
        # Warnings are not duplicated outside map context.
        self.assertEqual(prompt.count("No visible layers"), 1)
        # Anti-hallucination / visual-only constraints.
        self.assertIn("visual-only", prompt)
        self.assertIn("place names", prompt.lower())
        self.assertIn("world knowledge", prompt.lower())
        self.assertIn("readable as labels in the PNG", prompt)

        followup = build_followup_prompt(
            "Where is densest?",
            "## Seen in the image\nGreen points\n",
        )
        followup_l = followup.lower()
        self.assertIn("visual-only", followup_l)
        self.assertIn("place names", followup_l)
        self.assertIn("world knowledge", followup_l)
        self.assertIn("not determinable", followup_l)

    def test_project_notes_and_label_text(self):
        from datetime import datetime, timezone

        from helpers.cortex import (
            format_brief_label_text,
            format_project_notes_block,
        )

        sections = {
            "Seen in the image": "Dots",
            "From layer settings": "Roads",
            "Not determinable from this view": "",
            "Suggested next steps": "Zoom in",
        }
        label = format_brief_label_text(sections)
        self.assertIn("Seen in the image\nDots", label)
        self.assertIn("Suggested next steps\nZoom in", label)
        notes = format_project_notes_block(
            sections,
            when=datetime(2026, 3, 13, 12, 0, tzinfo=timezone.utc),
        )
        self.assertTrue(notes.startswith("Map brief (2026-03-13 12:00 UTC)"))
        self.assertIn("Dots", notes)

    def test_map_image_session_reads_local_png(self):
        import tempfile

        from helpers.map_stage import MapImageSession

        fd, path = tempfile.mkstemp(suffix=".png")
        try:
            os.write(fd, b"\x89PNG\r\n\x1a\n")
        finally:
            os.close(fd)
        try:
            session = MapImageSession(
                connection_name="c",
                database="DB",
                schema="PUBLIC",
            )
            session.set_local_png(path)
            self.assertEqual(session.read_png_bytes(), b"\x89PNG\r\n\x1a\n")
            session.release()
            with self.assertRaises(RuntimeError):
                session.read_png_bytes()
            session.cleanup_local_png()
            self.assertFalse(os.path.isfile(path))
        finally:
            if os.path.isfile(path):
                os.remove(path)

    def test_map_brief_task_prompt_template(self):
        task = _read("tasks/sf_map_brief_task.py")
        self.assertIn('PROMPT_TEMPLATE = "{0}\\n\\n{1}"', task)
        self.assertIn("PROMPT(%(template)s, TO_FILE(%(png_bytes)s, 'image/png')", task)
        self.assertIn("%(prompt)s)", task)
        self.assertIn("read_png_bytes", task)
        self.assertIn("normalize_cortex_text", task)
        self.assertIn("on_handle_error.emit", task)
        self.assertIn("def finished", task)
        self.assertNotIn("stage_ref", task)
        self.assertNotIn("ensure_staged", task)
        self.assertNotIn("CREATE STAGE", task)
        self.assertNotIn("restage_on_missing", task)

    def test_map_brief_dialog_and_capture_exist(self):
        dialog = _read("dialogs/sf_map_brief_dialog.py")
        self.assertIn("class SFMapBriefDialog", dialog)
        self.assertIn("Ask about this view", dialog)
        self.assertIn("Follow-up answers", dialog)
        self.assertIn("Insert into print layout", dialog)
        self.assertIn("Save to project notes", dialog)
        self.assertIn("sent to", dialog)
        self.assertIn("Snowflake Cortex", dialog)
        self.assertIn("Experimental feature", dialog)
        self.assertIn("self.help_btn", dialog)
        self.assertIn("How to use Map brief", dialog)
        self.assertIn("Focus (optional)", dialog)
        self.assertIn("road safety committee", dialog)
        self.assertIn("three short bullets", dialog)
        self.assertNotIn("audience or length", dialog)
        self.assertNotIn("Re-capture", dialog)
        self.assertNotIn("Save...", dialog)
        self.assertIn("QSignalBlocker", dialog)
        self.assertIn("fetch_cortex_base_models", dialog)
        self.assertIn("models_for_map_brief", dialog)
        self.assertIn("self.model_combo.setEditable(False)", dialog)
        self.assertIn(
            "multimodal Cortex models available for your role",
            dialog,
        )
        self.assertNotIn(
            "should be a multimodal Cortex model that can read images",
            dialog,
        )
        capture = _read("helpers/map_capture.py")
        self.assertIn("def render_canvas_png", capture)
        self.assertIn("def build_canvas_map_context", capture)
        self.assertIn("def collect_view_warnings", capture)
        stage = _read("helpers/map_stage.py")
        self.assertIn("class MapImageSession", stage)
        self.assertIn("def read_png_bytes", stage)
        self.assertNotIn("SNOWFLAKE_SSE", stage)
        self.assertNotIn("CREATE TEMPORARY STAGE", stage)
        self.assertNotIn("quote_put_file_uri", stage)


class TestExtentCacheAndCapabilities(unittest.TestCase):
    """Source and pure checks for map-extent cache safety."""

    def test_extent_cache_publishes_only_when_complete(self):
        iterator = _read("providers/sf_feature_iterator.py")
        self.assertIn("_extent_cache_buffer", iterator)
        self.assertIn("_publish_extent_cache_if_complete", iterator)
        self.assertIn("_extent_cache_pending_key", iterator)
        # Key must not be published before fetch starts.
        publish_block = iterator[
            iterator.index("self._populate_extent_cache = (")
            : iterator.index("self._extent_limit_n = None")
        ]
        self.assertNotIn("_extent_cache_key =", publish_block)

    def test_extent_cache_key_includes_attrs_and_crs(self):
        iterator = _read("providers/sf_feature_iterator.py")
        key_fn = iterator[
            iterator.index("def _build_extent_cache_key")
            : iterator.index("def _publish_extent_cache_if_complete")
        ]
        self.assertIn("nog=", key_fn)
        self.assertIn("attrs=", key_fn)
        self.assertIn("crs=", key_fn)
        self.assertIn("SubsetOfAttributes", key_fn)
        self.assertIn("destinationCrs", key_fn)

    def test_extent_mode_geometry_srid_and_single_geom_skip(self):
        iterator = _read("providers/sf_feature_iterator.py")
        self.assertIn("ST_GEOMETRYFROMWKT(", iterator)
        self.assertIn("_srid", iterator)
        self.assertIn("_single_geom_layer", iterator)
        self.assertIn("{quoted_geom} IS NOT NULL", iterator)

    def test_extent_mode_capabilities_readonly(self):
        provider = _read("providers/sf_vector_data_provider.py")
        caps = provider[
            provider.index("def capabilities")
            : provider.index("return base_capabilities")
        ]
        self.assertIn('_extent_mode', caps)
        self.assertIn("map-extent loading", caps)
        self.assertIn("_logged_readonly_reason", caps)

    def test_encode_uri_round_trip_keys(self):
        meta = _read("providers/sf_metadata_provider.py")
        self.assertIn('parts.get("sql_query"', meta)
        self.assertIn('parts.get("geom_column"', meta)
        self.assertIn("extent_mode=1", meta)
        self.assertIn("load_all_rows=1", meta)
        self.assertIn("single_geom_layer=1", meta)
        self.assertNotIn("sql={sql_query}", meta)
        self.assertNotIn("geo_column={geo_column}", meta)

    def test_convert_task_adds_layers_in_finished(self):
        task = _read("tasks/sf_convert_column_to_layer_task.py")
        run_fn = task[task.index("def run") : task.index("def cancel")]
        finished_fn = task[task.index("def finished") :]
        self.assertNotIn("QgsVectorLayer", run_fn)
        self.assertNotIn("addMapLayer", run_fn)
        self.assertIn("QgsVectorLayer", finished_fn)
        self.assertIn("addMapLayer", finished_fn)

    def test_attribute_only_passes_geom_type(self):
        data_item = _read("entities/sf_data_item.py")
        block = data_item[
            data_item.index("def _start_add_attribute_table_layer")
            : data_item.index("primary_key = prompt_and_get_primary_key")
        ]
        self.assertIn('"geom_type": ""', block)
        self.assertNotIn("{**context_information, \"geom_type\": \"\"}", block)

    def test_ask_dialog_hardening(self):
        ask = _read("dialogs/sf_ask_dialog.py")
        self.assertIn("QSignalBlocker", ask)
        self.assertIn("TABLE_CATALOG =", ask)
        self.assertNotIn("ILIKE", ask)
        self.assertIn("sent to Snowflake", ask)
        self.assertIn("Cortex on your connection", ask)
        self.assertIn("Experimental feature", ask)
        self.assertIn("read-only SELECT", ask)
        self.assertIn("_cleanup_task", ask)
        self.assertIn("self.help_btn", ask)
        self.assertIn("How to use Ask Snowflake", ask)
        self.assertIn("FAILED TO AUTHENTICATE", ask)
        brief = _read("dialogs/sf_map_brief_dialog.py")
        self.assertIn("FAILED TO AUTHENTICATE", brief)
        cortex = _read("tasks/sf_cortex_complete_task.py")
        self.assertIn("_fetch_schema_context", cortex)
        self.assertNotIn("TO_FILE", cortex)
        self.assertNotIn("CREATE STAGE", cortex)

    def test_blank_geometry_type_avoids_empty_in_list(self):
        iterator = _read("providers/sf_feature_iterator.py")
        self.assertIn(
            'self._provider._geometry_type or ""',
            iterator,
        )
        provider = _read("providers/sf_vector_data_provider.py")
        start = provider.index("def _geometry_type_filter(self)")
        # Next method after the helper (SFGeoVectorDataProvider.featureCount).
        end = provider.index("\n    def featureCount(self)", start)
        filter_fn = provider[start:end]
        self.assertIn('if not (self._geometry_type or "").strip():', filter_fn)
        self.assertIn("IS NOT NULL", filter_fn)

    def test_blank_geometry_type_discovery_helper(self):
        provider = _read("providers/sf_vector_data_provider.py")
        self.assertIn("def _discover_geometry_type_if_blank(self)", provider)
        self.assertIn("discover_geom_type", provider)
        self.assertIn("_discover_geometry_type_if_blank()", provider)

    def test_provider_init_pusherror_on_probe_failure(self):
        provider = _read("providers/sf_vector_data_provider.py")
        self.assertIn("self.pushError(message)", provider)
        self.assertIn("self.setError(QgsError(message, \"Snowflake\"))", provider)
        self.assertIn("Provider init failed:", provider)
        self.assertIn("QgsError,", provider)


if __name__ == "__main__":
    unittest.main()



