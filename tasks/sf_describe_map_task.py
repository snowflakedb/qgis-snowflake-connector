"""Upload a map PNG to a temporary SSE stage and call Cortex AI_COMPLETE."""

from __future__ import annotations

import os
import threading
import typing

from qgis.core import Qgis, QgsMessageLog, QgsTask
from qgis.PyQt.QtCore import pyqtSignal

from ..helpers.sql import qualified_table_name
from ..managers.sf_connection_manager import SFConnectionManager, build_op_tag


STAGE_NAME = "QGIS_MAP_IMAGES"


class SFDescribeMapTask(QgsTask):
    """CREATE TEMP STAGE → PUT png → AI_COMPLETE(TO_FILE) → REMOVE."""

    on_handle_error = pyqtSignal(str, str)
    on_complete = pyqtSignal(str)

    def __init__(
        self,
        connection_name: str,
        database: str,
        schema: str,
        model: str,
        prompt: str,
        png_path: str,
        context_information: typing.Dict[str, typing.Union[str, None]] = None,
    ) -> None:
        super().__init__("Snowflake Describe Map (Cortex)", QgsTask.Flag.CanCancel)
        self.connection_name = connection_name
        self.database = database
        self.schema = schema
        self.model = model
        self.prompt = prompt
        self.png_path = png_path
        self.context_information = context_information or {
            "connection_name": connection_name,
            "schema_name": schema,
        }
        self._run_thread_id: typing.Optional[int] = None
        self._response = ""
        self._staged_file = os.path.basename(png_path)

    def _qualified_stage(self) -> str:
        return qualified_table_name(self.database, self.schema, STAGE_NAME)

    def _stage_at(self) -> str:
        # PUT / TO_FILE / REMOVE take @db.schema.stage
        return f"@{self._qualified_stage()}"

    def run(self) -> bool:
        manager = SFConnectionManager.get_instance()
        staged = False
        try:
            self._run_thread_id = threading.get_ident()
            stage = self._qualified_stage()
            stage_at = self._stage_at()

            create_sql = (
                f"CREATE TEMPORARY STAGE IF NOT EXISTS {stage} "
                "ENCRYPTION=(TYPE='SNOWFLAKE_SSE')"
            )  # nosec B608 - stage built via qualified_table_name / quote_identifier
            cur = manager.execute_query(
                connection_name=self.connection_name,
                query=create_sql,
                context_information=self.context_information,
                op_tag=build_op_tag(
                    "describe-create-stage",
                    connection_name=self.connection_name,
                    schema=self.schema,
                ),
            )
            cur.close()

            # PUT requires a file:// URI; path is local temp we created.
            put_sql = (
                f"PUT file://{self.png_path} {stage_at} "
                "AUTO_COMPRESS=FALSE OVERWRITE=TRUE"
            )  # nosec B608 - local temp path + qualified stage
            cur = manager.execute_query(
                connection_name=self.connection_name,
                query=put_sql,
                context_information=self.context_information,
                op_tag=build_op_tag(
                    "describe-put",
                    connection_name=self.connection_name,
                    schema=self.schema,
                ),
            )
            cur.close()
            staged = True

            if self.isCanceled():
                return False

            complete_sql = (
                "SELECT AI_COMPLETE("
                "%(model)s, "
                "PROMPT(%(prompt)s, TO_FILE(%(stage_ref)s, %(stage_file)s))"
                ")"
            )
            cur = manager.execute_query_with_params(
                connection_name=self.connection_name,
                query=complete_sql,
                params={
                    "model": self.model,
                    "prompt": self.prompt,
                    "stage_ref": stage_at,
                    "stage_file": self._staged_file,
                },
                context_information=self.context_information,
                op_tag=build_op_tag(
                    "describe-complete",
                    connection_name=self.connection_name,
                    schema=self.schema,
                ),
            )
            row = cur.fetchone()
            cur.close()
            if not row or row[0] is None:
                self.on_handle_error.emit(
                    "Describe map returned no text",
                    "AI_COMPLETE completed but produced an empty result.",
                )
                return False
            self._response = str(row[0])
            return True
        except Exception as e:
            message = str(e)
            hint = ""
            upper = message.upper()
            if "CREATE STAGE" in upper or "INSUFFICIENT PRIVILEGES" in upper:
                hint = (
                    "\n\nHint: this feature needs CREATE STAGE on the selected "
                    "schema so the plugin can store a temporary SSE-encrypted "
                    "image of the map."
                )
            elif "UNKNOWN_MODEL" in upper or (
                "MODEL" in upper and "NOT" in upper
            ):
                hint = (
                    "\n\nHint: choose a multimodal Cortex model available in "
                    "this account/region (for example claude-3-5-sonnet)."
                )
            self.on_handle_error.emit(
                "Describe map failed",
                f"{message}{hint}",
            )
            return False
        finally:
            if staged:
                try:
                    remove_sql = (
                        f"REMOVE {self._stage_at()}/{self._staged_file}"
                    )  # nosec B608 - qualified stage + basename of our temp file
                    cur = manager.execute_query(
                        connection_name=self.connection_name,
                        query=remove_sql,
                        context_information=self.context_information,
                        op_tag=build_op_tag(
                            "describe-remove",
                            connection_name=self.connection_name,
                            schema=self.schema,
                        ),
                    )
                    cur.close()
                except Exception as cleanup_error:
                    QgsMessageLog.logMessage(
                        f"Describe map: failed to REMOVE staged image: {cleanup_error}",
                        "Snowflake Plugin",
                        Qgis.MessageLevel.Warning,
                    )

    def cancel(self) -> None:
        if self._run_thread_id is not None:
            SFConnectionManager.get_instance().cancel_pending_on_thread(
                self._run_thread_id
            )
        super().cancel()

    def finished(self, result: bool) -> None:
        if result:
            self.on_complete.emit(self._response)
