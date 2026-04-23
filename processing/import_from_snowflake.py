"""Import from Snowflake -- download a Snowflake table to a local vector layer."""

import os

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingParameterString,
    QgsProcessingParameterNumber,
    QgsProcessingParameterFeatureSink,
    QgsFields,
    QgsField,
    QgsFeature,
    QgsGeometry,
    QgsWkbTypes,
    QgsCoordinateReferenceSystem,
)
from qgis.PyQt.QtCore import QCoreApplication, QMetaType
from qgis.PyQt.QtGui import QIcon

_IMAGES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ui", "images")


_GEO_TYPE_TO_WKB = {
    "Point": QgsWkbTypes.Point,
    "MultiPoint": QgsWkbTypes.MultiPoint,
    "LineString": QgsWkbTypes.LineString,
    "MultiLineString": QgsWkbTypes.MultiLineString,
    "Polygon": QgsWkbTypes.Polygon,
    "MultiPolygon": QgsWkbTypes.MultiPolygon,
    "GeometryCollection": QgsWkbTypes.GeometryCollection,
}


def _pick_wkb_type(geo_types):
    """Choose a WKB type that can hold all detected source geometry types."""
    if not geo_types:
        return QgsWkbTypes.Unknown
    unique = list(dict.fromkeys(geo_types))
    if len(unique) == 1:
        return _GEO_TYPE_TO_WKB.get(unique[0], QgsWkbTypes.Unknown)
    categories = set()
    for t in unique:
        if "Point" in t:
            categories.add("point")
        elif "LineString" in t:
            categories.add("line")
        elif "Polygon" in t:
            categories.add("polygon")
        else:
            categories.add("other")
    if categories == {"point"}:
        return QgsWkbTypes.MultiPoint
    if categories == {"line"}:
        return QgsWkbTypes.MultiLineString
    if categories == {"polygon"}:
        return QgsWkbTypes.MultiPolygon
    return QgsWkbTypes.GeometryCollection


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
        from ..helpers.data_base import (
            get_geo_column_type,
            get_srid_from_table_geo_column,
            get_type_from_table_geo_column,
        )
        from ..helpers.utils import get_auth_information
        from ..helpers.sql import quote_identifier, quote_literal
        from ..managers.sf_connection_manager import SFConnectionManager

        connection_name = self.parameterAsString(parameters, self.CONNECTION, context)
        schema = self.parameterAsString(parameters, self.SCHEMA, context)
        table = self.parameterAsString(parameters, self.TABLE, context)
        geo_col = self.parameterAsString(parameters, self.GEO_COLUMN, context)
        where = self.parameterAsString(parameters, self.WHERE_CLAUSE, context)
        limit = self.parameterAsInt(parameters, self.LIMIT, context)

        auth = get_auth_information(connection_name)
        mgr = SFConnectionManager.get_instance()
        if mgr.get_connection(connection_name) is None:
            mgr.connect(connection_name, auth)

        ctx_info = {
            "connection_name": connection_name,
            "database_name": auth.get("database", ""),
            "schema_name": schema,
            "table_name": table,
        }

        geo_column_type = get_geo_column_type(geo_col, ctx_info) or "GEOGRAPHY"

        if geo_column_type == "GEOMETRY":
            try:
                srid = get_srid_from_table_geo_column(geo_col, table, ctx_info) or 4326
            except Exception:
                srid = 4326
        else:
            srid = 4326

        try:
            geo_types = get_type_from_table_geo_column(geo_col, table, ctx_info)
        except Exception:
            geo_types = []
        wkb_type = _pick_wkb_type(geo_types)
        feedback.pushInfo(
            f"Detected geo column type={geo_column_type}, srid={srid}, "
            f"geometry types={geo_types or 'unknown'}"
        )

        fq_table = f"{quote_identifier(schema)}.{quote_identifier(table)}"

        col_query = (
            f"SELECT COLUMN_NAME, DATA_TYPE "  # nosec B608 - values escaped via quote_literal
            f"FROM INFORMATION_SCHEMA.COLUMNS "
            f"WHERE TABLE_SCHEMA ILIKE {quote_literal(schema)} "
            f"AND TABLE_NAME ILIKE {quote_literal(table)} "
            f"ORDER BY ORDINAL_POSITION"
        )
        col_cursor = mgr.execute_query(connection_name, col_query, {"schema_name": schema})
        col_rows = col_cursor.fetchall() if col_cursor else []
        if col_cursor:
            col_cursor.close()

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

        crs = QgsCoordinateReferenceSystem.fromEpsgId(int(srid))
        (sink, dest_id) = self.parameterAsSink(
            parameters, self.OUTPUT, context,
            fields, wkb_type, crs,
        )

        select_cols = ", ".join(quote_identifier(c) for c in col_names)
        geo_select = f"ST_ASWKB({quote_identifier(geo_col)}) AS _wkb"
        if select_cols:
            sql = f"SELECT {select_cols}, {geo_select} FROM {fq_table}"  # nosec B608 - select_cols and fq_table built from quote_identifier; geo_select uses quote_identifier
        else:
            sql = f"SELECT {geo_select} FROM {fq_table}"  # nosec B608 - fq_table and geo_select built from quote_identifier
        if where:
            sql += f" WHERE {where}"
        if limit > 0:
            sql += f" LIMIT {limit}"

        feedback.pushInfo(f"Executing: {sql}")
        row_cursor = mgr.execute_query(connection_name, sql, {"schema_name": schema})
        rows = row_cursor.fetchall() if row_cursor else []
        if row_cursor:
            row_cursor.close()

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
