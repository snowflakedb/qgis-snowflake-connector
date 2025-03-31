import typing

from ..enums.snowflake_metadata_type import SnowflakeMetadataType

from ..managers.sf_connection_manager import SFConnectionManager
from ..helpers.utils import get_authentification_information, get_qsettings
from qgis.PyQt.QtCore import QSettings
from qgis.core import QgsFeature
from ..providers.sf_data_source_provider import SFDataProvider
from ..entities.sf_feature_iterator import SFFeatureIterator
import snowflake.connector
from snowflake.connector.errors import ProgrammingError
from ..helpers.mappings import (
    mapping_single_to_multi_geometry_type,
    mapping_multi_single_to_geometry_type,
)


def get_schema_iterator(settings: QSettings, connection_name: str) -> SFFeatureIterator:
    """
    Retrieves an iterator over the schema names in the specified database.

    Args:
        settings (QSettings): The settings object containing configuration details.
        connection_name (str): The name of the database connection.

    Returns:
        SFFeatureIterator: An iterator over the schema names in the database.
    """
    auth_information = get_authentification_information(settings, connection_name)
    sf_data_provider = SFDataProvider(auth_information)

    query = f"""SELECT DISTINCT SCHEMA_NAME
FROM INFORMATION_SCHEMA.SCHEMATA
WHERE CATALOG_NAME = '{auth_information["database"]}'
ORDER BY SCHEMA_NAME"""

    sf_data_provider.load_data(query, connection_name)
    return sf_data_provider.get_feature_iterator()


def filter_geo_columns(
    sf_data_provider: SFDataProvider,
    connection_name: str,
    columns: typing.Iterator[QgsFeature],
) -> typing.List[QgsFeature]:
    """
    Take only the geo columns from a list. Currently, GEOMETRY and GEOGRAPHY.
    H3 is not considered as the H3_IS_VALID_CELL query is too slow.

    Args:
        sf_data_provider: The connection to the database.
        connection_name (str): The name of the connection.
        columns (List[QgsFeature]): A list of the column metadata,
            required for the query. It should include the following keys:
            - 'DATA_TYPE': The Snowflake type of the column.

    Returns:
        typing.List[QgsFeature]: The `columns` that are geo
    """
    geo_columns = []
    number_queries = []
    h3_columns = []
    for feat in columns:
        if feat.attribute("DATA_TYPE") in ["GEOMETRY", "GEOGRAPHY"]:
            geo_columns.append(feat)

        if (
            feat.attribute("DATA_TYPE") in ["NUMBER", "TEXT"]
            and feat.attribute("COMMENT")
            and "h3" in feat.attribute("COMMENT").lower()
        ):
            h3_columns.append(feat)
            table = f'"{feat.attribute("TABLE_CATALOG")}"."{feat.attribute("TABLE_SCHEMA")}"."{feat.attribute("TABLE_NAME")}"'
            column = f'{table}."{feat.attribute("COLUMN_NAME")}"'
            number_queries.append(f"""
                (SELECT H3_IS_VALID_CELL({column})
                FROM {table}
                WHERE {column} IS NOT NULL
                LIMIT 1)""")
    if len(number_queries) > 0:
        query = f"SELECT {','.join(number_queries)}"
        result = sf_data_provider.execute_query(query, connection_name).fetchall()[0]
        for i in range(len(result)):
            if result[i]:
                geo_columns.append(h3_columns[i])
    return geo_columns


def get_table_geo_columns(
    connection_name: str, table_name: str
) -> typing.List[QgsFeature]:
    """
    Retrieves a list of the geo columns of a specified table in a database.

    Args:
        connection_name (str): The name of the database connection.
        table_name (str): The name of the table to retrieve columns from.

    Returns:
        List[QgsFeature]: A list of the features (geo columns) of the specified table.

    Raises:
        Any exceptions raised by the underlying data provider or database query execution.
    """
    settings = get_qsettings()
    auth_information = get_authentification_information(settings, connection_name)
    sf_data_provider = SFDataProvider(auth_information)
    schema_selected_query = f"""SELECT DISTINCT TABLE_NAME, COLUMN_NAME, DATA_TYPE, TABLE_CATALOG, TABLE_SCHEMA, COMMENT
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_CATALOG ILIKE '{sf_data_provider.connection_params["database"]}'
AND TABLE_SCHEMA ILIKE '{table_name}'
ORDER BY TABLE_NAME, COLUMN_NAME"""

    sf_data_provider.load_data(schema_selected_query, connection_name)
    columns = sf_data_provider.get_feature_iterator()
    return filter_geo_columns(
        sf_data_provider=sf_data_provider,
        connection_name=connection_name,
        columns=columns,
    )


