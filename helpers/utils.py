from datetime import datetime
import re
from typing import Dict
from qgis.PyQt.QtCore import QSettings
import os
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.core import QgsApplication, QgsAuthMethodConfig


def add_task_to_running_queue(task_name: str, status: str) -> None:
    """
    Adds a task to the running queue with the specified status.

    This function updates the QGIS settings to include a new task under the
    "running_tasks" group. The task is identified by its name and associated
    with a given status.

    Args:
        task_name (str): The name of the task to be added to the running queue.
        status (str): The status of the task to be added.

    Returns:
        None
    """
    settings = get_qsettings()
    settings.beginGroup("running_tasks")
    settings.setValue(task_name, status)
    settings.endGroup()
    settings.sync()


def get_task_status(task_name: str) -> str:
    """
    Retrieve the status of a specified task from QGIS settings.

    Args:
        task_name (str): The name of the task whose status is to be retrieved.

    Returns:
        str: The status of the task. If the task does not exist, returns "does not exist".
    """
    settings = get_qsettings()
    settings.beginGroup("running_tasks")
    task_status = settings.value(task_name, defaultValue="does not exist")
    settings.endGroup()
    return task_status


def remove_task_from_running_queue(task_name: str) -> None:
    """
    Removes a task from the running queue in QGIS settings.

    This function accesses the QGIS settings, navigates to the "running_tasks" group,
    and removes the specified task by its name. After making the changes, it ensures
    the settings are synchronized.

    Args:
        task_name (str): The name of the task to be removed from the running queue.

    Returns:
        None
    """
    settings = get_qsettings()
    settings.beginGroup("running_tasks")
    settings.remove(task_name)
    settings.endGroup()
    settings.sync()


def task_is_running(task_name: str) -> bool:
    """
    Check if a task with the given name is currently running.

    Args:
        task_name (str): The name of the task to check.

    Returns:
        bool: True if the task is running, False otherwise.
    """
    if get_task_status(task_name) == "does not exist":
        return False
    return True


def get_authentification_information(settings: QSettings, connection_name: str) -> dict:
    """
    Retrieves authentication information from the given settings for the specified connection name.

    Parameters:
    - settings (QSettings): The QSettings object containing the authentication settings.
    - connection_name (str): The name of the connection for which to retrieve the authentication information.

    Returns:
    - dict: A dictionary containing the authentication information with the following keys:
        - "warehouse" (str): The name of the warehouse.
        - "account" (str): The name of the Snowflake account.
        - "database" (str): The name of the Snowflake database.
        - "username" (str): The username for the Snowflake connection.
        - "connection_type" (str): The type of the Snowflake connection.
        - "password" (str): The password for the Snowflake connection.
    """
    auth_info = {}
    settings.beginGroup(f"connections/{connection_name}")
    auth_info["warehouse"] = settings.value("warehouse", defaultValue="")
    auth_info["account"] = settings.value("account", defaultValue="")
    auth_info["database"] = settings.value("database", defaultValue="")
    auth_info["username"] = settings.value("username", defaultValue="")
    auth_info["connection_type"] = settings.value("connection_type", defaultValue="")
    auth_info["password"] = settings.value("password", defaultValue="")
    auth_info["config_id"] = settings.value("config_id", defaultValue="")
    auth_info["password_encrypted"] = settings.value(
        "password_encrypted", defaultValue=False
    )

    if type(auth_info["password_encrypted"]) is str:
        if auth_info["password_encrypted"].lower() == "true":
            auth_info["password_encrypted"] = True
        else:
            auth_info["password_encrypted"] = False

    if auth_info["password_encrypted"]:
        encrypted_credentials = get_encrypted_credentials(
            settings.value("config_id", defaultValue="")
        )
        auth_info["username"] = encrypted_credentials["username"]
        auth_info["password"] = encrypted_credentials["password"]
    role = settings.value("role", defaultValue="")
    if role != "":
        auth_info["role"] = role
    settings.endGroup()

    return auth_info


def get_qsettings() -> QSettings:
    """
    Returns a QSettings object for the Snowflake QGIS plugin.

    Returns:
        QSettings: The QSettings object for the Snowflake QGIS plugin.
    """
    return QSettings(
        QSettings.IniFormat, QSettings.UserScope, "Snowflake", "SF_QGIS_PLUGIN"
    )


def write_to_log(string_to_write: str) -> None:
    """
    Writes the given string to a log file.

    Parameters:
        string_to_write (str): The string to be written to the log file.

    Returns:
        None
    """
    now = datetime.now()
    folder_path = "~/.sf_qgis_plugin"
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
    with open(
        f"{folder_path}/log.log",
        "a",
    ) as file:
        # Write data to the file
        file.write(f"{now} => {string_to_write}\n")


