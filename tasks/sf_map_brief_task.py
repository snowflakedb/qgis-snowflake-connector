"""Call Cortex AI_COMPLETE against a staged Map brief canvas image."""

from __future__ import annotations

import threading
import typing

from qgis.core import QgsTask
from qgis.PyQt.QtCore import pyqtSignal

from ..helpers.map_stage import MapImageSession
from ..managers.sf_connection_manager import SFConnectionManager, build_op_tag


# Snowflake PROMPT substitutes numbered placeholders; unused args are ignored.
# The image must be {0} or the model never receives the PNG.
PROMPT_TEMPLATE = "{0}\n\n{1}"


def _is_missing_staged_file_error(message: str) -> bool:
    upper = message.upper()
    missing_tokens = (
        "DOES NOT EXIST",
        "NOT FOUND",
        "NO SUCH FILE",
        "FAILED TO FETCH",
    )
    if not any(token in upper for token in missing_tokens):
        return False
    # Require a file/stage cue so privilege errors mentioning STAGE do not retry.
    return any(
        token in upper
        for token in ("FILE", "PATH", "OBJECT", "STAGE_FILE", "TO_FILE")
    )


class SFMapBriefTask(QgsTask):
    """Run AI_COMPLETE with TO_FILE against a session-owned staged PNG.

    Staging and cleanup belong to ``MapImageSession``; this task only calls
    the model. Errors are stored in ``run()`` and emitted from ``finished()``
    so the dialog always clears its busy state.
    """

    on_handle_error = pyqtSignal(str, str)
    on_complete = pyqtSignal(str)

    def __init__(
        self,
        session: MapImageSession,
        model: str,
        prompt: str,
    ) -> None:
        super().__init__("Snowflake Map Brief (Cortex)", QgsTask.Flag.CanCancel)
        self.session = session
        self.model = model
        self.prompt = prompt
        self._run_thread_id: typing.Optional[int] = None
        self._response = ""
        self._error_title = ""
        self._error_message = ""

    def _run_complete(self, manager: SFConnectionManager):
        complete_sql = (
            "SELECT AI_COMPLETE("
            "%(model)s, "
            "PROMPT(%(template)s, TO_FILE(%(stage_ref)s, %(stage_file)s), "
            "%(prompt)s)"
            ")"
        )
        cur = None
        try:
            cur = manager.execute_query_with_params(
                connection_name=self.session.connection_name,
                query=complete_sql,
                params={
                    "model": self.model,
                    "template": PROMPT_TEMPLATE,
                    "prompt": self.prompt,
                    "stage_ref": self.session.stage_at(),
                    "stage_file": self.session.staged_file,
                },
                context_information=self.session.context_information,
                op_tag=build_op_tag(
                    "map-brief-complete",
                    connection_name=self.session.connection_name,
                    schema=self.session.schema,
                ),
            )
            return cur.fetchone()
        finally:
            if cur is not None:
                try:
                    cur.close()
                except Exception:
                    pass

    def run(self) -> bool:
        manager = SFConnectionManager.get_instance()
        try:
            self._run_thread_id = threading.get_ident()
            if self.session.is_released:
                self._error_title = "Map brief failed"
                self._error_message = (
                    "The staged map image was released before the task ran."
                )
                return False
            self.session.ensure_staged()
            if self.isCanceled():
                self._error_title = "Map brief cancelled"
                self._error_message = "The Map brief task was cancelled."
                return False

            try:
                row = self._run_complete(manager)
            except Exception as first_error:
                if self.session.is_released or not _is_missing_staged_file_error(
                    str(first_error)
                ):
                    raise
                # Long-idle sessions can lose the temp stage; re-PUT once.
                self.session.mark_needs_restage()
                self.session.ensure_staged()
                row = self._run_complete(manager)

            if not row or row[0] is None:
                self._error_title = "Map brief returned no text"
                self._error_message = (
                    "AI_COMPLETE completed but produced an empty result."
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
                    "\n\nHint: Map brief needs CREATE STAGE on the selected "
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
            self._error_title = "Map brief failed"
            self._error_message = f"{message}{hint}"
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
        else:
            title = self._error_title or "Map brief failed"
            message = self._error_message or "The Map brief task did not complete."
            self.on_handle_error.emit(title, message)
