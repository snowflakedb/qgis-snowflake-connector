from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsDataProvider,
    QgsFeature,
    QgsFeatureIterator,
    QgsFeatureRequest,
    QgsField,
    QgsFields,
    QgsRectangle,
    QgsVectorDataProvider,
    QgsWkbTypes,
)
from qgis.PyQt.QtCore import QMetaType

from .sf_feature_iterator import SFFeatureIterator

from ..helpers.data_base import check_from_clause_exceeds_size, limit_size_for_type

from .sf_feature_source import SFFeatureSource

from ..helpers.utils import get_authentification_information, get_qsettings
from ..managers.sf_connection_manager import SFConnectionManager

from ..helpers.wrapper import parse_uri
from ..helpers.mappings import (
    SNOWFLAKE_METADATA_TYPE_CODE_DICT,
    mapping_snowflake_qgis_geometry,
    mapping_snowflake_qgis_type,
)


class SFVectorDataProvider(QgsVectorDataProvider):
    """The general VectorDataProvider, which can be extended based on column type"""

    def __init__(
        self,
        uri="",
        providerOptions=QgsDataProvider.ProviderOptions(),
        flags=QgsDataProvider.ReadFlags(),
    ):
        super().__init__(uri)
        self._features = []
        self._features_loaded = False
        self._is_valid = False
        self._uri = uri
        self._wkb_type = None
        self._extent = None
        self._column_geom = None
        self._fields = None
        self._feature_count = None
        self._primary_key = None
        self.filter_where_clause = None
        try:
            (
                self._connection_name,
                self._sql_query,
                self._schema_name,
                self._table_name,
                self._srid,
                self._column_geom,
                self._geometry_type,
                self._geo_column_type,
            ) = parse_uri(uri)

        except Exception as _:
            self._is_valid = False
            return

        if self._srid:
            self._crs = QgsCoordinateReferenceSystem.fromEpsgId(int(self._srid))
        else:
            self._crs = QgsCoordinateReferenceSystem()

        self._settings = get_qsettings()
        self._context_information = {
            "connection_name": self._connection_name,
        }
        if self._schema_name:
            self._context_information["schema_name"] = self._schema_name
        if "table_name" in self._context_information:
            self._context_information["table_name"] = self._table_name
        self._auth_information = get_authentification_information(
            self._settings, self._context_information["connection_name"]
        )

        self.connect_database()
        self._is_limited_unordered = False

        if self._sql_query and not self._table_name:
            self._from_clause = f"({self._sql_query})"
        else:
            self._from_clause = f'"{self._table_name}"'
            self._is_limited_unordered = check_from_clause_exceeds_size(
                from_clause=self._from_clause,
                context_information=self._context_information,
            )

        self.get_geometry_column()

        self._provider_options = providerOptions
        self._flags = flags
        self._is_valid = True

    @classmethod
    def providerKey(cls) -> str:
        """Returns the memory provider key"""
        return "snowflakedb"

    @classmethod
    def description(cls) -> str:
        """Returns the memory provider description"""
        return "SnowflakeDB"

    @classmethod
    def createProvider(cls, uri, providerOptions, flags=QgsDataProvider.ReadFlags()):
        """Creates a VectorDataProvider of the appropriate type for the given column"""
        base_provider = SFVectorDataProvider(uri, providerOptions, flags)
        if base_provider._geo_column_type in ["NUMBER", "TEXT"]:
            return SFH3VectorDataProvider(uri, providerOptions, flags)
        elif base_provider._geo_column_type in ["GEOGRAPHY", "GEOMETRY"]:
            return SFGeoVectorDataProvider(uri, providerOptions, flags)
        else:
            return base_provider

    def capabilities(self) -> QgsVectorDataProvider.Capabilities:
        return (
            QgsVectorDataProvider.CreateSpatialIndex | QgsVectorDataProvider.SelectAtId
        )

    def name(self) -> str:
        """Return the name of provider

        :return: Name of provider
        :rtype: str
        """
        return self.providerKey()

    def isValid(self) -> bool:
        return self._is_valid

    def connect_database(self):
        """Connects the database and loads the spatial extension"""
        self.connection_manager: SFConnectionManager = (
            SFConnectionManager.get_instance()
        )
        if self.connection_manager.get_connection(self._connection_name) is None:
            self.connection_manager.connect(
                self._connection_name, self._auth_information
            )

    def wkbType(self) -> QgsWkbTypes:
        """Detects the geometry type of the table, converts and return it to
        QgsWkbTypes.
        """
        if not self._column_geom:
            return QgsWkbTypes.NoGeometry
        if not self._wkb_type:
            if not self._is_valid:
                self._wkb_type = QgsWkbTypes.Unknown
            else:
                if self._geometry_type in mapping_snowflake_qgis_geometry:
                    geometry_type = mapping_snowflake_qgis_geometry[self._geometry_type]
                else:
                    self._wkb_type = QgsWkbTypes.Unknown
                    return self._wkb_type

                self._wkb_type = geometry_type

        return self._wkb_type

    def updateExtents(self) -> None:
        """Update extent"""
        return self._extent.setMinimal()

    def get_geometry_column(self) -> str:
        """Returns the name of the geometry column"""
        return self._column_geom

    def primary_key(self) -> int:
        self._primary_key = -1
        return self._primary_key

    def fields(self) -> QgsFields:
        """Detects field name and type. Converts the type into a QVariant, and returns a
        QgsFields containing QgsFields.
        If there is no sql subquery, all the fields are returned
        If there is a sql subquery, only the fields contained in the subquery are returned
        """
        if not self._fields:
            self._fields = QgsFields()
            if self._is_valid:
                if not self._sql_query:
                    query = (
                        "SELECT column_name, data_type FROM information_schema.columns "
                        f"WHERE table_name ILIKE '{self._table_name}' "
                        "AND data_type NOT IN ('GEOMETRY', 'GEOGRAPHY')"
                        " ORDER BY column_name, data_type"
                    )

                    cur = self.connection_manager.execute_query(
                        connection_name=self._connection_name,
                        query=query,
                        context_information=self._context_information,
                    )

                    field_info = cur.fetchall()
                    cur.close()
                    for field_name, field_type in field_info:
                        qgs_field = QgsField(
                            field_name, mapping_snowflake_qgis_type[field_type]
                        )
                        self._fields.append(qgs_field)
                else:
                    field_info = []
                    cur = self.connection_manager.execute_query(
                        connection_name=self._connection_name,
                        query=self._sql_query,
                        context_information=self._context_information,
                    )
                    description = cur.description
                    cur.close()

                    for data in description:
                        # it is already used to set the feature id
                        if data[1] not in [14, 15]:
                            qgs_field = QgsField(
                                data[0],
                                SNOWFLAKE_METADATA_TYPE_CODE_DICT.get(
                                    data[1],
                                    SNOWFLAKE_METADATA_TYPE_CODE_DICT[2][
                                        "qvariant_type"
                                    ],
                                ).get("qvariant_type"),
                            )
                            self._fields.append(qgs_field)

        return self._fields

    def dataSourceUri(self, expandAuthConfig=False):
        """Returns the data source specification: database path and
        table name.

        :param bool expandAuthConfig: expand credentials (unused)
        :returns: the data source uri
        """
        return self._uri

    def crs(self):
        return self._crs

    def featureSource(self):
        return SFFeatureSource(self)

    def storageType(self):
        return "Snowflake database"

    def is_view(self) -> bool:
        """
        Checks if the given table name corresponds to a view in the database.

        :return: True if the object is a view, False otherwise.
        :rtype: bool
        """
        if self._sql_query:
            return False

        query = (
            "SELECT table_name FROM information_schema.tables WHERE table_type = 'VIEW'"
        )
        cur = self.connection_manager.execute_query(
            connection_name=self._connection_name,
            query=query,
            context_information=self._context_information,
        )
        view_list = [elem[0] for elem in cur.fetchall()]
        cur.close()

        return self._table_name in view_list

    def uniqueValues(self, fieldIndex: int, limit: int = -1) -> set:
        """Returns the unique values of a field

        :param fieldIndex: Index of field
        :type fieldIndex: int
        :param limit: limit of returned values
        :type limit: int
        """
        column_name = self.fields().field(fieldIndex).name()
        results = set()
        query = (
            f"SELECT DISTINCT {column_name} FROM {self._from_clause} "
            f"ORDER BY {column_name}"
        )
        if limit >= 0:
            query += f" LIMIT {limit}"

        cur = self.connection_manager.execute_query(
            connection_name=self._connection_name,
            query=query,
            context_information=self._context_information,
        )

        for elem in cur.fetchall():
            results.add(elem[0])
        cur.close()

        return results

    def getFeatures(self, request=QgsFeatureRequest()) -> QgsFeature:
        """Return next feature"""
        return QgsFeatureIterator(SFFeatureIterator(SFFeatureSource(self), request))

    def subsetString(self) -> str:
        return self.filter_where_clause

    def setSubsetString(
        self, subsetstring: str, updateFeatureCount: bool = True
    ) -> bool:
        if subsetstring:
            # Check if the filter is valid
            try:
                cur = self.connection_manager.execute_query(
                    connection_name=self._connection_name,
                    query=(
                        f"SELECT COUNT(*) FROM {self._from_clause} "
                        f"WHERE {subsetstring} LIMIT 0"
                    ),
                    context_information=self._context_information,
                )
                cur.close()
            except Exception as _:
                return False
            self.filter_where_clause = subsetstring

        if not subsetstring:
            self.filter_where_clause = None

        if updateFeatureCount:
            # We set this variable to None to trigger featuresCount()
            # reloadData() is a private method, so we have to use it to force the featureCount() refresh.
            self._feature_count = None
            self.reloadData()

        return True

    def supportsSubsetString(self) -> bool:
        return True

    def get_field_index_by_type(self, field_type: QMetaType) -> list:
        """This method identifies the field index for the type passed as an argument.

        :return: List of column indexes for type requested
        :rtype: list
        """
        fields_index = []

        for i in range(self._fields.count()):
            field = self._fields[i]
            if field.type() == field_type:
                fields_index.append(i)

        return fields_index

    def reloadData(self):
        """Reload data from the data source."""
        self._features = []
        self._features_loaded = False


