"""Session-scoped local PNG for Map brief canvas images."""

from __future__ import annotations

import os
import typing


def _log_warning(message: str) -> None:
    try:
        from qgis.core import Qgis, QgsMessageLog

        QgsMessageLog.logMessage(
            message,
            "Snowflake Plugin",
            Qgis.MessageLevel.Warning,
        )
    except Exception:
        print(message)


class MapImageSession:
    """Own one local PNG for the lifetime of a Map brief dialog.

    The AI_COMPLETE task reads PNG bytes via ``read_png_bytes()`` and passes
    them to ``TO_FILE(<BINARY>, 'image/png')``. Staging is not used. The dialog
    cleans up the local file after the task finishes.
    """

    def __init__(
        self,
        connection_name: str,
        database: str,
        schema: str,
        context_information: typing.Optional[dict] = None,
        connection_manager: typing.Optional[object] = None,
    ) -> None:
        self.connection_name = connection_name
        self.database = database
        self.schema = schema
        self.context_information = context_information or {
            "connection_name": connection_name,
            "schema_name": schema,
        }
        # Kept for API compatibility with older call sites / tests.
        self._manager = connection_manager
        self.png_path: typing.Optional[str] = None
        self._released = False

    @property
    def is_released(self) -> bool:
        return self._released

    def set_local_png(self, png_path: str) -> None:
        """Point at a new local PNG for this dialog session."""
        self.png_path = png_path
        self._released = False

    def read_png_bytes(self) -> bytes:
        """Return the current local PNG contents for Cortex TO_FILE."""
        if self._released:
            raise RuntimeError("Map image session has already been released.")
        if not self.png_path or not os.path.isfile(self.png_path):
            raise RuntimeError("No local map image available.")
        with open(self.png_path, "rb") as handle:
            return handle.read()

    def release(self) -> None:
        """Mark the session released so later tasks refuse to read the image."""
        self._released = True

    def cleanup_local_png(self) -> None:
        """Delete the local temporary PNG if present."""
        if self.png_path and os.path.isfile(self.png_path):
            try:
                os.remove(self.png_path)
            except Exception as e:
                _log_warning(f"Map brief: could not remove temp PNG: {e}")
        self.png_path = None
