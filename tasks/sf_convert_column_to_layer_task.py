from ..helpers.data_base import (
    get_geo_column_type,
    get_srid_from_table_geo_column,
    get_type_from_table_geo_column,
)
from qgis.core import QgsProject, QgsTask, QgsVectorLayer
from qgis.PyQt.QtCore import pyqtSignal


class SFConvertColumnToLayerTask(QgsTask):
    on_handle_error = pyqtSignal(str, str)
    on_handle_warning = pyqtSignal(str, str)
    on_hadle_finished = pyqtSignal(str)

    def __init__(self, context_information: dict, path: str) -> None:
        """
        Initializes a SFConvertColumnToLayerTask object.

        Args:
            connection_name (str): The name of the connection.
            information_dict (dict): A dictionary containing information about the column, table, schema, and optional column type.

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

            self.path = path
            super().__init__(
                f"Snowflake Add Map Layer From {self.schema}.{self.table}.{self.column}",
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
            geo_column_type = get_geo_column_type(
                geo_column_name=self.column,
                context_information=self.context_information,
            )
            srid = (
                get_srid_from_table_geo_column(
                    geo_column_name=self.column,
                    table_name=self.table,
                    context_information=self.context_information,
                )
                if geo_column_type == "GEOMETRY"
                else 4326
            )
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
                uri = (
                    f"connection_name={self.connection_name} sql_query= "
                    f"schema_name={self.schema} "
                    f"table_name={self.table} srid={srid} "
                    f"geom_column={self.column} "
                    f"geometry_type={geo_type} "
                    f"geo_column_type={geo_column_type} "
                    f"primary_key={self.primary_key}"
                )

                layer_name = (
                    self.table
                    if len(geo_type_list) == 1
                    else f"{self.table}_{geo_type}"
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
        if result:
            self.on_hadle_finished.emit(self.path)
