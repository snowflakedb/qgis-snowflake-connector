# -*- coding: utf-8 -*-

"""
/***************************************************************************
 Snowflake Connector for QGIS
 This package includes the Snowflake Connector for QGIS.
                              -------------------
        begin                : 2024-08-07
        copyright            : (C) 2024 by Snowflake
        email                : erick.cuberojimenez@snowflake.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is licensed under the MIT License. You may use, modify,  *
 *   and distribute it under the terms specified in the license.           *
 *                                                                         *
 *   MIT License                                                           *
 *                                                                         *
 *   Permission is hereby granted, free of charge, to any person obtaining *
 *   a copy of this software and associated documentation files (the       *
 *   "Software"), to deal in the Software without restriction, including   *
 *   without limitation the rights to use, copy, modify, merge, publish,   *
 *   distribute, sublicense, and/or sell copies of the Software, and to    *
 *   permit persons to whom the Software is furnished to do so, subject    *
 *   to the following conditions:                                          *
 *                                                                         *
 *   The above copyright notice and this permission notice shall be        *
 *   included in all copies or substantial portions of the Software.       *
 *                                                                         *
 *   THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,       *
 *   EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF    *
 *   MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.*
 *   IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY  *
 *   CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,  *
 *   TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE     *
 *   SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.                *
 *                                                                         *
 ***************************************************************************/
"""

__author__ = "Snowflake Inc."
__date__ = "2024-08-07"
__copyright__ = "(C) 2024 by Snowflake"

__revision__ = "$Format:%H$"

import os
import threading

from qgis.core import (
    Qgis,
    QgsMessageLog,
    QgsApplication,
    QgsProviderRegistry,
)
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMessageBox

from .providers.sf_metadata_provider import SFMetadataProvider
from .qgis_snowflake_connector_provider import QGISSnowflakeConnectorProvider
from .providers.sf_data_item_provider import SFDataItemProvider
from .providers.sf_source_select_provider import SFSourceSelectProvider
from .sf_locator_filter import SFLocatorFilter
from .sf_expression_functions import register_sf_functions, unregister_sf_functions
from .helpers.toolbar import (
    connection_context_from_layer,
    selected_snowflake_layers,
    toggle_extent_mode_uri,
)
from .helpers.utils import get_connection_child_groups

from qgis.gui import QgsGui

_PLUGIN_DIR = os.path.dirname(__file__)
_ICON_PATH = os.path.join(_PLUGIN_DIR, "icon.png")


def get_plugin_version():
    """Read the plugin version from metadata.txt (fallback: 0.0.0)."""
    import configparser

    meta_path = os.path.join(os.path.dirname(__file__), "metadata.txt")
    cfg = configparser.ConfigParser()
    cfg.read(meta_path)
    return cfg.get("general", "version", fallback="0.0.0")


