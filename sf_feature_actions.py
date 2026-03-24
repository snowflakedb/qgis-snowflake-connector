"""Feature actions for Snowflake layers.

Registers context actions on Snowflake vector layers that appear in the
identify results panel and attribute table context menu.
"""

from qgis.core import (
    QgsAction,
    QgsMessageLog,
    Qgis,
)


def register_actions_for_layer(layer):
    """Register Snowflake-specific actions on a vector layer.

    Called after a Snowflake layer is added to the project.
    """
    if not layer or not layer.isValid():
        return

    dp = layer.dataProvider()
    if not dp or dp.name() != "snowflakedb":
        return

    uri = dp.dataSourceUri()
    manager = layer.actions()

    if not _has_action(manager, "sf_view_snowsight"):
        _add_view_in_snowsight(manager, uri)

    if not _has_action(manager, "sf_copy_sql"):
        _add_copy_as_sql(manager, uri)

    if not _has_action(manager, "sf_copy_row_json"):
        _add_copy_row_json(manager)


def _has_action(manager, action_name):
    for action in manager.actions():
        if action.name() == action_name:
            return True
    return False


def _add_view_in_snowsight(manager, uri):
    """Open the table in the Snowflake web UI (Snowsight)."""
    code = r"""
import re, webbrowser

uri = '[% @layer_id %]'
layer = QgsProject.instance().mapLayer('[% @layer_id %]')
if layer:
    dp_uri = layer.dataProvider().dataSourceUri()
    parts = dict(re.findall(r'(\w+)=(\S+)', dp_uri))
    account = ''
    # Retrieve account from stored connection settings
    from qgis.PyQt.QtCore import QSettings
    conn_name = parts.get('connection_name', '')
    settings = QSettings(QSettings.Format.IniFormat, QSettings.Scope.UserScope, 'Snowflake', 'SF_QGIS_PLUGIN')
    settings.beginGroup(f'connections/{conn_name}')
    account = settings.value('account', '')
    database = settings.value('database', '')
    settings.endGroup()
    schema = parts.get('schema_name', 'PUBLIC')
    table = parts.get('table_name', '')
    url = f'https://app.snowflake.com/{account}/#/data/databases/{database}/schemas/{schema}/table/{table}'
    webbrowser.open(url)
"""
    action = QgsAction(
        QgsAction.ActionType.GenericPython,
        "sf_view_snowsight",
        code,
        "",
        False,
        "View in Snowsight",
        {"Feature", "Layer"},
    )
    manager.addAction(action)


def _add_copy_as_sql(manager, uri):
    """Copy an INSERT statement for the selected feature to the clipboard."""
    code = r"""
from qgis.PyQt.QtWidgets import QApplication

layer = QgsProject.instance().mapLayer('[% @layer_id %]')
fid = [% $id %]
if layer:
    feat = layer.getFeature(fid)
    fields = layer.fields()
    cols = ', '.join(f.name() for f in fields)
    vals = []
    for i, f in enumerate(fields):
        v = feat.attribute(i)
        if v is None:
            vals.append('NULL')
        elif isinstance(v, str):
            vals.append("'" + v.replace("'", "''") + "'")
        else:
            vals.append(str(v))
    val_str = ', '.join(vals)
    dp_uri = layer.dataProvider().dataSourceUri()
    import re
    parts = dict(re.findall(r'(\w+)=(\S+)', dp_uri))
    table = parts.get('table_name', 'TABLE')
    sql = f'INSERT INTO {table} ({cols}) VALUES ({val_str});'
    QApplication.clipboard().setText(sql)
"""
    action = QgsAction(
        QgsAction.ActionType.GenericPython,
        "sf_copy_sql",
        code,
        "",
        False,
        "Copy as INSERT SQL",
        {"Feature"},
    )
    manager.addAction(action)


def _add_copy_row_json(manager):
    """Copy the feature attributes as a JSON object."""
    code = r"""
import json
from qgis.PyQt.QtWidgets import QApplication

layer = QgsProject.instance().mapLayer('[% @layer_id %]')
fid = [% $id %]
if layer:
    feat = layer.getFeature(fid)
    fields = layer.fields()
    data = {}
    for i, f in enumerate(fields):
        v = feat.attribute(i)
        if v is not None:
            data[f.name()] = v if not hasattr(v, 'toPyObject') else str(v)
        else:
            data[f.name()] = None
    QApplication.clipboard().setText(json.dumps(data, indent=2, default=str))
"""
    action = QgsAction(
        QgsAction.ActionType.GenericPython,
        "sf_copy_row_json",
        code,
        "",
        False,
        "Copy row as JSON",
        {"Feature"},
    )
    manager.addAction(action)
