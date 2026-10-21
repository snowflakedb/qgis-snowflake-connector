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


def _dependency_diagnostics() -> str:
    """Report versions and resolved paths of the SSL dependency chain.

    Never imports ``OpenSSL`` (that import is what fails in the GEN_EMAIL
    mismatch) and never imports ``helpers.utils`` (that chain may itself be
    broken).  Uses only the standard library so it can run even when the
    plugin's own imports are unusable.
    """
    import sys
    import importlib.metadata
    import importlib.util

    lines = [f"  python: {sys.executable}"]
    for dist_name, module_name in (
        ("snowflake-connector-python", "snowflake.connector"),
        ("cryptography", "cryptography"),
        ("pyOpenSSL", "OpenSSL"),
    ):
        try:
            version = importlib.metadata.version(dist_name)
        except Exception:  # nosec B110 - diagnostics are best-effort
            version = "not installed"
        try:
            spec = importlib.util.find_spec(module_name)
            location = spec.origin if spec is not None else "not found"
        except Exception:  # nosec B110 - diagnostics are best-effort
            location = "unresolved"
        lines.append(f"  {dist_name}: {version} ({location})")
    return "\n".join(lines)


# noinspection PyPep8Naming
def classFactory(iface):  # pylint: disable=invalid-name
    """Load QGISSnowflakeConnector class from file QGISSnowflakeConnector.

    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """
    from .helpers.utils import (
        check_install_snowflake_connector_package,
        check_package_installed,
    )

    missing = []

    try:
        if not check_install_snowflake_connector_package():
            missing.append("snowflake-connector-python")
    except Exception as exc:
        missing.append(f"snowflake-connector-python ({exc})")

    if missing:
        from qgis.core import QgsMessageLog, Qgis

        msg = (
            "Snowflake Connector: required dependencies could not be installed: "
            + ", ".join(missing)
            + ".\nInstall them manually with:\n"
            "  python3 -m pip install snowflake-connector-python\n"
            "Then restart QGIS."
        )
        QgsMessageLog.logMessage(msg, "Snowflake Plugin", Qgis.MessageLevel.Critical)
        try:
            iface.messageBar().pushCritical(
                "Snowflake Connector",
                "Required dependencies missing. See Log Messages for details.",
            )
        except Exception:  # nosec B110 - message bar is best-effort; never block plugin bootstrap if iface is unavailable
            pass
        return _StubPlugin()

    try:
        from .qgis_snowflake_connector import QGISSnowflakeConnectorPlugin

        return QGISSnowflakeConnectorPlugin()
    except Exception as load_err:
        from qgis.core import QgsMessageLog, Qgis

        hint = str(load_err)
        if "module 'lib' has no attribute" in hint:
            hint += (
                "\n\nThis is caused by an incompatible 'cryptography' / "
                "'pyOpenSSL' pair in the Python environment QGIS is using: "
                "cryptography 49+ dropped OpenSSL bindings (e.g. GEN_EMAIL) "
                "that older pyOpenSSL (<=26.1.0) still references.\n"
                "Upgrade BOTH together using QGIS's own interpreter (on "
                "Windows, the OSGeo4W Shell), never cryptography alone:\n"
                "  python -m pip install --upgrade cryptography pyopenssl\n"
                "If the mismatch persists, a copy in your per-user "
                "site-packages may be shadowing QGIS's bundled packages.\n"
                "Then restart QGIS."
            )
        elif "cryptography" in hint.lower() or "ExtensionOID" in hint:
            hint += (
                "\n\nThis is usually caused by an outdated 'cryptography' "
                "package. Using QGIS's own interpreter (on Windows, the "
                "OSGeo4W Shell), upgrade the pair together:\n"
                "  python -m pip install --upgrade cryptography pyopenssl\n"
                "Then restart QGIS."
            )
        QgsMessageLog.logMessage(
            f"Snowflake Connector failed to load: {hint}\n"
            "Dependency diagnostics:\n" + _dependency_diagnostics(),
            "Snowflake Plugin",
            Qgis.MessageLevel.Critical,
        )
        try:
            iface.messageBar().pushCritical(
                "Snowflake Connector",
                "Plugin failed to load. See Log Messages for details.",
            )
        except Exception:  # nosec B110 - message bar is best-effort; never block plugin bootstrap if iface is unavailable
            pass
        return _StubPlugin()