def get_geo_columns(
    sf_data_provider: SFDataProvider, connection_name: str
) -> typing.List[QgsFeature]:
    """
    Retrieves a list of the geo columns of a database.

    Args:
        sf_data_provider (SFDataProvider): The connection to the database.
        connection_name (str): The name of the database connection.

    Returns:
        List[QgsFeature]: A list of the features (geo columns).

    Raises:
        Any exceptions raised by the underlying data provider or database query execution.
    """
    schema_selected_query = f"""SELECT DISTINCT TABLE_NAME, COLUMN_NAME, DATA_TYPE, TABLE_CATALOG, TABLE_SCHEMA, COMMENT
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_CATALOG ILIKE '{sf_data_provider.connection_params["database"]}'
AND DATA_TYPE IN ('GEOGRAPHY', 'GEOMETRY', 'NUMBER', 'TEXT')
ORDER BY TABLE_NAME, COLUMN_NAME"""

    sf_data_provider.load_data(schema_selected_query, connection_name)
    columns = sf_data_provider.get_feature_iterator()
    return filter_geo_columns(
        sf_data_provider=sf_data_provider,
        connection_name=connection_name,
        columns=columns,
    )


def get_column_iterator(
    settings: QSettings, connection_name: str, table_data_item
) -> SFFeatureIterator:
    """
    Retrieves an iterator over the columns of a specified table in a database.

    Args:
        settings (QSettings): The settings object containing configuration details.
        connection_name (str): The name of the database connection.
        table_data_item (SFDataItem): The data item representing the table whose columns are to be retrieved.

    Returns:
        SFFeatureIterator: An iterator over the features (columns) of the specified table.
    """
    auth_information = get_authentification_information(settings, connection_name)
    sf_data_provider = SFDataProvider(auth_information)

    schema_data_item = table_data_item.parent()

    query = f"""SELECT DISTINCT COLUMN_NAME, DATA_TYPE, NUMERIC_SCALE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_CATALOG = '{auth_information["database"]}'
AND TABLE_SCHEMA ILIKE '{schema_data_item.clean_name}'
AND TABLE_NAME ILIKE '{table_data_item.clean_name}'
ORDER BY COLUMN_NAME"""

    sf_data_provider.load_data(query, connection_name)
    return sf_data_provider.get_feature_iterator()


def get_table_iterator(settings: QSettings, connection_name: str, schema_name: str):
    """
    Retrieves an iterator over the table names in a specified schema within a database.

    Args:
        settings (QSettings): The settings object containing configuration details.
        connection_name (str): The name of the database connection.
        schema_name (str): The name of the schema to query for table names.

    Returns:
        Iterator: An iterator over the table names in the specified schema.
    """
    auth_information = get_authentification_information(settings, connection_name)
    sf_data_provider = SFDataProvider(auth_information)

    query = f"""SELECT DISTINCT TABLE_NAME
FROM INFORMATION_SCHEMA.TABLES
WHERE table_catalog = '{auth_information["database"]}'
AND TABLE_SCHEMA = '{schema_name}'
ORDER BY TABLE_NAME"""

    sf_data_provider.load_data(query, connection_name)
    return sf_data_provider.get_feature_iterator()


