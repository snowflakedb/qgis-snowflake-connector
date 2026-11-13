"""Call Cortex AI_COMPLETE against a staged Map brief canvas image."""

from __future__ import annotations

import threading
import typing

from qgis.core import QgsTask
from qgis.PyQt.QtCore import pyqtSignal

from ..helpers.map_stage import MapImageSession
from ..managers.sf_connection_manager import SFConnectionManager, build_op_tag


class SFMapBriefTask(QgsTask):
    """Run AI_COMPLETE with TO_FILE against a session-owned staged PNG.

    Staging and cleanup belong to ``MapImageSession``; this task only calls
    the model.
    """

    on_handle_error = pyqtSignal(str, str)
    on_complete = pyqtSignal(str)

    def __init__(
        self,
        session: MapImageSession,
        model: str,
        prompt: str,
        restage_on_missing: bool = True,
    ) -> None:
        super().__init__("Snowflake Map Brief (Cortex)", QgsTask.Flag.CanCancel)
        self.session = session
        self.model = model
        self.prompt = prompt
        self.restage_on_missing = restage_on_missing
        self._run_thread_id: typing.Optional[int] = None
        self._response = ""

    def _run_complete(self, manager: SFConnectionManager):
        complete_sql = (
            "SELECT AI_COMPLETE("
            "%(model)s, "
            "PROMPT(%(prompt)s, TO_FILE(%(stage_ref)s, %(stage_file)s))"
            ")"
        )
        cur = manager.execute_query_with_params(
            connection_name=self.session.connection_name,
            query=complete_sql,
            params={
                "model": self.model,
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
        row = cur.fetchone()
        cur.close()
        return row

    def run(self) -> bool:
        manager = SFConnectionManager.get_instance()
        try:
            self._run_thread_id = threading.get_ident()
            self.session.ensure_staged()
            if self.isCanceled():
                return False

            try:
                row = self._run_complete(manager)
            except Exception as first_error:
                if not self.restage_on_missing:
                    raise
                message = str(first_error).upper()
                missing = any(
                    token in message
                    for token in (
                        "DOES NOT EXIST",
                        "NOT FOUND",
                        "NO SUCH FILE",
                        "FAILED TO FETCH",
                        "STAGE",
                    )
                )
                if not missing:
                    raise
                # Long-idle sessions can lose the temp stage; re-PUT once.
                self.session._staged = False
                self.session.ensure_staged()
                row = self._run_complete(manager)

            if not row or row[0] is None:
                self.on_handle_error.emit(
                    "Map brief returned no text",
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
            self.on_handle_error.emit(
                "Map brief failed",
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
