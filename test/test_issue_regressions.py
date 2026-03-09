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


if __name__ == "__main__":
    unittest.main()
