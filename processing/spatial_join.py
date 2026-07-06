"""Server-side spatial join between two Snowflake tables."""

import os

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterString,
    QgsProcessingParameterEnum,
    QgsProcessingOutputString,
)
from qgis.PyQt.QtCore import QCoreApplication
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
    OVERWRITE = "OVERWRITE"
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
            "Results are written to a new Snowflake table. "
            "Columns from the right table that duplicate left table columns "
            "are automatically prefixed with 'r_'."
        )

    def icon(self):
        return QIcon(os.path.join(_IMAGES_DIR, "qgis_logo.svg"))

    def tr(self, string):
        return QCoreApplication.translate("Processing", string)

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
        self.addParameter(QgsProcessingParameterBoolean(
            self.OVERWRITE,
            self.tr("Overwrite output table if it already exists"),
            defaultValue=False,
        ))
        self.addOutput(QgsProcessingOutputString(
            self.OUTPUT, self.tr("Result summary"),
        ))

    def _get_columns(self, mgr, connection_name, schema, table, ctx):
        """Return list of column names for a table."""
        from ..helpers.sql import quote_literal
        cursor = mgr.execute_query(
            connection_name,
            f"SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "  # nosec B608 - values escaped via quote_literal
            f"WHERE TABLE_SCHEMA ILIKE {quote_literal(schema)} "
            f"AND TABLE_NAME ILIKE {quote_literal(table)} "
            f"ORDER BY ORDINAL_POSITION",
            ctx,
        )
        return [r[0] for r in cursor.fetchall()] if cursor else []

    def processAlgorithm(self, parameters, context, feedback):
        from ..helpers.utils import get_auth_information
        from ..managers.sf_connection_manager import SFConnectionManager
        from ..helpers.sql import quote_identifier, quote_literal

        connection_name = self.parameterAsString(parameters, self.CONNECTION, context)
        schema = self.parameterAsString(parameters, self.SCHEMA, context)
        left = self.parameterAsString(parameters, self.LEFT_TABLE, context)
        left_geo = self.parameterAsString(parameters, self.LEFT_GEO, context)
        right = self.parameterAsString(parameters, self.RIGHT_TABLE, context)
        right_geo = self.parameterAsString(parameters, self.RIGHT_GEO, context)
        pred_idx = self.parameterAsEnum(parameters, self.PREDICATE, context)
        output = self.parameterAsString(parameters, self.OUTPUT_TABLE, context)
        overwrite = self.parameterAsBoolean(parameters, self.OVERWRITE, context)

        predicate = PREDICATES[pred_idx]

        auth = get_auth_information(connection_name)
        mgr = SFConnectionManager.get_instance()
        mgr.connect(connection_name, auth)

        qs = quote_identifier(schema)
        ql = quote_identifier(left)
        qr = quote_identifier(right)
        qo = quote_identifier(output)
        qlg = quote_identifier(left_geo)
        qrg = quote_identifier(right_geo)

        ctx = {"schema_name": schema}

        if not overwrite:
            exists_cursor = mgr.execute_query(
                connection_name,
                f"SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES "  # nosec B608 - values escaped via quote_literal
                f"WHERE TABLE_SCHEMA ILIKE {quote_literal(schema)} "
                f"AND TABLE_NAME ILIKE {quote_literal(output)}",
                ctx,
            )
            exists_row = exists_cursor.fetchone() if exists_cursor else None
            if exists_row and exists_row[0] > 0:
                raise QgsProcessingException(
                    f"Output table {schema}.{output} already exists. "
                    "Enable 'Overwrite' to replace it."
                )

        left_cols = {c.upper() for c in self._get_columns(mgr, connection_name, schema, left, ctx)}
        right_cols = self._get_columns(mgr, connection_name, schema, right, ctx)

        # Build right-side SELECT: skip right geo column, alias duplicates
        right_select_parts = []
        for col in right_cols:
            if col.upper() == right_geo.upper():
                continue
            qc = quote_identifier(col)
            if col.upper() in left_cols:
                right_select_parts.append(f"b.{qc} AS r_{qc}")
            else:
                right_select_parts.append(f"b.{qc}")

        right_select = ", ".join(right_select_parts)
        if right_select:
            select_clause = f"a.*, {right_select}"
        else:
            select_clause = "a.*"

        create_verb = "CREATE OR REPLACE TABLE" if overwrite else "CREATE TABLE"
        sql = (
            f"{create_verb} {qs}.{qo} AS "  # nosec B608 - create_verb and predicate are constants; identifiers escaped via quote_identifier; select_clause built from quoted identifiers
            f"SELECT {select_clause} "
            f"FROM {qs}.{ql} a "
            f"JOIN {qs}.{qr} b "
            f"ON {predicate}(a.{qlg}, b.{qrg})"
        )

        feedback.pushInfo(f"Running spatial join: {sql}")

        try:
            mgr.execute_query(connection_name, sql, ctx)
            count_cursor = mgr.execute_query(
                connection_name,
                f"SELECT COUNT(*) FROM {qs}.{qo}",  # nosec B608 - identifiers escaped via quote_identifier
                ctx,
            )
            count_result = count_cursor.fetchone() if count_cursor else None
            row_count = count_result[0] if count_result else 0
            summary = f"Spatial join complete. Output table {output} has {row_count} rows."
            feedback.pushInfo(summary)
        except Exception as e:
            summary = f"Error: {e}"
            feedback.reportError(summary)

        return {self.OUTPUT: summary}
