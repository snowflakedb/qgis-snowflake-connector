"""Describe map (Cortex): send the canvas image + legend context to AI_COMPLETE."""

from __future__ import annotations

import os
import typing

from qgis.core import QgsApplication, QgsMessageLog, Qgis
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QGuiApplication
from qgis.PyQt.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..helpers.cortex import (
    DEFAULT_MULTIMODAL_MODEL,
    build_describe_prompt,
    default_describe_prompt,
)
from ..helpers.map_capture import build_canvas_map_context, render_canvas_png
from ..helpers.sql import quote_literal
from ..helpers.utils import get_connection_child_groups, get_qsettings
from ..managers.sf_connection_manager import SFConnectionManager, build_op_tag
from ..tasks.sf_describe_map_task import SFDescribeMapTask


class SFDescribeMapDialog(QDialog):
    """Capture the current map and ask Cortex to describe it."""

    def __init__(
        self,
        context_information: typing.Dict[str, typing.Union[str, None]] = None,
        iface=None,
        parent: typing.Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.context_information = dict(context_information or {})
        self.iface = iface
        self.settings = get_qsettings()
        self._task = None
        self._png_path = None
        self._result_text = ""

        self.setWindowTitle("Describe map (Cortex)")
        self.setMinimumWidth(720)
        self.setMinimumHeight(520)
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
            DEFAULT_MULTIMODAL_MODEL,
            "claude-3-5-sonnet",
            "pixtral-large",
        ):
            if self.model_combo.findText(name) < 0:
                self.model_combo.addItem(name)
        saved = self.settings.value(
            "cortex/multimodal_model", defaultValue=DEFAULT_MULTIMODAL_MODEL
        )
        idx = self.model_combo.findText(str(saved))
        if idx >= 0:
            self.model_combo.setCurrentIndex(idx)
        else:
            self.model_combo.setEditText(str(saved))
        model_row.addWidget(self.model_combo, stretch=1)
        layout.addLayout(model_row)

        layout.addWidget(QLabel("Prompt:"))
        self.prompt_edit = QTextEdit()
        self.prompt_edit.setAcceptRichText(False)
        self.prompt_edit.setPlainText(default_describe_prompt())
        self.prompt_edit.setMaximumHeight(120)
        layout.addWidget(self.prompt_edit)

        btn_row = QHBoxLayout()
        self.describe_btn = QPushButton("Describe")
        self.describe_btn.clicked.connect(self._on_describe)
        btn_row.addWidget(self.describe_btn)
        self.copy_btn = QPushButton("Copy")
        self.copy_btn.setEnabled(False)
        self.copy_btn.clicked.connect(self._on_copy)
        btn_row.addWidget(self.copy_btn)
        self.save_btn = QPushButton("Save...")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(self.save_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        layout.addWidget(QLabel("Result:"))
        self.result_view = QTextBrowser()
        self.result_view.setReadOnly(True)
        self.result_view.setAcceptRichText(False)
        self.result_view.setOpenExternalLinks(False)
        layout.addWidget(self.result_view)

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
                    "describe-list-schemas", connection_name=connection_name
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
                f"Describe map: could not list schemas: {e}",
                "Snowflake Plugin",
                Qgis.MessageLevel.Warning,
            )

    def _on_describe(self) -> None:
        if self.iface is None or self.iface.mapCanvas() is None:
            QMessageBox.information(
                self,
                "Describe map (Cortex)",
                "No map canvas is available.",
            )
            return
        connection_name = self.connection_combo.currentText().strip()
        schema = self.schema_combo.currentText().strip()
        model = self.model_combo.currentText().strip() or DEFAULT_MULTIMODAL_MODEL
        user_prompt = self.prompt_edit.toPlainText().strip()
        if not connection_name or not schema or not user_prompt:
            QMessageBox.information(
                self,
                "Describe map (Cortex)",
                "Choose a connection and schema, and enter a prompt.",
            )
            return

        try:
            from ..helpers.utils import get_authentification_information

            auth = get_authentification_information(self.settings, connection_name)
            database = auth.get("database", "")
            canvas = self.iface.mapCanvas()
            map_context = build_canvas_map_context(canvas)
            prompt = build_describe_prompt(user_prompt, map_context)
            self._png_path = render_canvas_png(canvas)
        except Exception as e:
            QMessageBox.information(
                self,
                "Describe map (Cortex)",
                f"Could not capture the map.\n\n{e}",
            )
            return

        self.settings.setValue("cortex/multimodal_model", model)
        self.describe_btn.setEnabled(False)
        self.copy_btn.setEnabled(False)
        self.save_btn.setEnabled(False)
        self.result_view.setPlainText("Describing map…")

        self._task = SFDescribeMapTask(
            connection_name=connection_name,
            database=database,
            schema=schema,
            model=model,
            prompt=prompt,
            png_path=self._png_path,
            context_information={
                "connection_name": connection_name,
                "schema_name": schema,
            },
        )
        self._task.on_handle_error.connect(self._on_task_error)
        self._task.on_complete.connect(self._on_task_complete)
        QgsApplication.taskManager().addTask(self._task)

    def _on_task_error(self, title: str, message: str) -> None:
        self.describe_btn.setEnabled(True)
        self.result_view.setPlainText("")
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Icon.Warning)
        msg_box.setWindowTitle(title)
        msg_box.setTextFormat(Qt.TextFormat.PlainText)
        msg_box.setText(message)
        msg_box.exec()

    def _on_task_complete(self, text: str) -> None:
        self.describe_btn.setEnabled(True)
        self._result_text = text or ""
        self.result_view.setPlainText(self._result_text)
        self.copy_btn.setEnabled(bool(self._result_text))
        self.save_btn.setEnabled(bool(self._result_text))

    def _on_copy(self) -> None:
        if self._result_text:
            QGuiApplication.clipboard().setText(self._result_text)

    def _on_save(self) -> None:
        if not self._result_text:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save map description",
            "map_description.md",
            "Markdown (*.md);;Text (*.txt)",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(self._result_text)
                handle.write("\n")
            if self._png_path and os.path.isfile(self._png_path):
                png_dest = os.path.splitext(path)[0] + ".png"
                with open(self._png_path, "rb") as src, open(png_dest, "wb") as dst:
                    dst.write(src.read())
        except Exception as e:
            QMessageBox.information(
                self,
                "Describe map (Cortex)",
                f"Could not save the description.\n\n{e}",
            )

    def closeEvent(self, event) -> None:
        if self._png_path and os.path.isfile(self._png_path):
            try:
                os.remove(self._png_path)
            except Exception as e:
                QgsMessageLog.logMessage(
                    f"Describe map: could not remove temp PNG: {e}",
                    "Snowflake Plugin",
                    Qgis.MessageLevel.Warning,
                )
        super().closeEvent(event)
