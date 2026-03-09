from qgis.PyQt import QtWidgets

# from PyQt5 import QWidget
from qgis.PyQt.QtWidgets import QMessageBox


def get_proceed_cancel_message_box(title: str, text: str) -> int:
    message_box = QtWidgets.QMessageBox()

    message_box.setWindowTitle(title)
    message_box.setText(text)

    proceed_button = message_box.addButton("Proceed", QtWidgets.QMessageBox.ButtonRole.AcceptRole)
    cancel_button = message_box.addButton("Cancel", QtWidgets.QMessageBox.ButtonRole.RejectRole)

    message_box.exec()

    if message_box.clickedButton() == proceed_button:
        return QtWidgets.QMessageBox.StandardButton.Ok
    elif message_box.clickedButton() == cancel_button:
        return QtWidgets.QMessageBox.StandardButton.Cancel


def get_set_primary_key_message_box(
    title: str, text: str, combo_box_options: list[tuple[str]]
) -> tuple[int, str]:
    """
    Displays a message box prompting the user to select a primary key.

    Args:
        title (str): The title of the message box.
        text (str): The main text of the message box.
        combo_box_options (list[tuple[str]]): A list of tuples, where each tuple contains
            at least one string. The first element of each tuple is used as the display text
            in the combo box.

    Returns:
        tuple[int, str]: A tuple containing the result of the user's action
        (QMessageBox.Ok or QMessageBox.Cancel) and the selected combo box text.

    Raises:
        ValueError: If combo_box_options is not a list of tuples with at least one string element.
    """
    if not isinstance(combo_box_options, list) or not all(
        isinstance(option, tuple) and len(option) > 0 and isinstance(option[0], str)
        for option in combo_box_options
    ):
        raise ValueError(
            "combo_box_options must be a list of tuples, where each tuple contains at least one string."
        )

    message_box = QtWidgets.QMessageBox()

    message_box.setWindowTitle(title)
    message_box.setText(text)

    combo_box = QtWidgets.QComboBox()
    for option_tuple in combo_box_options:
        combo_box.addItem(option_tuple[0])

    grid_layout = message_box.layout()
    if grid_layout:
        grid_layout.addWidget(combo_box, 1, 1)

    proceed_button = message_box.addButton("Proceed", QtWidgets.QMessageBox.ButtonRole.AcceptRole)
    skip_button = message_box.addButton("Skip", QtWidgets.QMessageBox.ButtonRole.RejectRole)

    message_box.exec()

    clicked_button = None
    if message_box.clickedButton() == proceed_button:
        clicked_button = QtWidgets.QMessageBox.StandardButton.Ok
    elif message_box.clickedButton() == skip_button:
        clicked_button = QtWidgets.QMessageBox.StandardButton.Cancel

    return clicked_button, combo_box.currentText()


def create_reporting_error_message_box_for_query(
    parent: QtWidgets.QWidget, title: str, error_message: str, query_uuid: str
) -> None:
    link = "https://github.com/snowflakedb/qgis-snowflake-plugin/issues"
    message = f"Please report this issue to the <a href='{link}'>QGIS repo</a>."
    f" Add query id to description: {query_uuid}"
    f"<br>{error_message}"
    QMessageBox.critical(parent, title, message, QMessageBox.StandardButton.Ok)
