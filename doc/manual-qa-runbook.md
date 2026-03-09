# Manual QA Runbook for Open Issues

Use this runbook to validate each issue status in a real QGIS + Snowflake environment.

## Environment Baseline
- QGIS: test on at least one modern build (3.44.x) and one older build if possible.
- OS: include macOS for startup/dependency issues.
- Snowflake: account with at least one geospatial table and one non-geospatial table.

## Validation Order (Recommended)
1. Startup/load blockers (#109, #107)
2. Metadata/listing correctness (#83)
3. Data refresh/reload behavior (#110, #101)
4. Export behavior (#73, #102)
5. Compatibility edge case (#6)
6. Feature requests triage (#106, #105, #103, #92)

## Issue-by-Issue Steps

### #109 Plugin load on macOS
1. Install plugin in QGIS.
2. Restart QGIS.
3. Verify plugin loads without `classFactory()` crash.
4. Open Snowflake Data Source Manager tab.

Pass criteria: no startup exception; plugin is usable.

### #107 ExtensionOID / crypto dependency issue
1. Install plugin on mac environment similar to reporter.
2. Start plugin and attempt connection.
3. Check logs for import failures in dependency chain.

Pass criteria: no `ExtensionOID` import crash.

### #83 No tables showing (case sensitivity)
1. Create connection with mixed/lowercase DB/schema naming.
2. Connect via Browser and Data Source Manager.
3. Verify schemas/tables appear.

Pass criteria: tables listed regardless of case in configured names.

### #110 Refresh null attributes
1. Load Snowflake layer into project.
2. Open attribute table and note non-null values.
3. Trigger refresh (Snowflake item action or F5).
4. Reopen attribute table.

Pass criteria: attributes remain populated after refresh.

### #101 Null attributes after reopen
1. Add Snowflake layer.
2. Save project.
3. Close and reopen QGIS project.
4. Open attribute table.

Pass criteria: attributes are populated after reopen (without manual label refresh trick).

### #73 Export from marketplace listing fails
1. Load marketplace geospatial table in QGIS.
2. Run "Export to Snowflake".
3. Check processing result and Snowflake query history.

Pass criteria: no Geo parse error; rows insert successfully.

### #102 SRID missing on export
1. Use source layer with known SRID (including non-4326 case).
2. Export to Snowflake.
3. Run Snowflake SQL to validate SRID of inserted geometries.

Pass criteria: SRID in target data matches expected source SRID handling.

### #6 Data not loading (`QgsField` overload mismatch)
1. Use environment close to original report (older QGIS if available).
2. Load affected table.
3. Monitor task output and logs.

Pass criteria: no `QgsField` constructor overload error.

## Feature Requests (Tracking, Not Pass/Fail Bug Fixes)

- #106 dynamic map-driven query pushdown
- #105 show non-geometry tables
- #103 key pair authentication
- #92 plugin update notification

For these, validate behavior against accepted product decision once implemented.
