from qgis.PyQt import QtWidgets

# from PyQt5 import QWidget
from qgis.PyQt.QtWidgets import QMessageBox


def get_proceed_cancel_message_box(title: str, text: str) -> int:
    message_box = QtWidgets.QMessageBox()

    message_box.setWindowTitle(title)
    message_box.setText(text)

    proceed_button = message_box.addButton("Proceed", QtWidgets.QMessageBox.AcceptRole)
    cancel_button = message_box.addButton("Cancel", QtWidgets.QMessageBox.RejectRole)

    message_box.exec_()

    if message_box.clickedButton() == proceed_button:
        return QtWidgets.QMessageBox.Ok
    elif message_box.clickedButton() == cancel_button:
        return QtWidgets.QMessageBox.Cancel


def create_reporting_error_message_box_for_query(
    parent: QtWidgets.QWidget, title: str, error_message: str, query_uuid: str
) -> None:
    link = "https://github.com/snowflakedb/qgis-snowflake-plugin/issues"
    message = f"Please report this issue to the <a href='{link}'>QGIS repo</a>."
    f" Add query id to description: {query_uuid}"
    f"<br>{error_message}"
    QMessageBox.critical(parent, title, message, QMessageBox.Ok)
