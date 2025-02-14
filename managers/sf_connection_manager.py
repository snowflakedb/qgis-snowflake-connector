from typing import Dict
import typing
import snowflake.connector

from ..helpers.utils import get_auth_information


class SFConnectionManager:
    _instance = None

    def __new__(cls):
        """
        Create a new instance of the SFConnectionManager class if it doesn't already exist.

        Returns:
            SFConnectionManager: The instance of the SFConnectionManager class.
        """
        if cls._instance is None:
            cls._instance = super(SFConnectionManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        """
        Initializes the SFConnectionManager object.
        """
        self.opened_connections: Dict[str, snowflake.connector.SnowflakeConnection] = {}

    def create_snowflake_connection(
        self, conn_params: dict
    ) -> snowflake.connector.SnowflakeConnection:
        try:
            return snowflake.connector.connect(**conn_params)
        except Exception as e:
            raise e

    def connect(self, connection_name: str, connection_params: dict) -> None:
        """
        Connects to a Snowflake database using the provided connection parameters.

        Args:
            connection_name (str): The name of the connection.
            connection_params (dict): A dictionary containing the connection parameters.

        Raises:
            Exception: If there is an error connecting to the Snowflake database.

        Returns:
            None
        """
        try:
            if connection_name in self.opened_connections:
                self.opened_connections[connection_name].close()
                self.opened_connections[connection_name] = None

            conn_params = {
                "user": connection_params["username"],
                "account": connection_params["account"],
                "warehouse": connection_params["warehouse"],
                "database": connection_params["database"],
                "application": "OSGeo_QGIS",
                "login_timeout": 5,
                "client_session_keep_alive": True,
                "session_parameters": {
                    "QUERY_TAG": "qgis-snowflake-connector",
                },
            }

            if "long_timeout" in connection_params:
                conn_params["login_timeout"] = connection_params["long_timeout"]

            if connection_params["connection_type"] == "Default Authentication":
                conn_params["account"] = connection_params["account"]
                conn_params["password"] = connection_params["password"]
            elif connection_params["connection_type"] == "Single sign-on (SSO)":
                conn_params["authenticator"] = "externalbrowser"
            if "role" in connection_params:
                conn_params["role"] = connection_params["role"]

            self.opened_connections[connection_name] = self.create_snowflake_connection(
                conn_params
            )
        except Exception as e:
            if connection_name in self.opened_connections:
                del self.opened_connections[connection_name]
            raise e

    def get_connection(
        self, connection_name: str
    ) -> snowflake.connector.SnowflakeConnection:
        """
        Retrieves a Snowflake connection based on the given connection name.

        Parameters:
            connection_name (str): The name of the connection.

        Returns:
            snowflake.connector.SnowflakeConnection: The Snowflake connection object if found, otherwise None.
        """
        if connection_name in self.opened_connections:
            return self.opened_connections[connection_name]
        return None

    def close_connection(self, connection_name: str) -> None:
        """
        Closes the connection with the specified name.

        Parameters:
        - connection_name (str): The name of the connection to be closed.

        Raises:
        - Exception: If an error occurs while closing the connection.

        Returns:
        - None
        """
        try:
            if connection_name in self.opened_connections:
                connection = self.opened_connections[connection_name]
                connection.close()
                del connection
        except Exception as e:
            raise e

    def create_cursor(
        self, connection_name: str
    ) -> snowflake.connector.cursor.SnowflakeCursor:
        """
        Creates a cursor for the specified connection.

        Args:
            connection_name (str): The name of the connection.

        Returns:
            snowflake.connector.cursor.SnowflakeCursor: The created cursor.

        Raises:
            Exception: If an error occurs while creating the cursor.
        """
        try:
            connection = None
            if connection_name in self.opened_connections:
                connection = self.opened_connections[connection_name]
            if connection is None or connection.expired:
                self.reconnect(connection_name)
                connection = self.opened_connections[connection_name]
            return connection.cursor()
        except Exception as e:
            raise e

    def execute_query(
        self,
        connection_name: str,
        query: str,
        context_information: Dict[str, typing.Union[str, None]] = None,
    ) -> snowflake.connector.cursor.SnowflakeCursor:
        """
        Executes the given query on the specified connection.

        Args:
            connection_name (str): The name of the connection to use.
            query (str): The SQL query to execute.

        Returns:
            snowflake.connector.cursor.SnowflakeCursor: The cursor object used to execute the query.

        Raises:
            Exception: If an error occurs while executing the query.
        """
        try:
            cursor = self.create_cursor(connection_name)
            if context_information is not None:
                if (
                    "schema_name" in context_information
                    and context_information["schema_name"] is not None
                ):
                    cursor.execute(f'USE SCHEMA "{context_information["schema_name"]}"')
            cursor.execute(query)
            return cursor
        except Exception as e:
            raise e

    def reconnect(self, connection_name: str) -> None:
        """
        Reconnects to the specified Snowflake connection.

        This method iterates through the list of opened connections and attempts to
        reconnect to the connection specified by the connection_name parameter.

        Args:
            connection_name (str): The name of the connection to reconnect to.

        Returns:
            None
        """
        auth_information = get_auth_information(connection_name)
        self.connect(connection_name, auth_information)

    @staticmethod
    def get_instance() -> "SFConnectionManager":
        """
        Returns the instance of the SFConnectionManager class.

        If the instance does not exist, it creates a new instance and returns it.

        Returns:
            SFConnectionManager: The instance of the SFConnectionManager class.
        """
        if SFConnectionManager._instance is None:
            SFConnectionManager._instance = SFConnectionManager()
        return SFConnectionManager._instance
