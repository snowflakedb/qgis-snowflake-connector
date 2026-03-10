# Export Algorithm (`qgis_snowflake_connector_algorithm.py`)

## Overview

The "Export to Snowflake" processing algorithm (`QGISSnowflakeConnectorAlgorithm`) takes a QGIS vector layer and inserts its features into a Snowflake table. It handles three geometry paradigms: GEOGRAPHY, GEOMETRY, and H3.

## Parameters

| Name | Type | Purpose |
|------|------|---------|
| `INPUT` | FeatureSource | Source vector layer |
| `GEOMETRY_COLUMN` | String | Destination geometry column name |
| `CONNECTION_DYN_CB` | Dynamic combo | `[connection, database, schema, table]` JSON |

## Detection Flags

```python
is_snowflake_layer   # source URI has internal_provider=snowflake
is_h3_layer          # source geo_column_type in ("NUMBER", "TEXT")
use_geometry_type    # source SRID != 4326 -> GEOMETRY, else GEOGRAPHY
```

`is_h3_layer` is detected by calling `decodeUri()` on the source layer's URI.

## SQL Generation Strategy

Uses `INSERT INTO ... SELECT ... FROM VALUES ... AS v(c1, c2, ...)` pattern. This allows:
- VARIANT columns to be wrapped with `PARSE_JSON(v.cN)` in the SELECT projection
- Geometry columns to use spatial functions in the SELECT projection
- H3 columns to pass through raw values

### GEOGRAPHY (default, SRID=4326)

```sql
INSERT INTO db.schema.table ("GEOM", "NAME", "COUNT")
SELECT ST_GEOGFROMWKB(TO_BINARY(v.c1, 'HEX')), v.c2, v.c3
FROM VALUES ('hex_wkb', 'Alice', 42) AS v(c1, c2, c3)
```

### GEOMETRY (SRID != 4326)

```sql
SELECT ST_SETSRID(ST_GEOMETRYFROMWKB(TO_BINARY(v.c1, 'HEX')), 32632), v.c2, v.c3
FROM VALUES ...
```

### H3 (smart export)

When source is an H3 layer, the algorithm:
1. Creates the geometry column as NUMBER (or TEXT) instead of GEOGRAPHY
2. SELECT projection is just `v.c1` (pass-through, no spatial functions)
3. VALUES tuple writes the H3 cell index from the feature attribute, not polygon WKB

```sql
INSERT INTO db.schema.table ("H3", "NAME", "COUNT")
SELECT v.c1, v.c2, v.c3
FROM VALUES (612846778513358847, 'Alice', 42) AS v(c1, c2, c3)
```

The H3 cell value is read from `feature.attribute(source_geom_column_name)` -- the attribute preserved during loading (see data-providers.md).

## Batch Execution

Features are batched in groups of 5000. After every 5000 features, the accumulated VALUES are executed and a new query starts.

## VARIANT Column Detection

Before the insert loop, the algorithm queries `INFORMATION_SCHEMA.COLUMNS` for the target table to find VARIANT/OBJECT/ARRAY columns. Their aliases get `PARSE_JSON(v.cN)` in the SELECT projection.

## CREATE TABLE

`get_create_table_query()` generates `CREATE TABLE` DDL. Column types:
- Geometry column: `GEOGRAPHY`, `GEOMETRY`, or `NUMBER`/`TEXT` (for H3)
- Other fields: mapped via `get_field_type_from_code_type()` from QMetaType
- For Snowflake source layers: uses `field.subType()` (set by the provider)
- For non-Snowflake sources: uses `field.type()`

## Duplicate Geometry Column in Fields

When `source.fields()` includes a field with the same name as `geom_column`, the export writes the geometry value for that field slot too (WKB hex for geo, H3 cell for H3). Otherwise it reads the regular attribute.

## Known Caveats

- H3 NUMBER values lose precision through float conversion (64-bit int -> 53-bit mantissa). The value is close but may differ by 1-2 from the original.
- Snowflake layers use `field.subType()` for type decisions; non-Snowflake use `field.type()`. The subType is only set explicitly by the Snowflake provider.
- `ResourceWarning: unclosed ssl.SSLSocket` during `execute_query` is from the Snowflake connector internals, not a plugin leak.