class QGISSnowflakeConnectorPlugin(object):
    def __init__(self):
        self.provider = None
        self.locator_filter = None
        self.toolbar = None
        self.menu = None
        self.actions = []

    def initProcessing(self):
        self.provider = QGISSnowflakeConnectorProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

        self.tm = QgsApplication.taskManager()
        self.sf_source_select_provider = SFSourceSelectProvider("mssp")
        QgsGui.sourceSelectProviderRegistry().addProvider(
            self.sf_source_select_provider
        )

        self.sf_data_item_provider = SFDataItemProvider("dipk", "Snowflake")
        QgsApplication.dataItemProviderRegistry().addProvider(
            self.sf_data_item_provider
        )

        self._register_vector_provider()

    def _register_vector_provider(self):
        """Register the Snowflake vector data provider, detecting a stale
        registration left by a previous plugin version.

        QGIS registers a vector provider once per process and offers no way to
        unregister it, so an in-place upgrade cannot replace the running
        provider code. When that happens the previously registered provider is
        still serving layers with the OLD code; the user must restart QGIS to
        finish the upgrade. Detect this and warn instead of silently running
        stale code.
        """
        registry = QgsProviderRegistry.instance()
        current_version = get_plugin_version()

        existing = registry.providerMetadata("snowflakedb")
        if existing is not None:
            existing_version = getattr(existing, "plugin_version", None)
            # Warn on any version mismatch. An unmarked (None) provider was
            # registered by a release that predates version tracking (<= 1.0.25),
            # so it is still an older provider running stale code after an
            # in-place upgrade. Only a positive same-version match is a benign
            # same-version plugin reload.
            if existing_version != current_version:
                existing_label = existing_version or "an earlier version"
                QgsMessageLog.logMessage(
                    "A previous version of the Snowflake vector provider "
                    f"({existing_label}) is still registered and cannot be "
                    f"replaced by the installed version {current_version} while "
                    "QGIS is running. Please restart QGIS to finish the "
                    "upgrade.",
                    "Snowflake Plugin",
                    Qgis.MessageLevel.Warning,
                )
            else:
                QgsMessageLog.logMessage(
                    f"Snowflake vector provider already registered "
                    f"(version {existing_version or 'unknown'}).",
                    "Snowflake Plugin",
                    Qgis.MessageLevel.Info,
                )
            return

        sf_metadata_provider = SFMetadataProvider(current_version)
        registry.registerProvider(sf_metadata_provider)
        QgsMessageLog.logMessage(
            f"Snowflake vector provider {current_version} registered.",
            "Snowflake Plugin",
            Qgis.MessageLevel.Info,
        )

    def _check_for_updates(self):
        """Check GitHub for a newer plugin release in a background thread."""
        try:
            import urllib.request
            import json

            local_version = get_plugin_version()

            url = (
                "https://api.github.com/repos/"
                "snowflakedb/qgis-snowflake-connector/releases/latest"
            )
            # Defence-in-depth: the URL is a hardcoded constant, but validate
            # scheme/host explicitly before opening it to satisfy static
            # analysers (bandit B310) and protect against future refactors.
            from urllib.parse import urlparse

            parsed = urlparse(url)
            if parsed.scheme != "https" or parsed.netloc != "api.github.com":
                return
            req = urllib.request.Request(
                url, headers={"Accept": "application/vnd.github.v3+json"}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:  # nosec B310 - scheme/host validated to https://api.github.com above
                data = json.loads(resp.read().decode())
            remote_tag = data.get("tag_name", "").lstrip("v")
            if not remote_tag:
                return

            from packaging.version import Version

            if Version(remote_tag) > Version(local_version):
                QgsMessageLog.logMessage(
                    f"Snowflake Connector update available: "
                    f"{local_version} -> {remote_tag}. "
                    f"Download from {data.get('html_url', '')}",
                    "Snowflake Plugin",
                    Qgis.MessageLevel.Info,
                )
        except Exception:  # nosec B110 - update check runs in a daemon thread during plugin init; never block QGIS startup on network or version-parse errors
            pass

    def initGui(self):
        self.initProcessing()

        self.locator_filter = SFLocatorFilter()
        self.iface = None
        try:
            from qgis.utils import iface
            if iface:
                iface.registerLocatorFilter(self.locator_filter)
                self.iface = iface
        except Exception:  # nosec B110 - locator filter is optional; missing iface or registration failure must not prevent plugin init
            pass

        if self.iface is not None:
            self._init_toolbar()

        register_sf_functions()

        threading.Thread(
            target=self._check_for_updates, daemon=True
        ).start()

    def _init_toolbar(self):
        """Create the Snowflake toolbar and Plugins submenu."""
        self.menu = self.iface.pluginMenu().addMenu(
            QIcon(_ICON_PATH), "Snowflake"
        )
        self.toolbar = self.iface.addToolBar("Snowflake")
        self.toolbar.setObjectName("SnowflakeConnectorToolbar")

        action_specs = [
            ("Execute SQL...", self.on_execute_sql),
            ("Reload from Snowflake", self.on_reload_from_snowflake),
            ("Toggle map-extent loading", self.on_toggle_extent_mode),
            ("Ask Snowflake (Cortex)...", self.on_ask_snowflake),
            ("Map brief (Cortex)...", self.on_map_brief),
        ]
        for title, slot in action_specs:
            action = QAction(QIcon(_ICON_PATH), title, self.iface.mainWindow())
            action.triggered.connect(slot)
            self.toolbar.addAction(action)
            self.menu.addAction(action)
            self.actions.append(action)

    def _selected_layers(self):
        if self.iface is None:
            return []
        try:
            return list(self.iface.layerTreeView().selectedLayers())
        except Exception:
            return []

    def _context_for_dialogs(self) -> dict:
        """Connection context from the first selected Snowflake layer, or first saved connection."""
        sf_layers = selected_snowflake_layers(self._selected_layers())
        if sf_layers:
            return connection_context_from_layer(sf_layers[0])
        connections = get_connection_child_groups()
        if connections:
            return {"connection_name": connections[0]}
        return {}

    def on_execute_sql(self):
        from .dialogs.sf_sql_query_dialog import SFSQLQueryDialog

        context = self._context_for_dialogs()
        if not context.get("connection_name"):
            QMessageBox.information(
                self.iface.mainWindow() if self.iface else None,
                "Execute SQL",
                "Create a Snowflake connection first (Layer > Data Source Manager > Snowflake).",
            )
            return
        dialog = SFSQLQueryDialog(
            context_information=context,
            parent=self.iface.mainWindow() if self.iface else None,
        )
        dialog.exec()

    def on_reload_from_snowflake(self):
        layers = selected_snowflake_layers(self._selected_layers())
        if not layers:
            QMessageBox.information(
                self.iface.mainWindow() if self.iface else None,
                "Reload from Snowflake",
                "Select one or more Snowflake layers in the layer tree.",
            )
            return
        for layer in layers:
            provider = layer.dataProvider()
            if provider is not None:
                provider.reloadData()
            layer.triggerRepaint()

    def on_toggle_extent_mode(self):
        layers = selected_snowflake_layers(self._selected_layers())
        if not layers:
            QMessageBox.information(
                self.iface.mainWindow() if self.iface else None,
                "Toggle map-extent loading",
                "Select one or more Snowflake layers in the layer tree.",
            )
            return
        for layer in layers:
            provider = layer.dataProvider()
            if provider is None:
                continue
            new_uri = toggle_extent_mode_uri(provider.dataSourceUri())
            layer.setDataSource(new_uri, layer.name(), "snowflakedb")
            layer.triggerRepaint()

    def on_ask_snowflake(self):
        try:
            from .dialogs.sf_ask_dialog import SFAskDialog
        except ImportError:
            QMessageBox.information(
                self.iface.mainWindow() if self.iface else None,
                "Ask Snowflake (Cortex)",
                "The Ask Snowflake dialog is not available in this build.",
            )
            return
        context = self._context_for_dialogs()
        if not context.get("connection_name"):
            QMessageBox.information(
                self.iface.mainWindow() if self.iface else None,
                "Ask Snowflake (Cortex)",
                "Create a Snowflake connection first (Layer > Data Source Manager > Snowflake).",
            )
            return
        dialog = SFAskDialog(
            context_information=context,
            parent=self.iface.mainWindow() if self.iface else None,
        )
        dialog.exec()

    def on_map_brief(self):
        try:
            from .dialogs.sf_map_brief_dialog import SFMapBriefDialog
        except ImportError:
            QMessageBox.information(
                self.iface.mainWindow() if self.iface else None,
                "Map brief (Cortex)",
                "The Map brief dialog is not available in this build.",
            )
            return
        context = self._context_for_dialogs()
        if not context.get("connection_name"):
            QMessageBox.information(
                self.iface.mainWindow() if self.iface else None,
                "Map brief (Cortex)",
                "Create a Snowflake connection first (Layer > Data Source Manager > Snowflake).",
            )
            return
        dialog = SFMapBriefDialog(
            context_information=context,
            iface=self.iface,
            parent=self.iface.mainWindow() if self.iface else None,
        )
        dialog.exec()

    def unload(self):
        if self.provider:
            QgsApplication.processingRegistry().removeProvider(self.provider)

        QgsGui.sourceSelectProviderRegistry().removeProvider(
            self.sf_source_select_provider
        )
        QgsApplication.dataItemProviderRegistry().removeProvider(
            self.sf_data_item_provider
        )

        if self.locator_filter and self.iface:
            self.iface.deregisterLocatorFilter(self.locator_filter)

        if self.iface is not None:
            for action in self.actions:
                self.iface.removePluginMenu("Snowflake", action)
                if self.toolbar is not None:
                    self.toolbar.removeAction(action)
            self.actions = []
            if self.menu is not None:
                self.iface.pluginMenu().removeAction(self.menu.menuAction())
                self.menu = None
            if self.toolbar is not None:
                self.toolbar.deleteLater()
                self.toolbar = None

        unregister_sf_functions()
