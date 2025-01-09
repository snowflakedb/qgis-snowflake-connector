import typing
from ..helpers.data_base import (
    get_geo_column_type_from_query,
    get_srid_from_sql_query_geo_column,
    get_type_from_query_geo_column,
)
from qgis.core import QgsProject, QgsTask, QgsVectorLayer
from qgis.PyQt.QtCore import pyqtSignal


class SFConvertSQLQueryToLayerTask(QgsTask):
    on_handle_error = pyqtSignal(str, str)
    on_success = pyqtSignal()

    def __init__(
        self,
        query: str,
        layer_name: str,
        context_information: typing.Dict[str, typing.Union[str, None]] = None,
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

            self.query = query
            self.layer_name = layer_name
            super().__init__(
                f"Snowflake convert query to layer: {self.query}",
                QgsTask.CanCancel,
            )
        except Exception as e:
            self.on_handle_error.emit(
                "SFConvertColumnToLayerTask init failed",
                f"Initializing snowflake convert column to layer task failed.\n\nExtended error information:\n{str(e)}",
            )

    def run(self) -> bool:
        """
        Executes the task to convert a Snowflake column to a layer.

        Returns:
            bool: True if the task is executed successfully, False otherwise.
        """
        try:
            geo_column_type = (
                "NUMBER"
                if self.geo_column_type_is_h3
                else get_geo_column_type_from_query(
                    query=self.query,
                    context_information=self.context_information,
                )
            )
            srid = (
                get_srid_from_sql_query_geo_column(
                    query=self.query,
                    context_information=self.context_information,
                )
                if geo_column_type == "GEOMETRY"
                else 4326
            )
            geo_type_list = (
                get_type_from_query_geo_column(
                    query=self.query,
                    context_information=self.context_information,
                )
                if geo_column_type != "NUMBER"
                else ["POLYGON"]
            )
            for geo_type in geo_type_list:
                uri = (
                    f"connection_name={self.connection_name} "
                    f"sql_query={self.query} "
                    f"schema_name={self.schema} "
                    f"srid={srid} "
                    f"geom_column={self.geo_column_name} "
                    f"geometry_type={geo_type} "
                    f"geo_column_type={geo_column_type}"
                )

                layer_name = (
                    self.layer_name
                    if len(geo_type_list) == 1
                    else f"{self.layer_name}_{geo_type}"
                )
                layer = QgsVectorLayer(uri, layer_name, "snowflakedb")
                QgsProject.instance().addMapLayer(layer)
            return True
        except Exception as e:
            self.on_handle_error.emit(
                "SFConvertColumnToLayerTask run failed",
                f"Running snowflake convert column to layer task failed.\n\nExtended error information:\n{str(e)}",
            )
            return False

    def finished(self, result: bool) -> None:
        """
        Callback function called when the task is finished.

        Args:
            result (bool): The result of the task.

        Returns:
            None
        """
        self.on_success.emit() if result else self.on_handle_error.emit(
            "SFConvertColumnToLayerTask failed",
            "Running snowflake convert column to layer task did not finished.",
        )
