from ..managers.sf_connection_manager import SFConnectionManager
from ..helpers.data_base import (
    get_column_iterator,
    get_features_iterator,
    get_table_column_iterator,
)
from ..helpers.messages import get_ok_cancel_message_box
from ..helpers.layer_creation import check_table_exceeds_size
from ..helpers.utils import (
    add_task_to_running_queue,
    get_authentification_information,
    get_connection_child_groups,
    get_qsettings,
    on_handle_error,
    on_handle_warning,
    remove_connection,
    task_is_running,
)
from ..tasks.sf_convert_column_to_layer_task import SFConvertColumnToLayerTask
from ..ui.sf_connection_string_dialog import SFConnectionStringDialog
from PyQt5.QtCore import pyqtSignal
from qgis.core import QgsDataItem, Qgis, QgsApplication, QgsErrorItem
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QMessageBox, QAction, QWidget
import typing


class SFDataItem(QgsDataItem):
    message_handler = pyqtSignal(str, str)

    def __init__(
        self,
        type: Qgis.BrowserItemType,
        parent: "SFDataItem",
        name: str,
        path: str,
        provider_key: str,
        item_type: str,
        icon_path: str,
        clean_name: str,
        connection_name: str = None,
        geom_column: str = None,
    ) -> None:
        """
        Initializes a SFDataItem object.

        Args:
            type (Qgis.BrowserItemType): The type of the browser item.
            parent (SFDataItem): The parent item of the browser item.
            name (str): The name of the browser item.
            path (str): The path of the browser item.
            provider_key (str): The provider key of the browser item.
            item_type (str): The type of the item.
            icon_path (str): The path to the icon of the browser item.
            connection_name (str, optional): The name of the connection. Defaults to None.
        """
        super().__init__(type, parent, name, path, provider_key)
        self.item_type = item_type
        self.settings = get_qsettings()
        self.setIcon(QIcon(icon_path))
        self.connection_name = connection_name
        self.message_handler.connect(self.on_message_handler)
        self.clean_name = clean_name
        self.geom_column = geom_column

    def createChildren(self) -> typing.List["QgsDataItem"]:
        """
        Creates and returns a list of child QgsDataItem objects based on the item type.

        Returns:
            List[QgsDataItem]: A list of child QgsDataItem objects.

        Raises:
            Exception: If an error occurs during the creation of child items.
        """
        children: typing.List["SFDataItem"] = []
        try:
            if self.item_type == "field":
                pass
            elif self.item_type == "root":
                self.create_root_item(children)
            elif self.item_type == "schema":
                self.create_schema_item(children)

            elif self.item_type == "table":
                self.create_table_item(children)

            elif self.item_type == "fields":
                self.create_fields_item(children)
            else:
                self.create_default_item(children)

            return children

        except Exception as e:
            error_item = QgsErrorItem(
                self,
                f"SFDataItem - Data item children creation failed.\n\nExtended error information:\n{str(e)}",
                self.path() + "/error",
            )
            children.append(error_item)
        return children

    def create_default_item(self, children: typing.List["SFDataItem"]) -> None:
        """
        Creates default items and appends them to the provided children list.

        This method retrieves query metadata and uses it to fetch features from a data source.
        If the item type is "connection" and the connection type is "Single sign-on (SSO)",
        it emits a message indicating that SSO authorization is required.

        Args:
            children (typing.List["SFDataItem"]): A list to which the created data items will be appended.

        Returns:
            None
        """
        auth_information, column_name, children_item_type, query = (
            self._get_query_metadata()
        )
        if (
            self.item_type == "connection"
            and auth_information["connection_type"] == "Single sign-on (SSO)"
        ):
            self.parent().message_handler.emit(
                "Single Sign-On (SSO) Authorization Required",
                "Please check your third-party authentication application to authorize the connection. Ensure that any required permissions or approvals are granted to complete the Single Sign-On (SSO) process..",
            )

        feature_iterator = get_features_iterator(
            auth_information, query, self.connection_name
        )

        for feat in feature_iterator:
            item = self._create_data_item(
                name=feat.attribute(column_name),
                type=children_item_type,
                connection_name=self.connection_name,
                clean_name=feat.attribute(column_name),
            )
            children.append(item)
        feature_iterator.close()

    def create_root_item(self, children: typing.List["SFDataItem"]) -> None:
        """
        Creates root items and appends them to the provided children list.

        This method retrieves the root groups from the settings and creates a data item
        for each group. The created data items are then appended to the provided children list.

        Args:
            children (List[SFDataItem]): A list to which the created root items will be appended.

        Returns:
            None
        """
        root_groups = get_connection_child_groups()
        for group in root_groups:
            item = self._create_data_item(
                name=group,
                type="connection",
                connection_name=group,
                clean_name=group,
            )
            children.append(item)

    def create_schema_item(self, children: typing.List["SFDataItem"]) -> None:
        feature_iterator = get_table_column_iterator(
            self.settings, self.connection_name, self.clean_name
        )
        """
        Creates schema items and appends them to the provided children list.

        This method iterates over features obtained from a schema iterator and creates
        data items based on the feature attributes. It handles naming conflicts by 
        appending column names to the item names if necessary.

        Args:
            children (typing.List["SFDataItem"]): A list to which the created schema items will be appended.

        Returns:
            None
        """
        children_item_type = "table"

        items_metadata = []

        for feat in feature_iterator:
            item_name = feat.attribute(0)
            if len(items_metadata) > 0:
                last_child = children[-1]
                last_item_metadata = items_metadata[-1]

                if last_child.name() == feat.attribute(0):
                    last_child.setName(
                        f"{last_child.name()}.{last_item_metadata['column_name']}"
                    )
                    item_name = f"{feat.attribute(0)}.{feat.attribute(1)}"

            item = self._create_data_item(
                name=item_name,
                type=children_item_type,
                connection_name=self.connection_name,
                clean_name=feat.attribute(0),
            )
            item.geom_column = feat.attribute(1)
            children.append(item)
            items_metadata.append(
                {
                    "table_name": feat.attribute(0),
                    "column_name": feat.attribute(1),
                }
            )
        feature_iterator.close()

    def create_table_item(self, children: typing.List["SFDataItem"]) -> None:
        """
        Creates a table item and appends it to the provided list of children.

        This method creates a data item with the name "Fields" and type "fields",
        sets its capabilities to have no capabilities, and then appends it to the
        provided list of children.

        Args:
            children (typing.List["SFDataItem"]): The list to which the created item will be appended.

        Returns:
            None
        """
        item = self._create_data_item(
            name="Fields",
            type="fields",
            connection_name=self.connection_name,
            clean_name="Fields",
        )
        item.setCapabilitiesV2(
            Qgis.BrowserItemCapabilities(Qgis.BrowserItemCapability.NoCapabilities)
        )
        children.append(item)

    def create_fields_item(self, children: typing.List["SFDataItem"]) -> None:
        """
        Creates field items and appends them to the provided children list.

        This method iterates over features obtained from a column iterator and creates
        data items for each feature. It filters out geometry and geography columns that
        do not match the table's geometry column. Each created data item is appended to
        the provided children list.

        Args:
            children (typing.List["SFDataItem"]): A list to which the created field items
                                                  will be appended.

        Returns:
            None
        """
        table_data_item = self.parent()
        feature_iterator = get_column_iterator(
            self.settings, self.connection_name, table_data_item
        )

        for feat in feature_iterator:
            if feat.attribute(1) in [
                "GEOMETRY",
                "GEOGRAPHY",
            ] and table_data_item.geom_column != feat.attribute(0):
                continue
            item = self._create_data_item(
                name=feat.attribute(0),
                type="field",
                connection_name=self.connection_name,
                clean_name=feat.attribute(0),
                icon_path=f":/plugins/qgis-snowflake-connector/ui/images/fields/{self.get_field_type_svg_name(feat.attribute(1), feat.attribute(2))}.svg",
            )
            children.append(item)
        feature_iterator.close()

    def get_field_type_svg_name(self, field_type: str, field_pression: int) -> str:
        snowflake_types = {
            "ARRAY": "array",
            "BINARY": "binary",
            "BOOLEAN": "bool",
            "TEXT": "text",
            "DATE": "date",
            "FLOAT": "float",
            "GEOGRAPHY": "geometry",
            "GEOMETRY": "geometry",
            "OBJECT": "text",
            "TIMESTAMP_LTZ": "dateTime",
            "TIMESTAMP_NTZ": "dateTime",
            "TIMESTAMP_TZ": "dateTime",
            "TIME": "time",
            "VARIANT": "text",
        }

        if field_type == "NUMBER":
            if field_pression > 0:
                return "float"
            return "integer"
        else:
            if field_type in snowflake_types:
                return snowflake_types[field_type]
            else:
                return "text"

    def _get_query_metadata(self) -> typing.Tuple[dict, str, str, str]:
        """
        Retrieves the query metadata for the Snowflake data item.
        Returns:
            A tuple containing the following elements:
            - auth_information (dict): The authentication information for the Snowflake connection.
            - column_name (str): The name of the column used for filtering.
            - children_item_type (str): The type of children items.
            - query (str): The SQL query used to retrieve the metadata.
        """
        auth_information = get_authentification_information(
            self.settings, self.connection_name
        )

        schema_filter = ""
        table_filter = ""
        if self.item_type == "root":
            column_name = ""
            children_item_type = "connection"
        elif self.item_type == "connection":
            column_name = "TABLE_SCHEMA"
            children_item_type = "schema"
        elif self.item_type == "schema":
            column_name = "TABLE_NAME"
            children_item_type = "table"
            schema_filter = f"AND TABLE_SCHEMA = '{self.clean_name}'"
        elif self.item_type == "table":
            schema_filter = f"AND TABLE_SCHEMA = '{self.parent().clean_name}'"
            table_filter = f"AND TABLE_NAME = '{self.clean_name}'"
            column_name = "COLUMN_NAME"
            children_item_type = "column"
        query = f"""SELECT DISTINCT {column_name}
FROM INFORMATION_SCHEMA.COLUMNS
WHERE table_catalog = '{auth_information["database"]}'
{schema_filter}
{table_filter}
AND DATA_TYPE in ('GEOGRAPHY', 'GEOMETRY')
ORDER BY {column_name}"""

        return auth_information, column_name, children_item_type, query

    def _create_data_item(
        self,
        name: str,
        type: str,
        connection_name: str,
        clean_name: str,
        path: str = None,
        icon_path: str = None,
    ) -> "SFDataItem":
        """
        Create a SFDataItem object.

        Parameters:
        - name (str): The name of the data item.
        - type (str): The type of the data item.
        - connection_name (str): The name of the connection.

        Returns:
        - SFDataItem: The created SFDataItem object.
        """
        if icon_path is None:
            icon_path = f":/plugins/qgis-snowflake-connector/ui/images/{type}.svg"
        item = SFDataItem(
            type=Qgis.BrowserItemType.Field,
            parent=self,
            name=name,
            path=f"{self.path()}/{name}" if path is None else path,
            provider_key=self.providerKey(),
            item_type=type,
            icon_path=icon_path,
            clean_name=clean_name,
            connection_name=connection_name,
        )

        return item

    def handleDoubleClick(self) -> bool:
        """
        Handles the double click event for the data item.

        Returns:
            bool: True if the double click event is handled successfully, False otherwise.
        """
        try:
            # if self.item_type == "table" and not task_is_running(self.path()):
            #     schema_data_item = self.parent()
            #     auth_information = get_authentification_information(
            #         self.settings, self.connection_name
            #     )
            #     information_dict = {
            #         "schema": schema_data_item.clean_name,
            #         "table": self.clean_name,
            #         "column": self.geom_column,
            #         "database": auth_information["database"],
            #     }

            #     table_exceeds_size = check_table_exceeds_size(
            #         auth_information=auth_information,
            #         table_information=information_dict,
            #         connection_name=self.connection_name,
            #     )

            #     if table_exceeds_size:
            #         response = get_ok_cancel_message_box(
            #             "SFConvertColumnToLayerTask Dataset is too large",
            #             (
            #                 "The dataset is too large. Please consider using "
            #                 '"Execute SQL" to limit the result set. If you click '
            #                 '"Proceed," only a random sample of 1 million rows '
            #                 "will be loaded."
            #             ),
            #         )
            #         if response == QMessageBox.Cancel:
            #             return False

            #     snowflake_covert_column_to_layer_task = SFConvertColumnToLayerTask(
            #         connection_name=self.connection_name,
            #         information_dict=information_dict,
            #         path=self.path(),
            #     )
            #     snowflake_covert_column_to_layer_task.on_handle_error.connect(
            #         slot=on_handle_error
            #     )
            #     snowflake_covert_column_to_layer_task.on_handle_warning.connect(
            #         slot=on_handle_warning
            #     )
            #     QgsApplication.taskManager().addTask(
            #         task=snowflake_covert_column_to_layer_task
            #     )
            #     add_task_to_running_queue(task_name=self.path(), status="processing")
            schema_data_item = self.parent()
            auth_information = get_authentification_information(
                self.settings, self.connection_name
            )
            information_dict = {
                "schema": schema_data_item.clean_name,
                "table": self.clean_name,
                "column": self.geom_column,
                "database": auth_information["database"],
            }
            uri = (
                f"connection_name={self.connection_name} sql_query= "
                f"schema_name={schema_data_item.clean_name} table_name={self.clean_name} srid={4326} "
                f"geom_column={self.geom_column} geometry_type=POLYGON"
            )
            from qgis.core import (
                QgsProject,
                QgsVectorLayer,
            )

            print(uri)
            layer = QgsVectorLayer(uri, "layer_name", "snowflakedb")
            QgsProject.instance().addMapLayer(layer)
            return True
        except Exception as e:
            print(str(e))
            return False

    def actions(self, parent: QWidget) -> typing.List[QAction]:
        """
        Generates a list of QAction objects based on the item type.

        Args:
            parent (QWidget): The parent widget.

        Returns:
            typing.List[QAction]: A list of QAction objects.

        Raises:
            Exception: If there is an error creating the actions.

        """
        try:
            # Create a list to hold actions
            action_list: typing.List[QAction] = []

            # # Create another action
            self.refresh_action = QAction("Refresh", None)
            self.refresh_action.triggered.connect(self.on_refresh_action_triggered)
            action_list.append(self.refresh_action)

            if self.item_type == "schema":
                self.new_table_action = QAction("New Table...", None)
                self.new_table_action.triggered.connect(
                    self.on_new_table_action_triggered
                )
                action_list.append(self.new_table_action)

            if self.item_type == "connection":
                self.edit_connection_action = QAction("Edit Connection", None)
                self.edit_connection_action.triggered.connect(
                    self.on_edit_connection_action_triggered
                )
                action_list.append(self.edit_connection_action)

                self.remove_connection_action = QAction("Remove Connection", None)
                self.remove_connection_action.triggered.connect(
                    self.on_remove_connection_action_triggered
                )
                action_list.append(self.remove_connection_action)

                self.new_schema_action = QAction("New Schema...", None)
                self.new_schema_action.triggered.connect(
                    self.on_new_schema_action_triggered
                )
                action_list.append(self.new_schema_action)

            if self.item_type != "root":
                self.execute_sql_action = QAction("Execute SQL...", None)
                self.execute_sql_action.triggered.connect(
                    self.on_execute_sql_action_triggered
                )
                action_list.append(self.execute_sql_action)

            if self.item_type == "root":
                self.new_connection_action = QAction("New Connection", None)
                self.new_connection_action.triggered.connect(
                    self.on_new_connection_action_triggered
                )
                action_list.append(self.new_connection_action)

            return action_list
        except Exception as e:
            QMessageBox.information(
                None,
                "Data Item Actions Creation Error",
                f"SFDataItem - Data item actions creation failed.\n\nExtended error information:\n{str(e)}",
            )

    def on_execute_sql_action_triggered(self) -> None:
        """
        Opens a dialog for executing SQL queries on the Snowflake database.
        The dialog allows the user to enter the SQL query to be executed on the Snowflake database.
        After the user enters the SQL query and confirms, the query is executed and the connections are handled accordingly.
        """
        from ..ui.sf_sql_query_dialog import SFSQLQueryDialog

        path_splitted = self.path().split("/")
        context_information = {
            "connection_name": path_splitted[2] if len(path_splitted) > 2 else None,
            "schema_name": path_splitted[3] if len(path_splitted) > 3 else None,
            "table_name": path_splitted[4] if len(path_splitted) > 4 else None,
        }

        sf_sql_query_dialog = SFSQLQueryDialog(
            context_information=context_information,
            parent=None,
        )
        sf_sql_query_dialog.update_connections_signal.connect(
            self.on_update_connections_handle
        )
        sf_sql_query_dialog.exec_()

    def on_new_schema_action_triggered(self) -> None:
        """
        Opens a dialog for creating a new schema in the Snowflake database.
        The dialog allows the user to enter the necessary information for creating a new schema in the Snowflake database.
        After the user enters the schema details and confirms, the schema is created and the connections are handled accordingly.
        """
        from ..ui.sf_new_schema_dialog import SFNewSchemaDialog

        sf_connection_string_dialog = SFNewSchemaDialog(self.connection_name, None)
        sf_connection_string_dialog.update_connections_signal.connect(
            self.on_update_connections_handle
        )
        sf_connection_string_dialog.exec_()

    def on_new_table_action_triggered(self) -> None:
        """
        Opens a dialog for creating a new table in the Snowflake database.
        The dialog allows the user to enter the necessary information for creating a new table in the Snowflake database.
        After the user enters the table details and confirms, the table is created and the connections are handled accordingly.
        """
        from ..ui.sf_new_table_dialog import SFNewTableDialog

        sf_connection_string_dialog = SFNewTableDialog(
            self.clean_name, self.connection_name, None
        )
        sf_connection_string_dialog.update_connections_signal.connect(
            self.on_update_connections_handle
        )
        sf_connection_string_dialog.exec_()

    def on_new_connection_action_triggered(self) -> None:
        """
        Opens a dialog for creating a new Snowflake connection string.
        The dialog allows the user to enter the necessary information for establishing a connection to a Snowflake database.
        After the user enters the connection details and confirms, the connection string is updated and the connections are handled accordingly.
        """
        sf_connection_string_dialog = SFConnectionStringDialog(None)
        sf_connection_string_dialog.update_connections_signal.connect(
            self.on_update_connections_handle
        )
        sf_connection_string_dialog.exec_()

    def on_edit_connection_action_triggered(self) -> None:
        """
        Opens a dialog window for editing the connection settings.

        This method creates an instance of the SFConnectionStringDialog class and sets the parent to None.
        It passes the connection name as a parameter to the dialog window.
        The authentication information is retrieved using the get_authentification_information function.

        The connection type is set in the dialog window based on the value retrieved from the authentication information.
        The name, warehouse, account, and database fields in the dialog window are populated with the corresponding values from the authentication information.

        The username and password fields in the dialog window are set using the setUsername and setPassword methods of the mAuthSettings object.

        The update_connections_signal signal is connected to the on_update_connections_handle method.

        Finally, the dialog window is executed.
        """

        sf_connection_string_dialog_window = SFConnectionStringDialog(
            parent=None, connection_name=self.clean_name
        )
        auth_information = get_authentification_information(
            self.settings, self.clean_name
        )

        index = sf_connection_string_dialog_window.cbxConnectionType.findText(
            auth_information["connection_type"]
        )
        if index != -1:
            sf_connection_string_dialog_window.cbxConnectionType.setCurrentIndex(index)

        sf_connection_string_dialog_window.txtName.setText(self.clean_name)
        sf_connection_string_dialog_window.txtWarehouse.setText(
            auth_information["warehouse"]
        )
        sf_connection_string_dialog_window.txtAccount.setText(
            auth_information["account"]
        )
        sf_connection_string_dialog_window.txtDatabase.setText(
            auth_information["database"]
        )
        if "role" in auth_information:
            sf_connection_string_dialog_window.txtRole.setText(auth_information["role"])

        sf_connection_string_dialog_window.mAuthSettings.setUsername(
            auth_information["username"]
        )
        sf_connection_string_dialog_window.mAuthSettings.setPassword(
            auth_information["password"]
        )
        sf_connection_string_dialog_window.update_connections_signal.connect(
            self.on_update_connections_handle
        )
        sf_connection_string_dialog_window.exec_()

    def on_update_connections_handle(self) -> None:
        """
        Handle the update of connections.

        If the item type is "root", refresh the item.
        If the item type is "connection", refresh the parent item.
        """
        if self.item_type == "root":
            self.refresh_internal()
        if self.item_type == "connection":
            self.parent().refresh()

    def on_remove_connection_action_triggered(self) -> None:
        """
        Removes the connection associated with the data item.

        This method removes the connection from the settings and refreshes the parent widget.

        Returns:
            None
        """
        remove_connection(self.settings, self.clean_name)
        self.parent().refresh()

    def on_refresh_action_triggered(self) -> None:
        """
        Refreshes the data item.
        """
        self.refresh_internal()

    def on_message_handler(self, title: str, message: str) -> None:
        """
        Handle the message by displaying it in a QMessageBox.

        Parameters:
        - title (str): The title of the message box.
        - message (str): The message to be displayed.

        Returns:
        - None
        """
        QMessageBox.information(None, title, message)

    def refresh_internal(self) -> None:
        """
        Refreshes the data item.
        """
        try:
            connection_manager: SFConnectionManager = SFConnectionManager.get_instance()
            if self.item_type != "root":
                connection_manager.reconnect(self.connection_name)

            super().refresh()
        except Exception as e:
            QMessageBox.information(
                None,
                "Data Item Actions Refresh Error",
                f"SFDataItem - refresh failed.\n\nExtended error information:\n{str(e)}",
            )
