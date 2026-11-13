"""Session-scoped temporary stage for Map brief canvas images."""

from __future__ import annotations

import os
import typing

from .sql import qualified_table_name


STAGE_NAME = "QGIS_MAP_IMAGES"


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


def _build_op_tag(action: str, connection_name: str, schema: str = "") -> str:
    try:
        from ..managers.sf_connection_manager import build_op_tag

        return build_op_tag(
            action,
            connection_name=connection_name,
            schema=schema,
        )
    except Exception:
        # Unit tests inject a fake manager without loading PyQGIS.
        return action


class MapImageSession:
    """Own one staged PNG for the lifetime of a Map brief dialog.

    ``ensure_staged()`` creates a temporary SSE stage and PUTs the local file
    once. ``release()`` REMOVEs the staged object. The AI_COMPLETE task does
    not clean up the stage; the dialog does.
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
        self._manager = connection_manager
        self.png_path: typing.Optional[str] = None
        self.staged_file: typing.Optional[str] = None
        self._staged = False

    def _get_manager(self):
        if self._manager is None:
            from ..managers.sf_connection_manager import SFConnectionManager

            self._manager = SFConnectionManager.get_instance()
        return self._manager

    def qualified_stage(self) -> str:
        return qualified_table_name(self.database, self.schema, STAGE_NAME)

    def stage_at(self) -> str:
        return f"@{self.qualified_stage()}"

    def set_local_png(self, png_path: str) -> None:
        """Point at a new local PNG; next ensure_staged() will re-PUT it."""
        self.png_path = png_path
        self.staged_file = os.path.basename(png_path)
        self._staged = False

    def ensure_staged(self) -> None:
        """CREATE TEMP STAGE if needed and PUT the local PNG once."""
        if self._staged and self.staged_file:
            return
        if not self.png_path or not os.path.isfile(self.png_path):
            raise RuntimeError("No local map image available to stage.")
        if not self.staged_file:
            self.staged_file = os.path.basename(self.png_path)

        manager = self._get_manager()
        stage = self.qualified_stage()
        stage_at = self.stage_at()

        create_sql = (
            f"CREATE TEMPORARY STAGE IF NOT EXISTS {stage} "
            "ENCRYPTION=(TYPE='SNOWFLAKE_SSE')"
        )  # nosec B608 - stage built via qualified_table_name
        cur = manager.execute_query(
            connection_name=self.connection_name,
            query=create_sql,
            context_information=self.context_information,
            op_tag=_build_op_tag(
                "map-brief-create-stage",
                connection_name=self.connection_name,
                schema=self.schema,
            ),
        )
        if cur is not None:
            cur.close()

        put_sql = (
            f"PUT file://{self.png_path} {stage_at} "
            "AUTO_COMPRESS=FALSE OVERWRITE=TRUE"
        )  # nosec B608 - local temp path + qualified stage
        cur = manager.execute_query(
            connection_name=self.connection_name,
            query=put_sql,
            context_information=self.context_information,
            op_tag=_build_op_tag(
                "map-brief-put",
                connection_name=self.connection_name,
                schema=self.schema,
            ),
        )
        if cur is not None:
            cur.close()
        self._staged = True

    def release(self) -> None:
        """REMOVE the staged file if one was uploaded."""
        if not self._staged or not self.staged_file:
            self._staged = False
            return
        manager = self._get_manager()
        try:
            remove_sql = (
                f"REMOVE {self.stage_at()}/{self.staged_file}"
            )  # nosec B608 - qualified stage + basename of our temp file
            cur = manager.execute_query(
                connection_name=self.connection_name,
                query=remove_sql,
                context_information=self.context_information,
                op_tag=_build_op_tag(
                    "map-brief-remove",
                    connection_name=self.connection_name,
                    schema=self.schema,
                ),
            )
            if cur is not None:
                cur.close()
        except Exception as cleanup_error:
            _log_warning(
                f"Map brief: failed to REMOVE staged image: {cleanup_error}"
            )
        finally:
            self._staged = False

    def cleanup_local_png(self) -> None:
        """Delete the local temporary PNG if present."""
        if self.png_path and os.path.isfile(self.png_path):
            try:
                os.remove(self.png_path)
            except Exception as e:
                _log_warning(f"Map brief: could not remove temp PNG: {e}")
        self.png_path = None
