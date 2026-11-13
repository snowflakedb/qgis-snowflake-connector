# Connection Manager

## Singleton Pattern

`SFConnectionManager` (`managers/sf_connection_manager.py`) is a process-wide singleton. Access via `SFConnectionManager.get_instance()` or just `SFConnectionManager()` (both return the same object).

It maintains a dict `opened_connections: Dict[str, SnowflakeConnection]` keyed by connection name.

## Connection Lifecycle

```
connect(name, params)
  -> closes existing connection for that name
  -> builds conn_params from auth type
  -> calls snowflake.connector.connect(**conn_params)
  -> stores in opened_connections[name]

get_connection(name) -> returns stored connection or None

create_cursor(name)
  -> if connection is None or expired: reconnect(name)
  -> returns connection.cursor()

execute_query(name, query, context_information)
  -> create_cursor(name)
  -> if context has schema_name: cursor.execute(USE SCHEMA ...)
  -> cursor.execute(query)
  -> returns cursor (caller must close)

reconnect(name)
  -> reads auth info from QSettings
  -> calls connect(name, auth_info)
```

## Authentication Types

Configured in `dialogs/sf_connection_string_dialog.py`, stored in QSettings via `helpers/utils.py`.

| Type | conn_params keys |
|------|-----------------|
| Default Authentication | `user`, `account`, `password` |
| Single sign-on (SSO) | `authenticator="externalbrowser"` |
| Key Pair | `private_key_file`, `private_key_file_pwd` (optional) |

All types also set: `warehouse`, `database`, `application="OSGeo_QGIS"`, `login_timeout=5`, `client_session_keep_alive=True`, and a structured JSON `QUERY_TAG` (via `default_query_tag()` / `build_op_tag`).

### QUERY_TAG telemetry

`build_op_tag(op, ...)` in `managers/sf_connection_manager.py` builds a compact JSON tag:

```json
{"app":"qgis-snowflake-connector","ver":"1.0.x","op":"features","kind":"sql","conn":"MyConn","layer":"PUBLIC.CITIES"}
```

Optional fields: `model` (Cortex), `kind` (`sql` | `cortex` | `ddl` | `dml`). Connect sets `op=session`; callers that omit `op_tag` get `op=untagged` (still JSON). `execute_query` / `execute_query_with_params` apply the tag with `ALTER SESSION SET QUERY_TAG` only when it changes.

Snowflake-side filter:

```sql
SELECT query_id, start_time,
       TRY_PARSE_JSON(query_tag):op::string AS op,
       TRY_PARSE_JSON(query_tag):model::string AS model,
       total_elapsed_time
FROM TABLE(INFORMATION_SCHEMA.QUERY_HISTORY())
WHERE TRY_PARSE_JSON(query_tag):app::string = 'qgis-snowflake-connector'
ORDER BY start_time DESC;
```

Prefer `TRY_PARSE_JSON` so non-JSON tags from other clients do not fail the query.

Use `ACCOUNT_USAGE.QUERY_HISTORY` for org-wide history (with latency).

## Settings Storage

Connection settings are stored in QSettings under the group `connections/{connection_name}/`:

```
account, warehouse, database, username, password,
connection_type, role, auth_config_id,
private_key_file, key_passphrase
```

Read by `get_authentification_information()` and `get_auth_information()` in `helpers/utils.py`.

## Common Issues

- **Expired connections**: `create_cursor()` checks `connection.expired` and auto-reconnects. But if the reconnect fails, the error propagates.
- **ResourceWarning: unclosed ssl.SSLSocket**: Comes from the Snowflake connector's vendored urllib3, not from plugin code. Cosmetic; safe to ignore.
- **Schema context**: `execute_query` runs `USE SCHEMA` before the main query when `context_information["schema_name"]` is set. This affects the session state for that cursor.
