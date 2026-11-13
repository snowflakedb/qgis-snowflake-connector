import threading
import typing

from ..helpers.data_base import (
    get_geo_column_type,
    get_srid_from_table_geo_column,
    get_type_from_table_geo_column,
)
from ..helpers.map_zoom import zoom_canvas_to_layers
from ..managers.sf_connection_manager import SFConnectionManager
from ..helpers.utils import connection_uri_token
from qgis.core import Qgis, QgsProject, QgsTask, QgsVectorLayer
from qgis.PyQt.QtCore import pyqtSignal


class SFConvertColumnToLayerTask(QgsTask):
    on_handle_error = pyqtSignal(str, str)
    on_handle_warning = pyqtSignal(str, str)
    on_handle_finished = pyqtSignal(str)

    def __init__(
        self,
        context_information: dict,
        path: str,
        load_all_rows: bool = False,
        extent_mode: bool = False,
        zoom_on_success: bool = True,
    ) -> None:
        """
        Initializes a SFConvertColumnToLayerTask object.

        Args:
            connection_name (str): The name of the connection.
            information_dict (dict): A dictionary containing information about the column, table, schema, and optional column type.
            load_all_rows (bool): If True, the provider will load the full table
                instead of a random sample when it exceeds the row limit.
            extent_mode (bool): If True, the layer fetches only features inside
                the current map extent on each render (#106).

        Raises:
            Exception: If initialization fails.

        """
        try:
            self.context_information = context_information
            self.connection_name = context_information["connection_name"]
            self.database_name = context_information["database_name"]
            self.schema = context_information["schema_name"]
            self.table = context_information["table_name"]
            self.column = context_information["geo_column"]
            self.primary_key = context_information["primary_key"]
            self.load_all_rows = load_all_rows
            self.extent_mode = extent_mode
            self.zoom_on_success = zoom_on_success

            self.path = path
            self._run_thread_id: typing.Optional[int] = None
            self._pending_layers: typing.List[typing.Tuple[str, str]] = []
            self._cancelled = False
            self._error_title = ""
            self._error_message = ""
            super().__init__(
                f"Snowflake Add Map Layer From {self.schema}.{self.table}.{self.column}",
                QgsTask.Flag.CanCancel,
            )
        except Exception as e:
            self.on_handle_error.emit(
                "SFConvertColumnToLayerTask init failed",
                f"Initializing snowflake convert column to layer task failed.\n\nExtended error information:\n{str(e)}",
            )

    def run(self) -> bool:
        """
        Collect layer URIs on the worker thread. Layer objects are created in
        ``finished()`` on the main thread.
        """
        try:
            self._run_thread_id = threading.get_ident()
            self._pending_layers = []
            self.setProgress(5)
            geo_column_type = get_geo_column_type(
                geo_column_name=self.column,
                context_information=self.context_information,
            )
            if self.isCanceled():
                self._cancelled = True
                return False
            self.setProgress(30)
            srid = (
                get_srid_from_table_geo_column(
                    geo_column_name=self.column,
                    table_name=self.table,
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
                get_type_from_table_geo_column(
                    geo_column_name=self.column,
                    table_name=self.table,
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
                    f"{connection_uri_token(self.connection_name)} sql_query= "
                    f"schema_name={self.schema} "
                    f"table_name={self.table} srid={srid} "
                    f"geom_column={self.column} "
                    f"geometry_type={geo_type} "
                    f"geo_column_type={geo_column_type} "
                    f"primary_key={self.primary_key}"
                )
                if self.load_all_rows:
                    uri += " load_all_rows=1"
                if self.extent_mode:
                    uri += " extent_mode=1"
                # When the column has a single geometry family the layer covers
                # every row, so featureCount()/extent() can skip the per-row
                # geometry-type predicate and use a fast metadata COUNT(*).
                if len(geo_type_list) == 1:
                    uri += " single_geom_layer=1"

                layer_name = (
                    self.table
                    if len(geo_type_list) == 1
                    else f"{self.table}_{geo_type}"
                )
                self._pending_layers.append((uri, layer_name))
            self.setProgress(90)
            return True
        except Exception as e:
            self._error_title = "SFConvertColumnToLayerTask run failed"
            self._error_message = (
                "Running snowflake convert column to layer task failed.\n\n"
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
        """
        Create and add layers on the main thread.
        """
        if result:
            added = []
            for uri, layer_name in getattr(self, "_pending_layers", []):
                layer = QgsVectorLayer(uri, layer_name, "snowflakedb")
                if not layer.isValid():
                    self._push_message(
                        "Could not load layer",
                        f"The layer '{layer_name}' is not valid.",
                    )
                    self.on_handle_finished.emit(self.path)
                    return
                QgsProject.instance().addMapLayer(layer)
                added.append(layer)
            if not added:
                self._push_message(
                    "Empty result",
                    f"No loadable layers were produced for {self.schema}.{self.table}.",
                )
            elif self.zoom_on_success:
                zoom_canvas_to_layers(added)
            self.setProgress(100)
            self.on_handle_finished.emit(self.path)
            return
        if self._cancelled or self.isCanceled():
            self._push_message(
                "Snowflake",
                f"Layer download was canceled ({self.schema}.{self.table})",
            )
            self.on_handle_finished.emit(self.path)
            return
        if self._error_title:
            self._push_message(self._error_title, self._error_message)
        self.on_handle_finished.emit(self.path)
