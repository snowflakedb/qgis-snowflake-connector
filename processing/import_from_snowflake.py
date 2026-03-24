"""Import from Snowflake -- download a Snowflake table to a local vector layer."""

import os

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingParameterString,
    QgsProcessingParameterNumber,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterEnum,
    QgsFields,
    QgsField,
    QgsFeature,
    QgsGeometry,
    QgsWkbTypes,
    QgsCoordinateReferenceSystem,
    Qgis,
)
from qgis.PyQt.QtCore import QCoreApplication, QMetaType, QVariant
from qgis.PyQt.QtGui import QIcon

_IMAGES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ui", "images")


class ImportFromSnowflakeAlgorithm(QgsProcessingAlgorithm):

    CONNECTION = "CONNECTION"
    SCHEMA = "SCHEMA"
    TABLE = "TABLE"
    GEO_COLUMN = "GEO_COLUMN"
    WHERE_CLAUSE = "WHERE_CLAUSE"
    LIMIT = "LIMIT"
    OUTPUT = "OUTPUT"

    def name(self):
        return "importfromsnowflake"

    def displayName(self):
        return self.tr("Import from Snowflake")

    def group(self):
        return self.tr("Database")

    def groupId(self):
        return "database"

    def shortHelpString(self):
        return self.tr(
            "Downloads features from a Snowflake table into a local vector layer. "
            "Supports optional WHERE filtering and row limit."
        )

    def icon(self):
        return QIcon(os.path.join(_IMAGES_DIR, "qgis_logo.svg"))

    def tr(self, string):
        return QCoreApplication.translate("Processing", string)

    def createInstance(self):
        return ImportFromSnowflakeAlgorithm()

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterString(
            self.CONNECTION, self.tr("Connection name"),
        ))
        self.addParameter(QgsProcessingParameterString(
            self.SCHEMA, self.tr("Schema name"), defaultValue="PUBLIC",
        ))
        self.addParameter(QgsProcessingParameterString(
            self.TABLE, self.tr("Table name"),
        ))
        self.addParameter(QgsProcessingParameterString(
            self.GEO_COLUMN, self.tr("Geometry column name"), defaultValue="GEO",
        ))
        self.addParameter(QgsProcessingParameterString(
            self.WHERE_CLAUSE, self.tr("WHERE clause (optional)"),
            optional=True, defaultValue="",
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.LIMIT, self.tr("Row limit (0 = no limit)"),
            type=QgsProcessingParameterNumber.Integer,
            defaultValue=50000, minValue=0,
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, self.tr("Output layer"),
        ))

    def processAlgorithm(self, parameters, context, feedback):
        from ..helpers.utils import get_auth_information
        from ..managers.sf_connection_manager import SFConnectionManager
        from ..helpers.sql import quote_identifier

        connection_name = self.parameterAsString(parameters, self.CONNECTION, context)
        schema = self.parameterAsString(parameters, self.SCHEMA, context)
        table = self.parameterAsString(parameters, self.TABLE, context)
        geo_col = self.parameterAsString(parameters, self.GEO_COLUMN, context)
        where = self.parameterAsString(parameters, self.WHERE_CLAUSE, context)
        limit = self.parameterAsInt(parameters, self.LIMIT, context)

        auth = get_auth_information(connection_name)
        mgr = SFConnectionManager.get_instance()
        mgr.connect(connection_name, auth)

        fq_table = f"{quote_identifier(schema)}.{quote_identifier(table)}"

        col_query = (
            f"SELECT COLUMN_NAME, DATA_TYPE "
            f"FROM INFORMATION_SCHEMA.COLUMNS "
            f"WHERE TABLE_SCHEMA ILIKE '{schema}' AND TABLE_NAME ILIKE '{table}' "
            f"ORDER BY ORDINAL_POSITION"
        )
        col_rows = mgr.execute_query(col_query, {"schema_name": schema})

        fields = QgsFields()
        type_map = {
            "NUMBER": QMetaType.Type.Double,
            "FLOAT": QMetaType.Type.Double,
            "TEXT": QMetaType.Type.QString,
            "VARCHAR": QMetaType.Type.QString,
            "BOOLEAN": QMetaType.Type.Bool,
            "DATE": QMetaType.Type.QDate,
            "TIME": QMetaType.Type.QTime,
            "TIMESTAMP_NTZ": QMetaType.Type.QDateTime,
            "TIMESTAMP_LTZ": QMetaType.Type.QDateTime,
            "TIMESTAMP_TZ": QMetaType.Type.QDateTime,
        }

        col_names = []
        for col_name, col_type in col_rows:
            if col_name.upper() == geo_col.upper():
                continue
            qt_type = type_map.get(col_type, QMetaType.Type.QString)
            fields.append(QgsField(col_name, qt_type))
            col_names.append(col_name)

        crs = QgsCoordinateReferenceSystem("EPSG:4326")
        (sink, dest_id) = self.parameterAsSink(
            parameters, self.OUTPUT, context,
            fields, QgsWkbTypes.Point, crs,
        )

        select_cols = ", ".join(quote_identifier(c) for c in col_names)
        sql = (
            f"SELECT {select_cols}, ST_ASWKB({quote_identifier(geo_col)}) AS _wkb "
            f"FROM {fq_table}"
        )
        if where:
            sql += f" WHERE {where}"
        if limit > 0:
            sql += f" LIMIT {limit}"

        feedback.pushInfo(f"Executing: {sql}")
        rows = mgr.execute_query(sql, {"schema_name": schema})

        total = len(rows)
        for i, row in enumerate(rows):
            if feedback.isCanceled():
                break

            feat = QgsFeature(fields)
            for j, val in enumerate(row[:-1]):
                feat.setAttribute(j, val)

            wkb = row[-1]
            if wkb is not None:
                geom = QgsGeometry()
                geom.fromWkb(bytes(wkb) if not isinstance(wkb, bytes) else wkb)
                feat.setGeometry(geom)

            sink.addFeature(feat)
            feedback.setProgress(int((i + 1) / total * 100) if total else 100)

        feedback.pushInfo(f"Imported {total} features from {fq_table}")
        return {self.OUTPUT: dest_id}
