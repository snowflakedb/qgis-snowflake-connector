"""Server-side H3 indexing -- convert a geography table to H3 cells."""

import os

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingParameterString,
    QgsProcessingParameterNumber,
    QgsProcessingOutputString,
    Qgis,
)
from qgis.PyQt.QtGui import QIcon

_IMAGES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ui", "images")


class H3IndexAlgorithm(QgsProcessingAlgorithm):

    CONNECTION = "CONNECTION"
    SCHEMA = "SCHEMA"
    TABLE = "TABLE"
    GEO_COLUMN = "GEO_COLUMN"
    RESOLUTION = "RESOLUTION"
    OUTPUT_TABLE = "OUTPUT_TABLE"
    OUTPUT = "OUTPUT"

    def name(self):
        return "h3index"

    def displayName(self):
        return self.tr("H3 Index (server-side)")

    def group(self):
        return self.tr("Analysis")

    def groupId(self):
        return "analysis"

    def shortHelpString(self):
        return self.tr(
            "Converts point features in a Snowflake table to H3 cell indices "
            "at the specified resolution using H3_LATLNG_TO_CELL. "
            "Creates a new table with the H3 index and boundary geography."
        )

    def icon(self):
        return QIcon(os.path.join(_IMAGES_DIR, "qgis_logo.svg"))

    def createInstance(self):
        return H3IndexAlgorithm()

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterString(
            self.CONNECTION, self.tr("Connection name"),
        ))
        self.addParameter(QgsProcessingParameterString(
            self.SCHEMA, self.tr("Schema"), defaultValue="PUBLIC",
        ))
        self.addParameter(QgsProcessingParameterString(
            self.TABLE, self.tr("Source table"),
        ))
        self.addParameter(QgsProcessingParameterString(
            self.GEO_COLUMN, self.tr("Geometry column (point)"), defaultValue="GEO",
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.RESOLUTION, self.tr("H3 resolution (0-15)"),
            type=QgsProcessingParameterNumber.Integer,
            defaultValue=7, minValue=0, maxValue=15,
        ))
        self.addParameter(QgsProcessingParameterString(
            self.OUTPUT_TABLE, self.tr("Output table name"),
        ))
        self.addOutput(QgsProcessingOutputString(
            self.OUTPUT, self.tr("Result summary"),
        ))

    def processAlgorithm(self, parameters, context, feedback):
        from ..managers.sf_connection_manager import SFConnectionManager
        from ..helpers.sql import quote_identifier

        connection_name = self.parameterAsString(parameters, self.CONNECTION, context)
        schema = self.parameterAsString(parameters, self.SCHEMA, context)
        table = self.parameterAsString(parameters, self.TABLE, context)
        geo_col = self.parameterAsString(parameters, self.GEO_COLUMN, context)
        resolution = self.parameterAsInt(parameters, self.RESOLUTION, context)
        output = self.parameterAsString(parameters, self.OUTPUT_TABLE, context)

        mgr = SFConnectionManager.get_instance()
        mgr.connect(connection_name)

        qs = quote_identifier(schema)
        qt = quote_identifier(table)
        qg = quote_identifier(geo_col)
        qo = quote_identifier(output)

        sql = (
            f"CREATE OR REPLACE TABLE {qs}.{qo} AS "
            f"SELECT *, "
            f"H3_LATLNG_TO_CELL(ST_Y({qg}), ST_X({qg}), {resolution}) AS H3_INDEX, "
            f"H3_CELL_TO_BOUNDARY(H3_LATLNG_TO_CELL(ST_Y({qg}), ST_X({qg}), {resolution})) AS H3_BOUNDARY "
            f"FROM {qs}.{qt} "
            f"WHERE {qg} IS NOT NULL"
        )

        feedback.pushInfo(f"Running H3 indexing at resolution {resolution}: {sql}")

        try:
            mgr.execute_query(sql, {"schema_name": schema})
            count_result = mgr.execute_query(
                f"SELECT COUNT(*) FROM {qs}.{qo}",
                {"schema_name": schema},
            )
            row_count = count_result[0][0] if count_result else 0
            summary = f"H3 indexing complete. Output table {output} has {row_count} rows at resolution {resolution}."
            feedback.pushInfo(summary)
        except Exception as e:
            summary = f"Error: {e}"
            feedback.reportError(summary)

        return {self.OUTPUT: summary}
