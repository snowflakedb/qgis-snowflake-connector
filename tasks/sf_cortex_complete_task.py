"""Background task that calls Snowflake Cortex AI_COMPLETE."""

from __future__ import annotations

import threading
import typing

from qgis.core import QgsTask
from qgis.PyQt.QtCore import pyqtSignal

from ..managers.sf_connection_manager import SFConnectionManager, build_op_tag


class SFCortexCompleteTask(QgsTask):
    """Run ``SELECT AI_COMPLETE(...)`` (optionally with an image file on a stage)."""

    on_handle_error = pyqtSignal(str, str)
    on_complete = pyqtSignal(str)

    def __init__(
        self,
        connection_name: str,
        model: str,
        prompt: str,
        context_information: typing.Dict[str, typing.Union[str, None]] = None,
        stage_ref: typing.Optional[str] = None,
        stage_file: typing.Optional[str] = None,
    ) -> None:
        super().__init__("Snowflake Cortex AI_COMPLETE", QgsTask.Flag.CanCancel)
        self.connection_name = connection_name
        self.model = model
        self.prompt = prompt
        self.context_information = context_information or {}
        self.stage_ref = stage_ref
        self.stage_file = stage_file
        self._run_thread_id: typing.Optional[int] = None
        self._response = ""

    def run(self) -> bool:
        try:
            self._run_thread_id = threading.get_ident()
            manager = SFConnectionManager.get_instance()
            if self.stage_ref and self.stage_file:
                query = (
                    "SELECT AI_COMPLETE("
                    "%(model)s, "
                    "PROMPT(%(prompt)s, TO_FILE(%(stage_ref)s, %(stage_file)s))"
                    ")"
                )
                params = {
                    "model": self.model,
                    "prompt": self.prompt,
                    "stage_ref": self.stage_ref,
                    "stage_file": self.stage_file,
                }
            else:
                query = "SELECT AI_COMPLETE(%(model)s, %(prompt)s)"
                params = {"model": self.model, "prompt": self.prompt}

            cursor = manager.execute_query_with_params(
                connection_name=self.connection_name,
                query=query,
                params=params,
                context_information=self.context_information,
                op_tag=build_op_tag(
                    "cortex-complete",
                    connection_name=self.connection_name,
                    schema=self.context_information.get("schema_name"),
                ),
            )
            row = cursor.fetchone()
            cursor.close()
            if not row:
                self.on_handle_error.emit(
                    "Cortex AI_COMPLETE returned no rows",
                    "The model call completed but produced an empty result.",
                )
                return False
            self._response = "" if row[0] is None else str(row[0])
            return True
        except Exception as e:
            message = str(e)
            hint = ""
            upper = message.upper()
            if "CREATE STAGE" in upper or "INSUFFICIENT PRIVILEGES" in upper:
                hint = (
                    "\n\nHint: Map brief needs CREATE STAGE on the selected "
                    "schema (temporary SSE stage for the canvas image)."
                )
            elif "UNKNOWN_MODEL" in upper or "MODEL" in upper and "NOT" in upper:
                hint = (
                    "\n\nHint: the selected Cortex model may be unavailable in "
                    "this account or region. Try another model name."
                )
            self.on_handle_error.emit(
                "Cortex AI_COMPLETE failed",
                f"{message}{hint}",
            )
            return False

    def cancel(self) -> None:
        if self._run_thread_id is not None:
            SFConnectionManager.get_instance().cancel_pending_on_thread(
                self._run_thread_id
            )
        super().cancel()

    def finished(self, result: bool) -> None:
        if result:
            self.on_complete.emit(self._response)
