from qgis.gui import QgsCollapsibleGroupBox
from qgis.PyQt.QtGui import QStandardItemModel, QStandardItem
from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtWidgets import (
    QDialog,
    QMessageBox,
    QComboBox,
    QTableView,
    QPushButton,
    QCheckBox,
    QToolButton,
    QLineEdit,
    QWidget,
)
from qgis.core import QgsApplication
import typing

from ..enums.snowflake_metadata_type import SnowflakeMetadataType
from ..helpers.data_base import checks_sql_query_exceeds_size
from ..helpers.messages import get_proceed_cancel_message_box
from ..tasks.sf_convert_sql_query_to_layer_task import SFConvertSQLQueryToLayerTask
from ..tasks.sf_execute_sql_query_task import SFExecuteSQLQueryTask
from ..helpers.utils import get_qsettings
from ..ui.sf_sql_query_dialog import Ui_QgsQueryResultWidgetBase


class SFSQLQueryDialog(QDialog, Ui_QgsQueryResultWidgetBase):
    update_connections_signal = pyqtSignal()

    def __init__(
        self,
        context_information: typing.Dict[str, typing.Union[str, None]] = None,
        parent: typing.Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setupUi(self)
        self.mGeometryColumnComboBox: QComboBox
        self.mQueryResultsTableView: QTableView
        self.mExecuteButton: QPushButton
        self.mGeometryColumnCheckBox: QCheckBox
        self.mLoadLayerPushButton: QPushButton
        self.mClearButton: QToolButton
        self.mLayerNameLineEdit: QLineEdit
        self.mLoadAsNewLayerGroupBox: QgsCollapsibleGroupBox
        self.context_information = context_information
        self.settings = get_qsettings()
        self.temp_deactivated_options()
        self.mExecuteButton.setEnabled(True)
        self.mExecuteButton.clicked.connect(self.on_execute_button_clicked)
        self.mLoadLayerPushButton.clicked.connect(
            self.on_load_layer_push_button_clicked
        )
        self.mClearButton.clicked.connect(self.on_clear_button_clicked)
        self.mLoadAsNewLayerGroupBox.collapsedStateChanged.connect(
            self.on_collapsed_state_changed
        )

    def on_collapsed_state_changed(self, collapsed):
        self.temp_deactivated_options()

    def on_clear_button_clicked(self):
        self.model = QStandardItemModel()
        self.mQueryResultsTableView.setModel(self.model)
        self.mSqlErrorText.clear()
        self.mGeometryColumnCheckBox.setChecked(False)

    def get_query_without_semicolon(self):
        query: str = self.mSqlErrorText.text()
        stripped_query = query.strip()
        return stripped_query[:-1] if stripped_query.endswith(";") else stripped_query

    def on_load_layer_push_button_clicked(self):
        try:
            if self.mGeometryColumnCheckBox.isChecked():
                query_without_semicolon = self.get_query_without_semicolon()
                context_information_with_sql_query = self.context_information.copy()
                context_information_with_sql_query["sql_query"] = (
                    query_without_semicolon
                )
                table_exceeds_size = checks_sql_query_exceeds_size(
                    context_information=context_information_with_sql_query,
                )

                task_should_run = True
                if table_exceeds_size:
                    response = get_proceed_cancel_message_box(
                        title="Resultset is too large",
                        text=(
                            "You are trying to load more than 50 thousand rows. We "
                            'recommend you to apply a limit clause (e.g. "LIMIT 50000") to your query. '
                            'If you click "Proceed" your query will execute as is.'
                        ),
                    )
                    task_should_run = response != QMessageBox.StandardButton.Cancel
                if task_should_run:
                    geo_column_name = self.mGeometryColumnComboBox.currentText()
                    self.context_information["geo_column_name"] = geo_column_name
                    self.context_information["geo_column_type_is_h3"] = (
                        self.mGeometryColumnComboBox.itemData(
                            self.mGeometryColumnComboBox.currentIndex()
                        )["is_h3"]
                    )
                    sf_convert_sql_query_to_layer_task = SFConvertSQLQueryToLayerTask(
                        query=query_without_semicolon,
                        layer_name=self.mLayerNameLineEdit.text(),
                        context_information=self.context_information,
                    )

                    sf_convert_sql_query_to_layer_task.on_handle_error.connect(
                        self.on_handle_error
                    )
                    sf_convert_sql_query_to_layer_task.on_success.connect(
                        self.on_success
                    )
                    QgsApplication.taskManager().addTask(
                        sf_convert_sql_query_to_layer_task
                    )

        except Exception as e:
            QMessageBox.information(
                None,
                "SFSQLQueryDialog - Add Layer from SQL Query",
                f"Adding Layer from SQL Query failed.\n\nExtended error information:\n{str(e)}",
            )

    def on_success(self):
        self.close()

    def temp_deactivated_options(self) -> None:
        self.mProgressBar.setVisible(False)
        self.mPkColumnsCheckBox.setVisible(False)
        self.mPkColumnsComboBox.setVisible(False)
        self.mFilterLabel.setVisible(False)
        self.mFilterLineEdit.setVisible(False)
        self.mFilterToolButton.setVisible(False)
        self.mAvoidSelectingAsFeatureIdCheckBox.setVisible(False)
        self.mStopButton.setVisible(False)
        self.mStatusLabel.setVisible(False)

    def on_execute_button_clicked(self):
        try:
            snowflake_covert_column_to_layer_task = SFExecuteSQLQueryTask(
                context_information=self.context_information,
                query=self.get_query_without_semicolon(),
                limit=100,
            )
            snowflake_covert_column_to_layer_task.on_handle_error.connect(
                self.on_handle_error
            )
            snowflake_covert_column_to_layer_task.on_data_ready.connect(
                self.on_data_ready
            )
            QgsApplication.taskManager().addTask(snowflake_covert_column_to_layer_task)
        except Exception as e:
            QMessageBox.information(
                None,
                "SFSQLQueryDialog - Execute SQL Query",
                f"Executing SQL Query failed.\n\nExtended error information:\n{str(e)}",
            )

    def on_data_ready(
        self,
        result: tuple,
    ) -> None:
        try:
            self.model = QStandardItemModel()
            self.mQueryResultsTableView.setModel(self.model)
            self.mGeometryColumnComboBox.clear()
            col_names = []
            col_types = []

            col_description = result[0]
            h3_column_check = result[2][0]

            for index, result_meta_data in enumerate(col_description):
                col_name = result_meta_data[0]
                col_type = result_meta_data[1]
                col_names.append(col_name)
                col_types.append(col_type)
                if (
                    col_type
                    in [
                        SnowflakeMetadataType.GEOGRAPHY.value,
                        SnowflakeMetadataType.GEOMETRY.value,
                    ]
                    or h3_column_check[index]
                ):
                    self.mGeometryColumnComboBox.addItem(
                        col_name, {"is_h3": True if h3_column_check[index] else False}
                    )
            self.model.setHorizontalHeaderLabels(col_names)

            for idx, row in enumerate(result[1]):
                items = []
                for col_value in row:
                    if col_value is None:
                        items.append(QStandardItem(None))
                    else:
                        items.append(QStandardItem(str(col_value)))
                self.model.appendRow(items)

        except Exception as e:
            QMessageBox.information(
                None,
                "SFSQLQueryDialog - Data Ready",
                f"Data Ready failed.\n\nExtended error information:\n{str(e)}",
            )

    def on_handle_error(self, title, message):
        QMessageBox.information(None, title, message)
