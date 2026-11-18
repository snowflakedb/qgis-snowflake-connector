import threading
import typing

from ..enums.snowflake_metadata_type import SnowflakeMetadataType
from ..helpers.data_base import (
    get_geo_column_type_from_query,
    get_srid_from_sql_query_geo_column,
    get_type_from_query_geo_column,
)
from ..helpers.map_zoom import zoom_canvas_to_layers
from ..managers.sf_connection_manager import SFConnectionManager
from qgis.core import Qgis, QgsProject, QgsTask, QgsVectorLayer
from qgis.PyQt.QtCore import pyqtSignal


class SFConvertSQLQueryToLayerTask(QgsTask):
    on_handle_error = pyqtSignal(str, str)
    on_success = pyqtSignal()

    def __init__(
        self,
        query: str,
        layer_name: str,
        context_information: typing.Dict[str, typing.Union[str, None]] = None,
        zoom_on_success: bool = True,
    ):
        try:
            self.context_information = context_information
            self.connection_name = context_information["connection_name"]
            self.schema = (
                context_information["schema_name"]
                if "schema_name" in context_information
                else ""
            )
            self.geo_column_name = context_information["geo_column_name"]
            self.geo_column_type_is_h3 = context_information["geo_column_type_is_h3"]
            self.h3_sf_col_type = context_information.get("h3_sf_col_type")
            self.primary_key = (
                context_information["primary_key"]
                if "primary_key" in context_information
                else ""
            )

            self.query = query
            self.layer_name = layer_name
            self.zoom_on_success = zoom_on_success
            self._run_thread_id: typing.Optional[int] = None
            self._pending_layers: typing.List[typing.Tuple[str, str]] = []
            self._added_layers: typing.List[QgsVectorLayer] = []
            self._error_title = ""
            self._error_message = ""
            self._cancelled = False
            super().__init__(
                f"Snowflake convert query to layer: {self.layer_name}",
                QgsTask.Flag.CanCancel,
            )
        except Exception as e:
            self.on_handle_error.emit(
                "SFConvertSQLQueryToLayerTask init failed",
                f"Initializing snowflake convert SQL query to layer task failed.\n\nExtended error information:\n{str(e)}",
            )

    def run(self) -> bool:
        """Collect layer URIs on the worker thread."""
        try:
            self._run_thread_id = threading.get_ident()
            self._pending_layers = []
            self.setProgress(5)
            if self.geo_column_type_is_h3:
                geo_column_type = (
                    "TEXT" if self.h3_sf_col_type == SnowflakeMetadataType.TEXT.value
                    else "NUMBER"
                )
            else:
                geo_column_type = get_geo_column_type_from_query(
                    query=self.query,
                    context_information=self.context_information,
                )
            if self.isCanceled():
                self._cancelled = True
                return False
            self.setProgress(30)
            srid = (
                get_srid_from_sql_query_geo_column(
                    query=self.query,
                    context_information=self.context_information,
                )
                if geo_column_type == "GEOMETRY"
                else 4326
            )
            if self.isCanceled():
                self._cancelled = True
                return False
            self.setProgress(55)
            geo_type_list = (
                get_type_from_query_geo_column(
                    query=self.query,
                    context_information=self.context_information,
                )
                if geo_column_type not in ["NUMBER", "TEXT"]
                else ["MultiPolygon"]
            )
            for geo_type in geo_type_list:
                if self.isCanceled():
                    self._cancelled = True
                    return False
                uri = (
                    f"connection_name={self.connection_name} "
                    f"sql_query={self.query} "
                    f"schema_name={self.schema} "
                    f"srid={srid} "
                    f"geom_column={self.geo_column_name} "
                    f"geometry_type={geo_type} "
                    f"geo_column_type={geo_column_type} "
                    f"primary_key={self.primary_key}"
                )
                if len(geo_type_list) == 1:
                    uri += " single_geom_layer=1"

                layer_name = (
                    self.layer_name
                    if len(geo_type_list) == 1
                    else f"{self.layer_name}_{geo_type}"
                )
                self._pending_layers.append((uri, layer_name))
            self.setProgress(90)
            return True
        except Exception as e:
            self._error_title = "SFConvertSQLQueryToLayerTask run failed"
            self._error_message = (
                "Running snowflake convert SQL query to layer task failed.\n\n"
                f"Extended error information:\n{str(e)}"
            )
            return False

    def cancel(self) -> None:
        """Propagate user cancel to any in-flight Snowflake query (A9)."""
        self._cancelled = True
        if self._run_thread_id is not None:
            SFConnectionManager.get_instance().cancel_pending_on_thread(
                self._run_thread_id
            )
        super().cancel()

    def _push_message(self, title: str, message: str) -> None:
        try:
            from qgis.utils import iface

            if iface is not None:
                iface.messageBar().pushMessage(
                    title,
                    message,
                    level=Qgis.MessageLevel.Warning,
                    duration=8,
                )
                return
        except Exception:
            pass
        self.on_handle_error.emit(title, message)

    def finished(self, result: bool) -> None:
        """Create and add layers on the main thread."""
        if result:
            self._added_layers = []
            for uri, layer_name in getattr(self, "_pending_layers", []):
                layer = QgsVectorLayer(uri, layer_name, "snowflakedb")
                if not layer.isValid():
                    self._push_message(
                        "Could not load filtered layer",
                        f"The layer '{layer_name}' is not valid.",
                    )
                    return
                QgsProject.instance().addMapLayer(layer)
                self._added_layers.append(layer)
            if not self._added_layers:
                self._push_message(
                    "No data to load",
                    "The query did not produce a loadable layer.",
                )
                return
            total_features = 0
            try:
                total_features = sum(
                    max(0, int(layer.featureCount()))
                    for layer in self._added_layers
                )
            except Exception:
                total_features = -1
            if total_features == 0:
                self._push_message(
                    "Empty result",
                    f"The filtered query for '{self.layer_name}' returned no features.",
                )
            elif self.zoom_on_success:
                zoom_canvas_to_layers(self._added_layers)
            self.setProgress(100)
            self.on_success.emit()
            return

        if self._cancelled or self.isCanceled():
            self._push_message(
                "Snowflake",
                f"Layer download was canceled ({self.layer_name})",
            )
            return

        title = self._error_title or "SFConvertSQLQueryToLayerTask failed"
        message = self._error_message or (
            "Running snowflake convert SQL query to layer task did not finish."
        )
        self._push_message(title, message)
