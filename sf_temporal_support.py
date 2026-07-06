"""Temporal animation support for Snowflake layers.

Detects timestamp columns in loaded Snowflake layers and configures
QgsVectorLayerTemporalProperties so users can use the QGIS temporal
controller for time-based animation.
"""

from datetime import date, datetime

from qgis.core import (
    QgsDateTimeRange,
    QgsProviderRegistry,
    QgsVectorLayerTemporalProperties,
    QgsMessageLog,
    Qgis,
)
from qgis.PyQt.QtCore import QDateTime, Qt

TIMESTAMP_TYPES = frozenset({
    "TIMESTAMP_NTZ", "TIMESTAMP_LTZ", "TIMESTAMP_TZ",
    "TIMESTAMP", "DATETIME", "DATE",
})


def configure_temporal_for_layer(layer):
    """Auto-detect timestamp columns and enable temporal properties.

    Called after a Snowflake layer is added to the project.
    Only activates if exactly one timestamp column is found
    (to avoid ambiguity). If multiple exist, uses the first one
    and logs a message.
    """
    if not layer or not layer.isValid():
        return

    dp = layer.dataProvider()
    if not dp or dp.name() != "snowflakedb":
        return

    uri = dp.dataSourceUri()

    timestamp_fields = []
    try:
        metadata = QgsProviderRegistry.instance().providerMetadata("snowflakedb")
        if metadata is None:
            return
        parts = metadata.decodeUri(uri)
        conn_name = parts.get("connection_name", "")
        schema = parts.get("schema_name", "PUBLIC")
        table = parts.get("table_name", "")

        if not conn_name or not table:
            return

        from .helpers.sql import quote_literal
        from .helpers.utils import get_auth_information
        from .managers.sf_connection_manager import SFConnectionManager

        mgr = SFConnectionManager.get_instance()
        if mgr.get_connection(conn_name) is None:
            mgr.connect(conn_name, get_auth_information(conn_name))

        types_in = ", ".join(quote_literal(t) for t in TIMESTAMP_TYPES)
        sql = (
            f"SELECT COLUMN_NAME, DATA_TYPE "  # nosec B608 - values escaped via quote_literal; types_in built from quote_literal over fixed allowlist
            f"FROM INFORMATION_SCHEMA.COLUMNS "
            f"WHERE TABLE_SCHEMA ILIKE {quote_literal(schema)} "
            f"AND TABLE_NAME ILIKE {quote_literal(table)} "
            f"AND DATA_TYPE IN ({types_in}) "
            f"ORDER BY ORDINAL_POSITION"
        )
        cursor = mgr.execute_query(conn_name, sql, {"schema_name": schema})
        rows = cursor.fetchall() if cursor else []
        cursor.close() if cursor else None
        timestamp_fields = [(r[0], r[1]) for r in rows]

    except Exception as e:
        QgsMessageLog.logMessage(
            f"Temporal detection error: {e}",
            "Snowflake Plugin",
            Qgis.MessageLevel.Warning,
        )
        return

    if not timestamp_fields:
        return

    ts_field_name = timestamp_fields[0][0]

    if len(timestamp_fields) > 1:
        names = ", ".join(f[0] for f in timestamp_fields)
        QgsMessageLog.logMessage(
            f"Multiple timestamp columns found ({names}). "
            f"Using '{ts_field_name}' for temporal animation.",
            "Snowflake Plugin",
            Qgis.MessageLevel.Info,
        )

    field_idx = layer.fields().lookupField(ts_field_name)
    if field_idx < 0:
        return

    props = layer.temporalProperties()
    if not isinstance(props, QgsVectorLayerTemporalProperties):
        return

    props.setMode(QgsVectorLayerTemporalProperties.TemporalMode.ModeFeatureDateTimeInstantFromField)
    props.setStartField(ts_field_name)
    props.setIsActive(True)

    # D4: populate the layer's fixed temporal range with the actual MIN/MAX
    # of the timestamp column so the QGIS temporal controller opens on the
    # right window instead of defaulting to "now" / empty.
    _apply_fixed_temporal_range(props, mgr, conn_name, schema, table, ts_field_name)

    QgsMessageLog.logMessage(
        f"Temporal animation enabled for '{layer.name()}' using column '{ts_field_name}'",
        "Snowflake Plugin",
        Qgis.MessageLevel.Info,
    )


def _to_qdatetime(value):
    """Convert a Snowflake-returned datetime/date value to a QDateTime.

    Snowflake's TIMESTAMP variants deserialize to python ``datetime`` (with or
    without tzinfo); DATE deserializes to ``date``. Returns ``None`` if the
    value cannot be converted.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        qdt = QDateTime.fromString(value.isoformat(), Qt.DateFormat.ISODateWithMs)
        if not qdt.isValid():
            qdt = QDateTime.fromString(value.isoformat(), Qt.DateFormat.ISODate)
        return qdt if qdt.isValid() else None
    if isinstance(value, date):
        qdt = QDateTime.fromString(value.isoformat(), Qt.DateFormat.ISODate)
        return qdt if qdt.isValid() else None
    return None


def _apply_fixed_temporal_range(props, mgr, conn_name, schema, table, ts_field_name):
    """Query MIN/MAX of the timestamp column once and set the layer's
    ``fixedTemporalRange`` so the temporal controller knows the span without
    scanning every feature on demand.
    """
    try:
        from .helpers.sql import quote_identifier
        from .managers.sf_connection_manager import build_op_tag

        qcol = quote_identifier(ts_field_name)
        qtbl = f"{quote_identifier(schema)}.{quote_identifier(table)}"
        sql = f"SELECT MIN({qcol}), MAX({qcol}) FROM {qtbl}"  # nosec B608 - identifiers quoted via quote_identifier
        cursor = mgr.execute_query(
            conn_name,
            sql,
            {"schema_name": schema},
            op_tag=build_op_tag(
                "temporal-range",
                connection_name=conn_name,
                schema=schema,
                table=table,
            ),
        )
        row = cursor.fetchone() if cursor else None
        cursor.close() if cursor else None
    except Exception as e:
        QgsMessageLog.logMessage(
            f"Temporal range probe failed: {e}",
            "Snowflake Plugin",
            Qgis.MessageLevel.Info,
        )
        return

    if not row:
        return

    q_min = _to_qdatetime(row[0])
    q_max = _to_qdatetime(row[1])
    if q_min is None or q_max is None:
        return

    props.setFixedTemporalRange(QgsDateTimeRange(q_min, q_max))
