# Open Issues Analysis (One-by-One)

This document summarizes all currently open issues in the repository, the likely root cause, reproducibility status, and suggested fix direction.

Source: [GitHub Issues](https://github.com/snowflakedb/qgis-snowflake-connector/issues/)

## Bug Issues

### #110 - Refresh causes attributes to be null
- Link: [#110](https://github.com/snowflakedb/qgis-snowflake-connector/issues/110)
- Repro: likely reproducible from user report.
- Root cause area: provider reload/cache invalidation.
- Suggested fix: reset provider caches fully during `reloadData()` (`features`, `feature_count`, `extent`) and force clean refetch.

### #109 - Can't load plugin on Mac (QGIS 3.44.5)
- Link: [#109](https://github.com/snowflakedb/qgis-snowflake-connector/issues/109)
- Repro: reproducible from stack trace.
- Root cause area:
  - hardcoded Python path logic on macOS,
  - `pkg_resources` dependency not present in modern Python environments.
- Suggested fix:
  - use `sys.executable`,
  - use `importlib.metadata` for package detection,
  - ensure pip args use ASCII `--upgrade`.

### #107 - Unusable on M3 Mac with QGIS 3.42 (`ExtensionOID`)
- Link: [#107](https://github.com/snowflakedb/qgis-snowflake-connector/issues/107)
- Repro: reproducible from stack trace chain.
- Root cause area: runtime dependency mismatch (`snowflake-connector-python` vs `cryptography` in QGIS environment).
- Suggested fix: improve dependency bootstrap/upgrade path and provide actionable startup error when dependency chain is incompatible.

### #102 - SRID missing in geometry on export
- Link: [#102](https://github.com/snowflakedb/qgis-snowflake-connector/issues/102)
- Repro: plausible, consistent with current export pattern.
- Root cause area: export inserts WKB payload without explicit SRID handling.
- Suggested fix: apply SRID-aware geometry SQL (`ST_SETSRID(...)`) and correct geo/geometry function choice by CRS/type.

### #101 - Attribute table null when reopening project
- Link: [#101](https://github.com/snowflakedb/qgis-snowflake-connector/issues/101)
- Repro: likely reproducible from report; same symptom family as #110.
- Root cause area: stale/partial provider state after project reload.
- Suggested fix: same cache invalidation hardening as #110.

### #83 - No tables showing in Snowflake
- Link: [#83](https://github.com/snowflakedb/qgis-snowflake-connector/issues/83)
- Repro: confirmed in issue timeline.
- Root cause area: case-sensitive metadata filters for DB/schema/table.
- Suggested fix: use case-insensitive comparisons (`ILIKE`) consistently in metadata queries.

### #73 - Can't publish data from Marketplace listings
- Link: [#73](https://github.com/snowflakedb/qgis-snowflake-connector/issues/73)
- Repro: reproducible from provided traceback/query.
- Root cause area: invalid/empty geometry payload handling during export.
- Suggested fix: guard empty geometry as `NULL`; wrap WKB conversion with Snowflake geo conversion functions.

### #6 - Data not loading
- Link: [#6](https://github.com/snowflakedb/qgis-snowflake-connector/issues/6)
- Repro: version-dependent, likely tied to older QGIS/PyQt type handling.
- Root cause area: `QgsField` constructor subtype compatibility.
- Suggested fix: set subtype via explicit setter (`setSubType`) for cross-version safety.

## Feature Requests / Product Enhancements

### #106 - Dynamic query according to geomap
- Link: [#106](https://github.com/snowflakedb/qgis-snowflake-connector/issues/106)
- Nature: feature request (query pushdown / dynamic map-window fetch).
- Suggested implementation: reduce client-side caching and issue window-aware SQL for each extent request.

### #105 - Show tables with no geometry field
- Link: [#105](https://github.com/snowflakedb/qgis-snowflake-connector/issues/105)
- Nature: feature request.
- Suggested implementation: add optional "Show non-spatial tables" mode in browser and DSM views.

### #103 - Snowflake key pair authentication
- Link: [#103](https://github.com/snowflakedb/qgis-snowflake-connector/issues/103)
- Nature: feature request.
- Suggested implementation: add new connection mode and private key handling in connection manager + UI.

### #92 - Notification about plugin updates
- Link: [#92](https://github.com/snowflakedb/qgis-snowflake-connector/issues/92)
- Nature: feature request.
- Suggested implementation: lightweight startup version check and in-app notification.
