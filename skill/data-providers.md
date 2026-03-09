# Data Providers -- Provider Hierarchy, Fields, Features, H3

## Provider Hierarchy

```
SFVectorDataProvider          (base, handles fields, URI parsing, capabilities)
  |
  +-- SFGeoVectorDataProvider (GEOGRAPHY / GEOMETRY columns)
  |     - wkbType from geometry_type mapping
  |     - extent via ST_XMIN/ST_YMIN/ST_XMAX/ST_YMAX envelope
  |
  +-- SFH3VectorDataProvider  (NUMBER / TEXT H3 columns)
        - validates H3 via H3_IS_VALID_CELL
        - wkbType always Polygon
        - extent via H3_CELL_TO_BOUNDARY lat/lon bounds
```

Factory: `SFVectorDataProvider.createProvider(uri, options, flags)` reads `_geo_column_type` from the parsed URI and returns the correct subclass.

Provider key: `"snowflakedb"`

## Fields

`fields()` method queries `INFORMATION_SCHEMA.COLUMNS`:

```sql
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name ILIKE '{table}'
  AND table_schema ILIKE '{schema}'   -- added for correctness
  AND data_type NOT IN ('GEOMETRY', 'GEOGRAPHY')
ORDER BY column_name, data_type
```

Maps Snowflake types to QgsField via `mapping_snowflake_qgis_type`. Note: for H3 layers, the geometry column (NUMBER/TEXT) IS included in fields -- it's not filtered out.

## Feature Iterator (`sf_feature_iterator.py`)

### Query Construction

For GEOGRAPHY/GEOMETRY:
```sql
SELECT {field_cols}, ST_ASWKB({geom}), {geom}, ROW_NUMBER()...
FROM {table} WHERE ST_ASGEOJSON({geom}):type::string IN (...)
```

For H3 (NUMBER/TEXT):
```sql
SELECT {field_cols}, {geom}, {geom}, ROW_NUMBER()...
FROM {table} WHERE H3_IS_VALID_CELL({geom})
```

`index_geom_column = len(field_columns)` points to the first geometry column in the result.

### Geometry Conversion

For GEOGRAPHY/GEOMETRY: `geometry.fromWkb(result[index_geom_column])`

For H3:
```python
cell = result[index_geom_column]
converted_cell = __try_to_convert_hex_to_int(cell)  # handles hex TEXT -> int
coords = h3.cell_to_boundary(converted_cell)
geometry = QgsGeometry.fromPolygonXY([[QgsPointXY(lon, lat) for lat, lon in coords]])
```

### Attribute Setting

The skip condition determines whether the geometry column's value is set as an attribute:

```python
if (
    field_name == self._provider._column_geom
    and self._provider._geo_column_type not in ("NUMBER", "TEXT")
):
    continue  # skip for GEOGRAPHY/GEOMETRY (binary, not useful as attr)
```

For H3 layers (NUMBER/TEXT), the geometry column value IS preserved as an attribute so it can be used during export.

### Row Limits

Defined in `helpers/limits.py`:
- `DEFAULT_ROW_LIMIT = 50,000` (GEOGRAPHY/GEOMETRY)
- `H3_ROW_LIMIT = 500,000` (NUMBER/TEXT/H3GEO)

Applied when `_is_limited_unordered` is True (table exceeds limit threshold).

## Primary Key Selection

When a layer is loaded from the browser, the user is prompted to select a primary key column (`prompt_and_get_primary_key` in `helpers/utils.py`). The flow:

1. Show combo box with all non-geometry columns from `INFORMATION_SCHEMA.COLUMNS`
2. On selection, run `check_column_has_duplicates()` (`helpers/data_base.py`) which executes `SELECT COUNT(*) - COUNT(DISTINCT "col") FROM table`
3. If duplicates exist, show a warning dialog letting the user choose to proceed or skip
4. H3 layers (data_type `"H3GEO"` or `"H3"`) skip PK selection entirely

Without a valid PK, the provider falls back to `ROW_NUMBER() OVER (ORDER BY 1)` for feature IDs.

## Capabilities

H3 and custom SQL layers are read-only. Editing (AddFeatures, ChangeGeometries, etc.) requires:
- `geo_column_type` in `("GEOGRAPHY", "GEOMETRY")`
- Non-empty `primary_key`
- No custom `sql_query`

## reloadData()

Resets: `_features=[]`, `_features_loaded=False`, `_feature_count=None`, `_extent=None`, `_fields=None`, then calls `connect_database()` for fresh connection. Called on refresh and project reopen.
