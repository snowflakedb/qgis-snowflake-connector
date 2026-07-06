from collections import defaultdict
from typing import Dict, List, Optional
import json
import threading
import typing
import snowflake.connector

from qgis.core import Qgis, QgsMessageLog

from ..helpers.utils import get_auth_information
from ..helpers.sql import quote_identifier


_BASE_QUERY_TAG = "qgis-snowflake-connector"


def build_op_tag(
    op: str,
    connection_name: typing.Optional[str] = None,
    schema: typing.Optional[str] = None,
    table: typing.Optional[str] = None,
) -> str:
    """Build a JSON-encoded QUERY_TAG payload for cost attribution.

    The resulting string is set as the Snowflake session QUERY_TAG so that
    ACCOUNT_USAGE.QUERY_HISTORY rows issued by the plugin can be filtered by
    operation type and target layer.
    """
    payload = {"app": _BASE_QUERY_TAG, "op": op}
    if connection_name:
        payload["conn"] = connection_name
    if schema and table:
        payload["layer"] = f"{schema}.{table}"
    elif table:
        payload["layer"] = table
    return json.dumps(payload, separators=(",", ":"))


class SFConnectionManager:
    _instance = None

    def __new__(cls):
        """
        Create a new instance of the SFConnectionManager class if it doesn't already exist.

        Returns:
            SFConnectionManager: The instance of the SFConnectionManager class.
        """
        if cls._instance is None:
            cls._instance = super(SFConnectionManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        """
        Initializes the SFConnectionManager object.
        """
        self.opened_connections: Dict[str, snowflake.connector.SnowflakeConnection] = {}
        # A6: track the most recently-set active schema per connection so we
        # can skip redundant `USE SCHEMA` round-trips on every execute_query.
        self._active_schemas: Dict[str, str] = {}
        # E3: track the most recently-set QUERY_TAG per connection so we only
        # issue `ALTER SESSION SET QUERY_TAG` when the requested tag changes.
        self._active_query_tags: Dict[str, str] = {}
        # A9: track cursors currently executing, keyed by the thread that
        # owns them, so tasks can cancel their own queries on task.cancel()
        # without touching cursors running on other threads (e.g. the main
        # thread's feature iterator).
        self._active_cursors: Dict[int, List[snowflake.connector.cursor.SnowflakeCursor]] = defaultdict(list)
        self._lock = threading.Lock()

    def create_snowflake_connection(
        self, conn_params: dict
    ) -> snowflake.connector.SnowflakeConnection:
        try:
            return snowflake.connector.connect(**conn_params)
        except Exception as e:
            raise e

    def connect(self, connection_name: str, connection_params: dict) -> None:
        """
        Connects to a Snowflake database using the provided connection parameters.

        Args:
            connection_name (str): The name of the connection.
            connection_params (dict): A dictionary containing the connection parameters.

        Raises:
            Exception: If there is an error connecting to the Snowflake database.

        Returns:
            None
        """
        try:
            if connection_name in self.opened_connections:
                self.opened_connections[connection_name].close()
                self.opened_connections[connection_name] = None

            conn_params = {
                "user": connection_params["username"],
                "account": connection_params["account"],
                "warehouse": connection_params["warehouse"],
                "database": connection_params["database"],
                "application": "OSGeo_QGIS",
                "login_timeout": 5,
                "client_session_keep_alive": True,
                "session_parameters": {
                    "QUERY_TAG": _BASE_QUERY_TAG,
                },
            }

            if "long_timeout" in connection_params:
                conn_params["login_timeout"] = connection_params["long_timeout"]

            if connection_params["connection_type"] == "Default Authentication":
                conn_params["account"] = connection_params["account"]
                conn_params["password"] = connection_params["password"]
            elif connection_params["connection_type"] == "Single sign-on (SSO)":
                conn_params["authenticator"] = "externalbrowser"
            elif connection_params["connection_type"] == "Key Pair":
                key_file = connection_params.get("private_key_file", "")
                passphrase = connection_params.get("key_passphrase", "")
                if key_file:
                    conn_params["private_key_file"] = key_file
                    if passphrase:
                        conn_params["private_key_file_pwd"] = passphrase
            if "role" in connection_params:
                conn_params["role"] = connection_params["role"]

            self.opened_connections[connection_name] = self.create_snowflake_connection(
                conn_params
            )
            # Fresh session: forget whatever schema / query tag we thought was
            # active on the previous socket.
            self._active_schemas.pop(connection_name, None)
            self._active_query_tags[connection_name] = _BASE_QUERY_TAG
        except Exception as e:
            if connection_name in self.opened_connections:
                del self.opened_connections[connection_name]
            self._active_schemas.pop(connection_name, None)
            self._active_query_tags.pop(connection_name, None)
            raise e

    def get_connection(
        self, connection_name: str
    ) -> snowflake.connector.SnowflakeConnection:
        """
        Retrieves a Snowflake connection based on the given connection name.

        Parameters:
            connection_name (str): The name of the connection.

        Returns:
            snowflake.connector.SnowflakeConnection: The Snowflake connection object if found, otherwise None.
        """
        if connection_name in self.opened_connections:
            return self.opened_connections[connection_name]
        return None

    def close_connection(self, connection_name: str) -> None:
        """
        Closes the connection with the specified name.

        Parameters:
        - connection_name (str): The name of the connection to be closed.

        Raises:
        - Exception: If an error occurs while closing the connection.

        Returns:
        - None
        """
        try:
            if connection_name in self.opened_connections:
                connection = self.opened_connections[connection_name]
                connection.close()
                del connection
            self._active_schemas.pop(connection_name, None)
            self._active_query_tags.pop(connection_name, None)
        except Exception as e:
            raise e

    def create_cursor(
        self, connection_name: str
    ) -> snowflake.connector.cursor.SnowflakeCursor:
        """
        Creates a cursor for the specified connection.

        Args:
            connection_name (str): The name of the connection.

        Returns:
            snowflake.connector.cursor.SnowflakeCursor: The created cursor.

        Raises:
            Exception: If an error occurs while creating the cursor.
        """
        try:
            connection = None
            if connection_name in self.opened_connections:
                connection = self.opened_connections[connection_name]
            if connection is None or connection.expired:
                self.reconnect(connection_name)
                connection = self.opened_connections[connection_name]
            return connection.cursor()
        except Exception as e:
            raise e

    def _apply_schema_if_changed(
        self,
        cursor: snowflake.connector.cursor.SnowflakeCursor,
        connection_name: str,
        schema_name: Optional[str],
    ) -> None:
        """Issue `USE SCHEMA` only when the target differs from the cached
        active schema for this connection (A6).
        """
        if not schema_name:
            return
        active = self._active_schemas.get(connection_name)
        if active == schema_name:
            return
        cursor.execute(f'USE SCHEMA {quote_identifier(schema_name)}')
        self._active_schemas[connection_name] = schema_name

    def _apply_query_tag_if_changed(
        self,
        cursor: snowflake.connector.cursor.SnowflakeCursor,
        connection_name: str,
        op_tag: Optional[str],
    ) -> None:
        """Issue `ALTER SESSION SET QUERY_TAG` only when the tag changes (E3).

        ``op_tag=None`` means "no operation-specific tag", which we map to the
        base plugin tag so untagged queries don't inherit whatever operation
        tag the previous query set on the session.
        """
        effective = op_tag or _BASE_QUERY_TAG
        active = self._active_query_tags.get(connection_name)
        if active == effective:
            return
        # effective is either the base tag constant or a build_op_tag() JSON
        # payload of short string fields, so the only character we need to
        # escape for a Snowflake string literal is the single quote.
        escaped = effective.replace("'", "''")
        cursor.execute(f"ALTER SESSION SET QUERY_TAG = '{escaped}'")
        self._active_query_tags[connection_name] = effective

    def _register_cursor(
        self, cursor: snowflake.connector.cursor.SnowflakeCursor
    ) -> int:
        tid = threading.get_ident()
        with self._lock:
            self._active_cursors[tid].append(cursor)
        return tid

    def _unregister_cursor(
        self,
        tid: int,
        cursor: snowflake.connector.cursor.SnowflakeCursor,
    ) -> None:
        with self._lock:
            lst = self._active_cursors.get(tid)
            if not lst:
                return
            try:
                lst.remove(cursor)
            except ValueError:
                pass
            if not lst:
                self._active_cursors.pop(tid, None)

    def _wire_close_to_unregister(
        self,
        cursor: snowflake.connector.cursor.SnowflakeCursor,
        tid: int,
    ) -> None:
        """Unregister the cursor when the caller closes it, so it remains
        cancellable across the whole fetch lifetime instead of only during
        ``cursor.execute()`` (A9).
        """
        _orig_close = cursor.close

        def _close_and_unregister(*args, **kwargs):
            self._unregister_cursor(tid, cursor)
            return _orig_close(*args, **kwargs)

        cursor.close = _close_and_unregister

    def cancel_pending_on_thread(self, thread_id: int) -> int:
        """Cancel every Snowflake query currently executing on `thread_id`.

        Called from another thread (typically the main UI thread when the
        user hits Cancel on a QgsTask running on a worker thread).

        Returns the number of cursors whose `cancel()` was invoked.
        """
        with self._lock:
            cursors = list(self._active_cursors.get(thread_id, ()))
        cancelled = 0
        for cursor in cursors:
            try:
                cursor.cancel()
                cancelled += 1
            except Exception as e:
                QgsMessageLog.logMessage(
                    f"cursor.cancel() failed: {e}",
                    "Snowflake Plugin",
                    Qgis.MessageLevel.Warning,
                )
        return cancelled

    def execute_query(
        self,
        connection_name: str,
        query: str,
        context_information: Dict[str, typing.Union[str, None]] = None,
        op_tag: Optional[str] = None,
    ) -> snowflake.connector.cursor.SnowflakeCursor:
        """
        Executes the given query on the specified connection.

        Args:
            connection_name (str): The name of the connection to use.
            query (str): The SQL query to execute.
            op_tag (str, optional): A QUERY_TAG value (built via
                ``build_op_tag``) for Snowflake cost attribution. Only applied
                when different from the tag cached for this connection.

        Returns:
            snowflake.connector.cursor.SnowflakeCursor: The cursor object used to execute the query.

        Raises:
            Exception: If an error occurs while executing the query.
        """
        cursor = self.create_cursor(connection_name)
        schema_name = None
        if context_information is not None:
            schema_name = context_information.get("schema_name")
        tid = self._register_cursor(cursor)
        try:
            self._apply_schema_if_changed(cursor, connection_name, schema_name)
            self._apply_query_tag_if_changed(cursor, connection_name, op_tag)
            cursor.execute(query)
        except Exception as e:
            self._unregister_cursor(tid, cursor)
            QgsMessageLog.logMessage(
                f"execute_query failed: {e}\n"
                f"Query (first 2000 chars): {query[:2000]}",
                "Snowflake Plugin",
                Qgis.MessageLevel.Critical,
            )
            raise e
        self._wire_close_to_unregister(cursor, tid)
        return cursor

    def execute_query_with_params(
        self,
        connection_name: str,
        query: str,
        params: Dict[str, typing.Union[str, None]] = None,
        context_information: Dict[str, typing.Union[str, None]] = None,
        op_tag: Optional[str] = None,
    ) -> snowflake.connector.cursor.SnowflakeCursor:
        """Executes a SQL query with parameters on a specified Snowflake connection.

        This method first creates a cursor for the given connection. If context
        information is provided and includes a 'schema_name', it sets the current
        schema for the session before executing the main query. The query is then
        executed with the provided parameters.

        Args:
            connection_name: The name of the Snowflake connection to use.
            query: The SQL query string to be executed.
            params: A dictionary of parameters to be bound to the query.
                Defaults to None.
            context_information: An optional dictionary containing contextual
                information. If it contains a 'schema_name' key with a non-None
                value, the 'USE SCHEMA' command will be executed before the main
                query. Defaults to None.

        Returns:
            A snowflake.connector.cursor.SnowflakeCursor object after executing
            the query.

        Raises:
            Exception: Propagates any exception raised by the underlying
                Snowflake connector during cursor creation or query execution.
        """
        cursor = self.create_cursor(connection_name)
        schema_name = None
        if context_information is not None:
            schema_name = context_information.get("schema_name")
        tid = self._register_cursor(cursor)
        try:
            self._apply_schema_if_changed(cursor, connection_name, schema_name)
            self._apply_query_tag_if_changed(cursor, connection_name, op_tag)
            cursor.execute(query, params=params)
        except Exception as e:
            self._unregister_cursor(tid, cursor)
            raise e
        self._wire_close_to_unregister(cursor, tid)
        return cursor

    def reconnect(self, connection_name: str) -> None:
        """
        Reconnects to the specified Snowflake connection.

        This method iterates through the list of opened connections and attempts to
        reconnect to the connection specified by the connection_name parameter.

        Args:
            connection_name (str): The name of the connection to reconnect to.

        Returns:
            None
        """
        auth_information = get_auth_information(connection_name)
        self.connect(connection_name, auth_information)

    @staticmethod
    def get_instance() -> "SFConnectionManager":
        """
        Returns the instance of the SFConnectionManager class.

        If the instance does not exist, it creates a new instance and returns it.

        Returns:
            SFConnectionManager: The instance of the SFConnectionManager class.
        """
        if SFConnectionManager._instance is None:
            SFConnectionManager._instance = SFConnectionManager()
        return SFConnectionManager._instance
