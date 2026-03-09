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
 This script initializes the plugin, making it known to QGIS.
"""

__author__ = "Snowflake Inc."
__date__ = "2024-08-07"
__copyright__ = "(C) 2024 by Snowflake"


class _StubPlugin:
    """Minimal no-op plugin returned when required dependencies are missing."""
    def initGui(self):
        pass

    def unload(self):
        pass


# noinspection PyPep8Naming
def classFactory(iface):  # pylint: disable=invalid-name
    """Load QGISSnowflakeConnector class from file QGISSnowflakeConnector.

    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """
    from .helpers.utils import (
        check_install_snowflake_connector_package,
        check_install_h3_package,
        check_package_installed,
    )

    missing = []

    try:
        if not check_install_snowflake_connector_package():
            missing.append("snowflake-connector-python")
    except Exception as exc:
        missing.append(f"snowflake-connector-python ({exc})")

    try:
        if not check_install_h3_package():
            missing.append("h3")
    except Exception as exc:
        missing.append(f"h3 ({exc})")

    if missing:
        from qgis.core import QgsMessageLog, Qgis

        msg = (
            "Snowflake Connector: required dependencies could not be installed: "
            + ", ".join(missing)
            + ".\nInstall them manually with:\n"
            "  python3 -m pip install snowflake-connector-python h3\n"
            "Then restart QGIS."
        )
        QgsMessageLog.logMessage(msg, "Snowflake Plugin", Qgis.MessageLevel.Critical)
        try:
            iface.messageBar().pushCritical(
                "Snowflake Connector",
                "Required dependencies missing. See Log Messages for details.",
            )
        except Exception:
            pass
        return _StubPlugin()

    from .qgis_snowflake_connector import QGISSnowflakeConnectorPlugin

    return QGISSnowflakeConnectorPlugin()
