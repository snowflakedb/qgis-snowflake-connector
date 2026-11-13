"""Ask Snowflake (Cortex): natural-language question to SQL, then open the SQL editor."""

from __future__ import annotations

import typing

from qgis.core import QgsApplication, QgsMessageLog, Qgis
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..helpers.cortex import (
    DEFAULT_SQL_MODEL,
    build_schema_context,
    build_sql_prompt,
    extract_sql,
)
from ..helpers.sql import quote_literal, sql_statement_is_read_only
from ..helpers.utils import get_connection_child_groups, get_qsettings
from ..managers.sf_connection_manager import SFConnectionManager, build_op_tag
from ..tasks.sf_cortex_complete_task import SFCortexCompleteTask


class SFAskDialog(QDialog):
    """Generate a read-only Snowflake SELECT from a natural-language question."""

    def __init__(
        self,
        context_information: typing.Dict[str, typing.Union[str, None]] = None,
        parent: typing.Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.context_information = dict(context_information or {})
        self.settings = get_qsettings()
        self._task = None
        self._generated_sql = ""

        self.setWindowTitle("Ask Snowflake (Cortex)")
        self.setMinimumWidth(640)
        self._build_ui()
        self._populate_connections()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        row = QHBoxLayout()
        row.addWidget(QLabel("Connection:"))
        self.connection_combo = QComboBox()
        self.connection_combo.currentTextChanged.connect(self._on_connection_changed)
        row.addWidget(self.connection_combo, stretch=1)
        row.addWidget(QLabel("Schema:"))
        self.schema_combo = QComboBox()
        self.schema_combo.setEditable(True)
        row.addWidget(self.schema_combo, stretch=1)
        layout.addLayout(row)

        model_row = QHBoxLayout()
        model_row.addWidget(QLabel("Model:"))
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        for name in (
            DEFAULT_SQL_MODEL,
            "llama3.1-8b",
            "mistral-large2",
            "snowflake-arctic",
        ):
            self.model_combo.addItem(name)
        saved = self.settings.value("cortex/sql_model", defaultValue=DEFAULT_SQL_MODEL)
        idx = self.model_combo.findText(str(saved))
        if idx >= 0:
            self.model_combo.setCurrentIndex(idx)
        else:
            self.model_combo.setEditText(str(saved))
        model_row.addWidget(self.model_combo, stretch=1)
        layout.addLayout(model_row)

        layout.addWidget(QLabel("Question:"))
        self.question_edit = QTextEdit()
        self.question_edit.setPlaceholderText(
            "e.g. Show me the 100 densest census tracts as polygons"
        )
        self.question_edit.setAcceptRichText(False)
        layout.addWidget(self.question_edit)

        btn_row = QHBoxLayout()
        self.generate_btn = QPushButton("Generate SQL")
        self.generate_btn.clicked.connect(self._on_generate)
        btn_row.addWidget(self.generate_btn)
        self.open_btn = QPushButton("Open in SQL editor")
        self.open_btn.setEnabled(False)
        self.open_btn.clicked.connect(self._on_open_sql_editor)
        btn_row.addWidget(self.open_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        layout.addWidget(QLabel("Generated SQL:"))
        self.sql_preview = QTextEdit()
        self.sql_preview.setReadOnly(True)
        self.sql_preview.setAcceptRichText(False)
        self.sql_preview.setPlaceholderText("SQL appears here after Generate SQL")
        layout.addWidget(self.sql_preview)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _populate_connections(self) -> None:
        self.connection_combo.clear()
        connections = get_connection_child_groups()
        self.connection_combo.addItems(connections)
        preferred = self.context_information.get("connection_name")
        if preferred and preferred in connections:
            self.connection_combo.setCurrentText(preferred)
        elif connections:
            self.connection_combo.setCurrentIndex(0)
        self._on_connection_changed(self.connection_combo.currentText())

    def _on_connection_changed(self, connection_name: str) -> None:
        self.schema_combo.clear()
        if not connection_name:
            return
        try:
            from ..helpers.utils import get_authentification_information

            auth = get_authentification_information(self.settings, connection_name)
            database = auth.get("database", "")
            manager = SFConnectionManager.get_instance()
            if manager.get_connection(connection_name) is None:
                manager.connect(connection_name, auth)
            query = (
                "SELECT DISTINCT TABLE_SCHEMA FROM INFORMATION_SCHEMA.TABLES "
                f"WHERE TABLE_CATALOG ILIKE {quote_literal(database)} "
                "ORDER BY TABLE_SCHEMA"
            )
            cursor = manager.execute_query(
                connection_name=connection_name,
                query=query,
                context_information={"connection_name": connection_name},
                op_tag=build_op_tag(
                    "ask-list-schemas", connection_name=connection_name
                ),
            )
            schemas = [row[0] for row in cursor.fetchall() if row and row[0]]
            cursor.close()
            self.schema_combo.addItems(schemas)
            preferred = self.context_information.get("schema_name")
            if preferred:
                idx = self.schema_combo.findText(str(preferred))
                if idx >= 0:
                    self.schema_combo.setCurrentIndex(idx)
                else:
                    self.schema_combo.setEditText(str(preferred))
        except Exception as e:
            QgsMessageLog.logMessage(
                f"Ask Snowflake: could not list schemas: {e}",
                "Snowflake Plugin",
                Qgis.MessageLevel.Warning,
            )

    def _fetch_schema_context(self, connection_name: str, schema: str, database: str) -> str:
        manager = SFConnectionManager.get_instance()
        query = (
            "SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE "
            "FROM INFORMATION_SCHEMA.COLUMNS "
            f"WHERE TABLE_CATALOG ILIKE {quote_literal(database)} "
            f"AND TABLE_SCHEMA ILIKE {quote_literal(schema)} "
            "ORDER BY TABLE_NAME, ORDINAL_POSITION"
        )
        cursor = manager.execute_query(
            connection_name=connection_name,
            query=query,
            context_information={
                "connection_name": connection_name,
                "schema_name": schema,
            },
            op_tag=build_op_tag(
                "ask-schema-context",
                connection_name=connection_name,
                schema=schema,
            ),
        )
        rows = cursor.fetchall()
        cursor.close()
        return build_schema_context(rows)

    def _on_generate(self) -> None:
        connection_name = self.connection_combo.currentText().strip()
        schema = self.schema_combo.currentText().strip()
        question = self.question_edit.toPlainText().strip()
        model = self.model_combo.currentText().strip() or DEFAULT_SQL_MODEL
        if not connection_name or not schema or not question:
            QMessageBox.information(
                self,
                "Ask Snowflake (Cortex)",
                "Choose a connection and schema, then enter a question.",
            )
            return

        try:
            from ..helpers.utils import get_authentification_information

            auth = get_authentification_information(self.settings, connection_name)
            database = auth.get("database", "")
            schema_context = self._fetch_schema_context(
                connection_name, schema, database
            )
            if not schema_context:
                QMessageBox.information(
                    self,
                    "Ask Snowflake (Cortex)",
                    f"No columns found in schema {schema}.",
                )
                return
            prompt = build_sql_prompt(question, schema_context, database, schema)
        except Exception as e:
            QMessageBox.information(
                self,
                "Ask Snowflake (Cortex)",
                f"Could not build schema context.\n\n{e}",
            )
            return

        self.settings.setValue("cortex/sql_model", model)
        self.generate_btn.setEnabled(False)
        self.open_btn.setEnabled(False)
        self.sql_preview.setPlainText("Generating SQL…")

        context = {
            "connection_name": connection_name,
            "schema_name": schema,
        }
        self._task = SFCortexCompleteTask(
            connection_name=connection_name,
            model=model,
            prompt=prompt,
            context_information=context,
        )
        self._task.on_handle_error.connect(self._on_task_error)
        self._task.on_complete.connect(self._on_task_complete)
        QgsApplication.taskManager().addTask(self._task)

    def _on_task_error(self, title: str, message: str) -> None:
        self.generate_btn.setEnabled(True)
        self.sql_preview.setPlainText("")
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Icon.Warning)
        msg_box.setWindowTitle(title)
        msg_box.setTextFormat(Qt.TextFormat.PlainText)
        msg_box.setText(message)
        msg_box.exec()

    def _on_task_complete(self, response: str) -> None:
        self.generate_btn.setEnabled(True)
        sql = extract_sql(response)
        self._generated_sql = sql
        self.sql_preview.setPlainText(sql or response)
        can_open = bool(sql) and sql_statement_is_read_only(sql)
        self.open_btn.setEnabled(can_open)
        if sql and not can_open:
            QMessageBox.information(
                self,
                "Ask Snowflake (Cortex)",
                "The generated statement is not a read-only SELECT, so it "
                "cannot be opened in the SQL editor. You can copy it from the preview.",
            )

    def _on_open_sql_editor(self) -> None:
        if not self._generated_sql or not sql_statement_is_read_only(self._generated_sql):
            return
        from .sf_sql_query_dialog import SFSQLQueryDialog

        context = {
            "connection_name": self.connection_combo.currentText().strip(),
            "schema_name": self.schema_combo.currentText().strip(),
        }
        dialog = SFSQLQueryDialog(
            context_information=context,
            parent=self.parent(),
        )
        dialog.set_query(self._generated_sql)
        self.accept()
        dialog.exec()
