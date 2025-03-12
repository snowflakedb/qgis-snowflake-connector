from PyQt5.QtWidgets import QWidget
from qgis.core import Qgis
from qgis.gui import QgsMessageBar, QgsAuthSettingsWidget
from qgis.PyQt import uic
from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLineEdit,
    QMessageBox,
    QComboBox,
)
import os
import typing

from ..helpers.utils import (
    get_encrypted_credentials,
    get_qsettings,
    remove_connection,
    set_connection_settings,
)

from ..managers.sf_connection_manager import SFConnectionManager


FORM_CLASS_SFCS, _ = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), "sf_connection_string_dialog.ui")
)


class SFConnectionStringDialog(QDialog, FORM_CLASS_SFCS):
    update_connections_signal = pyqtSignal()

    def __init__(
        self, parent: typing.Optional[QWidget] = None, connection_name: str = ""
    ) -> None:
        """
        Initialize the SFConnectionStringDialog.

        Args:
            parent (QWidget, optional): The parent widget. Defaults to None.
            connection_name (str, optional): The name of the connection. Defaults to "".
        """
        super().__init__(parent)
        self.txtName: QLineEdit
        self.txtWarehouse: QLineEdit
        self.txtAccount: QLineEdit
        self.txtRole: QLineEdit
        self.btnConnect: QDialogButtonBox
        self.buttonBox: QDialogButtonBox
        self.cbxConnectionType: QComboBox
        self.txtDatabase: QLineEdit
        self.mAuthSettings: QgsAuthSettingsWidget
        self.setupUi(self)
        self.btnConnect.clicked.connect(self.test_connection_clicked)
        self.buttonBox.accepted.connect(self.button_box_ok_clicked)
        self.settings = get_qsettings()
        self.cbxConnectionType.addItem("Default Authentication")
        self.cbxConnectionType.addItem("Single sign-on (SSO)")
        self.connection_name = connection_name
        self._sf_connection_manager = SFConnectionManager.get_instance()
        self.deactivate_temp()

    def deactivate_temp(self) -> None:
        """
        Hides certain checkboxes in the UI.

        This method is used to hide specific checkboxes in the user interface.
        The checkboxes that are hidden include:
        - cb_geometryColumnsOnly
        - cb_dontResolveType
        - cb_publicSchemaOnly
        - cb_allowGeometrylessTables
        - cb_useEstimatedMetadata
        - cb_projectsInDatabase
        - cb_metadataInDatabase

        This method does not return any value.
        """
        self.cb_geometryColumnsOnly.setVisible(False)
        self.cb_dontResolveType.setVisible(False)
        self.cb_publicSchemaOnly.setVisible(False)
        self.cb_allowGeometrylessTables.setVisible(False)
        self.cb_useEstimatedMetadata.setVisible(False)
        self.cb_projectsInDatabase.setVisible(False)
        self.cb_metadataInDatabase.setVisible(False)

    def get_unfilled_required_fields(self) -> bool:
        """
        Checks for unfilled required fields in the connection dialog.

        This method verifies if the required fields in the connection dialog are filled.
        It returns a list of unfilled required fields with their corresponding names.

        Returns:
            list: A list of strings representing the names of unfilled required fields.
        """
        fields = [
            (self.txtName, "Connection Name", "text"),
            (self.txtWarehouse, "Warehouse", "text"),
            (self.txtAccount, "Account", "text"),
            (self.txtDatabase, "Database", "text"),
        ]

        if self.mAuthSettings.configurationTabIsSelected():
            fields.append(
                (
                    self.mAuthSettings,
                    "Authentication Configuration",
                    "configId",
                )
            )
        else:
            fields.append(
                (
                    self.mAuthSettings,
                    "Username (Under the Basic Authentification Tab)",
                    "username",
                )
            )

            if self.cbxConnectionType.currentText() == "Default Authentication":
                fields.append(
                    (
                        self.mAuthSettings,
                        "Password (Under the Basic Authentification Tab)",
                        "password",
                    )
                )

        unfilled_required_fields = []
        for widget, field_name, method_name in fields:
            try:
                method_to_call = getattr(widget, method_name)
                if method_to_call() == "":
                    unfilled_required_fields.append(f"- {field_name}\n")
            except Exception as _:
                pass

        return unfilled_required_fields

    def button_box_ok_clicked(self) -> None:
        """
        Save the connection settings when the OK button is clicked.

        This method saves the values entered in the dialog's text fields and combo boxes
        to the corresponding settings in the QSettings object. It also handles the removal
        of the previous connection settings if the connection name has been changed.

        Raises:
            Exception: If there is an error saving the connection settings.

        Signals:
            update_connections_signal: Emitted after the connection settings have been saved.
        """
        try:
            fields_not_verified = self.get_unfilled_required_fields()
            if len(fields_not_verified) > 0:
                QMessageBox.critical(
                    self,
                    "Error message in New/Edit connection",
                    f"Please specify all mandatory fields:\n{''.join(fields_not_verified)}",
                )
                return

            config_tab_selected = self.mAuthSettings.configurationTabIsSelected()
            conn_settings = {
                "username": self.mAuthSettings.username(),
                "name": self.txtName.text(),
                "warehouse": self.txtWarehouse.text(),
                "account": self.txtAccount.text(),
                "database": self.txtDatabase.text(),
                "connection_type": self.cbxConnectionType.currentText(),
                "password_encrypted": config_tab_selected,
            }

            is_default_auth = (
                self.cbxConnectionType.currentText() == "Default Authentication"
            )

            if is_default_auth:
                conn_settings["password"] = self.mAuthSettings.password()

            if config_tab_selected:
                encrypted_config_values = get_encrypted_credentials(
                    self.mAuthSettings.configId()
                )
                conn_settings["username"] = encrypted_config_values["username"]
                if is_default_auth:
                    conn_settings["config_id"] = self.mAuthSettings.configId()

            if self.txtRole.text() != "":
                conn_settings["role"] = self.txtRole.text()
            set_connection_settings(conn_settings)
            if self.connection_name != self.txtName.text():
                if self.connection_name is not None and self.connection_name != "":
                    remove_connection(self.settings, self.connection_name)

            if self.txtName.text() in self._sf_connection_manager.opened_connections:
                del self._sf_connection_manager.opened_connections[self.txtName.text()]
            self.update_connections_signal.emit()
            super().accept()
        except Exception as e:
            QMessageBox.information(
                None,
                "Save Connection",
                f"Error saving connection settings.\n\nExtended error information:\n{str(e)}",
            )

    def test_connection_clicked(self) -> None:
        """
        Test the connection to the Snowflake database using the provided settings.

        Raises:
            snowflake.connector.Error: If there is an error connecting to the Snowflake database.
            Exception: If there is an unexpected error during the connection process.
        """
        try:
            fields_not_verified = self.get_unfilled_required_fields()
            if len(fields_not_verified) > 0:
                QMessageBox.critical(
                    self,
                    "Error message in New/Edit connection",
                    f"Please specify all mandatory fields:\n{''.join(fields_not_verified)}",
                )
                return
            sf_connection_manager = SFConnectionManager.get_instance()
            connection_params = {
                "user": self.mAuthSettings.username(),
                "account": self.txtAccount.text(),
                "warehouse": self.txtWarehouse.text(),
                "database": self.txtDatabase.text(),
                "login_timeout": 5,
                "network_timeout": 20,
                "socket_timeout": 20,
            }

            is_default_auth = (
                self.cbxConnectionType.currentText() == "Default Authentication"
            )

            if self.txtRole.text() != "":
                connection_params["role"] = self.txtRole.text()
            if is_default_auth:
                connection_params["password"] = self.mAuthSettings.password()
            elif self.cbxConnectionType.currentText() == "Single sign-on (SSO)":
                connection_params["authenticator"] = "externalbrowser"

            if self.mAuthSettings.configurationTabIsSelected():
                encrypted_credentials = get_encrypted_credentials(
                    self.mAuthSettings.configId()
                )
                connection_params["user"] = encrypted_credentials["username"]
                if is_default_auth:
                    connection_params["password"] = encrypted_credentials["password"]

            conn = sf_connection_manager.create_snowflake_connection(connection_params)

            if conn:
                conn.close()

            qg_message_bar = QgsMessageBar(self)
            self.layout().addWidget(qg_message_bar, 0)
            style_sheet = "color: black;"
            qg_message_bar.setStyleSheet(style_sheet)
            qg_message_bar.pushMessage(
                "Test Connection",
                f"Connection to {self.txtName} was successful.",
                Qgis.MessageLevel.Success,
                5,
            )
        except Exception as e:
            QMessageBox.information(
                None,
                "Test Connection",
                f"Connection failed - Check settings and try again.\n\nExtended error information:\n{str(e)}",
            )
