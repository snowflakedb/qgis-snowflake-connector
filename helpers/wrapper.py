from typing import Optional, Union
from qgis.core import QgsProviderRegistry


def parse_uri(
    uri: str,
) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    snowflakedbProviderMetadata = QgsProviderRegistry.instance().providerMetadata(
        "snowflakedb"
    )
    parsed_uri = snowflakedbProviderMetadata.decodeUri(uri)

    connection_name = parsed_uri.get("connection_name")
    sql_query = parsed_uri.get("sql_query", None)
    schema_name = parsed_uri.get("schema_name", None)
    table_name = parsed_uri.get("table_name", None)
    srid = parsed_uri.get("srid", None)
    geom_column = parsed_uri.get("geom_column", None)
    geometry_type = parsed_uri.get("geometry_type", None)
    geo_column_type = parsed_uri.get("geo_column_type", None)
    primary_key = parsed_uri.get("primary_key", "")

    # check parsing results
    if not connection_name:
        raise ValueError(
            "Invalid URI. Expected something like: "
            'connection_name="connection_name" sql="sql_query" '
            'schema_name="schema_name" table_name="table_name" srid="srid". '
            "Received: {}".format(uri)
        )

    return (
        connection_name,
        sql_query,
        schema_name,
        table_name,
        srid,
        geom_column,
        geometry_type,
        geo_column_type,
        primary_key,
    )
