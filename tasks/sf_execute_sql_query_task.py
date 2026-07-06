import threading
import typing

from ..helpers.data_base import get_limit_sql_query
from ..managers.sf_connection_manager import SFConnectionManager
from qgis.core import QgsTask
from qgis.PyQt.QtCore import pyqtSignal


class SFExecuteSQLQueryTask(QgsTask):
    on_handle_error = pyqtSignal(str, str)
    on_data_ready = pyqtSignal(tuple)

    def __init__(
        self,
        query: str,
        limit: typing.Union[int, None] = None,
        context_information: typing.Dict[str, typing.Union[str, None]] = None,
    ) -> None:
        """
        Initializes the SFExecuteSQLQueryTask.

        Args:
            query (str): The SQL query to be executed.
            limit (typing.Union[int, None], optional): The maximum number of records to return. Defaults to None.
            context_information (typing.Dict[str, typing.Union[str, None]], optional): Additional context information for the query. Defaults to None.

        Raises:
            Exception: If initialization fails, an error message is emitted.
        """
        try:
            self.query = query
            super().__init__(
                f"Snowflake Execute Query: {self.query}",
                QgsTask.CanCancel,
            )
            self.context_information = context_information
            self.limit = limit
            self._run_thread_id: typing.Optional[int] = None
        except Exception as e:
            self.on_handle_error.emit(
                "SFExecuteSQLQueryTask init failed",
                f"Initializing snowflake execute sql query task failed.\n\nExtended error information:\n{str(e)}",
            )

    def run(self) -> bool:
        """
        Executes the SQL query with a limit and handles any errors that occur.

        Returns:
            bool: True if the query execution is successful, False otherwise.

        Raises:
            Emits an error signal with detailed error information if an exception occurs.
        """
        try:
            self._run_thread_id = threading.get_ident()
            self._result = get_limit_sql_query(
                query=self.query,
                context_information=self.context_information,
                limit=self.limit,
            )

            return True
        except Exception as e:
            self.on_handle_error.emit(
                "SFExecuteSQLQueryTask run failed",
                f"Running snowflake convert column to layer task failed.\n\nExtended error information:\n{str(e)}",
            )
            return False

    def cancel(self) -> None:
        """Propagate user cancel to any in-flight Snowflake query (A9)."""
        if self._run_thread_id is not None:
            SFConnectionManager.get_instance().cancel_pending_on_thread(
                self._run_thread_id
            )
        super().cancel()

    def finished(self, result: bool) -> None:
        """
        Slot that is called when the task is finished.

        Args:
            result (bool): The result of the task execution. If True, the task was successful.

        Emits:
            on_data_ready: Signal emitted with the result data if the task was successful.
        """
        if result:
            self.on_data_ready.emit(self._result)
