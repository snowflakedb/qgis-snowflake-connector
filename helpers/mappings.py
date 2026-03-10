from qgis.core import QgsWkbTypes
from qgis.PyQt.QtCore import (QVariant,QMetaType)

from ..enums.snowflake_metadata_type import SnowflakeMetadataType


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
