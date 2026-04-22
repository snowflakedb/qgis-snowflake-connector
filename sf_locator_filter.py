"""QgsLocatorFilter for quick Snowflake table search from the QGIS search bar.

Usage: type 'sf ' followed by a table name fragment (e.g. 'sf customers').
"""

from qgis.core import (
    QgsApplication,
    QgsLocatorFilter,
    QgsLocatorResult,
    Qgis,
    QgsMessageLog,
)


class SFLocatorFilter(QgsLocatorFilter):

    def __init__(self, parent=None):
        super().__init__(parent)

    def name(self):
        return "snowflake_tables"

    def displayName(self):
        return "Snowflake Tables"

    def prefix(self):
        return "sf"

    def priority(self):
        return QgsLocatorFilter.Priority.Medium

    def clone(self):
        return SFLocatorFilter()

    def fetchResults(self, string, context, feedback):
        if len(string) < 2:
            return

        try:
            from .helpers.utils import get_connection_child_groups, get_auth_information
            from .helpers.sql import quote_literal
            from .managers.sf_connection_manager import SFConnectionManager

            connections = get_connection_child_groups()

            for conn_name in connections:
                if feedback.isCanceled():
                    return

                try:
                    auth = get_auth_information(conn_name)
                    mgr = SFConnectionManager.get_instance()
                    if mgr.get_connection(conn_name) is None:
                        mgr.connect(conn_name, auth)

                    sql = (
                        f"SELECT TABLE_SCHEMA, TABLE_NAME "
                        f"FROM INFORMATION_SCHEMA.TABLES "
                        f"WHERE TABLE_NAME ILIKE {quote_literal(f'%{string}%')} "
                        f"AND TABLE_SCHEMA != 'INFORMATION_SCHEMA' "
                        f"ORDER BY TABLE_NAME LIMIT 20"
                    )
                    cursor = mgr.execute_query(conn_name, sql)
                    rows = cursor.fetchall() if cursor else []
                    cursor.close() if cursor else None

                    for schema_name, table_name in rows:
                        if feedback.isCanceled():
                            return

                        result = QgsLocatorResult()
                        result.filter = self
                        result.displayString = f"{table_name} ({conn_name}/{schema_name})"
                        result.description = f"Snowflake table in {auth.get('database', '')}.{schema_name}"
                        result.userData = {
                            "connection": conn_name,
                            "schema": schema_name,
                            "table": table_name,
                        }
                        self.resultFetched.emit(result)

                except Exception as inner:
                    QgsMessageLog.logMessage(
                        f"Locator search on '{conn_name}' failed: {inner}",
                        "Snowflake Plugin",
                        Qgis.MessageLevel.Warning,
                    )
                    continue

        except Exception as e:
            QgsMessageLog.logMessage(
                f"Locator search error: {e}",
                "Snowflake Plugin",
                Qgis.MessageLevel.Warning,
            )

    def triggerResult(self, result):
        data = result.userData
        if not data:
            return

        try:
            conn_name = data["connection"]
            schema = data["schema"]
            table = data["table"]

            from .helpers.utils import get_auth_information
            from .helpers.sql import quote_literal
            from .managers.sf_connection_manager import SFConnectionManager
            from .tasks.sf_convert_column_to_layer_task import SFConvertColumnToLayerTask

            auth = get_auth_information(conn_name)
            mgr = SFConnectionManager.get_instance()
            if mgr.get_connection(conn_name) is None:
                mgr.connect(conn_name, auth)

            geo_query = (
                f"SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                f"WHERE TABLE_SCHEMA ILIKE {quote_literal(schema)} "
                f"AND TABLE_NAME ILIKE {quote_literal(table)} "
                f"AND DATA_TYPE IN ('GEOGRAPHY', 'GEOMETRY') "
                f"ORDER BY ORDINAL_POSITION"
            )
            cursor = mgr.execute_query(
                conn_name, geo_query, {"schema_name": schema}
            )
            geo_rows = cursor.fetchall() if cursor else []
            cursor.close() if cursor else None

            if not geo_rows:
                QgsMessageLog.logMessage(
                    f"No GEOGRAPHY/GEOMETRY column found in {schema}.{table}",
                    "Snowflake Plugin",
                    Qgis.MessageLevel.Warning,
                )
                return

            geo_column = geo_rows[0][0]

            context_information = {
                "connection_name": conn_name,
                "database_name": auth.get("database", ""),
                "schema_name": schema,
                "table_name": table,
                "geo_column": geo_column,
                "primary_key": "",
            }
            task = SFConvertColumnToLayerTask(
                context_information=context_information,
                path=f"locator:{conn_name}/{schema}/{table}",
            )
            QgsApplication.taskManager().addTask(task)

            QgsMessageLog.logMessage(
                f"Loading Snowflake table: {schema}.{table}.{geo_column} from {conn_name}",
                "Snowflake Plugin",
                Qgis.MessageLevel.Info,
            )

        except Exception as e:
            QgsMessageLog.logMessage(
                f"Locator trigger error: {e}",
                "Snowflake Plugin",
                Qgis.MessageLevel.Warning,
            )