def get_features_iterator(
    auth_information: dict,
    query: str,
    connection_name: str,
    context_information: typing.Dict[str, typing.Union[str, None]] = None,
) -> SFFeatureIterator:
    """
    Retrieves an iterator for features from a Salesforce data provider.

    Args:
        auth_information (dict): A dictionary containing authentication information.
        query (str): The query string to retrieve data.
        connection_name (str): The name of the connection to use.

    Returns:
        SFFeatureIterator: An iterator for the retrieved features.
    """
    sf_data_provider = SFDataProvider(auth_information)

    sf_data_provider.load_data(
        query=query,
        connection_name=connection_name,
        context_information=context_information,
    )
    return sf_data_provider.get_feature_iterator()


def get_columns_cursor(
    auth_information: dict,
    database_name: str,
    schema: str,
    table: str,
    connection_name: str,
) -> snowflake.connector.cursor.SnowflakeCursor:
    """
    Retrieves a cursor containing the distinct column names and data types
    from a specified table in a Snowflake database.

    Args:
        auth_information (dict): Authentication information required to connect to Snowflake.
        database_name (str): The name of the database containing the table.
        schema (str): The schema within the database containing the table.
        table (str): The name of the table to retrieve column information from.
        connection_name (str): The name of the connection to use for executing the query.

    Returns:
        snowflake.connector.cursor.SnowflakeCursor: A cursor containing the results of the query.
    """
    sf_data_provider = SFDataProvider(auth_information)
    query_select_columns = f"""
        SELECT DISTINCT COLUMN_NAME, DATA_TYPE
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_CATALOG = '{database_name}'
        AND TABLE_SCHEMA ILIKE '{schema}'
        AND TABLE_NAME ILIKE '{table}'
        ORDER BY COLUMN_NAME
    """
    return sf_data_provider.execute_query(
        query=query_select_columns, connection_name=connection_name
    )


def get_cursor_description(
    auth_information: dict,
    query: str,
    connection_name: str,
    context_information: typing.Dict[str, typing.Union[str, None]] = None,
) -> list[snowflake.connector.cursor.ResultMetadata]:
    """
    Executes a query on a Snowflake database and retrieves the cursor description.

    Args:
        auth_information (dict): Authentication information required to connect to the Snowflake database.
        query (str): The SQL query to be executed.
        connection_name (str): The name of the connection to be used.

    Returns:
        list[snowflake.connector.cursor.ResultMetadata]: A list containing the metadata of the result set.
    """
    sf_data_provider = SFDataProvider(auth_information)
    cur_query = sf_data_provider.execute_query(
        query=query,
        connection_name=connection_name,
        context_information=context_information,
    )
    cur_description = cur_query.description
    cur_query.close()
    return cur_description


def __execute_query(
    settings: QSettings, connection_name: str, query: str
) -> snowflake.connector.cursor.SnowflakeCursor:
    """
    Executes a SQL query using the provided Snowflake connection settings.

    Args:
        settings (QSettings): The QSettings object containing the configuration settings.
        connection_name (str): The name of the Snowflake connection to use.
        query (str): The SQL query to be executed.

    Returns:
        snowflake.connector.cursor.SnowflakeCursor: The cursor object resulting from the executed query.
    """
    auth_information = get_authentification_information(
        settings=settings, connection_name=connection_name
    )
    sf_data_provider = SFDataProvider(auth_information)
    return sf_data_provider.execute_query(query=query, connection_name=connection_name)


def __get_cur_count(
    settings: QSettings,
    connection_name: str,
    query: str,
) -> int:
    """
    Executes a given SQL query and returns the number of rows affected.

    Args:
        settings (QSettings): The QSettings object containing database configuration.
        connection_name (str): The name of the database connection.
        query (str): The SQL query to be executed.

    Returns:
        int: The number of rows affected by the query.
    """
    cur = __execute_query(
        settings=settings, connection_name=connection_name, query=query
    )
    count = cur.rowcount
    cur.close()
    return count


