"""Spatial filter dialog for downloading Snowflake data within a map extent.

Lets users set an extent from the canvas, another layer, or by drawing a
rectangle, add an optional SQL WHERE and row limit, then build a filtered
SELECT using server-side ST_INTERSECTS.
"""

from __future__ import annotations

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
    QInputDialog,
)
from qgis.PyQt.QtCore import Qt
from qgis.core import (
    QgsRectangle,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsProject,
    QgsVectorLayer,
)
from qgis.gui import QgsMapToolExtent


class SFSpatialFilterDialog(QDialog):
    """Dialog for spatially-filtered download from a Snowflake table."""

    def __init__(
        self,
        connection_name,
        schema,
        table,
        geo_column,
        parent=None,
        geo_column_type: str = "GEOGRAPHY",
        srid: int = 4326,
    ):
        super().__init__(parent)
        self.connection_name = connection_name
        self.schema = schema
        self.table = table
        self.geo_column = geo_column
        self.geo_column_type = (geo_column_type or "GEOGRAPHY").upper()
        try:
            self.srid = int(srid) if srid else 4326
        except (TypeError, ValueError):
            self.srid = 4326
        self.extent = None
        self._previous_map_tool = None
        self._extent_tool = None

        self.setWindowTitle("Download with Spatial Filter")
        self.setMinimumWidth(520)
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
        self.btn_canvas = QPushButton("Use current map extent")
        self.btn_canvas.clicked.connect(self._use_canvas_extent)
        btn_layout.addWidget(self.btn_canvas)
        self.btn_layer = QPushButton("Use layer extent…")
        self.btn_layer.clicked.connect(self._use_layer_extent)
        btn_layout.addWidget(self.btn_layer)
        self.btn_draw = QPushButton("Draw extent on map")
        self.btn_draw.clicked.connect(self._draw_extent_on_map)
        btn_layout.addWidget(self.btn_draw)
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
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        for edit in (
            self.xmin_edit,
            self.ymin_edit,
            self.xmax_edit,
            self.ymax_edit,
            self.where_edit,
        ):
            edit.textChanged.connect(self._update_preview)
        self.limit_spin.valueChanged.connect(self._update_preview)

        self._update_preview()

    def _iface(self):
        try:
            from qgis.utils import iface

            return iface
        except Exception:
            return None

    def _set_extent_fields(self, extent: QgsRectangle) -> None:
        self.xmin_edit.setText(f"{extent.xMinimum():.6f}")
        self.ymin_edit.setText(f"{extent.yMinimum():.6f}")
        self.xmax_edit.setText(f"{extent.xMaximum():.6f}")
        self.ymax_edit.setText(f"{extent.yMaximum():.6f}")

    def _transform_extent_to_wgs84(
        self, extent: QgsRectangle, source_crs
    ) -> QgsRectangle:
        wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
        if source_crs is not None and source_crs.isValid() and source_crs != wgs84:
            transform = QgsCoordinateTransform(
                source_crs, wgs84, QgsProject.instance()
            )
            return transform.transformBoundingBox(extent)
        return extent

    def _use_canvas_extent(self):
        try:
            iface = self._iface()
            if iface is None or iface.mapCanvas() is None:
                raise RuntimeError("No map canvas is available.")
            canvas = iface.mapCanvas()
            extent = self._transform_extent_to_wgs84(
                canvas.extent(), canvas.mapSettings().destinationCrs()
            )
            self._set_extent_fields(extent)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not get map extent: {e}")

    def _use_layer_extent(self):
        try:
            layers = [
                layer
                for layer in QgsProject.instance().mapLayers().values()
                if isinstance(layer, QgsVectorLayer) and layer.isValid()
            ]
            if not layers:
                QMessageBox.information(
                    self,
                    "Use layer extent",
                    "No vector layers are in the project.",
                )
                return
            names = [layer.name() for layer in layers]
            chosen, ok = QInputDialog.getItem(
                self,
                "Use layer extent",
                "Layer:",
                names,
                0,
                False,
            )
            if not ok or not chosen:
                return
            layer = next(layer for layer in layers if layer.name() == chosen)
            extent = layer.extent()
            if extent is None or extent.isEmpty() or extent.isNull():
                QMessageBox.information(
                    self,
                    "Use layer extent",
                    "The selected layer has an empty extent.",
                )
                return
            extent = self._transform_extent_to_wgs84(extent, layer.crs())
            self._set_extent_fields(extent)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not use layer extent: {e}")

    def _draw_extent_on_map(self):
        iface = self._iface()
        if iface is None or iface.mapCanvas() is None:
            QMessageBox.warning(self, "Error", "No map canvas is available.")
            return
        canvas = iface.mapCanvas()
        self._previous_map_tool = canvas.mapTool()
        self._extent_tool = QgsMapToolExtent(canvas)
        self._extent_tool.extentChanged.connect(self._on_drawn_extent)
        canvas.setMapTool(self._extent_tool)
        self.showMinimized()
        iface.messageBar().pushMessage(
            "Snowflake",
            "Draw a rectangle on the map for the spatial filter.",
            duration=5,
        )

    def _on_drawn_extent(self, extent: QgsRectangle):
        try:
            iface = self._iface()
            canvas = iface.mapCanvas() if iface is not None else None
            if canvas is not None:
                extent = self._transform_extent_to_wgs84(
                    extent, canvas.mapSettings().destinationCrs()
                )
                if self._previous_map_tool is not None:
                    canvas.setMapTool(self._previous_map_tool)
                elif self._extent_tool is not None:
                    canvas.unsetMapTool(self._extent_tool)
            self._set_extent_fields(extent)
        finally:
            self._extent_tool = None
            self._previous_map_tool = None
            self.showNormal()
            self.raise_()
            self.activateWindow()

    def _extent_coords(self):
        return (
            self.xmin_edit.text().strip(),
            self.ymin_edit.text().strip(),
            self.xmax_edit.text().strip(),
            self.ymax_edit.text().strip(),
        )

    def _has_complete_extent(self) -> bool:
        return all(self._extent_coords())

    def _update_preview(self, *args):
        self.sql_preview.setPlainText(self.build_sql())

    def _spatial_predicate(self, quoted_geom: str, wkt: str) -> str:
        if self.geo_column_type == "GEOMETRY":
            srid = self.srid if self.srid else 0
            if srid:
                return (
                    f"ST_INTERSECTS({quoted_geom}, "
                    f"ST_GEOMETRYFROMWKT('{wkt}', {int(srid)}))"
                )
            return (
                f"ST_INTERSECTS({quoted_geom}, ST_GEOMETRYFROMWKT('{wkt}'))"
            )
        if self.geo_column_type in ("NUMBER", "TEXT"):
            return (
                f"ST_INTERSECTS(H3_CELL_TO_BOUNDARY({quoted_geom}), "
                f"TO_GEOGRAPHY('{wkt}'))"
            )
        return f"ST_INTERSECTS({quoted_geom}, TO_GEOGRAPHY('{wkt}'))"

    def build_sql(self):
        from ..helpers.sql import quote_identifier

        qs = quote_identifier(self.schema)
        qt = quote_identifier(self.table)
        qg = quote_identifier(self.geo_column)

        sql = f"SELECT * FROM {qs}.{qt}"  # nosec B608 - identifiers escaped via quote_identifier

        conditions = []
        xmin, ymin, xmax, ymax = self._extent_coords()
        if all([xmin, ymin, xmax, ymax]):
            wkt = (
                f"POLYGON(({xmin} {ymin}, {xmax} {ymin}, "
                f"{xmax} {ymax}, {xmin} {ymax}, {xmin} {ymin}))"
            )
            conditions.append(self._spatial_predicate(qg, wkt))

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
        has_extent = self._has_complete_extent()
        has_where = bool(self.where_edit.toPlainText().strip())
        if not has_extent and not has_where:
            reply = QMessageBox.question(
                self,
                "No filter selected",
                "No spatial extent or WHERE clause is set. "
                "The query may scan the whole table (subject to the row limit).\n\n"
                "Continue anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        if has_extent:
            try:
                coords = [float(v) for v in self._extent_coords()]
            except ValueError:
                QMessageBox.warning(
                    self,
                    "Invalid extent",
                    "Extent coordinates must be numbers.",
                )
                return
            if coords[0] >= coords[2] or coords[1] >= coords[3]:
                QMessageBox.warning(
                    self,
                    "Invalid extent",
                    "Extent must have xmin < xmax and ymin < ymax.",
                )
                return
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

    def reject(self):
        iface = self._iface()
        if iface is not None and iface.mapCanvas() is not None:
            canvas = iface.mapCanvas()
            if self._extent_tool is not None:
                try:
                    canvas.unsetMapTool(self._extent_tool)
                except Exception:
                    pass
            if self._previous_map_tool is not None:
                try:
                    canvas.setMapTool(self._previous_map_tool)
                except Exception:
                    pass
        self._extent_tool = None
        self._previous_map_tool = None
        super().reject()
