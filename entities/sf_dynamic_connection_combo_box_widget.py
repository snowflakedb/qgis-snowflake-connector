import json
from qgis.PyQt.QtWidgets import (
    QVBoxLayout,
    QLabel,
    QComboBox,
    QSizePolicy,
    QWidget,
    QMessageBox,
)
from qgis.core import QgsProcessingFeatureSourceDefinition, QgsProject
from ..helpers.data_base import get_schema_iterator, get_table_iterator
from ..helpers.wrapper import parse_uri

from ..helpers.utils import (
    get_authentification_information,
    get_connection_child_groups,
    get_qsettings,
)
from processing.gui.wrappers import WidgetWrapper


class DynamicConnectionComboBoxWidget(WidgetWrapper):
    def createWidget(self):
        self._input_wrapper = None
        self._prefilled = False

        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.connections_cb = QComboBox()
        self.schemas_cb = QComboBox()
        self.tables_cb = QComboBox()
        self.tables_cb.setEditable(True)

        # Keep combos shrinkable so the dropdown arrow stays visible when
        # items are wider than the processing panel column.
        for combo in (self.connections_cb, self.schemas_cb, self.tables_cb):
            combo.setSizeAdjustPolicy(
                QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
            )
            combo.setMinimumContentsLength(0)
            combo.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
            )
        self.tables_cb.lineEdit().setMinimumWidth(0)

        # Populate the comboboxes with your desired items
        self.settings = get_qsettings()
        self.connections_cb.addItems(self.get_connections_cb_options())
        self.connections_cb.currentIndexChanged.connect(self.update_schemas_cb)
        self.schemas_cb.currentIndexChanged.connect(self.update_tables_cb)

        layout.addWidget(self.connections_cb)
        self.schemas_lb = QLabel("Schema (schema name)")
        layout.addWidget(self.schemas_lb)
        layout.addWidget(self.schemas_cb)
        self.tables_lb = QLabel("Table to export to (leave blank to use layer name)")
        layout.addWidget(self.tables_lb)
        layout.addWidget(self.tables_cb)
        widget.setLayout(layout)

        return widget

    def get_connections_cb_options(self):
        connections_cb_options = []
        root_groups = get_connection_child_groups()
        for group in root_groups:
            connections_cb_options.append(group)
        connections_cb_options.insert(0, "")
        return connections_cb_options

    def update_tables_cb(self):
        try:
            selected_connection = self.connections_cb.currentText()
            selected_schema = self.schemas_cb.currentText()
            self.tables_cb.clear()
            if selected_connection == "" or selected_schema == "":
                return
            feature_iterator = get_table_iterator(
                self.settings, selected_connection, selected_schema
            )
            self.tables_cb.addItem("")
            for feat in feature_iterator:
                self.tables_cb.addItem(feat.attribute("TABLE_NAME"))
            feature_iterator.close()
        except Exception as e:
            QMessageBox.information(
                None,
                "Connection Widget - Update Table Combobox",
                f"Connection Widget - Update table failed.\n\nExtended error information:\n{str(e)}",
            )

    def update_schemas_cb(self):
        try:
            selected_connection = self.connections_cb.currentText()
            self.schemas_cb.clear()
            self.tables_cb.clear()
            if selected_connection == "":
                return
            feature_iterator = get_schema_iterator(self.settings, selected_connection)
            self.schemas_cb.addItem("")
            for feat in feature_iterator:
                self.schemas_cb.addItem(feat.attribute("SCHEMA_NAME"))
            feature_iterator.close()
        except Exception as e:
            QMessageBox.information(
                None,
                "Connection Widget - Update Schema Combobox",
                f"Connection Widget - Update schema failed.\n\nExtended error information:\n{str(e)}",
            )

    def get_selected_options(self):
        auth_information = get_authentification_information(
            self.settings, self.connections_cb.currentText()
        )
        return json.dumps(
            [
                self.connections_cb.currentText(),
                auth_information["database"],
                self.schemas_cb.currentText(),
                self.tables_cb.currentText(),
            ]
        )

    def value(self):
        return self.get_selected_options()

    def postInitialize(self, wrappers):
        try:
            for wrapper in wrappers:
                name = wrapper.parameterDefinition().name()
                if name == "INPUT":
                    self._input_wrapper = wrapper
                    break
            if not self._prefilled:
                self._prefilled = True
                self._prefill_from_snowflake_layer()
        except Exception:  # nosec B110 - prefill is a UX convenience; must never prevent the dialog from opening if the layer metadata is unexpected
            pass

    def _prefill_from_snowflake_layer(self):
        layer = self._get_input_layer()
        if layer is None:
            return
        provider = layer.dataProvider()
        if provider is None or provider.name() != "snowflakedb":
            return
        try:
            (
                connection_name,
                _sql_query,
                _schema_name,
                _table_name,
                _srid,
                _geom_column,
                _geometry_type,
                _geo_column_type,
                _primary_key,
                _load_all_rows,
            ) = parse_uri(provider.dataSourceUri())
        except Exception:
            return

        if connection_name:
            self._set_combo_text(self.connections_cb, connection_name)

    def _get_input_layer(self):
        if self._input_wrapper is None:
            return None
        widget = getattr(self._input_wrapper, "widget", None)
        if widget is not None and hasattr(widget, "currentLayer"):
            layer = widget.currentLayer()
            if layer is not None:
                return layer
        try:
            val = self._input_wrapper.parameterValue()
        except Exception:
            try:
                val = self._input_wrapper.value()
            except Exception:
                return None
        if isinstance(val, QgsProcessingFeatureSourceDefinition):
            source = val.source
            val = source.staticValue() if hasattr(source, "staticValue") else source
        if isinstance(val, str) and val:
            layer = QgsProject.instance().mapLayer(val)
            if layer is not None:
                return layer
        return None

    @staticmethod
    def _set_combo_text(combo, text):
        if text is None:
            return
        index = combo.findText(text)
        if index >= 0:
            combo.setCurrentIndex(index)
        elif combo.isEditable():
            combo.setCurrentText(text)
