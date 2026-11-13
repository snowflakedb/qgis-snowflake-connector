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

from .providers.sf_metadata_provider import SFMetadataProvider
from .qgis_snowflake_connector_provider import QGISSnowflakeConnectorProvider
from .providers.sf_data_item_provider import SFDataItemProvider
from .providers.sf_source_select_provider import SFSourceSelectProvider
from .sf_locator_filter import SFLocatorFilter
from .sf_expression_functions import register_sf_functions, unregister_sf_functions

from qgis.gui import QgsGui


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

        register_sf_functions()

        threading.Thread(
            target=self._check_for_updates, daemon=True
        ).start()

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

        unregister_sf_functions()
