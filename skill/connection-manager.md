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

All types also set: `warehouse`, `database`, `application="OSGeo_QGIS"`, `login_timeout=5`, `client_session_keep_alive=True`, `QUERY_TAG="qgis-snowflake-connector"`.

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
