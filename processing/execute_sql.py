"""Execute SQL -- run arbitrary SQL on Snowflake and optionally return results as a layer."""

import os

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterString,
    QgsProcessingOutputString,
)
from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtGui import QIcon

_IMAGES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ui", "images")


class ExecuteSQLAlgorithm(QgsProcessingAlgorithm):

    CONNECTION = "CONNECTION"
    SQL = "SQL"
    OUTPUT = "OUTPUT"

    def name(self):
        return "executesql"

    def displayName(self):
        return self.tr("Execute SQL")

    def group(self):
        return self.tr("Database")

    def groupId(self):
        return "database"

    def shortHelpString(self):
        return self.tr(
            "Executes an arbitrary SQL statement on a Snowflake connection. "
            "Useful in Processing models for DDL/DML steps (CREATE TABLE, INSERT, etc.)."
        )

    def icon(self):
        return QIcon(os.path.join(_IMAGES_DIR, "qgis_logo.svg"))

    def tr(self, string):
        return QCoreApplication.translate("Processing", string)

    def createInstance(self):
        return ExecuteSQLAlgorithm()

    def flags(self):
        # SNOW-3712080: run on the main thread so the confirmation prompt below
        # can be shown safely. This algorithm executes arbitrary SQL on the
        # user's Snowflake connection and can be triggered by an untrusted
        # Processing model (.model3), so it must not run unattended in the GUI
        # without explicit consent.
        return super().flags() | QgsProcessingAlgorithm.Flag.FlagNoThreading

    def _confirm_execution(self, connection_name, sql):
        """Require explicit consent before running attacker-supplied SQL."""
        from ..helpers.trust_policy import require_trusted_action_consent

        preview = sql if len(sql) <= 2000 else sql[:2000] + "\n…(truncated)"
        return require_trusted_action_consent(
            "Confirm SQL execution",
            "The Snowflake plugin is about to run a SQL statement on "
            f"connection '{connection_name}'.\n\n"
            "Only proceed if you trust the source of this statement (for "
            "example a Processing model you did not author).\n\n"
            f"{preview}",
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterString(
            self.CONNECTION, self.tr("Connection name"),
        ))
        self.addParameter(QgsProcessingParameterString(
            self.SQL, self.tr("SQL statement"), multiLine=True,
        ))
        self.addOutput(QgsProcessingOutputString(
            self.OUTPUT, self.tr("Result summary"),
        ))

    def processAlgorithm(self, parameters, context, feedback):
        from ..helpers.utils import get_auth_information
        from ..managers.sf_connection_manager import SFConnectionManager

        connection_name = self.parameterAsString(parameters, self.CONNECTION, context)
        sql = self.parameterAsString(parameters, self.SQL, context)

        if not self._confirm_execution(connection_name, sql):
            raise QgsProcessingException(
                "Execution of the SQL statement was cancelled by the user."
            )

        auth = get_auth_information(connection_name)
        mgr = SFConnectionManager.get_instance()
        # Reuse an existing open connection; connect() force-closes and rebuilds
        # the shared session, which disrupts already-loaded layers and can freeze
        # the UI thread when run synchronously.
        if mgr.get_connection(connection_name) is None:
            mgr.connect(connection_name, auth)

        feedback.pushInfo(f"Executing SQL on '{connection_name}'...")
        try:
            cursor = mgr.execute_query(connection_name, sql)
            is_select = sql.lstrip().upper().startswith(("SELECT", "WITH", "SHOW", "DESCRIBE", "DESC"))
            if cursor is None:
                summary = "Query executed successfully."
            elif is_select:
                rows = cursor.fetchall()
                summary = f"Query executed successfully. Rows returned: {len(rows)}"
            else:
                summary = f"Query executed successfully. Rows affected: {cursor.rowcount}"
            feedback.pushInfo(summary)
        except Exception as e:
            summary = f"Error: {e}"
            feedback.reportError(summary)

        return {self.OUTPUT: summary}
