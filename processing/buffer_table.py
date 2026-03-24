"""Server-side buffer on a Snowflake geography/geometry table."""

import os

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingParameterString,
    QgsProcessingParameterNumber,
    QgsProcessingOutputString,
    Qgis,
)
from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtGui import QIcon

_IMAGES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ui", "images")


class BufferTableAlgorithm(QgsProcessingAlgorithm):

    CONNECTION = "CONNECTION"
    SCHEMA = "SCHEMA"
    TABLE = "TABLE"
    GEO_COLUMN = "GEO_COLUMN"
    DISTANCE = "DISTANCE"
    OUTPUT_TABLE = "OUTPUT_TABLE"
    OUTPUT = "OUTPUT"

    def name(self):
        return "buffertable"

    def displayName(self):
        return self.tr("Buffer (server-side)")

    def group(self):
        return self.tr("Analysis")

    def groupId(self):
        return "analysis"

    def shortHelpString(self):
        return self.tr(
            "Creates a buffer around features in a Snowflake table using ST_BUFFER. "
            "The operation runs entirely on the Snowflake server. "
            "Distance is in meters for GEOGRAPHY columns."
        )

    def icon(self):
        return QIcon(os.path.join(_IMAGES_DIR, "qgis_logo.svg"))

    def tr(self, string):
        return QCoreApplication.translate("Processing", string)

    def createInstance(self):
        return BufferTableAlgorithm()

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterString(
            self.CONNECTION, self.tr("Connection name"),
        ))
        self.addParameter(QgsProcessingParameterString(
            self.SCHEMA, self.tr("Schema"), defaultValue="PUBLIC",
        ))
        self.addParameter(QgsProcessingParameterString(
            self.TABLE, self.tr("Table name"),
        ))
        self.addParameter(QgsProcessingParameterString(
            self.GEO_COLUMN, self.tr("Geometry column"), defaultValue="GEO",
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.DISTANCE, self.tr("Buffer distance (meters)"),
            type=QgsProcessingParameterNumber.Double,
            defaultValue=1000.0, minValue=0.0,
        ))
        self.addParameter(QgsProcessingParameterString(
            self.OUTPUT_TABLE, self.tr("Output table name"),
        ))
        self.addOutput(QgsProcessingOutputString(
            self.OUTPUT, self.tr("Result summary"),
        ))

    def processAlgorithm(self, parameters, context, feedback):
        from ..helpers.utils import get_auth_information
        from ..managers.sf_connection_manager import SFConnectionManager
        from ..helpers.sql import quote_identifier

        connection_name = self.parameterAsString(parameters, self.CONNECTION, context)
        schema = self.parameterAsString(parameters, self.SCHEMA, context)
        table = self.parameterAsString(parameters, self.TABLE, context)
        geo_col = self.parameterAsString(parameters, self.GEO_COLUMN, context)
        distance = self.parameterAsDouble(parameters, self.DISTANCE, context)
        output = self.parameterAsString(parameters, self.OUTPUT_TABLE, context)

        auth = get_auth_information(connection_name)
        mgr = SFConnectionManager.get_instance()
        mgr.connect(connection_name, auth)

        qs = quote_identifier(schema)
        qt = quote_identifier(table)
        qg = quote_identifier(geo_col)
        qo = quote_identifier(output)

        sql = (
            f"CREATE OR REPLACE TABLE {qs}.{qo} AS "
            f"SELECT * EXCLUDE ({qg}), "
            f"ST_BUFFER({qg}, {distance}) AS {qg} "
            f"FROM {qs}.{qt}"
        )

        feedback.pushInfo(f"Running buffer: {sql}")

        try:
            mgr.execute_query(sql, {"schema_name": schema})
            count_result = mgr.execute_query(
                f"SELECT COUNT(*) FROM {qs}.{qo}",
                {"schema_name": schema},
            )
            row_count = count_result[0][0] if count_result else 0
            summary = f"Buffer complete. Output table {output} has {row_count} rows."
            feedback.pushInfo(summary)
        except Exception as e:
            summary = f"Error: {e}"
            feedback.reportError(summary)

        return {self.OUTPUT: summary}
