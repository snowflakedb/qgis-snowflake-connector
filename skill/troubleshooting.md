# Troubleshooting Guide

## Plugin Won't Load

### "No module named 'qgis-snowflake-connector.tasks.sf_connect_task'"

The installed zip is missing the `tasks/` directory. Rebuild the package ensuring all directories (`tasks`, `scripts`, `help`, etc.) are included. See packaging section in SKILL.md.

### "No root folder was found inside"

The zip has files at the top level instead of inside a root directory. The zip must contain `qgis-snowflake-connector/` as the root folder with all plugin files inside it.

### "cannot import name 'ExtensionOID' from 'cryptography.hazmat._oid'"

Outdated `cryptography` package. Fix: `python3 -m pip install --upgrade cryptography pyopenssl`, then restart QGIS. The plugin's `__init__.py` catches this and logs a diagnostic message.

### "required dependencies could not be installed"

`snowflake-connector-python` or `h3` failed to auto-install. Fix manually:
```bash
python3 -m pip install snowflake-connector-python h3
```
Then restart QGIS.

## Data Issues

### Attributes show NULL after refresh or project reopen

The `reloadData()` method must reset `_fields = None` and call `connect_database()`. Also verify the `INFORMATION_SCHEMA.COLUMNS` query includes `table_schema ILIKE` filter (without it, columns from same-named tables in different schemas can collide).

### H3 column shows NULL during export

Two possible causes:
1. **TEXT-type H3**: The feature iterator skip condition must use `not in ("NUMBER", "TEXT")` instead of `!= "NUMBER"`. Without this fix, TEXT H3 cell values are not stored as attributes.
2. **Smart export not active**: If the source layer is not detected as H3 (`is_h3_layer=False`), the export writes polygon WKB instead of the H3 cell index. Verify the source URI contains `geo_column_type=NUMBER` or `geo_column_type=TEXT`.

### H3 cell value precision loss

H3 cell indices are 64-bit unsigned integers. The provider maps NUMBER to QMetaType.Double, and the feature iterator converts via `float()`. This loses precision for large indices (float has 53-bit mantissa). The exported value may differ by 1-2 from the original. A future fix could store H3 NUMBER values as strings to preserve exact values.

### PARSE_JSON errors in VALUES clause

Snowflake does not allow function calls like `PARSE_JSON()` directly in a VALUES clause. The plugin uses `INSERT INTO ... SELECT ... FROM VALUES ... AS v(...)` and places `PARSE_JSON(v.cN)` in the SELECT projection instead.

### Primary key column has duplicates

If a user selects a column with duplicate values as the primary key, features may get duplicate IDs causing rendering glitches or editing failures. The plugin now validates uniqueness via `check_column_has_duplicates()` in `helpers/data_base.py` and warns the user before accepting. If the user proceeds anyway, the layer will load but editing may be unreliable.

### Empty geometry becomes error instead of NULL

The VALUES tuple must write `NULL` (not empty string) when `hex_string == ""`. This applies to both the first position (geometry column) and the duplicate geometry field slot.

## Connection Issues

### ResourceWarning: unclosed ssl.SSLSocket

Comes from inside `snowflake-connector-python`'s vendored urllib3. Not a plugin bug. The warning is cosmetic. Suppressing globally with `warnings.filterwarnings` is not recommended.

### Login timeout

Default `login_timeout=5` seconds. For SSO (externalbrowser), this may be too short. The dialog can pass `long_timeout` to extend it.

### Connection expired during long operations

`create_cursor()` checks `connection.expired` and auto-reconnects via `reconnect()`. But if the reconnect itself fails (e.g., credentials changed), the error propagates to the caller.

## Debugging Tips

- **QGIS Log Messages panel**: The plugin logs to tag "Snowflake Plugin". Check for WARNING and CRITICAL messages.
- **Feature iterator errors**: Attribute conversion errors are logged via `QgsMessageLog` (not `print`).
- **SQL debugging**: The generated SQL can be inspected by adding temporary logging in `execute_query()` or the algorithm's batch loop.
- **URI inspection**: Call `layer.source()` on any loaded Snowflake layer to see the full URI with all key=value pairs.
- **Test without QGIS**: Regression tests use source-file assertions and a stubbed `qgis` module. See testing section in SKILL.md.

## Browser Panel Issues

### Schemas or non-geo tables not visible

The `INFORMATION_SCHEMA.COLUMNS` query in `sf_data_item.py:get_query_metadata()` applies a `DATA_TYPE` filter. This filter must only apply when `item_type == "table"`, not for schema-level queries. Non-geo tables should be visible but not double-clickable for layer creation (guarded by `if not self.geom_column: return False`).

### Double-clicking non-geo table crashes

The `handleDoubleClick` method must check `if self.item_type == "table" and not self.geom_column: return False` before attempting layer creation.
