"""Map brief (Cortex): sectioned description of the current QGIS map view."""

from __future__ import annotations

import typing

from qgis.core import QgsApplication, QgsMessageLog, Qgis
from qgis.PyQt.QtCore import Qt, QSignalBlocker
from qgis.PyQt.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..helpers.cortex import (
    BRIEF_SECTIONS,
    DEFAULT_MULTIMODAL_MODEL,
    build_brief_prompt,
    build_followup_prompt,
    format_brief_label_text,
    split_brief_sections,
)
from ..helpers.map_capture import (
    build_canvas_map_context,
    collect_view_warnings,
    render_canvas_png,
)
from ..helpers.map_outputs import (
    append_brief_to_project_notes,
    insert_brief_into_layout,
)
from ..helpers.map_stage import MapImageSession
from ..helpers.sql import quote_literal
from ..helpers.utils import get_connection_child_groups, get_qsettings
from ..managers.sf_connection_manager import SFConnectionManager, build_op_tag
from ..tasks.sf_map_brief_task import SFMapBriefTask


class SFMapBriefDialog(QDialog):
    """Capture the current map and produce a four-section Cortex brief."""

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
        self._session: typing.Optional[MapImageSession] = None
        self._sections = {section: "" for section in BRIEF_SECTIONS}
        self._sections["Other"] = ""
        self._latest_brief = ""
        self._history: typing.List[typing.Tuple[str, str]] = []
        self._warnings: typing.List[str] = []
        self._followup_mode = False
        self._pending_question = ""
        self._cleanup_after_task = False
        self._closing = False

        self.setWindowTitle("Map brief (Cortex)")
        self.setMinimumWidth(760)
        self.setMinimumHeight(680)
        self._build_ui()
        self._populate_connections()
        self._refresh_view_checks()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        self.warnings_label = QLabel("")
        self.warnings_label.setWordWrap(True)
        self.warnings_label.setTextFormat(Qt.TextFormat.PlainText)
        self.warnings_label.setStyleSheet("color: #a15c00;")
        layout.addWidget(self.warnings_label)

        notice = QLabel(
            "The current map image and visible layer details are sent to "
            "Snowflake Cortex on your connection."
        )
        notice.setWordWrap(True)
        notice.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(notice)

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

        focus_row = QHBoxLayout()
        focus_row.addWidget(QLabel("Focus (optional):"))
        self.focus_edit = QLineEdit()
        self.focus_edit.setPlaceholderText(
            "e.g. road safety committee, three bullet points"
        )
        focus_row.addWidget(self.focus_edit, stretch=1)
        layout.addLayout(focus_row)

        advanced = QGroupBox("Advanced")
        advanced.setCheckable(True)
        advanced.setChecked(False)
        advanced_layout = QHBoxLayout(advanced)
        advanced_layout.addWidget(QLabel("Model:"))
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        for name in (
            DEFAULT_MULTIMODAL_MODEL,
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
        advanced_layout.addWidget(self.model_combo, stretch=1)
        layout.addWidget(advanced)

        btn_row = QHBoxLayout()
        self.brief_btn = QPushButton("Write brief")
        self.brief_btn.clicked.connect(self._on_write_brief)
        btn_row.addWidget(self.brief_btn)
        self.layout_btn = QPushButton("Insert into print layout")
        self.layout_btn.setEnabled(False)
        self.layout_btn.clicked.connect(self._on_insert_layout)
        btn_row.addWidget(self.layout_btn)
        self.notes_btn = QPushButton("Save to project notes")
        self.notes_btn.setEnabled(False)
        self.notes_btn.clicked.connect(self._on_save_notes)
        btn_row.addWidget(self.notes_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        self.section_edits: typing.Dict[str, QTextEdit] = {}
        for section in BRIEF_SECTIONS:
            layout.addWidget(QLabel(section + ":"))
            edit = QTextEdit()
            edit.setReadOnly(True)
            edit.setAcceptRichText(False)
            edit.setMaximumHeight(100)
            self.section_edits[section] = edit
            layout.addWidget(edit)

        layout.addWidget(QLabel("Other:"))
        self.other_edit = QTextEdit()
        self.other_edit.setReadOnly(True)
        self.other_edit.setAcceptRichText(False)
        self.other_edit.setMaximumHeight(80)
        self.other_edit.setVisible(False)
        layout.addWidget(self.other_edit)

        layout.addWidget(QLabel("Ask about this view:"))
        follow_row = QHBoxLayout()
        self.followup_edit = QLineEdit()
        self.followup_edit.setEnabled(False)
        self.followup_edit.setPlaceholderText(
            "Follow-up question about the captured map"
        )
        follow_row.addWidget(self.followup_edit, stretch=1)
        self.followup_btn = QPushButton("Ask")
        self.followup_btn.setEnabled(False)
        self.followup_btn.clicked.connect(self._on_followup)
        follow_row.addWidget(self.followup_btn)
        layout.addLayout(follow_row)

        layout.addWidget(QLabel("Follow-up answers:"))
        self.qa_edit = QTextEdit()
        self.qa_edit.setReadOnly(True)
        self.qa_edit.setAcceptRichText(False)
        self.qa_edit.setMaximumHeight(120)
        layout.addWidget(self.qa_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _populate_connections(self) -> None:
        connections = get_connection_child_groups()
        preferred = self.context_information.get("connection_name")
        with QSignalBlocker(self.connection_combo):
            self.connection_combo.clear()
            self.connection_combo.addItems(connections)
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
                f"WHERE TABLE_CATALOG = {quote_literal(database)} "
                "ORDER BY TABLE_SCHEMA"
            )
            cursor = manager.execute_query(
                connection_name=connection_name,
                query=query,
                context_information={"connection_name": connection_name},
                op_tag=build_op_tag(
                    "list_schemas", connection_name=connection_name, kind="sql"
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
                f"Map brief: could not list schemas: {e}",
                "Snowflake Plugin",
                Qgis.MessageLevel.Warning,
            )

    def _refresh_view_checks(self) -> None:
        self._warnings = []
        if self.iface is None or self.iface.mapCanvas() is None:
            self._warnings = ["No map canvas is available."]
            self.warnings_label.setText(self._warnings[0])
            self.brief_btn.setEnabled(False)
            return
        canvas = self.iface.mapCanvas()
        layers = list(canvas.layers())
        self._warnings = collect_view_warnings(canvas, layers=layers, image=None)
        blocking = any("No visible layers" in w for w in self._warnings)
        if self._warnings:
            self.warnings_label.setText("\n".join(self._warnings))
        else:
            self.warnings_label.setText("")
        self.brief_btn.setEnabled(not blocking)

    def _connection_ready(self) -> typing.Optional[typing.Tuple[str, str, str, str]]:
        connection_name = self.connection_combo.currentText().strip()
        schema = self.schema_combo.currentText().strip()
        model = self.model_combo.currentText().strip() or DEFAULT_MULTIMODAL_MODEL
        if not connection_name or not schema:
            QMessageBox.information(
                self,
                "Map brief (Cortex)",
                "Choose a connection and schema.",
            )
            return None
        from ..helpers.utils import get_authentification_information

        auth = get_authentification_information(self.settings, connection_name)
        database = auth.get("database", "")
        return connection_name, schema, database, model

    def _ensure_session(
        self, connection_name: str, schema: str, database: str
    ) -> MapImageSession:
        if (
            self._session is None
            or self._session.connection_name != connection_name
            or self._session.schema != schema
            or self._session.database != database
        ):
            if self._session is not None:
                self._session.release()
                self._session.cleanup_local_png()
            self._session = MapImageSession(
                connection_name=connection_name,
                database=database,
                schema=schema,
                context_information={
                    "connection_name": connection_name,
                    "schema_name": schema,
                },
            )
        return self._session

    def _capture_png(self) -> None:
        canvas = self.iface.mapCanvas()
        png_path, image = render_canvas_png(canvas)
        layers = list(canvas.layers())
        self._warnings = collect_view_warnings(
            canvas, layers=layers, image=image
        )
        if self._warnings:
            self.warnings_label.setText("\n".join(self._warnings))
        else:
            self.warnings_label.setText("")
        if self._session is not None:
            self._session.release()
            self._session.cleanup_local_png()
            self._session.set_local_png(png_path)

    def _set_busy(self, busy: bool) -> None:
        self.brief_btn.setEnabled(not busy and not any(
            "No visible layers" in w for w in self._warnings
        ))
        has_result = bool(self._latest_brief)
        self.layout_btn.setEnabled(not busy and has_result)
        self.notes_btn.setEnabled(not busy and has_result)
        self.followup_edit.setEnabled(not busy and has_result)
        self.followup_btn.setEnabled(not busy and has_result)

    def _disconnect_task(self) -> None:
        if self._task is None:
            return
        try:
            self._task.on_handle_error.disconnect(self._on_task_error)
        except Exception:
            pass
        try:
            self._task.on_complete.disconnect(self._on_task_complete)
        except Exception:
            pass

    def _start_task(self, session: MapImageSession, model: str, prompt: str) -> None:
        self._task = SFMapBriefTask(
            session=session,
            model=model,
            prompt=prompt,
        )
        self._task.on_handle_error.connect(self._on_task_error)
        self._task.on_complete.connect(self._on_task_complete)
        QgsApplication.taskManager().addTask(self._task)

    def _on_write_brief(self) -> None:
        self._refresh_view_checks()
        if any("No visible layers" in w for w in self._warnings):
            return
        if self.iface is None or self.iface.mapCanvas() is None:
            QMessageBox.information(
                self,
                "Map brief (Cortex)",
                "No map canvas is available.",
            )
            return
        ready = self._connection_ready()
        if ready is None:
            return
        connection_name, schema, database, model = ready

        try:
            session = self._ensure_session(connection_name, schema, database)
            self._capture_png()
            map_context = build_canvas_map_context(
                self.iface.mapCanvas(),
                warnings=self._warnings,
            )
            prompt = build_brief_prompt(
                self.focus_edit.text(),
                map_context,
                warnings=self._warnings,
            )
        except Exception as e:
            QMessageBox.information(
                self,
                "Map brief (Cortex)",
                f"Could not capture the map.\n\n{e}",
            )
            return

        self.settings.setValue("cortex/multimodal_model", model)
        self._followup_mode = False
        self._pending_question = ""
        self._set_busy(True)
        for edit in self.section_edits.values():
            edit.setPlainText("Writing brief…")
        self.other_edit.clear()
        self.other_edit.setVisible(False)
        self.qa_edit.clear()
        self._start_task(session, model, prompt)

    def _on_followup(self) -> None:
        question = self.followup_edit.text().strip()
        if not question or not self._latest_brief or self._session is None:
            return
        ready = self._connection_ready()
        if ready is None:
            return
        _connection_name, _schema, _database, model = ready
        prompt = build_followup_prompt(
            question,
            self._latest_brief,
            history=self._history,
        )
        self._followup_mode = True
        self._pending_question = question
        self._set_busy(True)
        self._start_task(self._session, model, prompt)

    def _on_task_error(self, title: str, message: str) -> None:
        self._task = None
        if self._cleanup_after_task:
            self._finish_deferred_cleanup()
            return
        self._set_busy(False)
        if not self._latest_brief:
            for edit in self.section_edits.values():
                edit.setPlainText("")
        if self._closing:
            return
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Icon.Warning)
        msg_box.setWindowTitle(title)
        msg_box.setTextFormat(Qt.TextFormat.PlainText)
        msg_box.setText(message)
        msg_box.exec()

    def _on_task_complete(self, text: str) -> None:
        self._task = None
        if self._cleanup_after_task:
            self._finish_deferred_cleanup()
            return
        response = text or ""
        if self._followup_mode:
            self._history.append((self._pending_question, response))
            self._history = self._history[-6:]
            lines = [f"Q: {q}\nA: {a}" for q, a in self._history]
            self.qa_edit.setPlainText("\n\n".join(lines))
            self.followup_edit.clear()
        else:
            self._sections = split_brief_sections(response)
            self._latest_brief = format_brief_label_text(self._sections)
            for section in BRIEF_SECTIONS:
                self.section_edits[section].setPlainText(
                    self._sections.get(section, "")
                )
            other = (self._sections.get("Other") or "").strip()
            self.other_edit.setPlainText(other)
            self.other_edit.setVisible(bool(other))
            self._history = []
            self.qa_edit.clear()
        self._followup_mode = False
        self._pending_question = ""
        self._set_busy(False)

    def _on_insert_layout(self) -> None:
        if not self._latest_brief:
            return
        try:
            name = insert_brief_into_layout(self._sections)
            QMessageBox.information(
                self,
                "Map brief (Cortex)",
                f"Inserted the brief into print layout '{name}'.",
            )
        except Exception as e:
            QMessageBox.information(
                self,
                "Map brief (Cortex)",
                f"Could not insert into a print layout.\n\n{e}",
            )

    def _on_save_notes(self) -> None:
        if not self._latest_brief:
            return
        try:
            append_brief_to_project_notes(self._sections)
            QMessageBox.information(
                self,
                "Map brief (Cortex)",
                "Appended the brief to the project notes (metadata abstract).",
            )
        except Exception as e:
            QMessageBox.information(
                self,
                "Map brief (Cortex)",
                f"Could not save project notes.\n\n{e}",
            )

    def _finish_deferred_cleanup(self) -> None:
        self._cleanup_after_task = False
        self._disconnect_task()
        if self._session is not None:
            self._session.release()
            self._session.cleanup_local_png()
            self._session = None
        self._task = None

    def _cleanup_session(self) -> None:
        self._closing = True
        if self._task is not None:
            self._cleanup_after_task = True
            try:
                self._task.cancel()
            except Exception:
                pass
            # If the task already finished between check and cancel, clean up now.
            if self._task is None:
                self._finish_deferred_cleanup()
            return
        self._disconnect_task()
        if self._session is not None:
            self._session.release()
            self._session.cleanup_local_png()
            self._session = None

    def reject(self) -> None:
        self._cleanup_session()
        super().reject()

    def closeEvent(self, event) -> None:
        self._cleanup_session()
        super().closeEvent(event)
