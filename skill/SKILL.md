---
name: qgis-snowflake-plugin
description: Architecture and contributor guide for the QGIS Snowflake Connector plugin. Use when adding features, fixing bugs, writing tests, understanding data flow, or troubleshooting the plugin. Covers connection management, data providers, H3/geography handling, the export algorithm, UI dialogs, and packaging.
---

# QGIS Snowflake Connector -- Contributor Skill

## Repository Layout

```
__init__.py                          # classFactory entry point, dependency checks
qgis_snowflake_connector.py          # Plugin class (initGui / unload / update check)
qgis_snowflake_connector_algorithm.py # "Export to Snowflake" processing algorithm
qgis_snowflake_connector_provider.py  # Processing provider registration

managers/
  sf_connection_manager.py           # Singleton Snowflake connection pool

providers/
  sf_vector_data_provider.py         # Core data provider (fields, features, extent)
  sf_feature_iterator.py             # Feature fetching + H3 polygon conversion
  sf_feature_source.py               # Feature source wrapper
  sf_data_source_provider.py         # Thin query executor for algorithms
  sf_data_item_provider.py           # Browser panel provider
  sf_source_select_provider.py       # Data Source Manager integration
  sf_metadata_provider.py            # Provider metadata (encodeUri/decodeUri)

entities/
  sf_data_item.py                    # Browser tree items (connections/schemas/tables)

helpers/
  sql.py          # quote_identifier, quote_literal, qualified_table_name
  utils.py        # Settings, auth, URI parsing, dependency install
  mappings.py     # Snowflake type -> QMetaType/QgsWkbTypes maps
  limits.py       # Row-fetch limits (DEFAULT_ROW_LIMIT, H3_ROW_LIMIT)
  data_base.py    # Schema/table DDL helpers, INFORMATION_SCHEMA queries
  layer_creation.py # Build QgsVectorLayer from query results
  wrapper.py      # parse_uri (delegates to provider metadata)
  messages.py     # UI message boxes

dialogs/
  sf_connection_string_dialog.py     # Connection settings (auth, key pair, SSO)
  sf_data_source_manager_widget.py   # Data Source Manager tab
  sf_sql_query_dialog.py             # SQL query execution dialog
  sf_new_table_dialog.py / sf_new_schema_dialog.py

tasks/
  sf_connect_task.py                 # Background connection task
  sf_convert_column_to_layer_task.py # Column -> map layer
  sf_convert_sql_query_to_layer_task.py
  sf_execute_sql_query_task.py

ui/    # Generated PyQt .py/.ui files (do NOT hand-edit .py files)
test/  # Regression tests (see testing section below)
```

## Key Concepts

### URI Format

Every Snowflake layer is identified by a URI string with space-separated key=value pairs:

```
connection_name=MyConn schema_name=PUBLIC table_name=CITIES
srid=4326 geom_column=GEOM geometry_type=Point
geo_column_type=GEOGRAPHY primary_key=ID
```

Parsed by `helpers/wrapper.py:parse_uri()` and `helpers/utils.py:decodeUri()`.

### Geometry Column Types (geo_column_type)

| Value | Meaning | Provider subclass |
|-------|---------|-------------------|
| `GEOGRAPHY` | Snowflake native geography (WGS84) | `SFGeoVectorDataProvider` |
| `GEOMETRY` | Snowflake native geometry (any SRID) | `SFGeoVectorDataProvider` |
| `NUMBER` | H3 cell index stored as integer | `SFH3VectorDataProvider` |
| `TEXT` | H3 cell index stored as hex string | `SFH3VectorDataProvider` |

The factory method `SFVectorDataProvider.createProvider()` dispatches based on `geo_column_type`.

### H3 Architecture (TEXT-normalized)

H3 is handled entirely via Snowflake server-side functions. The Python `h3` package is **not** a dependency.

**Normalization**: NUMBER H3 columns are converted to hex strings via `H3_INT_TO_STRING()` in the feature iterator SELECT. Internally, the plugin always works with TEXT (hex string) H3 values. This avoids float precision loss (64-bit int → 53-bit Double) and eliminates NUMBER/TEXT branching.

**Rendering**: `ST_ASWKB(H3_CELL_TO_BOUNDARY(col))` returns WKB polygons from Snowflake. The standard `geometry.fromWkb()` path is used — no special H3 branch.

**Export**: H3 layers always create a TEXT column. Values are always quoted with `quote_literal()`.

**Detection**: `filter_geo_columns()` checks `INFORMATION_SCHEMA.COLUMNS` for NUMBER/TEXT columns with "h3" in the COMMENT, then validates with `H3_IS_VALID_CELL()`. The SQL query task always sets `geo_column_type="TEXT"` for H3.

### Type Mappings

`helpers/mappings.py` defines two key dicts:

- `mapping_snowflake_qgis_type` -- Snowflake SQL type name -> `QMetaType.Type`
- `SNOWFLAKE_METADATA_TYPE_CODE_DICT` -- Snowflake type code (int) -> QMetaType

NUMBER maps to Double, TEXT/VARCHAR to QString. Be aware that H3 cell indices stored as NUMBER lose precision when converted to float (53-bit mantissa vs 64-bit int).

## Data Flow Details

For deep dives into specific subsystems, see the companion files:

- [connection-manager.md](connection-manager.md) -- Connection lifecycle, auth types, reconnect
- [data-providers.md](data-providers.md) -- Provider hierarchy, fields, features, H3 conversion
- [export-algorithm.md](export-algorithm.md) -- Export to Snowflake, H3-aware export, VARIANT handling
- [troubleshooting.md](troubleshooting.md) -- Common errors, debugging strategies, known issues

## Testing

Tests live in `test/test_issue_regressions.py`. They use source-file assertions (no Snowflake connection needed):

```bash
python -c "
import sys, types
qgis = types.ModuleType('qgis')
sys.modules['qgis'] = qgis
import unittest
loader = unittest.TestLoader()
suite = loader.discover('test', pattern='test_issue_regressions.py', top_level_dir='.')
runner = unittest.TextTestRunner(verbosity=2)
result = runner.run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
"
```

The `qgis` module must be stubbed because the test environment has no QGIS runtime.

## Packaging

Build the installable zip (must have a root folder matching the plugin directory name):

```bash
rm -rf /tmp/build && mkdir -p /tmp/build/qgis-snowflake-connector
rsync -a --exclude='__pycache__' --exclude='*.pyc' --exclude='.DS_Store' \
  __init__.py metadata.txt icon.png favicon-32x32.webp \
  qgis_snowflake_connector.py qgis_snowflake_connector_algorithm.py \
  qgis_snowflake_connector_provider.py \
  helpers managers providers entities enums dialogs ui assets tasks scripts help \
  /tmp/build/qgis-snowflake-connector/
cd /tmp/build && zip -r output.zip qgis-snowflake-connector/
```

Common packaging mistakes:
- Missing root folder -> "No root folder was found inside"
- Missing `tasks/` or other directories -> ImportError on load
- Trailing `/` on rsync directory args flattens structure

## SQL Safety

All identifiers must use `quote_identifier()`, all literals must use `quote_literal()`. Both are in `helpers/sql.py`. Use `qualified_table_name(db, schema, table)` for fully-qualified references. Never use f-string interpolation for user-supplied names without quoting.