def remove_connection(settings: QSettings, connection_name: str) -> None:
    """
    Remove a connection from the settings.

    Parameters:
    - settings (QSettings): The QSettings object to remove the connection from.
    - connection_name (str): The name of the connection to remove.

    Returns:
    - None
    """
    settings.beginGroup(f"connections/{connection_name}")
    settings.remove("")
    settings.endGroup()
    settings.sync()


def set_connection_settings(connection_settings: dict) -> None:
    """
    Configures and saves the connection settings for a Snowflake connection in QGIS.

    Args:
        connection_settings (dict): A dictionary containing the connection settings with the following keys:
            - name (str): The name of the connection.
            - warehouse (str): The Snowflake warehouse to use.
            - account (str): The Snowflake account identifier.
            - database (str): The Snowflake database to connect to.
            - username (str): The username for the Snowflake connection.
            - connection_type (str): The type of connection, e.g., "Default Authentication".
            - password (str, optional): The password for the Snowflake connection. Required if connection_type is "Default Authentication".

    Returns:
        None
    """
    settings = get_qsettings()
    settings.beginGroup(f"connections/{connection_settings['name']}")
    settings.setValue("warehouse", connection_settings["warehouse"])
    settings.setValue("account", connection_settings["account"])
    settings.setValue("database", connection_settings["database"])
    settings.setValue("username", connection_settings["username"])
    settings.setValue("connection_type", connection_settings["connection_type"])
    if "role" in connection_settings:
        settings.setValue("role", connection_settings["role"])
    if connection_settings["connection_type"] == "Default Authentication":
        settings.setValue("password", connection_settings["password"])
    settings.setValue("password_encrypted", connection_settings["password_encrypted"])
    if "config_id" in connection_settings:
        settings.setValue("config_id", connection_settings["config_id"])
    settings.endGroup()
    settings.sync()


def on_handle_error(title: str, message: str) -> None:
    """
    Displays a critical error message box with the given title and message.

    Args:
        title (str): The title of the error message box.
        message (str): The content of the error message.

    Returns:
        None
    """
    QMessageBox.critical(None, title, message, QMessageBox.Ok)


def on_handle_warning(title: str, message: str) -> None:
    """
    Displays a warning message box with the given title and message.

    Args:
        title (str): The title of the warning message box.
        message (str): The warning message to be displayed.

    Returns:
        None
    """
    QMessageBox.warning(None, title, message, QMessageBox.Ok)


def check_package_installed(package_name) -> bool:
    """
    Checks if a given package is installed in the current Python environment.

    Args:
        package_name (str): The name of the package to check.

    Returns:
        bool: True if the package is installed, False otherwise.
    """
    import pkg_resources

    # Iterate over all installed distributions
    for package in pkg_resources.working_set:
        if package.key == package_name:
            return True
    return False


def check_install_package(package_name) -> None:
    """
    Checks if a given package is installed, and if not, installs it along with the 'pyopenssl' package.

    This function determines the appropriate Python executable path based on the operating system and uses it to run pip commands for installing the required packages.

    Raises:
        subprocess.CalledProcessError: If the pip installation commands fail.
    """
    if not check_package_installed(package_name):
        import subprocess
        import platform
        import sys
        import os

        if platform.system() == "Windows":
            prefixPath = sys.exec_prefix
            python3_path = os.path.join(prefixPath, "python3")
        else:
            prefixPath = sys.exec_prefix
            python3_path = os.path.join(prefixPath, "bin", "python3")
        subprocess.call([python3_path, "-m", "pip", "install", "pip", "—upgrade"])
        subprocess.call(
            [
                python3_path,
                "-m",
                "pip",
                "install",
                package_name,
            ]
        )
        subprocess.call(
            [python3_path, "-m", "pip", "install", "pyopenssl", "--upgrade"]
        )


def check_install_snowflake_connector_package() -> None:
    """
    Checks if the 'snowflake-connector-python' package is installed, and if not, installs it along with the 'pyopenssl' package.

    This function determines the appropriate Python executable path based on the operating system and uses it to run pip commands for installing the required packages.

    Raises:
        subprocess.CalledProcessError: If the pip installation commands fail.
    """
    check_install_package("snowflake-connector-python")


def check_install_h3_package() -> None:
    """
    Checks if the 'h3' package is installed, and if not, installs it along with the 'pyopenssl' package.

    This function determines the appropriate Python executable path based on the operating system and uses it to run pip commands for installing the required packages.

    Raises:
        subprocess.CalledProcessError: If the pip installation commands fail.
    """
    check_install_package("h3")


