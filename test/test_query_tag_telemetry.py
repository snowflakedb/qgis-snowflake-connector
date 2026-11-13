"""Unit and source-coverage tests for structured QUERY_TAG telemetry."""

from __future__ import annotations

import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_connection_manager(testcase: unittest.TestCase):
    """Load sf_connection_manager with stubbed qgis/snowflake deps."""
    names = (
        "snowflake",
        "snowflake.connector",
        "snowflake.connector.cursor",
        "qgis",
        "qgis.core",
        "qgis_snowflake_connector",
        "qgis_snowflake_connector.managers",
        "qgis_snowflake_connector.managers.sf_connection_manager",
        "qgis_snowflake_connector.helpers",
        "qgis_snowflake_connector.helpers.utils",
        "qgis_snowflake_connector.helpers.sql",
    )
    saved = {n: sys.modules.get(n) for n in names}

    def _restore():
        for n, prev in saved.items():
            if prev is None:
                sys.modules.pop(n, None)
            else:
                sys.modules[n] = prev

    testcase.addCleanup(_restore)

    snowflake = types.ModuleType("snowflake")
    connector = types.ModuleType("snowflake.connector")
    connector.SnowflakeConnection = type("SnowflakeConnection", (), {})
    connector.connect = lambda **_k: (_ for _ in ()).throw(RuntimeError("no connect"))
    cursor_mod = types.ModuleType("snowflake.connector.cursor")
    cursor_mod.SnowflakeCursor = type("SnowflakeCursor", (), {})
    connector.cursor = cursor_mod
    snowflake.connector = connector

    qgis = types.ModuleType("qgis")
    core = types.ModuleType("qgis.core")
    core.Qgis = type(
        "Qgis", (), {"MessageLevel": type("ML", (), {"Critical": 0, "Warning": 1})}
    )
    core.QgsMessageLog = type(
        "QgsMessageLog", (), {"logMessage": staticmethod(lambda *a, **k: None)}
    )
    qgis.core = core

    plugin_pkg = types.ModuleType("qgis_snowflake_connector")
    plugin_pkg.__path__ = [str(ROOT)]
    managers_pkg = types.ModuleType("qgis_snowflake_connector.managers")
    managers_pkg.__path__ = [str(ROOT / "managers")]
    helpers_pkg = types.ModuleType("qgis_snowflake_connector.helpers")
    helpers_pkg.__path__ = [str(ROOT / "helpers")]
    helpers_utils = types.ModuleType("qgis_snowflake_connector.helpers.utils")
    helpers_utils.get_auth_information = lambda name: {}
    helpers_utils.connection_settings_exist = lambda name: True
    helpers_sql = types.ModuleType("qgis_snowflake_connector.helpers.sql")
    helpers_sql.quote_identifier = lambda n: n

    for mod in (
        snowflake,
        connector,
        cursor_mod,
        qgis,
        core,
        plugin_pkg,
        managers_pkg,
        helpers_pkg,
        helpers_utils,
        helpers_sql,
    ):
        sys.modules[mod.__name__] = mod

    spec = importlib.util.spec_from_file_location(
        "qgis_snowflake_connector.managers.sf_connection_manager",
        ROOT / "managers" / "sf_connection_manager.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TestBuildOpTag(unittest.TestCase):
    def setUp(self):
        self.mod = _load_connection_manager(self)

    def test_always_json_with_app_ver_op_kind(self):
        tag = self.mod.build_op_tag("features", connection_name="c1")
        payload = json.loads(tag)
        self.assertEqual(payload["app"], "qgis-snowflake-connector")
        self.assertIn("ver", payload)
        self.assertTrue(payload["ver"])
        self.assertEqual(payload["op"], "features")
        self.assertEqual(payload["kind"], "sql")
        self.assertEqual(payload["conn"], "c1")

    def test_layer_and_model_fields(self):
        tag = self.mod.build_op_tag(
            "cortex_complete",
            connection_name="c1",
            schema="PUBLIC",
            table="T",
            model="llama3.1-70b",
        )
        payload = json.loads(tag)
        self.assertEqual(payload["layer"], "PUBLIC.T")
        self.assertEqual(payload["model"], "llama3.1-70b")
        self.assertEqual(payload["kind"], "cortex")

    def test_default_and_untagged_are_structured(self):
        for factory, op in (
            (self.mod.default_query_tag, "session"),
            (self.mod.untagged_query_tag, "untagged"),
        ):
            payload = json.loads(factory())
            self.assertEqual(payload["app"], "qgis-snowflake-connector")
            self.assertEqual(payload["op"], op)
            self.assertIn("ver", payload)


class TestApplyQueryTag(unittest.TestCase):
    def setUp(self):
        self.mod = _load_connection_manager(self)

    def test_none_op_tag_applies_structured_untagged(self):
        class FakeCursor:
            def __init__(self):
                self.statements = []

            def execute(self, sql):
                self.statements.append(sql)

        mgr = self.mod.SFConnectionManager.get_instance()
        mgr._active_query_tags = {}
        cur = FakeCursor()
        mgr._apply_query_tag_if_changed(cur, "conn_a", None)
        self.assertEqual(len(cur.statements), 1)
        self.assertIn("ALTER SESSION SET QUERY_TAG", cur.statements[0])
        applied = mgr._active_query_tags["conn_a"]
        payload = json.loads(applied)
        self.assertEqual(payload["op"], "untagged")
        # Second call with None must not re-issue ALTER SESSION
        mgr._apply_query_tag_if_changed(cur, "conn_a", None)
        self.assertEqual(len(cur.statements), 1)

    def test_cache_skips_identical_tag(self):
        class FakeCursor:
            def __init__(self):
                self.statements = []

            def execute(self, sql):
                self.statements.append(sql)

        mgr = self.mod.SFConnectionManager.get_instance()
        mgr._active_query_tags = {}
        cur = FakeCursor()
        tag = self.mod.build_op_tag("features", connection_name="c")
        mgr._apply_query_tag_if_changed(cur, "c", tag)
        mgr._apply_query_tag_if_changed(cur, "c", tag)
        self.assertEqual(len(cur.statements), 1)


class TestQueryTagSourceCoverage(unittest.TestCase):
    """Major paths must pass op_tag= into execute_query*."""

    def _read(self, rel: str) -> str:
        return (ROOT / rel).read_text()

    def test_iterator_features_tag(self):
        src = self._read("providers/sf_feature_iterator.py")
        self.assertIn('"features"', src)
        self.assertIn("op_tag=build_op_tag(", src)

    def test_cortex_tasks_include_model(self):
        complete = self._read("tasks/sf_cortex_complete_task.py")
        brief = self._read("tasks/sf_map_brief_task.py")
        self.assertIn('"cortex_complete"', complete)
        self.assertIn("model=self.model", complete)
        self.assertIn('"cortex_map_brief"', brief)
        self.assertIn("model=self.model", brief)

    def test_map_stage_ops(self):
        src = self._read("helpers/map_stage.py")
        for action in ("create", "put", "remove"):
            self.assertIn(f'"{action}"', src)
        self.assertIn("stage_create", src)
        self.assertIn("stage_put", src)
        self.assertIn("stage_remove", src)

    def test_processing_entrypoints_tag(self):
        expectations = {
            "processing/execute_sql.py": "proc_sql",
            "processing/import_from_snowflake.py": "proc_import",
            "processing/buffer_table.py": "proc_buffer",
            "processing/spatial_join.py": "proc_join",
            "processing/h3_index.py": "proc_h3",
        }
        for path, op in expectations.items():
            src = self._read(path)
            self.assertIn(f'build_op_tag("{op}"', src, path)
            self.assertIn("op_tag=", src, path)

    def test_data_source_provider_forwards_op_tag(self):
        src = self._read("providers/sf_data_source_provider.py")
        self.assertIn("op_tag: typing.Optional[str] = None", src)
        self.assertIn("op_tag=op_tag", src)

    def test_provider_featurecount_and_extent(self):
        src = self._read("providers/sf_vector_data_provider.py")
        self.assertIn('"featurecount"', src)
        self.assertIn('"extent"', src)
        self.assertIn('"fields"', src)


if __name__ == "__main__":
    unittest.main()
