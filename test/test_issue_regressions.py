import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class TestIssueRegressions(unittest.TestCase):
    def test_utils_uses_importlib_metadata(self):
        content = (ROOT / "helpers" / "utils.py").read_text(encoding="utf-8")
        self.assertIn("import importlib.metadata", content)

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

    def test_browser_shows_non_geo_tables(self):
        """Geo-type filter should only apply at column level, not schema/table level."""
        content = (ROOT / "entities" / "sf_data_item.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('if self.item_type == "table":', content)
        self.assertIn("geo_type_filter", content)
        self.assertIn("not self.geom_column", content)

    def test_export_algorithm_has_geometry_insert_sql(self):
        content = (ROOT / "qgis_snowflake_connector_algorithm.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("def get_geometry_insert_sql(", content)
        self.assertIn("ST_GEOGFROMWKB(TO_BINARY", content)
        self.assertIn("ST_SETSRID(ST_GEOMETRYFROMWKB", content)

    def test_export_select_projection_applies_geometry_conversion(self):
        """The SELECT projection must wrap the geometry alias with spatial functions."""
        content = (ROOT / "qgis_snowflake_connector_algorithm.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("ST_GEOGFROMWKB(TO_BINARY(v.", content)
        self.assertIn("ST_SETSRID(ST_GEOMETRYFROMWKB(TO_BINARY(v.", content)

    def test_export_values_null_for_empty_geometry(self):
        """Empty hex_string must produce NULL in the VALUES tuple, not empty string."""
        content = (ROOT / "qgis_snowflake_connector_algorithm.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('if hex_string == "":', content)
        self.assertIn('query += "(NULL"', content)

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

        self.assertEqual(mod.quote_identifier("foo"), 'foo')
        self.assertEqual(mod.quote_identifier("FOO_BAR"), 'FOO_BAR')
        self.assertEqual(mod.quote_identifier('foo"bar'), '"foo""bar"')
        self.assertEqual(mod.quote_identifier("col name"), '"col name"')
        self.assertEqual(mod.quote_identifier(""), '""')
        self.assertEqual(mod.quote_identifier('"already_quoted"'), '"already_quoted"')

    def test_quote_literal_basic(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "helpers.sql", ROOT / "helpers" / "sql.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        self.assertEqual(mod.quote_literal("foo"), "'foo'")
        self.assertEqual(mod.quote_literal("it's"), "'it''s'")

    def test_quote_json_literal_for_parse_json_prefers_dollar_quotes(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "helpers.sql", ROOT / "helpers" / "sql.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        payload = '{"name":"O\'Brien"}'
        self.assertEqual(
            mod.quote_json_literal_for_parse_json(payload),
            f"$${payload}$$",
        )

    def test_quote_json_literal_for_parse_json_strict_raises_when_delimiter_present(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "helpers.sql", ROOT / "helpers" / "sql.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        payload = '{"k":"contains $$ delimiter and it\'s ok"}'
        with self.assertRaises(ValueError):
            mod.quote_json_literal_for_parse_json(payload)

    def test_qualified_table_name(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "helpers.sql", ROOT / "helpers" / "sql.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        self.assertEqual(
            mod.qualified_table_name("DB", "SCH", "TBL"),
            'DB.SCH.TBL',
        )
        self.assertEqual(
            mod.qualified_table_name("my db", "SCH", "TBL"),
            '"my db".SCH.TBL',
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
        self.assertIn("PARSE_JSON(v.", content)
        self.assertNotIn("replace(\"'\", \"\\\\'\")", content)

    def test_algorithm_variant_insert_uses_select_over_values_alias(self):
        content = (ROOT / "qgis_snowflake_connector_algorithm.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("SELECT {','.join(select_projection)} FROM VALUES", content)
        self.assertIn("AS v({','.join(value_aliases)})", content)
        self.assertIn("PARSE_JSON(v.{alias})", content)

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

    def test_reload_data_resets_feature_caches(self):
        """reloadData() must clear features, count, extent but preserve _fields."""
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
        self.assertNotIn("self._fields = None", body,
                         "reloadData must NOT reset _fields to preserve column order")
        self.assertIn("self.connect_database()", body)

    def test_fields_query_filters_by_schema(self):
        """fields() INFORMATION_SCHEMA query must include table_schema ILIKE filter."""
        content = (ROOT / "providers" / "sf_vector_data_provider.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("table_schema ILIKE", content)

    def test_feature_iterator_logs_errors(self):
        """fetchFeature() must log attribute errors via QgsMessageLog, not print()."""
        content = (ROOT / "providers" / "sf_feature_iterator.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("QgsMessageLog.logMessage(", content)
        self.assertNotIn(
            'print(\n                                    f"Feature Iterator Error',
            content,
        )

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
        skip = {"__init__.py", "sf_spatial_filter_dialog.py"}
        for py_file in sorted(dialogs_dir.glob("*.py")):
            if py_file.name in skip:
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
            if str(rel).startswith(("scripts", "test", "zip_build")):
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

    def test_init_catches_import_errors(self):
        """classFactory must catch ImportError during plugin load and return stub."""
        content = (ROOT / "__init__.py").read_text(encoding="utf-8")
        self.assertIn("except ImportError as imp_err:", content)
        self.assertIn("cryptography", content)
        self.assertIn("ExtensionOID", content)

    def test_check_install_package_returns_bool(self):
        content = (ROOT / "helpers" / "utils.py").read_text(encoding="utf-8")
        self.assertIn("def check_install_package(package_name) -> bool:", content)
        self.assertIn("def check_install_snowflake_connector_package() -> bool:", content)

    def test_check_install_package_delegates_to_check_package_installed(self):
        content = (ROOT / "helpers" / "utils.py").read_text(encoding="utf-8")
        idx_func = content.index("def check_install_package(")
        idx_next = content.index("\ndef ", idx_func + 1)
        func_body = content[idx_func:idx_next]
        self.assertIn("return check_package_installed(package_name)", func_body)
        self.assertNotIn("subprocess", func_body)
        self.assertNotIn("pip._internal", func_body)


class TestEditabilityCapabilities(unittest.TestCase):
    """Tests for GeoJSON editability / provider capability gating."""

    def _get_provider_content(self):
        return (ROOT / "providers" / "sf_vector_data_provider.py").read_text(
            encoding="utf-8"
        )

    def test_context_information_sets_table_name(self):
        """__init__ must add table_name to _context_information when _table_name is set."""
        content = self._get_provider_content()
        self.assertIn("if self._table_name:", content)
        self.assertNotIn(
            'if "table_name" in self._context_information:',
            content,
            "Dead conditional should be replaced with 'if self._table_name:'",
        )

    def test_capabilities_uses_geo_column_type_for_h3(self):
        """H3 read-only gate must check _geo_column_type, not _geometry_type == 'H3'."""
        content = self._get_provider_content()
        self.assertNotIn(
            '_geometry_type == "H3"',
            content,
            "capabilities() should not compare _geometry_type to 'H3'",
        )
        self.assertIn(
            '_geo_column_type not in ("GEOGRAPHY", "GEOMETRY")',
            content,
        )

    def test_capabilities_editable_for_geography_with_pk(self):
        """Verify capabilities logic allows editing for GEOGRAPHY/GEOMETRY with PK."""
        content = self._get_provider_content()
        idx = content.index("def capabilities(self)")
        next_def = content.index("\n    def ", idx + 1)
        body = content[idx:next_def]
        self.assertIn('self._primary_key == ""', body)
        self.assertIn("self._sql_query is not None", body)
        self.assertIn("AddFeatures", body)
        self.assertIn("ChangeGeometries", body)

    def test_change_geometry_values_propagates_failure(self):
        """changeGeometryValues must propagate update_table_feature failure."""
        content = self._get_provider_content()
        idx = content.index("def changeGeometryValues(")
        next_def = content.index("\n    def ", idx + 1)
        body = content[idx:next_def]
        self.assertIn("if not update_table_feature(context):", body)
        self.assertIn("all_ok = False", body)
        self.assertIn("return all_ok", body)

    def test_update_table_feature_logs_on_failure(self):
        """update_table_feature must log to QgsMessageLog on exception."""
        content = (ROOT / "helpers" / "data_base.py").read_text(encoding="utf-8")
        idx = content.index("def update_table_feature(")
        body = content[idx:]
        self.assertIn("QgsMessageLog.logMessage(", body)
        self.assertIn("update_table_feature failed", body)

    def _decode_uri(self, uri):
        """Replicates the decodeUri regex from helpers/utils.py for CI testing."""
        import re
        supported_keys = [
            "connection_name", "sql_query", "schema_name", "table_name",
            "srid", "geom_column", "geometry_type", "geo_column_type",
            "primary_key",
        ]
        matches = re.findall(
            f"({'|'.join(supported_keys)})=(.*?) *?(?={'|'.join(supported_keys)}=|$)",
            uri, flags=re.DOTALL,
        )
        return {key: value for key, value in matches}

    def test_uri_parsing_primary_key_roundtrip(self):
        """Verify decodeUri extracts primary_key correctly from browser-style URI."""
        uri = (
            "connection_name=myconn sql_query= "
            "schema_name=PUBLIC "
            "table_name=MYTABLE srid=4326 "
            "geom_column=GEOM "
            "geometry_type=Polygon "
            "geo_column_type=GEOGRAPHY "
            "primary_key=ID"
        )
        params = self._decode_uri(uri)
        self.assertEqual(params.get("primary_key"), "ID")
        self.assertEqual(params.get("sql_query"), "")

    def test_uri_parsing_empty_primary_key(self):
        """Verify decodeUri returns empty primary_key when none selected."""
        uri = (
            "connection_name=myconn sql_query= "
            "schema_name=PUBLIC "
            "table_name=MYTABLE srid=4326 "
            "geom_column=GEOM "
            "geometry_type=Polygon "
            "geo_column_type=GEOGRAPHY "
            "primary_key="
        )
        params = self._decode_uri(uri)
        self.assertEqual(params.get("primary_key"), "")


class TestUpdateNotification(unittest.TestCase):
    """Tests for #92: plugin update notification."""

    def test_plugin_has_update_check(self):
        content = (ROOT / "qgis_snowflake_connector.py").read_text(encoding="utf-8")
        self.assertIn("_check_for_updates", content)
        self.assertIn("releases/latest", content)
        self.assertIn("threading.Thread", content)

    def test_update_check_uses_metadata_version(self):
        content = (ROOT / "qgis_snowflake_connector.py").read_text(encoding="utf-8")
        self.assertIn("metadata.txt", content)
        self.assertIn("local_version", content)


class TestKeyPairAuth(unittest.TestCase):
    """Tests for #103: key pair authentication support."""

    def test_connection_dialog_has_key_pair_option(self):
        content = (ROOT / "dialogs" / "sf_connection_string_dialog.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"Key Pair"', content)
        self.assertIn("_txtKeyFile", content)
        self.assertIn("_txtKeyPassphrase", content)
        self.assertIn("_browse_key_file", content)

    def test_connection_manager_handles_key_pair(self):
        content = (ROOT / "managers" / "sf_connection_manager.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"Key Pair"', content)
        self.assertIn("private_key_file", content)
        self.assertIn("private_key_file_pwd", content)

    def test_settings_persist_key_pair_fields(self):
        content = (ROOT / "helpers" / "utils.py").read_text(encoding="utf-8")
        self.assertIn('"private_key_file"', content)
        self.assertIn('"key_passphrase"', content)


class TestH3TextNormalization(unittest.TestCase):
    """Tests that H3 cells are normalized to TEXT (hex string) internally."""

    def _get_iterator_content(self):
        return (ROOT / "providers" / "sf_feature_iterator.py").read_text(
            encoding="utf-8"
        )

    def _get_algorithm_content(self):
        return (ROOT / "qgis_snowflake_connector_algorithm.py").read_text(
            encoding="utf-8"
        )

    def test_no_python_h3_dependency(self):
        """Python h3 package must not be imported."""
        content = self._get_iterator_content()
        self.assertNotIn("import h3", content)

    def test_boundary_computed_server_side(self):
        """H3 boundary conversion uses Snowflake H3_CELL_TO_BOUNDARY."""
        content = self._get_iterator_content()
        self.assertIn("H3_CELL_TO_BOUNDARY", content)

    def test_number_h3_normalized_to_string(self):
        """NUMBER H3 columns are normalized to TEXT via H3_INT_TO_STRING."""
        content = self._get_iterator_content()
        self.assertIn("H3_INT_TO_STRING", content)

    def test_attribute_skip_preserves_h3(self):
        """Attribute skip condition allows H3 values through."""
        content = self._get_iterator_content()
        self.assertIn('not in ("NUMBER", "TEXT")', content)

    def test_sql_query_task_detects_h3_text_vs_number(self):
        """SQL query task distinguishes TEXT vs NUMBER H3 columns."""
        content = (ROOT / "tasks" / "sf_convert_sql_query_to_layer_task.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"TEXT"', content)
        self.assertIn('"NUMBER"', content)
        self.assertIn("h3_sf_col_type", content)


class TestPrimaryKeyValidation(unittest.TestCase):
    """Tests that primary key selection validates for duplicate values."""

    def _get_utils_content(self):
        return (ROOT / "helpers" / "utils.py").read_text(encoding="utf-8")

    def _get_database_content(self):
        return (ROOT / "helpers" / "data_base.py").read_text(encoding="utf-8")

    def test_check_column_has_duplicates_exists(self):
        """data_base.py must have a check_column_has_duplicates function."""
        content = self._get_database_content()
        self.assertIn("def check_column_has_duplicates(", content)

    def test_check_column_has_duplicates_uses_count_distinct(self):
        """The duplicate check must compare COUNT(*) vs COUNT(DISTINCT col)."""
        content = self._get_database_content()
        idx = content.index("def check_column_has_duplicates(")
        next_def = content.index("\ndef ", idx + 1)
        body = content[idx:next_def]
        self.assertIn("COUNT(*)", body)
        self.assertIn("COUNT(DISTINCT", body)
        self.assertIn("quote_identifier(column_name)", body)

    def test_prompt_calls_duplicate_check(self):
        """prompt_and_get_primary_key must call check_column_has_duplicates."""
        content = self._get_utils_content()
        idx = content.index("def prompt_and_get_primary_key(")
        next_def = content.index("\ndef ", idx + 1) if "\ndef " in content[idx + 1:] else len(content)
        body = content[idx:next_def]
        self.assertIn("check_column_has_duplicates", body)

    def test_prompt_warns_on_duplicates(self):
        """prompt_and_get_primary_key must show a warning when duplicates exist."""
        content = self._get_utils_content()
        self.assertIn("Duplicate Values Detected", content)


class TestEditingOperations(unittest.TestCase):
    """Tests that all declared editing capabilities have implementations."""

    def _get_provider_content(self):
        return (ROOT / "providers" / "sf_vector_data_provider.py").read_text(
            encoding="utf-8"
        )

    def _get_database_content(self):
        return (ROOT / "helpers" / "data_base.py").read_text(encoding="utf-8")

    def test_change_attribute_values_implemented(self):
        """changeAttributeValues must be implemented in the provider."""
        content = self._get_provider_content()
        self.assertIn("def changeAttributeValues(self", content)

    def test_add_features_implemented(self):
        """addFeatures must be implemented in the provider."""
        content = self._get_provider_content()
        self.assertIn("def addFeatures(self", content)

    def test_delete_features_implemented(self):
        """deleteFeatures must be implemented in the provider."""
        content = self._get_provider_content()
        self.assertIn("def deleteFeatures(self", content)

    def test_add_attributes_implemented(self):
        """addAttributes must be implemented with ALTER TABLE ADD COLUMN."""
        content = self._get_provider_content()
        self.assertIn("def addAttributes(self", content)
        db_content = self._get_database_content()
        self.assertIn("def alter_table_add_columns(", db_content)
        self.assertIn("ALTER TABLE", db_content)
        self.assertIn("ADD COLUMN", db_content)

    def test_delete_attributes_implemented(self):
        """deleteAttributes must be implemented with ALTER TABLE DROP COLUMN."""
        content = self._get_provider_content()
        self.assertIn("def deleteAttributes(self", content)
        db_content = self._get_database_content()
        self.assertIn("def alter_table_drop_columns(", db_content)
        self.assertIn("DROP COLUMN", db_content)

    def _get_func_body(self, content, func_name):
        idx = content.index(f"def {func_name}(")
        next_def = content.find("\ndef ", idx + 1)
        return content[idx:next_def] if next_def != -1 else content[idx:]

    def test_update_table_attributes_helper_exists(self):
        """data_base.py must have update_table_attributes helper."""
        content = self._get_database_content()
        body = self._get_func_body(content, "update_table_attributes")
        self.assertIn("UPDATE", body)
        self.assertIn("SET", body)
        self.assertIn("WHERE", body)

    def test_insert_table_feature_helper_exists(self):
        """data_base.py must have insert_table_feature helper."""
        content = self._get_database_content()
        body = self._get_func_body(content, "insert_table_feature")
        self.assertIn("INSERT INTO", body)
        self.assertIn("VALUES", body)

    def test_delete_table_features_helper_exists(self):
        """data_base.py must have delete_table_features helper."""
        content = self._get_database_content()
        body = self._get_func_body(content, "delete_table_features")
        self.assertIn("DELETE FROM", body)
        self.assertIn("IN (", body)

    def test_provider_imports_all_helpers(self):
        """Provider must import all editing helpers."""
        content = self._get_provider_content()
        for helper in [
            "update_table_attributes",
            "insert_table_feature",
            "delete_table_features",
            "alter_table_add_columns",
            "alter_table_drop_columns",
        ]:
            self.assertIn(helper, content)

    def test_context_information_includes_database_name(self):
        """_context_information must include database_name for FQ table refs."""
        content = self._get_provider_content()
        self.assertIn('database_name', content)
        self.assertIn('_auth_information', content)

    def test_qgis_to_snowflake_type_mapping(self):
        """Provider must have _QGIS_TO_SF_TYPE mapping for addAttributes."""
        content = self._get_provider_content()
        self.assertIn("_QGIS_TO_SF_TYPE", content)
        for sf_type in ["TEXT", "INTEGER", "DOUBLE", "DATE", "BOOLEAN"]:
            self.assertIn(f'"{sf_type}"', content)

    def test_all_helpers_log_errors(self):
        """All DML helpers must log errors via QgsMessageLog."""
        content = self._get_database_content()
        for func in [
            "update_table_attributes",
            "insert_table_feature",
            "delete_table_features",
            "alter_table_add_columns",
            "alter_table_drop_columns",
        ]:
            idx = content.index(f"def {func}(")
            next_def_pos = content.find("\ndef ", idx + 1)
            body = content[idx:next_def_pos] if next_def_pos != -1 else content[idx:]
            self.assertIn("QgsMessageLog.logMessage", body,
                          f"{func} must log errors")

    def test_editing_methods_call_reload_or_update_cache(self):
        """Editing methods must call reloadData() to refresh the cache."""
        content = self._get_provider_content()
        for method in ["addFeatures", "deleteFeatures", "changeAttributeValues"]:
            idx = content.index(f"def {method}(self")
            next_def = content.index("\n    def ", idx + 1)
            body = content[idx:next_def]
            self.assertIn("reloadData()", body,
                          f"{method} must call reloadData()")
        idx = content.index("def changeAttributeValues(self")
        next_def = content.index("\n    def ", idx + 1)
        body = content[idx:next_def]
        self.assertIn("update_table_attributes", body,
                      "changeAttributeValues must persist to Snowflake")

    def test_editing_methods_propagate_errors_via_push_error(self):
        """All editing methods must call pushError() to surface Snowflake errors."""
        content = self._get_provider_content()
        for method in [
            "changeAttributeValues", "addFeatures", "deleteFeatures",
            "addAttributes", "deleteAttributes",
        ]:
            idx = content.index(f"def {method}(self")
            next_def = content.find("\n    def ", idx + 1)
            body = content[idx:next_def] if next_def != -1 else content[idx:]
            self.assertIn("self.pushError(", body,
                          f"{method} must call pushError() to propagate Snowflake errors")


    def test_reload_data_preserves_fields(self):
        """reloadData() must NOT reset _fields to avoid column order scrambling."""
        content = self._get_provider_content()
        idx = content.index("def reloadData(self)")
        next_def = content.index("\n    def ", idx + 1)
        body = content[idx:next_def]
        self.assertNotIn("self._fields = None", body,
                         "reloadData() must not reset _fields")

    def test_default_value_implemented_for_primary_key(self):
        """Provider must implement defaultValue() for auto-increment PK."""
        content = self._get_provider_content()
        self.assertIn("def defaultValue(self", content)
        idx = content.index("def defaultValue(self")
        next_def = content.index("\n    def ", idx + 1)
        body = content[idx:next_def]
        self.assertIn("_primary_key", body,
                      "defaultValue must check primary key column")
        self.assertIn("get_next_primary_key_value", body,
                      "defaultValue must query next PK value from Snowflake")

    def test_get_next_primary_key_value_helper_exists(self):
        """data_base.py must have get_next_primary_key_value helper."""
        content = self._get_database_content()
        self.assertIn("def get_next_primary_key_value(", content)
        idx = content.index("def get_next_primary_key_value(")
        next_def = content.find("\ndef ", idx + 1)
        body = content[idx:next_def] if next_def != -1 else content[idx:]
        self.assertIn("MAX(", body)
        self.assertIn("COALESCE", body)


class TestGitHubIssuesFixes(unittest.TestCase):
    """Tests for remaining GitHub issues fixes."""

    def test_no_subprocess_or_pip_in_install_path_issue_114(self):
        """check_install_package must NOT invoke subprocess or pip (issue #114).

        Auto-installing via pip on the UI thread froze QGIS on macOS because
        the resolved 'python3' was actually a QGIS launcher stub.
        """
        content = (ROOT / "helpers" / "utils.py").read_text(encoding="utf-8")
        self.assertNotIn("def _safe_pip_call(", content)
        self.assertNotIn("def _in_process_pip(", content)
        self.assertNotIn("def get_python_executable_path(", content)
        self.assertNotIn("subprocess", content)
        self.assertNotIn("pip._internal", content)

        init_content = (ROOT / "__init__.py").read_text(encoding="utf-8")
        self.assertIn("_StubPlugin", init_content)
        self.assertIn("python3 -m pip install snowflake-connector-python", init_content)

    def test_sql_branch_qgsfield_type_default_fixed(self):
        """SQL-query branch QgsField construction should use correct default."""
        content = (ROOT / "providers" / "sf_vector_data_provider.py").read_text(encoding="utf-8")
        # The buggy pattern was: SNOWFLAKE_METADATA_TYPE_CODE_DICT[2]["qvariant_type"] as default
        # Fixed pattern: SNOWFLAKE_METADATA_TYPE_CODE_DICT[2] as default (the full dict)
        # Check that the fixed pattern exists
        self.assertIn("SNOWFLAKE_METADATA_TYPE_CODE_DICT.get", content)
        # Ensure we're not using the buggy nested default
        buggy_pattern = 'SNOWFLAKE_METADATA_TYPE_CODE_DICT[2]["qvariant_type"]'
        self.assertNotIn(buggy_pattern, content,
                         "SQL branch should not use buggy nested default for unknown type codes")

    def test_non_geo_tables_support_added(self):
        """Browser should support showing non-geometry tables."""
        content = (ROOT / "entities" / "sf_data_item.py").read_text(encoding="utf-8")
        self.assertIn("get_table_iterator", content)
        self.assertIn("table_no_geom", content)
        self.assertIn("Tables (no geometry)", content)

    def test_empty_schema_feedback_added(self):
        """Schema with no tables should show QgsErrorItem feedback."""
        content = (ROOT / "entities" / "sf_data_item.py").read_text(encoding="utf-8")
        self.assertIn("No accessible tables found", content)
        self.assertIn("QgsErrorItem", content)


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