def get_count_schemas(
    settings: QSettings, connection_name: str, data_base_name: str, schema_name: str
) -> int:
    """
    Retrieves the count of schemas in a specified database that match the given schema name.

    Args:
        settings (QSettings): The QSettings object containing configuration settings.
        connection_name (str): The name of the database connection.
        data_base_name (str): The name of the database to search within.
        schema_name (str): The name of the schema to search for.

    Returns:
        int: The count of schemas that match the specified schema name in the given database.
    """
    query_search_public_schema = f"""SELECT DISTINCT SCHEMA_NAME
FROM INFORMATION_SCHEMA.SCHEMATA
WHERE CATALOG_NAME ilike '{data_base_name}'
and SCHEMA_NAME ilike '{schema_name}'"""
    return __get_cur_count(settings, connection_name, query_search_public_schema)


def create_schema(settings: QSettings, connection_name: str, schema_name: str):
    """
    Creates a new schema in the specified database connection.

    Args:
        settings (QSettings): The QSettings object containing the database configuration.
        connection_name (str): The name of the database connection.
        schema_name (str): The name of the schema to be created.

    Returns:
        None
    """
    query_create_public_schema = f"""CREATE SCHEMA {schema_name}"""
    cur = __execute_query(
        settings=settings,
        connection_name=connection_name,
        query=query_create_public_schema,
    )
    cur.close()


def get_count_tables(
    connection_name: str, database_name: str, schema_name: str, table_name: str
) -> int:
    """
    Retrieves the count of tables matching the specified criteria from the database.

    Args:
        connection_name (str): The name of the database connection.
        database_name (str): The name of the database.
        schema_name (str): The name of the schema.
        table_name (str): The name of the table.

    Returns:
        int: The count of tables that match the specified criteria.
    """
    settings = get_qsettings()
    query_search_table = f"""SELECT DISTINCT TABLE_NAME
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_CATALOG ilike '{database_name}'
and TABLE_SCHEMA ilike '{schema_name}'
and TABLE_NAME ilike '{table_name}'"""

    return __get_cur_count(settings, connection_name, query_search_table)


def create_table(connection_name: str, query: str):
    settings = get_qsettings()
    cur = __execute_query(
        settings=settings,
        connection_name=connection_name,
        query=query,
    )
    cur.close()


def get_srid_from_table_geo_column(
    geo_column_name: str,
    table_name: str,
    context_information: dict,
) -> int:
    """
    Retrieves the Spatial Reference System Identifier (SRID) from a specified
    geometry column in a given table.

    Args:
        geo_column_name (str): The name of the geometry column.
        table_name (str): The name of the table containing the geometry column.
        context_information (dict): A dictionary containing context information
                                    including the connection name.

    Returns:
        int: The SRID of the specified geometry column.
    """
    connection_manager: SFConnectionManager = SFConnectionManager.get_instance()
    query_srid = (
        f'SELECT ANY_VALUE(ST_SRID("{geo_column_name}")) '
        f'FROM "{table_name}" where "{geo_column_name}" IS NOT NULL'
    )
    cur = connection_manager.execute_query(
        connection_name=context_information["connection_name"],
        query=query_srid,
        context_information=context_information,
    )
    srid = cur.fetchone()[0]
    cur.close()
    return srid


def get_type_from_table_geo_column(
    geo_column_name: str,
    table_name: str,
    context_information: dict,
) -> list:
    """
    Retrieves the distinct geographic types from a specified geographic column in a table.

    Args:
        geo_column_name (str): The name of the geographic column to query.
        table_name (str): The name of the table containing the geographic column.
        context_information (dict): A dictionary containing context information, including the connection name.

    Returns:
        list: A list of distinct geographic types found in the specified column, converted to uppercase.
    """
    return get_geo_types_from_geo_json_column(
        column=geo_column_name,
        from_clause=table_name,
        context_information=context_information,
    )


