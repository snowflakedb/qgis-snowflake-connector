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


if __name__ == "__main__":
    unittest.main()
