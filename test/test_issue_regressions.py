import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class TestIssueRegressions(unittest.TestCase):
    def test_utils_uses_sys_executable_and_importlib_metadata(self):
        content = (ROOT / "helpers" / "utils.py").read_text(encoding="utf-8")
        self.assertIn("import importlib.metadata", content)
        self.assertIn("def get_python_executable_path()", content)
        self.assertIn("python3_path = get_python_executable_path()", content)
        self.assertIn('"--upgrade"', content)
        self.assertIn('"cryptography"', content)

    def test_vector_provider_reload_resets_caches(self):
        content = (ROOT / "providers" / "sf_vector_data_provider.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("self._feature_count = None", content)
        self.assertIn("self._extent = None", content)

    def test_browser_queries_use_case_insensitive_filters(self):
        content = (ROOT / "entities" / "sf_data_item.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("table_catalog ILIKE", content)
        self.assertIn("TABLE_SCHEMA ILIKE", content)
        self.assertIn("TABLE_NAME ILIKE", content)

    def test_export_algorithm_has_geometry_insert_sql(self):
        content = (ROOT / "qgis_snowflake_connector_algorithm.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("def get_geometry_insert_sql(", content)
        self.assertIn("ST_GEOGFROMWKB(TO_BINARY", content)
        self.assertIn("ST_SETSRID(ST_GEOMETRYFROMWKB", content)

    def test_data_source_provider_uses_set_subtype(self):
        content = (ROOT / "providers" / "sf_data_source_provider.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("qgsField.setSubType(subType)", content)


class TestSQLSafety(unittest.TestCase):
    """Tests for Track 1: centralized SQL quoting."""

    def test_sql_helpers_exist(self):
        content = (ROOT / "helpers" / "sql.py").read_text(encoding="utf-8")
        self.assertIn("def quote_identifier(", content)
        self.assertIn("def quote_literal(", content)
        self.assertIn("def qualified_table_name(", content)

    def test_quote_identifier_basic(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "helpers.sql", ROOT / "helpers" / "sql.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        self.assertEqual(mod.quote_identifier("foo"), '"foo"')
        self.assertEqual(mod.quote_identifier('foo"bar'), '"foo""bar"')
        self.assertEqual(mod.quote_identifier(""), '""')

    def test_quote_literal_basic(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "helpers.sql", ROOT / "helpers" / "sql.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        self.assertEqual(mod.quote_literal("foo"), "'foo'")
        self.assertEqual(mod.quote_literal("it's"), "'it''s'")

    def test_qualified_table_name(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "helpers.sql", ROOT / "helpers" / "sql.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        self.assertEqual(
            mod.qualified_table_name("DB", "SCH", "TBL"),
            '"DB"."SCH"."TBL"',
        )

    def test_data_base_uses_quote_helpers(self):
        content = (ROOT / "helpers" / "data_base.py").read_text(encoding="utf-8")
        self.assertIn("from ..helpers.sql import", content)
        self.assertIn("quote_literal(", content)
        self.assertIn("quote_identifier(", content)

    def test_algorithm_uses_quote_helpers(self):
        content = (ROOT / "qgis_snowflake_connector_algorithm.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("from .helpers.sql import", content)
        self.assertIn("qualified_table_name(", content)
        self.assertIn("quote_literal(", content)
        self.assertNotIn("replace(\"'\", \"\\\\'\")", content)

    def test_feature_iterator_uses_quote_identifier(self):
        content = (ROOT / "providers" / "sf_feature_iterator.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("from ..helpers.sql import quote_identifier", content)
        self.assertIn("quote_identifier(", content)

    def test_vector_provider_uses_quote_helpers(self):
        content = (ROOT / "providers" / "sf_vector_data_provider.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("from ..helpers.sql import", content)
        self.assertIn("quote_identifier(", content)

    def test_connection_manager_uses_quote_identifier(self):
        content = (ROOT / "managers" / "sf_connection_manager.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("from ..helpers.sql import quote_identifier", content)

    def test_dialogs_use_quote_helpers(self):
        content_table = (ROOT / "dialogs" / "sf_new_table_dialog.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("qualified_table_name(", content_table)
        content_schema = (ROOT / "dialogs" / "sf_new_schema_dialog.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("quote_identifier(", content_schema)


class TestProviderLifecycle(unittest.TestCase):
    """Tests for Track 3: provider cache correctness and geometry handling."""

    def test_reload_data_resets_all_caches(self):
        """reloadData() must clear features list, loaded flag, count, and extent."""
        content = (ROOT / "providers" / "sf_vector_data_provider.py").read_text(
            encoding="utf-8"
        )
        idx = content.index("def reloadData(self)")
        next_def = content.index("\n    def ", idx + 1)
        body = content[idx:next_def]
        self.assertIn("self._features = []", body)
        self.assertIn("self._features_loaded = False", body)
        self.assertIn("self._feature_count = None", body)
        self.assertIn("self._extent = None", body)

    def test_subset_string_triggers_reload(self):
        """setSubsetString with updateFeatureCount must call reloadData."""
        content = (ROOT / "providers" / "sf_vector_data_provider.py").read_text(
            encoding="utf-8"
        )
        idx = content.index("def setSubsetString(")
        next_def = content.index("\n    def ", idx + 1)
        body = content[idx:next_def]
        self.assertIn("self._feature_count = None", body)
        self.assertIn("self.reloadData()", body)

    def test_geometry_insert_sql_null_handling(self):
        """get_geometry_insert_sql must return 'NULL' for empty hex strings."""
        content = (ROOT / "qgis_snowflake_connector_algorithm.py").read_text(
            encoding="utf-8"
        )
        idx = content.index("def get_geometry_insert_sql(")
        next_def = content.index("\n    def ", idx + 1) if "\n    def " in content[idx + 1:] else len(content)
        body = content[idx:next_def]
        self.assertIn('if hex_string == "":', body)
        self.assertIn('return "NULL"', body)

    def test_geometry_insert_sql_geography_path(self):
        content = (ROOT / "qgis_snowflake_connector_algorithm.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("ST_GEOGFROMWKB(TO_BINARY(", content)

    def test_geometry_insert_sql_geometry_path(self):
        content = (ROOT / "qgis_snowflake_connector_algorithm.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("ST_SETSRID(ST_GEOMETRYFROMWKB(TO_BINARY(", content)

    def test_limits_constants_exist(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "helpers.limits", ROOT / "helpers" / "limits.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        self.assertEqual(mod.DEFAULT_ROW_LIMIT, 50_000)
        self.assertEqual(mod.H3_ROW_LIMIT, 500_000)
        self.assertIn("NUMBER", mod.H3_COLUMN_TYPES)
        self.assertIn("TEXT", mod.H3_COLUMN_TYPES)
        self.assertIn("H3GEO", mod.H3_COLUMN_TYPES)

    def test_limits_function_uses_constants(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "helpers.limits", ROOT / "helpers" / "limits.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        self.assertEqual(mod.limit_size_for_type("GEOGRAPHY"), mod.DEFAULT_ROW_LIMIT)
        self.assertEqual(mod.limit_size_for_type("GEOMETRY"), mod.DEFAULT_ROW_LIMIT)
        self.assertEqual(mod.limit_size_for_type("NUMBER"), mod.H3_ROW_LIMIT)
        self.assertEqual(mod.limit_size_for_type("TEXT"), mod.H3_ROW_LIMIT)
        self.assertEqual(mod.limit_size_for_type("H3GEO"), mod.H3_ROW_LIMIT)

    def test_feature_iterator_uses_limits_import(self):
        content = (ROOT / "providers" / "sf_feature_iterator.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("from ..helpers.limits import limit_size_for_type", content)


class TestUIBoundary(unittest.TestCase):
    """Tests for Track 4: generated-ui vs dialogs boundary."""

    def test_ui_readme_exists(self):
        readme = ROOT / "ui" / "README.md"
        self.assertTrue(readme.exists(), "ui/README.md should exist")
        content = readme.read_text(encoding="utf-8")
        self.assertIn("pyuic6", content)
        self.assertIn("do not edit", content.lower())

    def test_generated_ui_files_have_warning(self):
        ui_dir = ROOT / "ui"
        for py_file in sorted(ui_dir.glob("*.py")):
            content = py_file.read_text(encoding="utf-8")
            if content.strip() == "":
                continue
            self.assertIn(
                "generated",
                content[:300].lower(),
                f"{py_file.name} missing generated-file header",
            )

    def test_dialogs_import_from_ui(self):
        """Each dialog wrapper should import its generated UI base class."""
        dialogs_dir = ROOT / "dialogs"
        for py_file in sorted(dialogs_dir.glob("*.py")):
            if py_file.name == "__init__.py":
                continue
            content = py_file.read_text(encoding="utf-8")
            has_ui_import = "from ..ui." in content
            self.assertTrue(
                has_ui_import,
                f"{py_file.name} should import from ..ui.*",
            )

    def test_no_raw_pyqt_imports(self):
        """All plugin code should use qgis.PyQt, not raw PyQt5/PyQt6 imports."""
        for py_file in sorted(ROOT.rglob("*.py")):
            rel = py_file.relative_to(ROOT)
            if str(rel).startswith("scripts"):
                continue
            if str(rel).startswith("test"):
                continue
            content = py_file.read_text(encoding="utf-8")
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                self.assertNotRegex(
                    stripped,
                    r"^(from|import)\s+PyQt[56]",
                    f"{rel} uses raw PyQt import: {stripped}",
                )


class TestStartupReliability(unittest.TestCase):
    """Tests for Track 2: guarded startup and dependency diagnostics."""

    def test_init_has_stub_plugin(self):
        content = (ROOT / "__init__.py").read_text(encoding="utf-8")
        self.assertIn("class _StubPlugin", content)
        self.assertIn("def initGui(self)", content)
        self.assertIn("def unload(self)", content)

    def test_init_checks_missing_deps(self):
        content = (ROOT / "__init__.py").read_text(encoding="utf-8")
        self.assertIn("missing = []", content)
        self.assertIn("check_package_installed", content)
        self.assertIn("QgsMessageLog.logMessage(", content)
        self.assertIn("return _StubPlugin()", content)

    def test_check_install_package_returns_bool(self):
        content = (ROOT / "helpers" / "utils.py").read_text(encoding="utf-8")
        self.assertIn("def check_install_package(package_name) -> bool:", content)
        self.assertIn("def check_install_snowflake_connector_package() -> bool:", content)
        self.assertIn("def check_install_h3_package() -> bool:", content)

    def test_check_install_package_has_exception_guard(self):
        content = (ROOT / "helpers" / "utils.py").read_text(encoding="utf-8")
        idx_func = content.index("def check_install_package(")
        idx_next = content.index("\ndef ", idx_func + 1)
        func_body = content[idx_func:idx_next]
        self.assertIn("except Exception:", func_body)
        self.assertIn("return check_package_installed(package_name)", func_body)


class TestQualityBaseline(unittest.TestCase):
    """Tests for Track 5: CONTRIBUTING and CI baseline."""

    def test_ci_workflow_exists(self):
        path = ROOT / ".github" / "workflows" / "ci.yml"
        self.assertTrue(path.exists(), ".github/workflows/ci.yml should exist")
        content = path.read_text(encoding="utf-8")
        self.assertIn("flake8", content)
        self.assertIn("py_compile", content)
        self.assertIn("test_issue_regressions", content)

    def test_tests_are_split_by_track(self):
        """Test file should have separate classes for each improvement track."""
        content = (ROOT / "test" / "test_issue_regressions.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("class TestIssueRegressions", content)
        self.assertIn("class TestSQLSafety", content)
        self.assertIn("class TestStartupReliability", content)
        self.assertIn("class TestProviderLifecycle", content)
        self.assertIn("class TestUIBoundary", content)
        self.assertIn("class TestQualityBaseline", content)


if __name__ == "__main__":
    unittest.main()