def get_geo_column_type(
    geo_column_name: str,
    context_information: dict,
) -> typing.Union[str, None]:
    """
    Retrieves the data type of a specified geographic column from the database.

    Args:
        geo_column_name (str): The name of the geographic column.
        context_information (dict): A dictionary containing context information
            required for the query. It should include the following keys:
            - 'database_name': The name of the database.
            - 'schema_name': The name of the schema.
            - 'table_name': The name of the table.
            - 'connection_name': The name of the connection.

    Returns:
        typing.Union[str, None]: The data type of the geographic column if found,
        otherwise None.
    """
    connection_manager: SFConnectionManager = SFConnectionManager.get_instance()
    query_geo_column_type = (
        f"SELECT DISTINCT DATA_TYPE "
        f"FROM INFORMATION_SCHEMA.COLUMNS "
        f"WHERE TABLE_CATALOG ILIKE '{context_information['database_name']}' "
        f"AND TABLE_SCHEMA ILIKE '{context_information['schema_name']}' "
        f"AND TABLE_NAME ILIKE '{context_information['table_name']}' "
        f"AND COLUMN_NAME ILIKE '{geo_column_name}' "
    )
    cur = connection_manager.execute_query(
        connection_name=context_information["connection_name"],
        query=query_geo_column_type,
        context_information=context_information,
    )
    result_row = cur.fetchone()
    cur.close()
    return result_row[0] if result_row else None


def limit_size_for_type(
    column_type: str,
) -> int:
    """
    The limit number of rows to be fetched from a table. Currently 50k by default, and 500k for H3 columns

    Args:
        column_type (str): The type of the column

    Returns:
        int: The size limit.
    """
    if column_type in ["NUMBER", "TEXT", "H3GEO"]:
        return 500000  # 500k
    return 50000  # 50k


def limit_size_for_table(
    context_information: dict,
) -> int:
    """
    The limit number of rows to be fetched from a table. Currently based on type

    Args:
        context_information (dict): A dictionary containing context information, including the column type.

    Returns:
        int: The size limit.
    """
    return limit_size_for_type(context_information["geom_type"])


def check_table_exceeds_size(
    context_information: dict,
) -> bool:
    """
    Checks if the number of rows in a specified table exceeds the limit.

    Args:
        context_information (dict): A dictionary containing the context information
            required to connect to the database. It should include the keys
            "table_name" and "connection_name".

    Returns:
        bool: True if the number of rows in the table exceeds the limit size, False otherwise.
    """

    limit_size = limit_size_for_table(context_information=context_information)
    return check_from_clause_exceeds_size(
        from_clause=f'"{context_information["table_name"]}"',
        context_information=context_information,
        limit_size=limit_size,
    )


def get_cursor_description_from_sql(
    query: str,
    context_information: typing.Dict[str, typing.Union[str, None]] = None,
) -> list[snowflake.connector.cursor.ResultMetadata]:
    """
    Executes a SQL query and retrieves the cursor description.

    Args:
        query (str): The SQL query to be executed.
        context_information (Dict[str, Union[str, None]], optional): A dictionary containing context information
            such as connection name. Defaults to None.

    Returns:
        list[snowflake.connector.cursor.ResultMetadata]: A list of metadata describing the columns of the result set.
    """
    connection_manager: SFConnectionManager = SFConnectionManager.get_instance()
    cur = connection_manager.execute_query(
        connection_name=context_information["connection_name"],
        query=query,
        context_information=context_information,
    )
    cur_description = cur.description
    cur.close()
    return cur_description


def get_srid_from_sql_query_geo_column(
    query: str,
    context_information: dict,
) -> int:
    connection_manager: SFConnectionManager = SFConnectionManager.get_instance()
    query_srid = (
        f'SELECT ANY_VALUE(ST_SRID("{context_information["geo_column_name"]}")) '
        f'FROM ({query}) WHERE "{context_information["geo_column_name"]}" IS NOT NULL'
    )
    cur = connection_manager.execute_query(
        connection_name=context_information["connection_name"],
        query=query_srid,
        context_information=context_information,
    )
    srid = cur.fetchone()[0]
    cur.close()
    return srid


def get_type_from_query_geo_column(
    query: str,
    context_information: dict,
) -> list:
    return get_geo_types_from_geo_json_column(
        column=context_information["geo_column_name"],
        from_clause=f"({query})",
        context_information=context_information,
    )


