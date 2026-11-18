from typing import Dict
from qgis.core import QgsProviderMetadata

from ..helpers.utils import decodeUri as du
from ..helpers.utils import connection_uri_token

from .sf_vector_data_provider import SFVectorDataProvider


class SFMetadataProvider(QgsProviderMetadata):
    def __init__(self, plugin_version: str = ""):
        super().__init__(
            SFVectorDataProvider.providerKey(),
            SFVectorDataProvider.description(),
            SFVectorDataProvider.createProvider,
        )
        # Version marker used to detect a stale provider left registered by a
        # previous plugin version after an in-place upgrade. QGIS registers the
        # vector provider once per process and never unregisters it, so the
        # plugin inspects this marker on startup to warn when a restart is
        # required to finish an upgrade.
        self.plugin_version = plugin_version

    def decodeUri(self, uri: str) -> Dict[str, str]:
        """Breaks a provider data source URI into its component paths
        (e.g. file path, layer name).

        :param str uri: uri to convert
        :returns: dict of components as strings
        """
        return du(uri)

    def encodeUri(self, parts: Dict[str, str]) -> str:
        """Reassembles a provider data source URI from its component paths
        (e.g. file path, layer name).

        Keys match ``decodeUri`` / ``helpers.utils.decodeUri``.
        """
        connection_name = parts.get("connection_name", "")
        sql_query = parts.get("sql_query", "")
        schema_name = parts.get("schema_name", "")
        table_name = parts.get("table_name", "")
        srid = parts.get("srid", "")
        geom_column = parts.get("geom_column", "")
        geometry_type = parts.get("geometry_type", "")
        geo_column_type = parts.get("geo_column_type", "")
        primary_key = parts.get("primary_key", "")
        uri = (
            f"{connection_uri_token(connection_name)} sql_query={sql_query} "
            f"schema_name={schema_name} table_name={table_name} srid={srid} "
            f"geom_column={geom_column} geometry_type={geometry_type} "
            f"geo_column_type={geo_column_type} primary_key={primary_key}"
        )
        if parts.get("extent_mode") in ("1", 1, True, "true", "True"):
            uri += " extent_mode=1"
        if parts.get("load_all_rows") in ("1", 1, True, "true", "True"):
            uri += " load_all_rows=1"
        if parts.get("single_geom_layer") in ("1", 1, True, "true", "True"):
            uri += " single_geom_layer=1"
        return uri
