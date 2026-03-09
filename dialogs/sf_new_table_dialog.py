from qgis.PyQt.QtGui import QStandardItemModel, QStandardItem
from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtWidgets import QDialog, QDialogButtonBox, QMessageBox, QTableView, QWidget
import typing

from ..providers.sf_data_source_provider import SFDataProvider
from ..helpers.utils import get_authentification_information, get_qsettings
from ..ui.sf_new_table_dialog import Ui_QgsNewVectorTableDialogBase


class SFNewTableDialog(QDialog, Ui_QgsNewVectorTableDialogBase):
    update_connections_signal = pyqtSignal()

    def __init__(
        self,
        schema_name: str,
        connection_name: str,
        parent: typing.Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setupUi(self)
        self.schema_name = schema_name
        self.connection_name = connection_name
        self.settings = get_qsettings()
        self.__load_schemas_combobox()

        self.model = QStandardItemModel()
        self.set_headers_model()

        self.__load_geo_type_column()

        self.temp_deactivated_options()
        self.mTableName.setText("new_table_name")
        self.mAddFieldBtn.clicked.connect(self.on_add_field_btn_clicked)
        self.mDeleteFieldBtn.clicked.connect(self.on_delete_field_btn_clicked)
        self.mFieldUpBtn.clicked.connect(self.on_field_up_button_clicked)
        self.mFieldDownBtn.clicked.connect(self.on_field_down_button_clicked)
        ok_button = self.mButtonBox.button(QDialogButtonBox.StandardButton.Ok)
        ok_button.setEnabled(False)
        ok_button.clicked.connect(self.button_box_ok_clicked)

    def button_box_ok_clicked(self):
        try:
            auth_information = get_authentification_information(
                self.settings, self.connection_name
            )
            sf_data_provider = SFDataProvider(auth_information)
            table_name = self.mTableName.text()
            schema_name = self.mSchemaCbo.currentText()
            query = f"CREATE OR REPLACE TABLE {auth_information['database']}.{schema_name}.{table_name} ("
            for row in range(self.model.rowCount()):
                field_name = self.model.item(row, 0).text()
                field_type = self.model.item(row, 1).text()
                field_comment = self.model.item(row, 2).text()
                query += f"{field_name} {field_type}"
                if field_comment != "":
                    query += f" COMMENT '{field_comment}'"
                query += ", "

            query += f"{self.mGeomColumn.text()} {self.mGeomTypeCbo.currentText()})"
            sf_data_provider.load_data(query, self.connection_name)
            self.update_connections_signal.emit()
        except Exception as e:
            QMessageBox.information(
                None,
                "New Table Add Table Btn",
                f"Adding Table failed.\n\nExtended error information:\n{str(e)}",
            )

    def on_delete_field_btn_clicked(self) -> None:
        try:
            mFieldsTableView: QTableView = self.mFieldsTableView
            selection_model = mFieldsTableView.selectionModel()
            selected_indexes = selection_model.selectedIndexes()
            for index in selected_indexes:
                self.model.removeRow(index.row())

            if self.model.rowCount() == 0:
                self.mButtonBox.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        except Exception as e:
            QMessageBox.information(
                None,
                "New Table Delete Field Btn",
                f"Deleting field failed.\n\nExtended error information:\n{str(e)}",
            )

    def on_field_up_button_clicked(self) -> None:
        mFieldsTableView: QTableView = self.mFieldsTableView
        selection_model = mFieldsTableView.selectionModel()
        selected_indexes = selection_model.selectedIndexes()

        if not selected_indexes:
            return

        row = selected_indexes[0].row()

        if row > 0:
            self.model.insertRow(row - 1, self.model.takeRow(row))
            selection_model.select(self.model.index(row - 1, 0), selection_model.SelectionFlag.Select)

    def on_field_down_button_clicked(self):
        mFieldsTableView: QTableView = self.mFieldsTableView
        selection_model = mFieldsTableView.selectionModel()
        selected_indexes = selection_model.selectedIndexes()

        if not selected_indexes:
            return

        row = selected_indexes[0].row()

        if row < self.model.rowCount() - 1:
            self.model.insertRow(row + 1, self.model.takeRow(row))
            selection_model.select(self.model.index(row + 1, 0), selection_model.SelectionFlag.Select)

    def on_add_field_btn_clicked(self) -> None:
        try:
            row_items = [
                QStandardItem("new_field_name"),
                QStandardItem("TEXT"),
                QStandardItem(""),
            ]
            self.model.appendRow(row_items)
            if self.model.rowCount() > 0:
                self.mButtonBox.button(QDialogButtonBox.StandardButton.Ok).setEnabled(True)
        except Exception as e:
            QMessageBox.information(
                None,
                "New Table Add Field Btn",
                f"Adding new field failed.\n\nExtended error information:\n{str(e)}",
            )

    def __load_geo_type_column(self) -> None:
        self.mGeomTypeCbo.clear()
        self.mGeomTypeCbo.addItem("GEOGRAPHY")
        self.mGeomTypeCbo.addItem("GEOMETRY")

    def __load_schemas_combobox(self) -> None:
        auth_information = get_authentification_information(
            self.settings, self.connection_name
        )
        query = f"""
                    SELECT DISTINCT TABLE_SCHEMA
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE table_catalog ILIKE '{auth_information["database"]}'
                    ORDER BY TABLE_SCHEMA
                """

        sf_data_provider = SFDataProvider(auth_information)

        sf_data_provider.load_data(query, self.connection_name)
        feature_iterator = sf_data_provider.get_feature_iterator()

        self.mSchemaCbo.clear()
        for feat in feature_iterator:
            self.mSchemaCbo.addItem(feat.attribute("TABLE_SCHEMA"))
        feature_iterator.close()

    def temp_deactivated_options(self) -> None:
        self.mDimensionsLabel.setVisible(False)
        self.mHasZChk.setVisible(False)
        self.mHasMChk.setVisible(False)
        self.mCrsLabel.setVisible(False)
        self.mSpatialIndexLabel.setVisible(False)
        self.mSpatialIndexChk.setVisible(False)
        self.mValidationResults.setVisible(False)
        self.mWarningIcon.setVisible(False)
        self.mValidationFrame.setVisible(False)
        self.mCrs.setVisible(False)

    def set_headers_model(self) -> None:
        self.model.setHorizontalHeaderLabels(
            [
                "Name",
                "Type",
                "Comment",
            ]
        )

        self.mFieldsTableView.setModel(self.model)