class SFGeoVectorDataProvider(SFVectorDataProvider):
    """The VectorDataProvider for GEOGRAPHY and GEOMETRY columns"""

    def __init__(
        self,
        uri="",
        providerOptions=QgsDataProvider.ProviderOptions(),
        flags=QgsDataProvider.ReadFlags(),
    ):
        super().__init__(uri, providerOptions, flags)

    def featureCount(self) -> int:
        """returns the number of entities in the table"""

        if not self._feature_count:
            if not self._is_valid:
                self._feature_count = 0
            else:
                if self._is_limited_unordered:
                    self._feature_count = limit_size_for_type(self._geo_column_type)
                else:
                    query = f"SELECT COUNT(*) FROM {self._from_clause}"
                    if self.subsetString():
                        query += f" WHERE {self.subsetString()}"

                    cur = self.connection_manager.execute_query(
                        connection_name=self._connection_name,
                        query=query,
                        context_information=self._context_information,
                    )

                    self._feature_count = cur.fetchone()[0]
                    cur.close()

        return self._feature_count

    def extent(self) -> QgsRectangle:
        """Calculates the extent of the bend and returns a QgsRectangle"""
        if not self._extent:
            if not self._is_valid or not self._column_geom:
                self._extent = QgsRectangle()
            else:
                query = (
                    f'SELECT MIN(ST_XMIN("{self._column_geom}")), '
                    f'MIN(ST_YMIN("{self._column_geom}")), '
                    f'MAX(ST_XMAX("{self._column_geom}")), '
                    f'MAX(ST_YMAX("{self._column_geom}")) '
                    f"FROM {self._from_clause} "
                    f'WHERE "{self._column_geom}" IS NOT NULL AND '
                    f"ST_ASGEOJSON(\"{self._column_geom}\"):type ILIKE '{self._geometry_type}'"
                )

                cur = self.connection_manager.execute_query(
                    connection_name=self._connection_name,
                    query=query,
                    context_information=self._context_information,
                )

                extent_bounds = cur.fetchone()
                cur.close()

                self._extent = QgsRectangle(*extent_bounds)

        return self._extent


