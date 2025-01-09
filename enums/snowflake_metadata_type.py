from enum import Enum


class SnowflakeMetadataType(Enum):
    """
    Enum representing different Snowflake metadata types.

    Attributes:
        FIXED (int): Represents a fixed-point number.
        REAL (int): Represents a floating-point number.
        TEXT (int): Represents a text string.
        DATE (int): Represents a date.
        TIMESTAMP (int): Represents a timestamp.
        VARIANT (int): Represents a variant type.
        TIMESTAMP_LTZ (int): Represents a timestamp with local time zone.
        TIMESTAMP_TZ (int): Represents a timestamp with time zone.
        TIMESTAMP_NTZ (int): Represents a timestamp with no time zone.
        OBJECT (int): Represents an object type.
        ARRAY (int): Represents an array type.
        BINARY (int): Represents binary data.
        TIME (int): Represents a time.
        BOOLEAN (int): Represents a boolean value.
        GEOGRAPHY (int): Represents a geography type.
        GEOMETRY (int): Represents a geometry type.
        VECTOR (int): Represents a vector type.
    """

    FIXED = 0
    REAL = 1
    TEXT = 2
    DATE = 3
    TIMESTAMP = 4
    VARIANT = 5
    TIMESTAMP_LTZ = 6
    TIMESTAMP_TZ = 7
    TIMESTAMP_NTZ = 8
    OBJECT = 9
    ARRAY = 10
    BINARY = 11
    TIME = 12
    BOOLEAN = 13
    GEOGRAPHY = 14
    GEOMETRY = 15
    VECTOR = 16
