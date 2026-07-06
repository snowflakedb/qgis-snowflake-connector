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
        return super().flags() | QgsProcessingAlgorithm.FlagNoThreading

    def _confirm_execution(self, connection_name, sql):
        """Require explicit user consent when a GUI is available.

        Headless runs (qgis_process CLI / PyQGIS) are treated as user-initiated
        and proceed without a prompt; interactive runs must be confirmed so a
        malicious Processing model cannot silently run SQL as the victim.
        """
        try:
            from qgis.utils import iface
        except Exception:
            iface = None
        if iface is None:
            return True

        from qgis.PyQt.QtWidgets import QMessageBox
        from qgis.PyQt.QtCore import Qt

        preview = sql if len(sql) <= 2000 else sql[:2000] + "\n…(truncated)"
        box = QMessageBox(iface.mainWindow())
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Confirm SQL execution")
        # Plain text so a crafted connection name / SQL cannot render rich text.
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.setText(
            "The Snowflake plugin is about to run a SQL statement on "
            f"connection '{connection_name}'.\n\n"
            "Only proceed if you trust the source of this statement (for "
            "example a Processing model you did not author).\n\n"
            f"{preview}"
        )
        box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        box.setDefaultButton(QMessageBox.StandardButton.No)
        return box.exec() == QMessageBox.StandardButton.Yes

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
