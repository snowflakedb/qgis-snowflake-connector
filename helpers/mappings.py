from qgis.core import Qgis, QgsField, QgsWkbTypes
from qgis.PyQt.QtCore import (QVariant,QMetaType)

from ..enums.snowflake_metadata_type import SnowflakeMetadataType


def create_qgs_field(name, metatype, type_name="", sub_type=None):
    """Construct a QgsField in a QGIS-version-compatible way.

    QGIS >= 3.38 accepts a QMetaType.Type argument; older builds (e.g. QGIS
    3.34 on Qt5) only accept the deprecated QVariant.Type overload. QVariant.Type
    and QMetaType.Type share the same integer values for the types used here, so
    converting via int() is safe.
    """
    if Qgis.QGIS_VERSION_INT >= 33800:
        field = QgsField(name, metatype, type_name)
        if sub_type is not None:
            field.setSubType(sub_type)
        return field
    field = QgsField(name, QVariant.Type(int(metatype)), type_name)
    if sub_type is not None:
        field.setSubType(QVariant.Type(int(sub_type)))
    return field


def map_numeric_type(data_type: str, numeric_scale):
    """Map a Snowflake numeric column to a QMetaType, honoring scale.

    A ``NUMBER``/``DECIMAL``/``NUMERIC`` column declared with scale 0 is an
    integer (including primary keys); mapping it to ``Double`` makes QGIS show
    values like ``1.0`` and breaks integer joins. Anything with a fractional
    scale (or an unknown scale) falls back to the type table.
    """
    if data_type in ("NUMBER", "DECIMAL", "NUMERIC") and str(numeric_scale) in (
        "0",
        "0.0",
    ):
        return QMetaType.Type.LongLong
    return mapping_snowflake_qgis_type[data_type]


mapping_single_to_multi_geometry_type = {
    "Point": "MultiPoint",
    "LineString": "MultiLineString",
    "Polygon": "MultiPolygon",
}

mapping_multi_single_to_geometry_type = {
    "MultiPoint": "Point",
    "MultiLineString": "LineString",
    "MultiPolygon": "Polygon",
}

mapping_snowflake_qgis_geometry = {
    "LineString": QgsWkbTypes.LineString,
    "MultiLineString": QgsWkbTypes.MultiLineString,
    "MultiPoint": QgsWkbTypes.MultiPoint,
    "MultiPolygon": QgsWkbTypes.MultiPolygon,
    "Point": QgsWkbTypes.Point,
    "Polygon": QgsWkbTypes.Polygon,
}

mapping_snowflake_qgis_type = {
    "BIGINT": QMetaType.Type.Int,
    "BOOLEAN": QMetaType.Type.Bool,
    "DATE": QMetaType.Type.QDate,
    "TIME": QMetaType.Type.QTime,
    "DOUBLE": QMetaType.Type.Double,
    "FLOAT": QMetaType.Type.Double,
    "INTEGER": QMetaType.Type.Int,
    "TIMESTAMP": QMetaType.Type.QDateTime,
    "VARCHAR": QMetaType.Type.QString,
    # Type used for custom sql when table is not created
    # Not difference betwenn float and integer so all the numeric field are NUMBER
    "NUMBER": QMetaType.Type.Double,
    "STRING": QMetaType.Type.QString,
    "Date": QMetaType.Type.QDate,
    "BOOL": QMetaType.Type.Bool,
    "JSON": QMetaType.Type.QString,
    "TEXT": QMetaType.Type.QString,
    "ARRAY": QMetaType.Type.QVariantList,
    "BINARY": QMetaType.Type.QByteArray,
    "GEOGRAPHY": QMetaType.Type.QString,
    "GEOMETRY": QMetaType.Type.QString,
    "OBJECT": QMetaType.Type.QString,
    "TIMESTAMP_LTZ": QMetaType.Type.QDateTime,
    "TIMESTAMP_NTZ": QMetaType.Type.QDateTime,
    "TIMESTAMP_TZ": QMetaType.Type.QDateTime,
    "VARIANT": QMetaType.Type.QString,
}


