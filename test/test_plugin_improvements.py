"""Tests for the plugin-improvements branch features.

Tests cover:
- Processing provider activation and algorithm registration
- Locator filter
- Expression functions
- Feature actions
- Temporal support
- Spatial filter dialog
"""

import unittest
import sys
import os
import inspect

# Ensure plugin root is on sys.path for imports
_plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _plugin_root not in sys.path:
    sys.path.insert(0, _plugin_root)


class TestProcessingProvider(unittest.TestCase):
    """Verify the dedicated Snowflake Processing provider."""

    def test_provider_class_exists(self):
        source = self._read("qgis_snowflake_connector_provider.py")
        self.assertIn("class QGISSnowflakeConnectorProvider", source)

    def test_provider_id_is_snowflake(self):
        source = self._read("qgis_snowflake_connector_provider.py")
        self.assertIn('return "snowflake"', source)

    def test_provider_loads_all_algorithms(self):
        source = self._read("qgis_snowflake_connector_provider.py")
        for algo_class in [
            "ImportFromSnowflakeAlgorithm",
            "ExecuteSQLAlgorithm",
            "SpatialJoinAlgorithm",
            "BufferTableAlgorithm",
            "H3IndexAlgorithm",
        ]:
            self.assertIn(algo_class, source, f"Missing algorithm: {algo_class}")

    def test_main_plugin_uses_provider(self):
        source = self._read("qgis_snowflake_connector.py")
        self.assertIn("QGISSnowflakeConnectorProvider", source)
        self.assertIn("addProvider", source)
        self.assertNotIn("postgis_native_provider", source,
                         "Should no longer attach to native provider")

    def _read(self, filename):
        path = os.path.join(_plugin_root, filename)
        with open(path) as f:
            return f.read()


class TestProcessingAlgorithms(unittest.TestCase):
    """Verify each new processing algorithm file."""

    def test_import_from_snowflake_algorithm(self):
        source = self._read("processing/import_from_snowflake.py")
        self.assertIn("class ImportFromSnowflakeAlgorithm", source)
        self.assertIn("importfromsnowflake", source)
        self.assertIn("QgsProcessingParameterFeatureSink", source)
        self.assertIn("ST_ASWKB", source)

    def test_execute_sql_algorithm(self):
        source = self._read("processing/execute_sql.py")
        self.assertIn("class ExecuteSQLAlgorithm", source)
        self.assertIn("executesql", source)
        self.assertIn("multiLine=True", source)

    def test_spatial_join_algorithm(self):
        source = self._read("processing/spatial_join.py")
        self.assertIn("class SpatialJoinAlgorithm", source)
        self.assertIn("spatialjoin", source)
        self.assertIn("ST_INTERSECTS", source)
        self.assertIn("ST_CONTAINS", source)
        self.assertIn("ST_WITHIN", source)

    def test_buffer_table_algorithm(self):
        source = self._read("processing/buffer_table.py")
        self.assertIn("class BufferTableAlgorithm", source)
        self.assertIn("buffertable", source)
        self.assertIn("ST_BUFFER", source)

    def test_h3_index_algorithm(self):
        source = self._read("processing/h3_index.py")
        self.assertIn("class H3IndexAlgorithm", source)
        self.assertIn("h3index", source)
        self.assertIn("H3_LATLNG_TO_CELL", source)
        self.assertIn("H3_CELL_TO_BOUNDARY", source)

    def test_all_algorithms_have_create_instance(self):
        for filename in [
            "processing/import_from_snowflake.py",
            "processing/execute_sql.py",
            "processing/spatial_join.py",
            "processing/buffer_table.py",
            "processing/h3_index.py",
        ]:
            source = self._read(filename)
            self.assertIn("def createInstance(self)", source,
                           f"{filename} missing createInstance")

    def _read(self, filename):
        path = os.path.join(_plugin_root, filename)
        with open(path) as f:
            return f.read()


class TestLocatorFilter(unittest.TestCase):
    """Verify the Snowflake locator filter."""

    def test_locator_filter_exists(self):
        source = self._read("sf_locator_filter.py")
        self.assertIn("class SFLocatorFilter", source)
        self.assertIn("QgsLocatorFilter", source)

    def test_locator_prefix(self):
        source = self._read("sf_locator_filter.py")
        self.assertIn('return "sf"', source)

    def test_locator_has_fetch_and_trigger(self):
        source = self._read("sf_locator_filter.py")
        self.assertIn("def fetchResults", source)
        self.assertIn("def triggerResult", source)

    def test_locator_registered_in_plugin(self):
        source = self._read("qgis_snowflake_connector.py")
        self.assertIn("SFLocatorFilter", source)
        self.assertIn("registerLocatorFilter", source)
        self.assertIn("deregisterLocatorFilter", source)

    def _read(self, filename):
        path = os.path.join(_plugin_root, filename)
        with open(path) as f:
            return f.read()


