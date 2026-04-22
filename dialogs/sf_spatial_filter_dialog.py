"""Spatial filter dialog for downloading Snowflake data within a map extent.

Lets users draw a rectangle on the map, add optional SQL WHERE and row limit,
then downloads only features within that extent using server-side ST_INTERSECTS.
"""

from qgis.PyQt.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QPushButton,
    QDialogButtonBox,
    QGroupBox,
    QTextEdit,
    QMessageBox,
)
from qgis.PyQt.QtCore import Qt
from qgis.core import (
    QgsRectangle,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsProject,
    QgsVectorLayer,
    QgsMessageLog,
    Qgis,
)


class SFSpatialFilterDialog(QDialog):
    """Dialog for spatially-filtered download from a Snowflake table."""

    def __init__(self, connection_name, schema, table, geo_column, parent=None):
        super().__init__(parent)
        self.connection_name = connection_name
        self.schema = schema
        self.table = table
        self.geo_column = geo_column
        self.extent = None

        self.setWindowTitle("Download with Spatial Filter")
        self.setMinimumWidth(500)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        info = QLabel(
            f"<b>Table:</b> {self.schema}.{self.table}<br>"
            f"<b>Connection:</b> {self.connection_name}"
        )
        layout.addWidget(info)

        extent_group = QGroupBox("Spatial Extent")
        extent_layout = QVBoxLayout(extent_group)

        btn_layout = QHBoxLayout()
        self.btn_canvas = QPushButton("Use Current Map Extent")
        self.btn_canvas.clicked.connect(self._use_canvas_extent)
        btn_layout.addWidget(self.btn_canvas)
        extent_layout.addLayout(btn_layout)

        coord_layout = QHBoxLayout()
        self.xmin_edit = QLineEdit()
        self.ymin_edit = QLineEdit()
        self.xmax_edit = QLineEdit()
        self.ymax_edit = QLineEdit()
        for label, edit in [
            ("xmin:", self.xmin_edit),
            ("ymin:", self.ymin_edit),
            ("xmax:", self.xmax_edit),
            ("ymax:", self.ymax_edit),
        ]:
            coord_layout.addWidget(QLabel(label))
            coord_layout.addWidget(edit)
        extent_layout.addLayout(coord_layout)
        layout.addWidget(extent_group)

        filter_group = QGroupBox("Additional Filter")
        filter_layout = QVBoxLayout(filter_group)
        filter_layout.addWidget(QLabel("WHERE clause (optional):"))
        self.where_edit = QTextEdit()
        self.where_edit.setMaximumHeight(60)
        filter_layout.addWidget(self.where_edit)
        layout.addWidget(filter_group)

        limit_layout = QHBoxLayout()
        limit_layout.addWidget(QLabel("Row limit:"))
        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(0, 10_000_000)
        self.limit_spin.setValue(50_000)
        self.limit_spin.setSpecialValueText("No limit")
        limit_layout.addWidget(self.limit_spin)
        limit_layout.addStretch()
        layout.addLayout(limit_layout)

        self.sql_preview = QTextEdit()
        self.sql_preview.setReadOnly(True)
        self.sql_preview.setMaximumHeight(80)
        self.sql_preview.setStyleSheet("background-color: #f5f5f5;")
        layout.addWidget(QLabel("SQL Preview:"))
        layout.addWidget(self.sql_preview)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        for edit in (self.xmin_edit, self.ymin_edit, self.xmax_edit, self.ymax_edit, self.where_edit):
            edit.textChanged.connect(self._update_preview)
        self.limit_spin.valueChanged.connect(self._update_preview)

        self._update_preview()

    def _use_canvas_extent(self):
        try:
            from qgis.utils import iface
            canvas = iface.mapCanvas()
            extent = canvas.extent()

            canvas_crs = canvas.mapSettings().destinationCrs()
            wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
            if canvas_crs != wgs84:
                transform = QgsCoordinateTransform(canvas_crs, wgs84, QgsProject.instance())
                extent = transform.transformBoundingBox(extent)

            self.xmin_edit.setText(f"{extent.xMinimum():.6f}")
            self.ymin_edit.setText(f"{extent.yMinimum():.6f}")
            self.xmax_edit.setText(f"{extent.xMaximum():.6f}")
            self.ymax_edit.setText(f"{extent.yMaximum():.6f}")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not get map extent: {e}")

    def _update_preview(self, *args):
        sql = self.build_sql()
        self.sql_preview.setPlainText(sql)

    def build_sql(self):
        from ..helpers.sql import quote_identifier

        qs = quote_identifier(self.schema)
        qt = quote_identifier(self.table)
        qg = quote_identifier(self.geo_column)

        sql = f"SELECT * FROM {qs}.{qt}"

        conditions = []

        xmin = self.xmin_edit.text().strip()
        ymin = self.ymin_edit.text().strip()
        xmax = self.xmax_edit.text().strip()
        ymax = self.ymax_edit.text().strip()

        if all([xmin, ymin, xmax, ymax]):
            wkt = f"POLYGON(({xmin} {ymin}, {xmax} {ymin}, {xmax} {ymax}, {xmin} {ymax}, {xmin} {ymin}))"
            conditions.append(
                f"ST_INTERSECTS({qg}, TO_GEOGRAPHY('{wkt}'))"
            )

        where_clause = self.where_edit.toPlainText().strip()
        if where_clause:
            conditions.append(f"({where_clause})")

        if conditions:
            sql += " WHERE " + " AND ".join(conditions)

        limit = self.limit_spin.value()
        if limit > 0:
            sql += f" LIMIT {limit}"

        return sql

    def _validate_and_accept(self):
        self.accept()

    def get_parameters(self):
        return {
            "connection": self.connection_name,
            "schema": self.schema,
            "table": self.table,
            "geo_column": self.geo_column,
            "sql": self.build_sql(),
            "limit": self.limit_spin.value(),
        }
