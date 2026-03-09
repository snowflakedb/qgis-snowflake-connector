import typing
from ..entities.sf_feature_iterator import SFFeatureIterator
from ..managers.sf_connection_manager import SFConnectionManager
from PyQt5.QtCore import QVariant
from qgis.core import (
    QgsDataProvider,
    QgsField,
    QgsFields,
)
import snowflake.connector


class SFDataProvider(QgsDataProvider):
    TYPE_CODE_DICT = {
        0: {"name": "FIXED", "qvariant_type": QVariant.Double},  # NUMBER/INT
        1: {"name": "REAL", "qvariant_type": QVariant.Double},  # REAL
        2: {"name": "TEXT", "qvariant_type": QVariant.String},  # VARCHAR/STRING
        3: {"name": "DATE", "qvariant_type": QVariant.Date},  # DATE
        4: {"name": "TIMESTAMP", "qvariant_type": QVariant.DateTime},  # TIMESTAMP
        5: {"name": "VARIANT", "qvariant_type": QVariant.String},  # VARIANT
        6: {
            "name": "TIMESTAMP_LTZ",
            "qvariant_type": QVariant.DateTime,
        },  # TIMESTAMP_LTZ
        7: {"name": "TIMESTAMP_TZ", "qvariant_type": QVariant.DateTime},  # TIMESTAMP_TZ
        8: {
            "name": "TIMESTAMP_NTZ",
            "qvariant_type": QVariant.DateTime,
        },  # TIMESTAMP_NTZ
        9: {"name": "OBJECT", "qvariant_type": QVariant.String},  # OBJECT
        10: {"name": "ARRAY", "qvariant_type": QVariant.String},  # ARRAY
        11: {"name": "BINARY", "qvariant_type": QVariant.BitArray},  # BINARY
        12: {"name": "TIME", "qvariant_type": QVariant.Time},  # TIME
        13: {"name": "BOOLEAN", "qvariant_type": QVariant.Bool},  # BOOLEAN
        14: {"name": "GEOGRAPHY", "qvariant_type": QVariant.String},  # GEOGRAPHY
        15: {"name": "GEOMETRY", "qvariant_type": QVariant.String},  # GEOMETRY
        16: {"name": "VECTOR", "qvariant_type": QVariant.Vector2D},  # VECTOR
    }

    def __init__(self, connection_params: dict) -> None:
        """
        Initializes the SFDataSourceProvider object.

        Args:
            connection_params (dict): A dictionary containing the connection parameters.

        Returns:
            None
        """
        super().__init__()
        self.connection_params = connection_params
        self.connection_manager: SFConnectionManager = (
            SFConnectionManager.get_instance()
        )

    def get_field_type_from_code_type(self, code_type: int) -> QVariant.Type:
        """
        Returns the QVariant.Type corresponding to the given code_type.

        Parameters:
            code_type (int): The code_type to get the QVariant.Type for.

        Returns:
            QVariant.Type: The QVariant.Type corresponding to the given code_type. If the code_type is not found in the TYPE_CODE_DICT, QVariant.String is returned.
        """
        if code_type in self.TYPE_CODE_DICT:
            return self.TYPE_CODE_DICT[code_type]["qvariant_type"]
        else:
            return QVariant.String

    def execute_query(
        self,
        query: str,
        connection_name: str,
        context_information: typing.Dict[str, typing.Union[str, None]] = None,
    ) -> snowflake.connector.cursor.SnowflakeCursor:
        """
        Executes the given query on the specified connection.

        Args:
            query (str): The query to execute.
            connection_name (str): The name of the connection.

        Raises:
            Exception: If there is an error executing the query.
        """
        return self.connection_manager.execute_query(
            connection_name=connection_name,
            query=query,
            context_information=context_information,
        )

    snowflake_type_codes = {
        0: QVariant.Int,  # BIGINT_COL, DECIMAL_COL, ID, INT_COL, NUM_COL, SMALLINT_COL, TINYINT_COL
        1: QVariant.Double,  # DOUBLE_COL, REAL_COL
        2: QVariant.String,  # CHAR_COL, STR_COL, TEXT_COL
        3: QVariant.Date,  # DATE_COL
        4: QVariant.String,  #
        5: QVariant.String,  # VARIANT_COL
        6: QVariant.DateTime,  # TIMESTAMP_LTZ_COL
        7: QVariant.DateTime,  # TIMESTAMP_TZ_COL
        8: QVariant.DateTime,  # TIMESTAMP_NTZ_COL
        9: QVariant.String,  # OBJECT_COL
        10: QVariant.String,  # ARRAY
        11: QVariant.String,  # BINARY_COL, GEOGRAPHY_COL
        12: QVariant.Time,  # TIME_COL
        13: QVariant.Bool,  # BOOL_COL
        14: QVariant.String,
    }

    def load_data(
        self,
        query: str,
        connection_name: str,
        force_refresh: bool = False,
        context_information: typing.Dict[str, typing.Union[str, None]] = None,
    ) -> None:
        """
        Loads data from a Snowflake database based on the given query and connection name.

        Args:
            query (str): The SQL query to execute.
            connection_name (str): The name of the Snowflake connection.

        Raises:
            Exception: If there is an error during the data loading process.
        """
        try:
            if (
                force_refresh
                or self.connection_manager.get_connection(connection_name) is None
            ):
                self.connection_manager.connect(connection_name, self.connection_params)
            cursor: snowflake.connector.cursor.SnowflakeCursor = (
                self.connection_manager.execute_query(
                    connection_name=connection_name,
                    query=query,
                    context_information=context_information,
                )
            )

            # Create QgsFields based on Snowflake schema
            fields = QgsFields()
            c_description = cursor.description
            for col in c_description:
                code_type = col[1]
                type = self.snowflake_type_codes.get(code_type, QVariant.String)
                subType = type
                if type == QVariant.Int:
                    if col[5] > 0:
                        type = QVariant.Double
                if type in [QVariant.DateTime, QVariant.Date, QVariant.Time]:
                    type = QVariant.String
                qgsField = QgsField(col[0], type, str(type))
                qgsField.setSubType(subType)
                fields.append(qgsField)

            # Create a QgsFeatureSource
            self.feature_source = SFFeatureIterator(cursor, fields)
        except Exception as e:
            raise e

    def get_feature_iterator(self) -> SFFeatureIterator:
        """
        Returns an iterator for retrieving features from the data source.

        Returns:
            SFFeatureIterator: An iterator object that allows iterating over the features in the data source.
        """
        return self.feature_source

    def name(self) -> str:
        """Return the name of the provider."""
        return "Snowflake Data Provider"
