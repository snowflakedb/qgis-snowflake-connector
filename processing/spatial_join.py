"""Server-side spatial join between two Snowflake tables."""

import os

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingParameterString,
    QgsProcessingParameterEnum,
    QgsProcessingOutputString,
    Qgis,
)
from qgis.PyQt.QtGui import QIcon

_IMAGES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ui", "images")

PREDICATES = [
    "ST_INTERSECTS",
    "ST_CONTAINS",
    "ST_WITHIN",
    "ST_DWITHIN",
]


class SpatialJoinAlgorithm(QgsProcessingAlgorithm):

    CONNECTION = "CONNECTION"
    SCHEMA = "SCHEMA"
    LEFT_TABLE = "LEFT_TABLE"
    LEFT_GEO = "LEFT_GEO"
    RIGHT_TABLE = "RIGHT_TABLE"
    RIGHT_GEO = "RIGHT_GEO"
    PREDICATE = "PREDICATE"
    OUTPUT_TABLE = "OUTPUT_TABLE"
    OUTPUT = "OUTPUT"

    def name(self):
        return "spatialjoin"

    def displayName(self):
        return self.tr("Spatial Join (server-side)")

    def group(self):
        return self.tr("Analysis")

    def groupId(self):
        return "analysis"

    def shortHelpString(self):
        return self.tr(
            "Performs a server-side spatial join between two Snowflake tables "
            "using a chosen spatial predicate (ST_INTERSECTS, ST_CONTAINS, etc.). "
            "Results are written to a new Snowflake table."
        )

    def icon(self):
        return QIcon(os.path.join(_IMAGES_DIR, "qgis_logo.svg"))

    def createInstance(self):
        return SpatialJoinAlgorithm()

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterString(
            self.CONNECTION, self.tr("Connection name"),
        ))
        self.addParameter(QgsProcessingParameterString(
            self.SCHEMA, self.tr("Schema"), defaultValue="PUBLIC",
        ))
        self.addParameter(QgsProcessingParameterString(
            self.LEFT_TABLE, self.tr("Left table"),
        ))
        self.addParameter(QgsProcessingParameterString(
            self.LEFT_GEO, self.tr("Left geometry column"),
        ))
        self.addParameter(QgsProcessingParameterString(
            self.RIGHT_TABLE, self.tr("Right table"),
        ))
        self.addParameter(QgsProcessingParameterString(
            self.RIGHT_GEO, self.tr("Right geometry column"),
        ))
        self.addParameter(QgsProcessingParameterEnum(
            self.PREDICATE, self.tr("Spatial predicate"),
            options=PREDICATES, defaultValue=0,
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
        left = self.parameterAsString(parameters, self.LEFT_TABLE, context)
        left_geo = self.parameterAsString(parameters, self.LEFT_GEO, context)
        right = self.parameterAsString(parameters, self.RIGHT_TABLE, context)
        right_geo = self.parameterAsString(parameters, self.RIGHT_GEO, context)
        pred_idx = self.parameterAsEnum(parameters, self.PREDICATE, context)
        output = self.parameterAsString(parameters, self.OUTPUT_TABLE, context)

        predicate = PREDICATES[pred_idx]

        mgr = SFConnectionManager.get_instance()
        mgr.connect(connection_name)

        qs = quote_identifier(schema)
        ql = quote_identifier(left)
        qr = quote_identifier(right)
        qo = quote_identifier(output)
        qlg = quote_identifier(left_geo)
        qrg = quote_identifier(right_geo)

        sql = (
            f"CREATE OR REPLACE TABLE {qs}.{qo} AS "
            f"SELECT a.*, b.* EXCLUDE ({qrg}) "
            f"FROM {qs}.{ql} a "
            f"JOIN {qs}.{qr} b "
            f"ON {predicate}(a.{qlg}, b.{qrg})"
        )

        feedback.pushInfo(f"Running spatial join: {sql}")

        try:
            mgr.execute_query(sql, {"schema_name": schema})
            count_result = mgr.execute_query(
                f"SELECT COUNT(*) FROM {qs}.{qo}",
                {"schema_name": schema},
            )
            row_count = count_result[0][0] if count_result else 0
            summary = f"Spatial join complete. Output table {output} has {row_count} rows."
            feedback.pushInfo(summary)
        except Exception as e:
            summary = f"Error: {e}"
            feedback.reportError(summary)

        return {self.OUTPUT: summary}