class SFH3VectorDataProvider(SFVectorDataProvider):
    """The VectorDataProvider for H3 columns"""

    def __init__(
        self,
        uri="",
        providerOptions=QgsDataProvider.ProviderOptions(),
        flags=QgsDataProvider.ReadFlags(),
    ):
        super().__init__(uri, providerOptions, flags)
        query = f'SELECT H3_IS_VALID_CELL("{self._column_geom}") FROM {self._from_clause} WHERE "{self._column_geom}" IS NOT NULL LIMIT 1'

        cur = self.connection_manager.execute_query(
            connection_name=self._connection_name,
            query=query,
            context_information=self._context_information,
        )

        self._is_valid = cur.fetchone()[0]

    def featureCount(self) -> int:
        """returns the number of entities in the table"""

        if not self._feature_count:
            if not self._is_valid:
                self._feature_count = 0
            else:
                query = f"SELECT COUNT(*) FROM {self._from_clause}"
                query += f' WHERE H3_IS_VALID_CELL("{self._column_geom}")'
                if self.subsetString():
                    query += f" AND {self.subsetString()}"

                cur = self.connection_manager.execute_query(
                    connection_name=self._connection_name,
                    query=query,
                    context_information=self._context_information,
                )

                self._feature_count = cur.fetchone()[0]
                cur.close()

        return self._feature_count

    def extent(self) -> QgsRectangle:
        """Calculates the extent of the bend and returns a QgsRectangle"""
        if not self._extent:
            if not self._is_valid or not self._column_geom:
                self._extent = QgsRectangle()
            else:
                query = (
                    f'SELECT MIN(ST_XMIN(H3_CELL_TO_BOUNDARY("{self._column_geom}"))), '
                    f'MIN(ST_YMIN(H3_CELL_TO_BOUNDARY("{self._column_geom}"))), '
                    f'MAX(ST_XMAX(H3_CELL_TO_BOUNDARY("{self._column_geom}"))), '
                    f'MAX(ST_YMAX(H3_CELL_TO_BOUNDARY("{self._column_geom}"))) '
                    f"FROM {self._from_clause} "
                    f'WHERE H3_IS_VALID_CELL("{self._column_geom}")'
                )

                cur = self.connection_manager.execute_query(
                    connection_name=self._connection_name,
                    query=query,
                    context_information=self._context_information,
                )

                extent_bounds = cur.fetchone()
                cur.close()

                self._extent = QgsRectangle(*extent_bounds)

        return self._extent
