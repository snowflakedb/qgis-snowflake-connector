import os

from ..dialogs.sf_data_source_manager_widget import SFDataSourceManagerWidget
from qgis.core import QgsProviderRegistry
from qgis.gui import QgsAbstractDataSourceWidget, QgsSourceSelectProvider
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QWidget
import typing

_IMAGES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ui", "images")


class SFSourceSelectProvider(QgsSourceSelectProvider):
    def __init__(self, providerKey: str) -> None:
        """
        Initializes the SFSourceSelectProvider class.

        Args:
            providerKey (str): The provider key.

        Returns:
            None
        """
        super().__init__()
        self._providerKey = providerKey

    def createDataSourceWidget(
        self,
        parent: typing.Optional[QWidget] = ...,
        fl: typing.Union[Qt.WindowFlags, Qt.WindowType] = ...,
        widgetMode: QgsProviderRegistry.WidgetMode = ...,
    ) -> QgsAbstractDataSourceWidget:
        """
        Creates a data source widget for the SF source select provider.

        Args:
            parent (QWidget, optional): The parent widget. Defaults to None.
            fl (Union[Qt.WindowFlags, Qt.WindowType], optional): The window flags. Defaults to None.
            widgetMode (QgsProviderRegistry.WidgetMode, optional): The widget mode. Defaults to None.

        Returns:
            QgsAbstractDataSourceWidget: The created data source widget.
        """
        return SFDataSourceManagerWidget(parent)

    def providerKey(self) -> str:
        """
        Returns the provider key.

        :return: The provider key.
        :rtype: str
        """
        return self._providerKey

    def text(self) -> str:
        """
        Returns the text representation of the provider.

        :return: The text representation of the provider.
        :rtype: str
        """
        return "Snowflake"

    def icon(self) -> QIcon:
        """
        Returns the icon for the source select provider.

        :return: The icon for the source select provider.
        :rtype: QIcon
        """
        return QIcon(os.path.join(_IMAGES_DIR, "qgis_sf_plus.png"))