def get_geo_types_from_geo_json_column(
    column: str,
    from_clause: str,
    context_information: dict,
) -> list:
    """
    Retrieves distinct geometry types from a GeoJSON column in a Snowflake table.

    Args:
        column (str): The name of the column containing GeoJSON data.
        from_clause (str): The FROM clause specifying the table name or query.
        context_information (dict): A dictionary containing context information, including the connection name.

    Returns:
        list: A list of distinct geometry types.
    """
    connection_manager: SFConnectionManager = SFConnectionManager.get_instance()
    query_geo_type = (
        f'SELECT DISTINCT ST_ASGEOJSON("{column}"):type::string '
        f'FROM {from_clause} WHERE "{column}" IS NOT NULL'
    )
    cur = connection_manager.execute_query(
        connection_name=context_information["connection_name"],
        query=query_geo_type,
        context_information=context_information,
    )
    geo_type_list = cur.fetchall()
    cleaned_geo_type_list = []

    for geo_type_tuple in geo_type_list:
        geo_type: str = geo_type_tuple[0]
        if geo_type.lower().startswith("multi"):
            # Checks if the single type already exists and removes it
            single_type = mapping_multi_single_to_geometry_type.get(geo_type)
            if single_type and single_type in cleaned_geo_type_list:
                cleaned_geo_type_list.remove(single_type)
        else:
            # Checks if the multi type already exists
            multi_type = mapping_single_to_multi_geometry_type.get(geo_type)
            if multi_type and multi_type in cleaned_geo_type_list:
                continue
        cleaned_geo_type_list.append(geo_type)
    cur.close()
    return cleaned_geo_type_list


def get_geo_column_type_from_query(
    query: str,
    context_information: dict,
) -> typing.Union[str, None]:
    connection_manager: SFConnectionManager = SFConnectionManager.get_instance()
    cur = connection_manager.execute_query(
        connection_name=context_information["connection_name"],
        query=query,
        context_information=context_information,
    )

    for col in cur.description:
        col_name = col[0]
        col_type = col[1]
        if col_name == context_information["geo_column_name"]:
            if col_type == 14:
                return "GEOGRAPHY"
            elif col_type == 15:
                return "GEOMETRY"
            return None
    cur.close()

    return None


def check_from_clause_exceeds_size(
    from_clause: str,
    context_information: dict,
    limit_size: int = 50000,
) -> bool:
    """
    Checks if the number of rows in the specified FROM clause exceeds the given limit size.

    Args:
        from_clause (str): The FROM clause to be checked.
        context_information (dict): A dictionary containing context information, including the connection and schema name.
        limit_size (int, optional): The maximum allowed number of rows. Defaults to 50000.

    Returns:
        bool: True if the number of rows exceeds the limit size, False otherwise.
    """
    connection_manager: SFConnectionManager = SFConnectionManager.get_instance()
    query = f"SELECT count(*) FROM {from_clause}"
    cur = connection_manager.execute_query(
        connection_name=context_information["connection_name"],
        query=query,
        context_information=context_information,
    )

    count_tuple = cur.fetchone()
    cur.close()

    if count_tuple[0] > limit_size:
        return True
    return False


def checks_sql_query_exceeds_size(
    context_information: dict,
    limit_size: int = 50000,
) -> bool:
    """
    Checks if the SQL query exceeds the specified size limit.

    Args:
        context_information (dict): A dictionary containing context information, including the SQL query.
        limit_size (int, optional): The size limit to check against. Defaults to 50000.

    Returns:
        bool: True if the SQL query exceeds the specified size limit, False otherwise.
    """
    return check_from_clause_exceeds_size(
        from_clause=f"({context_information['sql_query']})",
        context_information=context_information,
        limit_size=limit_size,
    )


