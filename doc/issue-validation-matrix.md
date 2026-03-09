# Issue Validation Matrix

Legend:
- `Bug`: defect report
- `Feature`: enhancement request
- `Status`: current recommendation state

- #110 | Bug | Refresh causes attributes to be null | Repro likely | Fix direction identified | Validate with refresh workflow
- #109 | Bug | Plugin fails to load on macOS | Repro from traceback | Fix direction identified | Validate startup on macOS QGIS 3.44.x
- #107 | Bug | ExtensionOID import error | Repro from traceback | Fix direction identified | Validate dependency bootstrap/runtime
- #106 | Feature | Dynamic geomap pushdown query | N/A | Design pending | Needs architecture decision
- #105 | Feature | Show non-geometry tables | N/A | Design pending | Add UI mode and query strategy
- #103 | Feature | Key pair auth support | N/A | Design pending | Add auth type + key handling
- #102 | Bug | SRID missing in exported geometry | Repro plausible | Fix direction identified | Validate SRID in Snowflake
- #101 | Bug | Null attributes after reopen | Repro likely | Fix direction identified | Validate project reopen path
- #92 | Feature | Plugin update notification | N/A | Design pending | Product/UI decision
- #83 | Bug | No tables shown (case sensitivity) | Confirmed in issue timeline | Fix direction identified | Validate mixed/lower case metadata lookup
- #73 | Bug | Export fails on marketplace listing data | Repro from traceback/query | Fix direction identified | Validate geometry conversion and null handling
- #6 | Bug | Data not loading (`QgsField` mismatch) | Version-dependent repro | Fix direction identified | Validate on older QGIS runtime

## Suggested Closure Sequence
1. Close startup blockers: #109, #107
2. Close data discoverability: #83
3. Close reload correctness: #110, #101
4. Close export correctness: #73, #102
5. Close compatibility edge: #6
6. Prioritize feature requests by product impact: #106, #105, #103, #92
