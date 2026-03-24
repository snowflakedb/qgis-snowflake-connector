"""Execute SQL -- run arbitrary SQL on Snowflake and optionally return results as a layer."""

import os

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingParameterString,
    QgsProcessingOutputString,
    Qgis,
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

        auth = get_auth_information(connection_name)
        mgr = SFConnectionManager.get_instance()
        mgr.connect(connection_name, auth)

        feedback.pushInfo(f"Executing SQL on '{connection_name}'...")
        try:
            result = mgr.execute_query(sql)
            row_count = len(result) if result else 0
            summary = f"Query executed successfully. Rows returned: {row_count}"
            feedback.pushInfo(summary)
        except Exception as e:
            summary = f"Error: {e}"
            feedback.reportError(summary)

        return {self.OUTPUT: summary}
