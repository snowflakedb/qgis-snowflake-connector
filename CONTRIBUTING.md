# Contributing to Snowflake Connector for QGIS

## Prerequisites

| Tool | Version |
|------|---------|
| QGIS | 3.34.1+ (Qt6 builds supported) |
| Python | 3.9+ (bundled with QGIS) |
| `pyuic6` | For regenerating UI code |

## Development setup

1. Clone the repository into your QGIS plugin directory:

   ```bash
   # macOS / Linux
   ln -s $(pwd) ~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/qgis_snowflake_connector

   # Windows (run as admin)
   mklink /D "%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\qgis_snowflake_connector" "%cd%"
   ```

2. Install runtime dependencies (done automatically by the plugin on first
   load, but you can install manually):

   ```bash
   python3 -m pip install snowflake-connector-python h3
   ```

3. Restart QGIS.

## Running tests

Pure-Python regression tests (no QGIS runtime required):

```bash
python3 test/test_issue_regressions.py -v
```

## UI files

Generated Python files live in `ui/` and **must not be edited manually**.
Edit the `.ui` source in Qt Designer, then regenerate:

```bash
pyuic6 ui/<name>.ui -o ui/<name>.py
```

All runtime logic belongs in the matching `dialogs/` wrapper.
See `ui/README.md` for details.

## SQL safety

All SQL identifiers (database, schema, table, column names) must be quoted
through `helpers/sql.py`:

- `quote_identifier(name)` — wraps in double quotes, escapes internal `"`.
- `quote_literal(value)` — wraps in single quotes, escapes internal `'`.
- `qualified_table_name(db, schema, table)` — fully qualified reference.

Never use raw f-string interpolation for identifiers or literal values in SQL.

## Backward compatibility

- Do **not** change the provider URI key names (`connection_name`,
  `schema_name`, `table_name`, etc.).
- Preserve existing `QSettings` connection keys.
- Keep current auth modes working as-is.
- Gate new optional features behind defaults that match current behavior.

## Commit conventions

- One logical change per commit.
- Reference issue numbers where applicable (`Fixes #123`).
- Run the test suite before pushing.
