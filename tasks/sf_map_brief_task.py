"""Call Cortex AI_COMPLETE against a local Map brief canvas PNG."""

from __future__ import annotations

import threading
import typing

from qgis.core import QgsTask
from qgis.PyQt.QtCore import pyqtSignal

from ..helpers.cortex import normalize_cortex_text
from ..helpers.map_stage import MapImageSession
from ..managers.sf_connection_manager import SFConnectionManager, build_op_tag


# Snowflake PROMPT substitutes numbered placeholders; unused args are ignored.
# The image must be {0} or the model never receives the PNG.
PROMPT_TEMPLATE = "{0}\n\n{1}"


class SFMapBriefTask(QgsTask):
    """Run AI_COMPLETE with TO_FILE(BINARY, image/png) against a session PNG.

    Local PNG lifecycle belongs to ``MapImageSession``; this task only reads
    bytes and calls the model. Errors are stored in ``run()`` and emitted from
    ``finished()`` so the dialog always clears its busy state.
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

    def _run_complete(self, manager: SFConnectionManager, png_bytes: bytes):
        complete_sql = (
            "SELECT AI_COMPLETE("
            "%(model)s, "
            "PROMPT(%(template)s, TO_FILE(%(png_bytes)s, 'image/png'), "
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
                    "png_bytes": png_bytes,
                },
                context_information=self.session.context_information,
                op_tag=build_op_tag(
                    "cortex_map_brief",
                    connection_name=self.session.connection_name,
                    schema=self.session.schema,
                    model=self.model,
                    kind="cortex",
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
                    "The map image was released before the task ran."
                )
                return False
            png_bytes = self.session.read_png_bytes()
            if self.isCanceled():
                self._error_title = "Map brief cancelled"
                self._error_message = "The Map brief task was cancelled."
                return False

            row = self._run_complete(manager, png_bytes)

            if not row or row[0] is None:
                self._error_title = "Map brief returned no text"
                self._error_message = (
                    "AI_COMPLETE completed but produced an empty result."
                )
                return False
            self._response = normalize_cortex_text(str(row[0]))
            return True
        except Exception as e:
            message = str(e)
            hint = ""
            upper = message.upper()
            if "UNKNOWN_MODEL" in upper or (
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