SNOWFLAKE_METADATA_TYPE_CODE_DICT = {
    SnowflakeMetadataType.FIXED.value: {
        "name": SnowflakeMetadataType.FIXED.name,
        "qvariant_type": QMetaType.Type.Double,
    },  # NUMBER/INT
    SnowflakeMetadataType.REAL.value: {
        "name": SnowflakeMetadataType.REAL.name,
        "qvariant_type": QMetaType.Type.Double,
    },  # REAL
    SnowflakeMetadataType.TEXT.value: {
        "name": SnowflakeMetadataType.TEXT.name,
        "qvariant_type": QMetaType.Type.QString,
    },  # VARCHAR/STRING
    SnowflakeMetadataType.DATE.value: {
        "name": SnowflakeMetadataType.DATE.name,
        "qvariant_type": QMetaType.Type.QDate,
    },  # DATE
    SnowflakeMetadataType.TIMESTAMP.value: {
        "name": SnowflakeMetadataType.TIMESTAMP.name,
        "qvariant_type": QMetaType.Type.QDateTime,
    },  # TIMESTAMP
    SnowflakeMetadataType.VARIANT.value: {
        "name": SnowflakeMetadataType.VARIANT.name,
        "qvariant_type": QMetaType.Type.QString,
    },  # VARIANT
    SnowflakeMetadataType.TIMESTAMP_LTZ.value: {
        "name": SnowflakeMetadataType.TIMESTAMP_LTZ.name,
        "qvariant_type": QMetaType.Type.QDateTime,
    },  # TIMESTAMP_LTZ
    SnowflakeMetadataType.TIMESTAMP_TZ.value: {
        "name": SnowflakeMetadataType.TIMESTAMP_TZ.name,
        "qvariant_type": QMetaType.Type.QDateTime,
    },  # TIMESTAMP_TZ
    SnowflakeMetadataType.TIMESTAMP_NTZ.value: {
        "name": SnowflakeMetadataType.TIMESTAMP_NTZ.name,
        "qvariant_type": QMetaType.Type.QDateTime,
    },  # TIMESTAMP_NTZ
    SnowflakeMetadataType.OBJECT.value: {
        "name": SnowflakeMetadataType.OBJECT.name,
        "qvariant_type": QMetaType.Type.QString,
    },  # OBJECT
    SnowflakeMetadataType.ARRAY.value: {
        "name": SnowflakeMetadataType.ARRAY.name,
        "qvariant_type": QMetaType.Type.QString,
    },  # ARRAY
    SnowflakeMetadataType.BINARY.value: {
        "name": SnowflakeMetadataType.BINARY.name,
        "qvariant_type": QMetaType.Type.QBitArray,
    },  # BINARY
    SnowflakeMetadataType.TIME.value: {
        "name": SnowflakeMetadataType.TIME.name,
        "qvariant_type": QMetaType.Type.QTime,
    },  # TIME
    SnowflakeMetadataType.BOOLEAN.value: {
        "name": SnowflakeMetadataType.BOOLEAN.name,
        "qvariant_type": QMetaType.Type.Bool,
    },  # BOOLEAN
    SnowflakeMetadataType.GEOGRAPHY.value: {
        "name": SnowflakeMetadataType.GEOGRAPHY.name,
        "qvariant_type": QMetaType.Type.QString,
    },  # GEOGRAPHY
    SnowflakeMetadataType.GEOMETRY.value: {
        "name": SnowflakeMetadataType.GEOMETRY.name,
        "qvariant_type": QMetaType.Type.QString,
    },  # GEOMETRY
    SnowflakeMetadataType.VECTOR.value: {
        "name": SnowflakeMetadataType.VECTOR.name,
        "qvariant_type": QMetaType.Type.QVector2D,
    },  # VECTOR
}
