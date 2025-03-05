from qgis.core import QgsWkbTypes
from qgis.PyQt.QtCore import QVariant

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
    "BIGINT": QVariant.Int,
    "BOOLEAN": QVariant.Bool,
    "DATE": QVariant.Date,
    "TIME": QVariant.Time,
    "DOUBLE": QVariant.Double,
    "FLOAT": QVariant.Double,
    "INTEGER": QVariant.Int,
    "TIMESTAMP": QVariant.DateTime,
    "VARCHAR": QVariant.String,
    # Type used for custom sql when table is not created
    # Not difference betwenn float and integer so all the numeric field are NUMBER
    "NUMBER": QVariant.Double,
    "STRING": QVariant.String,
    "Date": QVariant.Date,
    "BOOL": QVariant.Bool,
    "JSON": QVariant.String,
    "TEXT": QVariant.String,
    "ARRAY": QVariant.List,
    "BINARY": QVariant.ByteArray,
    "GEOGRAPHY": QVariant.String,
    "GEOMETRY": QVariant.String,
    "OBJECT": QVariant.String,
    "TIMESTAMP_LTZ": QVariant.DateTime,
    "TIMESTAMP_NTZ": QVariant.DateTime,
    "TIMESTAMP_TZ": QVariant.DateTime,
    "VARIANT": QVariant.String,
}


SNOWFLAKE_METADATA_TYPE_CODE_DICT = {
    SnowflakeMetadataType.FIXED.value: {
        "name": SnowflakeMetadataType.FIXED.name,
        "qvariant_type": QVariant.Double,
    },  # NUMBER/INT
    SnowflakeMetadataType.REAL.value: {
        "name": SnowflakeMetadataType.REAL.name,
        "qvariant_type": QVariant.Double,
    },  # REAL
    SnowflakeMetadataType.TEXT.value: {
        "name": SnowflakeMetadataType.TEXT.name,
        "qvariant_type": QVariant.String,
    },  # VARCHAR/STRING
    SnowflakeMetadataType.DATE.value: {
        "name": SnowflakeMetadataType.DATE.name,
        "qvariant_type": QVariant.Date,
    },  # DATE
    SnowflakeMetadataType.TIMESTAMP.value: {
        "name": SnowflakeMetadataType.TIMESTAMP.name,
        "qvariant_type": QVariant.DateTime,
    },  # TIMESTAMP
    SnowflakeMetadataType.VARIANT.value: {
        "name": SnowflakeMetadataType.VARIANT.name,
        "qvariant_type": QVariant.String,
    },  # VARIANT
    SnowflakeMetadataType.TIMESTAMP_LTZ.value: {
        "name": SnowflakeMetadataType.TIMESTAMP_LTZ.name,
        "qvariant_type": QVariant.DateTime,
    },  # TIMESTAMP_LTZ
    SnowflakeMetadataType.TIMESTAMP_TZ.value: {
        "name": SnowflakeMetadataType.TIMESTAMP_TZ.name,
        "qvariant_type": QVariant.DateTime,
    },  # TIMESTAMP_TZ
    SnowflakeMetadataType.TIMESTAMP_NTZ.value: {
        "name": SnowflakeMetadataType.TIMESTAMP_NTZ.name,
        "qvariant_type": QVariant.DateTime,
    },  # TIMESTAMP_NTZ
    SnowflakeMetadataType.OBJECT.value: {
        "name": SnowflakeMetadataType.OBJECT.name,
        "qvariant_type": QVariant.String,
    },  # OBJECT
    SnowflakeMetadataType.ARRAY.value: {
        "name": SnowflakeMetadataType.ARRAY.name,
        "qvariant_type": QVariant.String,
    },  # ARRAY
    SnowflakeMetadataType.BINARY.value: {
        "name": SnowflakeMetadataType.BINARY.name,
        "qvariant_type": QVariant.BitArray,
    },  # BINARY
    SnowflakeMetadataType.TIME.value: {
        "name": SnowflakeMetadataType.TIME.name,
        "qvariant_type": QVariant.Time,
    },  # TIME
    SnowflakeMetadataType.BOOLEAN.value: {
        "name": SnowflakeMetadataType.BOOLEAN.name,
        "qvariant_type": QVariant.Bool,
    },  # BOOLEAN
    SnowflakeMetadataType.GEOGRAPHY.value: {
        "name": SnowflakeMetadataType.GEOGRAPHY.name,
        "qvariant_type": QVariant.String,
    },  # GEOGRAPHY
    SnowflakeMetadataType.GEOMETRY.value: {
        "name": SnowflakeMetadataType.GEOMETRY.name,
        "qvariant_type": QVariant.String,
    },  # GEOMETRY
    SnowflakeMetadataType.VECTOR.value: {
        "name": SnowflakeMetadataType.VECTOR.name,
        "qvariant_type": QVariant.Vector2D,
    },  # VECTOR
}