def get_limit_sql_query(
    query: str,
    context_information: dict,
    limit: int = 50000,
) -> typing.Tuple[typing.List[snowflake.connector.cursor.ResultMetadata], list, list]:
    """
    Executes a SQL query with a specified limit on the number of rows returned.

    Args:
        query (str): The SQL query to be executed.
        context_information (dict): A dictionary containing context information, including the connection name.
        limit (int, optional): The maximum number of rows to return. Defaults to 50000.

    Returns:
        typing.Tuple[typing.List[snowflake.connector.cursor.ResultMetadata], list, list]:
            A tuple containing:
            - A list of column descriptions (metadata) from the query result.
            - A list of rows from the query result.
            - A list of H3 columns derived from the query.
    """
    connection_manager: SFConnectionManager = SFConnectionManager.get_instance()
    cur_desc = connection_manager.execute_query(
        connection_name=context_information["connection_name"],
        query=query,
        context_information=context_information,
    )
    cur_description = cur_desc.description
    cur_desc.close()

    query_columns = ""
    h3_query_any_value_columns = []
    for desc in cur_description:
        col_name = desc[0].replace('"', '""')
        col_type = desc[1]
        if query_columns != "":
            query_columns += ", "

        h3_query_any_value_column_value = {
            "column_value": "FALSE",
            "col_alias": f'"{col_name}"',
        }
        if col_type in (
            SnowflakeMetadataType.GEOGRAPHY.value,
            SnowflakeMetadataType.GEOMETRY.value,
        ):
            query_columns += f'ST_ASWKT("{col_name}") AS "{col_name}"'
        else:
            query_columns += f'"{col_name}"'
            if col_type in [
                SnowflakeMetadataType.FIXED.value,
                SnowflakeMetadataType.TEXT.value,
            ]:
                h3_query_any_value_column_value = {
                    "column_value": f'ANY_VALUE(H3_IS_VALID_CELL("{col_name}"))',
                    "col_alias": f'"{col_name}"',
                }
        h3_query_any_value_columns.append(h3_query_any_value_column_value)

    sub_query = f"SELECT {query_columns} FROM ({query}) LIMIT {limit}"
    cur = connection_manager.execute_query(
        connection_name=context_information["connection_name"],
        query=sub_query,
        context_information=context_information,
    )

    resultset = cur.fetchall()
    cur.close()

    return (
        cur_description,
        resultset,
        get_h3_columns_from_query(
            h3_query_any_value_columns, query, context_information
        ),
    )


def get_h3_columns_from_query(
    query_columns: typing.List[str], query: str, context_information: dict
) -> typing.List:
    """
    Executes a sub-query to retrieve specified columns from a given query and returns the result set.

    Args:
        query_columns (str): The columns to be selected in the sub-query.
        query (str): The main query from which the sub-query will be derived.
        context_information (dict): A dictionary containing context information, including the connection name.

    Returns:
        typing.List: A list containing the rows of the result set from the executed sub-query.
    """
    connection_manager: SFConnectionManager = SFConnectionManager.get_instance()
    sub_query = f"SELECT {generate_query_columns(query_columns)} FROM ({query})"
    cur = None
    try:
        cur = connection_manager.execute_query(
            connection_name=context_information["connection_name"],
            query=sub_query,
            context_information=context_information,
        )

        resultset = cur.fetchall()
        cur.close()
    except ProgrammingError as e:
        if cur:
            cur.close()
        error_code = e.errno
        error_message = e.msg
        if error_code == 100419 and error_message.startswith("100419 (P0000)"):
            # H3_IS_VALID_CELL is throwing an error because the column is not
            # H3. All columns will be treated as non-H3.
            resultset = [tuple(False for col in query_columns)]
        else:
            raise e

    return resultset


def generate_query_columns(
    columns_info: typing.List[typing.Dict[str, str]], set_value_false: bool = False
) -> str:
    """
    Generates a SQL query string for selecting columns with optional aliasing.

    Args:
        columns_info (List[Dict[str, str]]): A list of dictionaries where each dictionary contains
                                             'column_value' and 'col_alias' keys representing the
                                             column name and its alias respectively.
        set_value_false (bool, optional): If True, all column values will be replaced with 'FALSE'.
                                          Defaults to False.

    Returns:
        str: A string representing the SQL query part for selecting columns with their aliases.
    """
    col_map = list(
        map(
            lambda col: f"{'FALSE' if set_value_false else col['column_value']} AS {col['col_alias']}",
            columns_info,
        )
    )
    return ", ".join(col_map)
