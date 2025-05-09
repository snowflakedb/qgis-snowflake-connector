from ..helpers.data_base import (
    check_table_exceeds_size,
    limit_size_for_table,
)
from ..helpers.messages import (
    get_proceed_cancel_message_box,
)
from ..helpers.utils import (
    get_auth_information,
    get_auth_method_config,
    get_authentification_information,
    get_connection_child_groups,
    prompt_and_get_primary_key,
    get_qsettings,
    on_handle_error,
    remove_connection,
)
from ..tasks.sf_connect_task import SFConnectTask
from ..tasks.sf_convert_column_to_layer_task import (
    SFConvertColumnToLayerTask,
)
from .sf_connection_string_dialog import SFConnectionStringDialog
from qgis.core import QgsApplication
from qgis.gui import QgsAbstractDataSourceWidget
from qgis.PyQt import uic
from qgis.PyQt.QtCore import QModelIndex
from qgis.PyQt.QtGui import QStandardItemModel, QStandardItem
from qgis.PyQt.QtWidgets import QMessageBox, QWidget, QComboBox, QTabWidget
import os
import typing


FORM_CLASS_SFDSM, _ = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), "sf_data_source_manager_widget.ui")
)


class SFDataSourceManagerWidget(QgsAbstractDataSourceWidget, FORM_CLASS_SFDSM):
    def __init__(self, parent: typing.Optional[QWidget] = None):
        """
        Initialize the SFDataSourceManagerWidget.

        Args:
            parent (QWidget, optional): The parent widget. Defaults to None.
        """
        super().__init__(parent)
        self.setupUi(self)
        self.cmbConnections: QComboBox
        self.btnNew.clicked.connect(self.on_btn_new_clicked)
        self.btnConnect.clicked.connect(self.on_btn_connect_clicked)
        self.btnEdit.clicked.connect(self.on_btn_edit_clicked)
        self.btnDelete.clicked.connect(self.on_btn_delete_clicked)
        self.mTablesTreeView.doubleClicked.connect(
            self.on_m_tables_tree_view_double_clicked
        )
        self.settings = get_qsettings()
        self.model = QStandardItemModel()
        self.set_headers_model()
        self.update_cmb_connections()
        self.deactivate_temp()
        self._running_tasks = {}

    def deactivate_temp(self) -> None:
        """
        Hides the load, save, allow geometryless tables, hold dialog open, and button box widgets.

        This method is used to deactivate temporary widgets in the SFDataSourceManagerWidget.
        """
        self.btnLoad.setVisible(False)
        self.btnSave.setVisible(False)
        self.cbxAllowGeometrylessTables.setVisible(False)
        self.mHoldDialogOpen.setVisible(False)
        self.buttonBox.setVisible(False)

    def on_m_tables_tree_view_double_clicked(self, index: QModelIndex) -> bool:
        """
        Handle the double-click event on the tables tree view.

        Args:
            index (QModelIndex): The index of the double-clicked item.

        Returns:
            bool: True if the event was handled successfully, False otherwise.
        """
        try:
            model = index.model()
            qmi_schema = index.siblingAtColumn(0)
            qmi_table = index.siblingAtColumn(1)
            qmi_comment = index.siblingAtColumn(2)
            qmi_column = index.siblingAtColumn(3)
            qmi_data_type = index.siblingAtColumn(4)

            schema = model.data(qmi_schema)
            table = model.data(qmi_table)
            comment = model.data(qmi_comment)
            column = model.data(qmi_column)
            data_type = model.data(qmi_data_type)

            selected_connection = self.cmbConnections.currentText()
            auth_information = get_auth_information(selected_connection)

            context_information = {
                "connection_name": selected_connection,
                "database_name": auth_information["database"],
                "schema_name": schema,
                "table_name": table,
                "geo_column": column,
                "geom_type": data_type,
            }

            table_exceeds_size = check_table_exceeds_size(
                context_information=context_information,
            )

            limit_size = limit_size_for_table(context_information=context_information)

            if table_exceeds_size:
                response = get_proceed_cancel_message_box(
                    "SFConvertColumnToLayerTask Dataset is too large",
                    (
                        "The dataset is too large. Please consider using "
                        '"Execute SQL" to limit the result set. If you click '
                        f'"Proceed", only a random sample of {limit_size // 1000} thousand rows '
                        "will be loaded."
                    ),
                )
                if response == QMessageBox.Cancel:
                    return False

            context_information["primary_key"] = prompt_and_get_primary_key(
                context_information=context_information, data_type=data_type
            )

            path = f"/Snowflake/{selected_connection}/{schema}/{table}"

            if (
                selected_connection is not None
                and selected_connection != ""
                and path not in self._running_tasks
            ):
                snowflake_covert_column_to_layer_task = SFConvertColumnToLayerTask(
                    context_information=context_information,
                    path=path,
                )
                self._running_tasks[path] = True
                snowflake_covert_column_to_layer_task.on_handle_error.connect(
                    on_handle_error
                )
                snowflake_covert_column_to_layer_task.on_handle_finished.connect(
                    slot=self.on_handle_finished
                )
                QgsApplication.taskManager().addTask(
                    snowflake_covert_column_to_layer_task
                )

            return True

        except Exception as e:
            QMessageBox.information(
                None,
                "Double-clicked on Table",
                f"Double-clicked on table failed.\n\nExtended error information:\n{str(e)}",
            )
            return False

    def on_handle_finished(self, path: str) -> None:
        """
        Handles a warning by removing the specified path from the running tasks.

        Args:
            path (str): The path associated with the warning to be handled.

        Returns:
            None
        """
        del self._running_tasks[path]

    def update_cmb_connections(self) -> None:
        """
        Updates the combo box with the available connections.

        This method retrieves the root groups from the settings and populates the combo box
        with the names of these groups. If an exception occurs during the process, an
        information message box is displayed with the error details.

        Returns:
            None
        """
        try:
            root_groups = get_connection_child_groups()
            self.mTablesTreeView.setModel(self.model)
            self.cmbConnections.clear()
            for group in root_groups:
                self.cmbConnections.addItem(group)

            self.refresh()
        except Exception as e:
            QMessageBox.information(
                None,
                "Refreshing Connection List",
                f"Refreshing connection list failed.\n\nExtended error information:\n{str(e)}",
            )

    def on_btn_delete_clicked(self) -> None:
        """
        Handle the click event of the delete button.

        This method removes the selected connection from the data source manager widget.
        If a connection is selected, it calls the 'remove_connection' function to delete the connection.
        After deleting the connection, it updates the combo box with the remaining connections.

        Raises:
            Exception: If deleting the connection fails, an exception is raised.

        Returns:
            None
        """
        try:
            selected_connection = self.cmbConnections.currentText()
            if selected_connection is not None and selected_connection != "":
                remove_connection(
                    settings=self.settings, connection_name=selected_connection
                )
                self.update_cmb_connections()
        except Exception as e:
            QMessageBox.information(
                None,
                "Deleting Connection",
                f"Deleting connection failed.\n\nExtended error information:\n{str(e)}",
            )

    def on_btn_edit_clicked(self) -> None:
        """
        Opens a dialog window to edit the selected connection.

        Raises:
            Exception: If editing the connection fails.

        Returns:
            None
        """
        try:
            selected_connection = self.cmbConnections.currentText()
            if selected_connection is not None and selected_connection != "":
                another_window = SFConnectionStringDialog(self, selected_connection)
                another_window.update_connections_signal.connect(
                    self.update_cmb_connections
                )
                auth_information = get_authentification_information(
                    self.settings, selected_connection
                )

                index = another_window.cbxConnectionType.findText(
                    auth_information["connection_type"]
                )
                if index != -1:
                    another_window.cbxConnectionType.setCurrentIndex(index)

                another_window.txtName.setText(selected_connection)
                another_window.txtWarehouse.setText(auth_information["warehouse"])
                another_window.txtAccount.setText(auth_information["account"])
                another_window.txtDatabase.setText(auth_information["database"])

                if "role" in auth_information:
                    another_window.txtRole.setText(auth_information["role"])

                if auth_information["password_encrypted"]:
                    m_auth_settings_tab_widget: QTabWidget = (
                        another_window.mAuthSettings.findChild(QTabWidget)
                    )
                    if m_auth_settings_tab_widget:
                        m_auth_settings_tab_widget.setCurrentIndex(0)

                    m_auth_settings_combo_box: QComboBox = (
                        another_window.mAuthSettings.findChild(QComboBox)
                    )

                    auth_method_config = get_auth_method_config(
                        auth_information["config_id"]
                    )

                    for i in range(m_auth_settings_combo_box.count()):
                        m_auth_settings_combo_box.setCurrentIndex(i)
                        if (
                            m_auth_settings_combo_box.currentText()
                            == auth_method_config.name()
                        ):
                            break
                else:
                    another_window.mAuthSettings.setUsername(
                        auth_information["username"]
                    )
                    another_window.mAuthSettings.setPassword(
                        auth_information["password"]
                    )
                another_window.exec_()
        except Exception as e:
            QMessageBox.information(
                None,
                "Editing Connection",
                f"Editing connection failed.\n\nExtended error information:\n{str(e)}",
            )

    def set_headers_model(self) -> None:
        """
        Set the horizontal header labels for the model.

        Returns:
            None
        """
        self.model.setHorizontalHeaderLabels(
            [
                "Schema",
                "Table",
                "Comment",
                "Columns",
                "Data Type",
                # "Spatial Type",
                "SRID",
            ]
        )

    def clean_items_from_model(self) -> None:
        """
        Clears the items from the model and sets the headers for the model.
        """
        self.model.clear()
        self.set_headers_model()

    def on_btn_connect_clicked(self) -> None:
        """
        Connects to the selected database connection.

        Raises:
            Exception: If the connection fails.
        """
        try:
            selected_connection = self.cmbConnections.currentText()
            if selected_connection is not None and selected_connection != "":
                task = SFConnectTask(selected_connection)
                task.on_data_ready.connect(self.on_data_ready)
                task.on_handle_error.connect(on_handle_error)
                QgsApplication.taskManager().addTask(task)
            else:
                QMessageBox.information(
                    None,
                    "No Connection Selected",
                    f"No connection selected. {selected_connection}",
                )
        except Exception as e:
            QMessageBox.information(
                None,
                "Connect Database",
                f"Connection failed - Check settings and try again.\n\nExtended error information:\n{str(e)}",
            )

    def on_data_ready(self, rows_items: typing.List[QStandardItem]) -> None:
        """
        Handle the event when data is ready.

        Args:
            rows_items (List[QStandardItem]): A list of QStandardItem objects representing the rows of data.

        Returns:
            None
        """
        try:
            self.clean_items_from_model()
            # self.model.appendRows(rows_items)
            for row in rows_items:
                self.model.appendRow(row)
        except Exception as e:
            QMessageBox.information(
                None,
                "Data Ready",
                f"Data ready failed.\n\nExtended error information:\n{str(e)}",
            )

    def on_btn_new_clicked(self) -> None:
        """
        Opens a dialog for creating a new Snowflake connection string.

        This method is triggered when the "New" button is clicked. It creates an instance of the SFConnectionStringDialog
        dialog and connects its update_connections_signal to the update_cmb_connections method. The dialog is then executed.
        If an exception occurs during the execution, an information message box is displayed with the error details.

        Raises:
            Exception: If an error occurs during the creation of the new connection.

        """
        try:
            self.sf_connection_string_dialog = SFConnectionStringDialog(self)
            self.sf_connection_string_dialog.update_connections_signal.connect(
                self.update_cmb_connections
            )
            self.sf_connection_string_dialog.exec_()
        except Exception as e:
            QMessageBox.information(
                None,
                "New Connection",
                f"Creating new connection failed.\n\nExtended error information:\n{str(e)}",
            )
