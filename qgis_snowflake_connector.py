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

# This will get replaced with a git SHA1 when you do a git archive

__revision__ = "$Format:%H$"

import os
import sys
import inspect
import threading

from qgis.core import (
    Qgis,
    QgsMessageLog,
    QgsProcessingAlgorithm,
    QgsApplication,
    QgsProviderRegistry,
)

from .providers.sf_metadata_provider import SFMetadataProvider

from .qgis_snowflake_connector_algorithm import QGISSnowflakeConnectorAlgorithm

from .providers.sf_data_item_provider import SFDataItemProvider

from .providers.sf_source_select_provider import SFSourceSelectProvider
from .qgis_snowflake_connector_provider import QGISSnowflakeConnectorProvider
from qgis.gui import QgsGui

cmd_folder = os.path.split(inspect.getfile(inspect.currentframe()))[0]

if cmd_folder not in sys.path:
    sys.path.insert(0, cmd_folder)


class QGISSnowflakeConnectorPlugin(object):
    def __init__(self):
        self.provider = None

    def initProcessing(self):
        """Init Processing provider for QGIS >= 3.8."""
        self.postgis_native_provider = QgsApplication.processingRegistry().providerById(
            "native"
        )

        if self.postgis_native_provider:
            self.qgis_snowflake_connector_algorithm = QGISSnowflakeConnectorAlgorithm()
            self.postgis_native_provider.addAlgorithm(
                self.qgis_snowflake_connector_algorithm
            )

        self.tm = QgsApplication.taskManager()
        self.sf_source_select_provider = SFSourceSelectProvider("mssp")
        QgsGui.sourceSelectProviderRegistry().addProvider(
            self.sf_source_select_provider
        )

        self.sf_data_item_provider = SFDataItemProvider("dipk", "Snowflake")
        QgsApplication.dataItemProviderRegistry().addProvider(
            self.sf_data_item_provider
        )

        self.provider = QGISSnowflakeConnectorProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

        registry = QgsProviderRegistry.instance()
        sf_metadata_provider = SFMetadataProvider()
        registry.registerProvider(sf_metadata_provider)

    def _check_for_updates(self):
        """Check GitHub for a newer plugin release in a background thread."""
        try:
            import urllib.request
            import json
            import configparser

            meta_path = os.path.join(
                os.path.dirname(__file__), "metadata.txt"
            )
            cfg = configparser.ConfigParser()
            cfg.read(meta_path)
            local_version = cfg.get("general", "version", fallback="0.0.0")

            url = (
                "https://api.github.com/repos/"
                "snowflakedb/qgis-snowflake-connector/releases/latest"
            )
            req = urllib.request.Request(
                url, headers={"Accept": "application/vnd.github.v3+json"}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
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
        except Exception:
            pass

    def initGui(self):
        self.initProcessing()
        threading.Thread(
            target=self._check_for_updates, daemon=True
        ).start()

    def unload(self):
        QgsApplication.processingRegistry().removeProvider(self.provider)
        self.postgis_native_provider.algorithms().remove(
            self.qgis_snowflake_connector_algorithm
        )
        self.postgis_native_provider.refreshAlgorithms()
        QgsGui.sourceSelectProviderRegistry().removeProvider(
            self.sf_source_select_provider
        )
        QgsApplication.dataItemProviderRegistry().removeProvider(
            self.sf_data_item_provider
        )