def uninstall_snowflake_connector_package() -> None:
    """
    Uninstalls the Snowflake Connector for Python package.

    This function determines the appropriate Python executable path based on the
    operating system and uses it to run the pip uninstall command for the
    'snowflake-connector-python[secure-local-storage]' package.

    It supports both Windows and non-Windows platforms.

    Raises:
        subprocess.CalledProcessError: If the uninstallation process fails.
    """
    import subprocess
    import platform
    import sys

    if platform.system() == "Windows":
        prefixPath = sys.exec_prefix
        python3_path = os.path.join(prefixPath, "python3")
    else:
        prefixPath = sys.exec_prefix
        python3_path = os.path.join(prefixPath, "bin", "python3")
    subprocess.call(
        [
            python3_path,
            "-m",
            "pip",
            "uninstall",
            "snowflake-connector-python[secure-local-storage]",
            "-y",
        ]
    )


def get_auth_information(connection_name: str) -> dict:
    """
    Retrieves authentication information for a given connection name from QGIS settings.

    Args:
        connection_name (str): The name of the connection for which to retrieve authentication information.

    Returns:
        dict: A dictionary containing the authentication information with the following keys:
            - "warehouse": The warehouse name.
            - "account": The account name.
            - "database": The database name.
            - "username": The username.
            - "connection_type": The type of connection.
            - "password": The password.
    """
    settings = get_qsettings()
    auth_info = {}
    settings.beginGroup(f"connections/{connection_name}")
    auth_info["warehouse"] = settings.value("warehouse", defaultValue="")
    auth_info["account"] = settings.value("account", defaultValue="")
    auth_info["database"] = settings.value("database", defaultValue="")
    auth_info["username"] = settings.value("username", defaultValue="")
    auth_info["connection_type"] = settings.value("connection_type", defaultValue="")
    auth_info["password_encrypted"] = settings.value(
        "password_encrypted", defaultValue=False
    )

    if type(auth_info["password_encrypted"]) is str:
        if auth_info["password_encrypted"].lower() == "true":
            auth_info["password_encrypted"] = True
        else:
            auth_info["password_encrypted"] = False

    auth_info["password"] = settings.value("password", defaultValue="")
    auth_info["config_id"] = settings.value("config_id", defaultValue="")
    if auth_info["password_encrypted"]:
        encrypted_credentials = get_encrypted_credentials(
            settings.value("config_id", defaultValue="")
        )
        auth_info["username"] = encrypted_credentials["username"]
        auth_info["password"] = encrypted_credentials["password"]
    role = settings.value("role", defaultValue="")
    if role != "":
        auth_info["role"] = role
    settings.endGroup()
    return auth_info


def get_connection_child_groups() -> list:
    """
    Retrieves the child groups under the "connections" group from QGIS settings.

    This function accesses the QGIS settings, navigates to the "connections" group,
    and retrieves all child groups within it. It then returns a list of these child
    groups.

    Returns:
        list: A list of child group names under the "connections" group.
    """
    settings = get_qsettings()
    settings.beginGroup("connections")
    root_groups = settings.childGroups()
    settings.endGroup()
    return root_groups


def decodeUri(uri: str) -> Dict[str, str]:
    """Breaks a provider data source URI into its component paths
    (e.g. file path, layer name).

    :param str uri: uri to convert
    :returns: dict of components as strings
    """
    supported_keys = [
        "connection_name",
        "sql_query",
        "schema_name",
        "table_name",
        "srid",
        "geom_column",
        "geometry_type",
        "geo_column_type",
    ]
    matches = re.findall(
        f"({'|'.join(supported_keys)})=(.*?) *?(?={'|'.join(supported_keys)}=|$)",
        uri,
        flags=re.DOTALL,
    )
    params = {key: value for key, value in matches}
    return params


def get_path_nodes(path: str):
    """
    Extracts and returns the connection name, schema name, and table name from a given path.

    Args:
        path (str): The path string to be split and parsed.

    Returns:
        tuple: A tuple containing the connection name, schema name, and table name.
               If any of these components are not present in the path, their value will be None.
    """
    path_splitted = path.split("/")
    connection_name = path_splitted[2] if len(path_splitted) > 2 else None
    schema_name = path_splitted[3] if len(path_splitted) > 3 else None
    table_name = path_splitted[4] if len(path_splitted) > 4 else None

    return connection_name, schema_name, table_name


def get_encrypted_credentials(config_id: str) -> dict[str, str]:
    """
    Retrieves encrypted credentials from QGIS authentication manager.

    Args:
        config_id (str): The ID of the authentication configuration to load.

    Returns:
        dict[str, str]: A dictionary containing the encrypted credentials.
    """
    method_config = get_auth_method_config(config_id)
    return method_config.configMap()


def get_auth_method_config(config_id: str) -> QgsAuthMethodConfig:
    """
    Retrieves authentication method configuration from QGIS authentication manager.

    Args:
        config_id (str): The ID of the authentication configuration to load.

    Returns:
        QgsAuthMethodConfig: The authentication method configuration.
    """
    auth_manager = QgsApplication.authManager()
    method_config = QgsAuthMethodConfig()
    auth_manager.loadAuthenticationConfig(config_id, method_config, True)
    return method_config
