"""QgsLocatorFilter for quick Snowflake table search from the QGIS search bar.

Usage: type 'sf ' followed by a table name fragment (e.g. 'sf customers').
"""

from qgis.core import (
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
            connections = get_connection_child_groups()

            for conn_name in connections:
                if feedback.isCanceled():
                    return

                try:
                    auth = get_auth_information(conn_name)
                    from .managers.sf_connection_manager import SFConnectionManager
                    mgr = SFConnectionManager.get_instance()
                    mgr.connect(conn_name)

                    sql = (
                        f"SELECT TABLE_SCHEMA, TABLE_NAME "
                        f"FROM INFORMATION_SCHEMA.TABLES "
                        f"WHERE TABLE_NAME ILIKE '%{string}%' "
                        f"AND TABLE_SCHEMA != 'INFORMATION_SCHEMA' "
                        f"ORDER BY TABLE_NAME LIMIT 20"
                    )
                    rows = mgr.execute_query(sql)

                    for schema_name, table_name in (rows or []):
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

                except Exception:
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
            from .helpers.data_base import get_geo_columns

            auth = get_auth_information(conn_name)

            from qgis.core import QgsVectorLayer

            uri = (
                f"connection_name={conn_name} "
                f"schema_name={schema} "
                f"table_name={table}"
            )

            QgsMessageLog.logMessage(
                f"Loading Snowflake table: {schema}.{table} from {conn_name}",
                "Snowflake Plugin",
                Qgis.MessageLevel.Info,
            )

        except Exception as e:
            QgsMessageLog.logMessage(
                f"Locator trigger error: {e}",
                "Snowflake Plugin",
                Qgis.MessageLevel.Warning,
            )
