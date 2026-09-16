"""Consent and trust-boundary helpers for attacker-influenceable workflows.

Processing models (.model3), project files (.qgs/.qgz), and headless runs can
supply parameters that execute SQL with the victim's saved Snowflake
credentials. Interactive GUI runs must prompt; headless runs are denied unless
the user explicitly opts in via plugin settings or an environment variable.
"""

import os

from qgis.PyQt.QtCore import Qt

from .utils import get_qsettings

_HEADLESS_OPT_IN_ENV = "SNOWFLAKE_QGIS_ALLOW_HEADLESS_TRUSTED_ACTIONS"
_HEADLESS_OPT_IN_SETTING = "security/allow_headless_trusted_actions"


def gui_is_available():
    """Return True when a QGIS main window is available for modal prompts."""
    try:
        from qgis.utils import iface
    except Exception:
        iface = None
    return iface is not None


def headless_trusted_actions_enabled() -> bool:
    """Return True when the user has explicitly allowed headless trusted actions."""
    env_value = os.environ.get(_HEADLESS_OPT_IN_ENV, "").strip().lower()
    if env_value in {"1", "true", "yes", "on"}:
        return True
    try:
        settings = get_qsettings()
        return settings.value(_HEADLESS_OPT_IN_SETTING, defaultValue=False) in (
            True,
            "true",
            "1",
            1,
        )
    except Exception:
        return False


def require_trusted_action_consent(title: str, message: str) -> bool:
    """Require explicit consent before a trusted/destructive Snowflake action.

    - GUI: show a warning dialog defaulting to **No**.
    - Headless: allow only when ``headless_trusted_actions_enabled()`` is True.
    """
    if gui_is_available():
        from qgis.PyQt.QtWidgets import QMessageBox
        from qgis.utils import iface

        box = QMessageBox(iface.mainWindow())
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(title)
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.setText(message)
        box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        box.setDefaultButton(QMessageBox.StandardButton.No)
        return box.exec() == QMessageBox.StandardButton.Yes

    return headless_trusted_actions_enabled()
