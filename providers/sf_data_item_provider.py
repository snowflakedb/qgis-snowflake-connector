import os

from qgis.core import QgsDataItem, QgsDataItemProvider, Qgis
from ..helpers.utils import get_qsettings

_IMAGES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ui", "images")


class SFDataItemProvider(QgsDataItemProvider):
    def __init__(self, provider_key: str, name: str) -> None:
        """
        Initialize the SFDataItemProvider class.

        Args:
            provider_key (str): The provider key.
            name (str): The name.

        Returns:
            None
        """
        super().__init__()
        self._dataProviderKey = provider_key
        self._name = name
        self.settings = get_qsettings()

    def createDataItem(self, path: str, parentItem: QgsDataItem) -> QgsDataItem:
        """
        Creates a QgsDataItem object.

        Args:
            path (str): The path of the data item.
            parentItem (QgsDataItem): The parent item of the data item.

        Returns:
            QgsDataItem: The created QgsDataItem object.
        """
        try:
            if path == "":
                from ..entities.sf_data_item import SFDataItem

                root_data_item = SFDataItem(
                    type=Qgis.BrowserItemType.Field,
                    parent=parentItem,
                    name=self._name,
                    path="/Snowflake",
                    provider_key=self._dataProviderKey,
                    item_type="root",
                    icon_path=os.path.join(_IMAGES_DIR, "qgis_sf.png"),
                    clean_name=self._name,
                )
                return root_data_item
        except Exception as e:
            print(f"SFDataItemProvider - Failed creating data item: {str(e)}")

    def capabilities(self) -> int:
        """
        Returns the capabilities of the data item provider.

        :return: An integer representing the capabilities of the data item provider.
        """

        from qgis.core import QgsDataProvider

        return (
            QgsDataProvider.DataCapability.File
            | QgsDataProvider.DataCapability.Dir
            | QgsDataProvider.DataCapability.Database
        )

    def name(self) -> str:
        """
        Returns the name of the data item provider.

        :return: The name of the data item provider.
        :rtype: str
        """
        return self._name

    def dataProviderKey(self) -> str:
        """
        Returns the data provider key.

        :return: The data provider key.
        :rtype: str
        """
        return self._dataProviderKey
