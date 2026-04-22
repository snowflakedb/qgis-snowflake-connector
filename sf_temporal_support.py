"""Temporal animation support for Snowflake layers.

Detects timestamp columns in loaded Snowflake layers and configures
QgsVectorLayerTemporalProperties so users can use the QGIS temporal
controller for time-based animation.
"""

from qgis.core import (
    QgsVectorLayerTemporalProperties,
    QgsMessageLog,
    Qgis,
)

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
        import re
        parts = dict(re.findall(r'(\w+)=(\S+)', uri))
        conn_name = parts.get("connection_name", "")
        schema = parts.get("schema_name", "PUBLIC")
        table = parts.get("table_name", "")

        if not conn_name or not table:
            return

        from .managers.sf_connection_manager import SFConnectionManager
        mgr = SFConnectionManager.get_instance()
        mgr.connect(conn_name)

        sql = (
            f"SELECT COLUMN_NAME, DATA_TYPE "
            f"FROM INFORMATION_SCHEMA.COLUMNS "
            f"WHERE TABLE_SCHEMA ILIKE '{schema}' "
            f"AND TABLE_NAME ILIKE '{table}' "
            f"AND DATA_TYPE IN ({','.join(repr(t) for t in TIMESTAMP_TYPES)}) "
            f"ORDER BY ORDINAL_POSITION"
        )
        rows = mgr.execute_query(sql, {"schema_name": schema})
        timestamp_fields = [(r[0], r[1]) for r in (rows or [])]

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

    QgsMessageLog.logMessage(
        f"Temporal animation enabled for '{layer.name()}' using column '{ts_field_name}'",
        "Snowflake Plugin",
        Qgis.MessageLevel.Info,
    )
