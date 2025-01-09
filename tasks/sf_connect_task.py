import typing

from ..helpers.data_base import get_geo_columns
from ..helpers.utils import get_authentification_information, get_qsettings
from ..providers.sf_data_source_provider import SFDataProvider
from qgis.core import QgsTask
from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QStandardItem


class SFConnectTask(QgsTask):
    on_handle_error = pyqtSignal(str, str)
    on_data_ready = pyqtSignal(list)

    def __init__(self, connection_name: str) -> None:
        """
        Initializes the SFConnectTask object.

        Args:
            connection_name (str): The name of the Snowflake connection.

        Raises:
            Exception: If the initialization fails.
        """
        try:
            super().__init__("Snowflake Connection Task", QgsTask.CanCancel)
            self.settings = get_qsettings()
            self.auth_information = get_authentification_information(
                self.settings, connection_name
            )
            self.query = f"""
            SELECT TABLE_CATALOG, TABLE_SCHEMA, TABLE_NAME, COMMENT, COLUMN_NAME, DATA_TYPE
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_CATALOG = '{self.auth_information["database"].upper()}'
            AND DATA_TYPE in ('GEOGRAPHY', 'GEOMETRY', 'NUMBER', 'TEXT')
            ORDER BY TABLE_CATALOG, TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE
            """
            self.connection_name = connection_name
        except Exception as e:
            self.on_handle_error.emit(
                "SFConnectTask init failed",
                f"Initiating sf connect task failed.\n\nExtended error information:\n{str(e)}",
            )

    def run(self) -> bool:
        """
        Executes the SFConnectTask.

        Returns:
            bool: True if the task is executed successfully, False otherwise.
        """
        try:
            sf_data_provider = SFDataProvider(self.auth_information)
            columns = get_geo_columns(
                sf_data_provider, self.connection_name
            )
            columns.sort(key=lambda x: (x.attribute("TABLE_CATALOG"), x.attribute("TABLE_SCHEMA"), x.attribute("TABLE_NAME")))
            current_schema = None
            current_item = None
            self.rows_items: typing.List[QStandardItem] = []
            for feat in columns:

                from qgis.core import QgsMessageLog
                QgsMessageLog.logMessage(f"col {feat.attributes()}", 'SF Plugin')

                if current_schema != feat.attribute("TABLE_SCHEMA"):
                    current_schema = feat.attribute("TABLE_SCHEMA")
                    current_item = QStandardItem(feat.attribute("TABLE_SCHEMA"))
                    self.rows_items.append(current_item)
                srid = ""
                if feat.attribute("DATA_TYPE") != "GEOMETRY":
                    srid = "4326"

                if (
                    isinstance(feat.attribute("COMMENT"), QVariant)
                    and feat.attribute("COMMENT").isNull()
                ) or feat.attribute("COMMENT") is None:
                    standard_item_comment = QStandardItem()
                else:
                    standard_item_comment = QStandardItem(feat.attribute("COMMENT"))

                data_type = feat.attribute("DATA_TYPE")
                if data_type in ["NUMBER", "TEXT"]:
                    data_type = "H3GEO"

                row_items = [
                    QStandardItem(feat.attribute("TABLE_SCHEMA")),
                    QStandardItem(feat.attribute("TABLE_NAME")),
                    standard_item_comment,
                    QStandardItem(feat.attribute("COLUMN_NAME")),
                    QStandardItem(data_type),
                    QStandardItem(srid),
                ]

                if current_item is not None:
                    current_item.appendRow(row_items)

            return True
        except Exception as e:
            self.on_handle_error.emit(
                "SFConnectTask run failed",
                f"Running sf connect task failed.\n\nExtended error information:\n{str(e)}",
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
            self.on_data_ready.emit(self.rows_items)
