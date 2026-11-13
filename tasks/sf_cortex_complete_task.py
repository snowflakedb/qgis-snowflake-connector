"""Background task that calls Snowflake Cortex AI_COMPLETE."""

from __future__ import annotations

import threading
import typing

from qgis.core import QgsTask
from qgis.PyQt.QtCore import pyqtSignal

from ..helpers.cortex import build_schema_context, build_sql_prompt
from ..helpers.sql import quote_literal
from ..managers.sf_connection_manager import SFConnectionManager, build_op_tag


class SFCortexCompleteTask(QgsTask):
    """Run ``SELECT AI_COMPLETE(...)`` for a text prompt.

    When ``question``, ``database``, and ``schema`` are provided, the task
    fetches INFORMATION_SCHEMA columns and builds the prompt itself so the
    GUI thread is not blocked.
    """

    on_handle_error = pyqtSignal(str, str)
    on_complete = pyqtSignal(str)

    def __init__(
        self,
        connection_name: str,
        model: str,
        prompt: str = "",
        context_information: typing.Dict[str, typing.Union[str, None]] = None,
        question: typing.Optional[str] = None,
        database: typing.Optional[str] = None,
        schema: typing.Optional[str] = None,
    ) -> None:
        super().__init__("Snowflake Cortex AI_COMPLETE", QgsTask.Flag.CanCancel)
        self.connection_name = connection_name
        self.model = model
        self.prompt = prompt
        self.context_information = context_information or {}
        self.question = question
        self.database = database
        self.schema = schema
        self._run_thread_id: typing.Optional[int] = None
        self._response = ""
        self.omitted_tables = 0

    def _fetch_schema_context(self, manager: SFConnectionManager) -> str:
        query = (
            "SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE "
            "FROM INFORMATION_SCHEMA.COLUMNS "
            f"WHERE TABLE_CATALOG = {quote_literal(self.database)} "
            f"AND TABLE_SCHEMA = {quote_literal(self.schema)} "
            "ORDER BY TABLE_NAME, ORDINAL_POSITION"
        )
        cursor = None
        try:
            cursor = manager.execute_query(
                connection_name=self.connection_name,
                query=query,
                context_information=self.context_information,
                op_tag=build_op_tag(
                    "ask_schema",
                    connection_name=self.connection_name,
                    schema=self.schema,
                    kind="sql",
                ),
            )
            rows = cursor.fetchall()
        finally:
            if cursor is not None:
                try:
                    cursor.close()
                except Exception:
                    pass
        text, omitted = build_schema_context(rows)
        self.omitted_tables = omitted
        return text

    def run(self) -> bool:
        cursor = None
        try:
            self._run_thread_id = threading.get_ident()
            manager = SFConnectionManager.get_instance()

            prompt = self.prompt
            if self.question and self.database and self.schema:
                schema_context = self._fetch_schema_context(manager)
                if self.isCanceled():
                    return False
                if not schema_context:
                    self.on_handle_error.emit(
                        "Ask Snowflake (Cortex)",
                        f"No columns found in schema {self.schema}.",
                    )
                    return False
                prompt = build_sql_prompt(
                    self.question, schema_context, self.database, self.schema
                )
                self.prompt = prompt

            if not prompt:
                self.on_handle_error.emit(
                    "Cortex AI_COMPLETE failed",
                    "No prompt was provided.",
                )
                return False

            query = "SELECT AI_COMPLETE(%(model)s, %(prompt)s)"
            params = {"model": self.model, "prompt": prompt}
            cursor = manager.execute_query_with_params(
                connection_name=self.connection_name,
                query=query,
                params=params,
                context_information=self.context_information,
                op_tag=build_op_tag(
                    "cortex_complete",
                    connection_name=self.connection_name,
                    schema=self.context_information.get("schema_name"),
                    model=self.model,
                    kind="cortex",
                ),
            )
            row = cursor.fetchone()
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
            if "UNKNOWN_MODEL" in upper or ("MODEL" in upper and "NOT" in upper):
                hint = (
                    "\n\nHint: the selected Cortex model may be unavailable in "
                    "this account or region. Try another model name."
                )
            self.on_handle_error.emit(
                "Cortex AI_COMPLETE failed",
                f"{message}{hint}",
            )
            return False
        finally:
            if cursor is not None:
                try:
                    cursor.close()
                except Exception:
                    pass

    def cancel(self) -> None:
        if self._run_thread_id is not None:
            SFConnectionManager.get_instance().cancel_pending_on_thread(
                self._run_thread_id
            )
        super().cancel()

    def finished(self, result: bool) -> None:
        if result:
            self.on_complete.emit(self._response)