class TestExpressionFunctions(unittest.TestCase):
    """Verify custom QGIS expression functions."""

    def test_expression_module_exists(self):
        source = self._read("sf_expression_functions.py")
        self.assertIn("register_sf_functions", source)
        self.assertIn("unregister_sf_functions", source)

    def test_h3_functions_defined(self):
        source = self._read("sf_expression_functions.py")
        for func_name in [
            "sf_h3_resolution",
            "sf_h3_is_valid",
            "sf_h3_parent",
            "sf_h3_grid_distance",
            "sf_h3_to_string",
        ]:
            self.assertIn(func_name, source, f"Missing function: {func_name}")

    def test_functions_use_qgsfunction_decorator(self):
        source = self._read("sf_expression_functions.py")
        self.assertIn("@qgsfunction", source)
        self.assertIn('group="Snowflake"', source)

    def test_registered_in_plugin(self):
        source = self._read("qgis_snowflake_connector.py")
        self.assertIn("register_sf_functions", source)
        self.assertIn("unregister_sf_functions", source)

    def _read(self, filename):
        path = os.path.join(_plugin_root, filename)
        with open(path) as f:
            return f.read()


class TestFeatureActions(unittest.TestCase):
    """Verify feature actions module."""

    def test_feature_actions_module_exists(self):
        source = self._read("sf_feature_actions.py")
        self.assertIn("register_actions_for_layer", source)

    def test_view_in_snowsight_action(self):
        source = self._read("sf_feature_actions.py")
        self.assertIn("sf_view_snowsight", source)
        self.assertIn("webbrowser", source)
        self.assertIn("snowflake.com", source)

    def test_copy_as_sql_action(self):
        source = self._read("sf_feature_actions.py")
        self.assertIn("sf_copy_sql", source)
        self.assertIn("INSERT INTO", source)

    def test_copy_row_json_action(self):
        source = self._read("sf_feature_actions.py")
        self.assertIn("sf_copy_row_json", source)
        self.assertIn("json.dumps", source)

    def _read(self, filename):
        path = os.path.join(_plugin_root, filename)
        with open(path) as f:
            return f.read()


class TestTemporalSupport(unittest.TestCase):
    """Verify temporal animation support."""

    def test_temporal_module_exists(self):
        source = self._read("sf_temporal_support.py")
        self.assertIn("configure_temporal_for_layer", source)

    def test_detects_timestamp_types(self):
        source = self._read("sf_temporal_support.py")
        for ts_type in ["TIMESTAMP_NTZ", "TIMESTAMP_LTZ", "TIMESTAMP_TZ", "DATE"]:
            self.assertIn(ts_type, source)

    def test_uses_temporal_properties(self):
        source = self._read("sf_temporal_support.py")
        self.assertIn("QgsVectorLayerTemporalProperties", source)
        self.assertIn("setIsActive(True)", source)

    def _read(self, filename):
        path = os.path.join(_plugin_root, filename)
        with open(path) as f:
            return f.read()


class TestSpatialFilterDialog(unittest.TestCase):
    """Verify spatial filter / extent download dialog."""

    def test_dialog_exists(self):
        source = self._read("dialogs/sf_spatial_filter_dialog.py")
        self.assertIn("class SFSpatialFilterDialog", source)
        self.assertIn("QDialog", source)

    def test_dialog_has_extent_controls(self):
        source = self._read("dialogs/sf_spatial_filter_dialog.py")
        self.assertIn("xmin_edit", source)
        self.assertIn("ymin_edit", source)
        self.assertIn("xmax_edit", source)
        self.assertIn("ymax_edit", source)

    def test_dialog_uses_st_intersects(self):
        source = self._read("dialogs/sf_spatial_filter_dialog.py")
        self.assertIn("ST_INTERSECTS", source)

    def test_dialog_has_sql_preview(self):
        source = self._read("dialogs/sf_spatial_filter_dialog.py")
        self.assertIn("sql_preview", source)
        self.assertIn("build_sql", source)

    def test_dialog_supports_where_clause(self):
        source = self._read("dialogs/sf_spatial_filter_dialog.py")
        self.assertIn("where_edit", source)
        self.assertIn("WHERE", source)

    def test_dialog_supports_row_limit(self):
        source = self._read("dialogs/sf_spatial_filter_dialog.py")
        self.assertIn("limit_spin", source)
        self.assertIn("LIMIT", source)

    def _read(self, filename):
        path = os.path.join(_plugin_root, filename)
        with open(path) as f:
            return f.read()


if __name__ == "__main__":
    unittest.main()
