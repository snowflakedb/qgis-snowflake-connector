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

from ..providers.sf_feature_iterator import SFFeatureIterator

from ..providers.sf_feature_source import SFFeatureSource

from ..helpers.utils import get_authentification_information, get_qsettings
from ..managers.sf_connection_manager import SFConnectionManager

from ..helpers.wrapper import parse_uri
from ..helpers.mappings import (
    mapping_snowflake_qgis_geometry,
    mapping_snowflake_qgis_type,
)


class SFProvider(QgsVectorDataProvider):
    def __init__(
        self,
        uri="",
        # uri_model = path=/home/path/my_db.db table=the_table
        providerOptions=QgsDataProvider.ProviderOptions(),
        flags=QgsDataProvider.ReadFlags(),
    ):
        super().__init__(uri)
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
            ) = parse_uri(uri)

        except Exception as exc:
            self._is_valid = False
            return

        if self._srid:
            self._crs = QgsCoordinateReferenceSystem.fromEpsgId(int(self._srid))
        else:
            self._crs = QgsCoordinateReferenceSystem()

        self._settings = get_qsettings()
        self._context_information = {
            "connection_name": self._connection_name,
            "schema_name": self._schema_name,
            "table_name": self._table_name,
        }
        self._auth_information = get_authentification_information(
            self._settings, self._context_information["connection_name"]
        )
        print("auth")
        print(self._auth_information)

        self.connect_database()

        if self._sql_query and not self._table_name:
            # if not self.test_sql_query():
            #     return

            # If the rowid pseudocolumn is not in the sql add it to
            # the clause. It will be used to build the feature ids if
            # the table does not have a primary key.
            cur = self.connection_manager.execute_query(
                connection_name=self._connection_name,
                query=self._sql_query,
                context_information=self._context_information,
            )
            columns = cur.description
            # if "rowid" not in columns:
            #     self._sql = re.sub(
            #         "select", "select rowid, ", self._sql, flags=re.IGNORECASE
            #     )

            self._from_clause = f"({self._sql_query})"
        else:
            self._from_clause = self._table_name

        self.get_geometry_column()

        self._provider_options = providerOptions
        self._flags = flags
        self._is_valid = True
        # weakref.finalize(self, self.disconnect_database)

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
        return SFProvider(uri, providerOptions, flags)

    def capabilities(self) -> QgsVectorDataProvider.Capabilities:
        return (
            QgsVectorDataProvider.CreateSpatialIndex | QgsVectorDataProvider.SelectAtId
        )

    def featureCount(self) -> int:
        """returns the number of entities in the table"""

        if not self._feature_count:
            if not self._is_valid:
                self._feature_count = 0
            else:
                query = f"select count(*) from {self._from_clause}"
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
        # self._con = self.ddb_wrapper.connect(read_only=True, requires_spatial=True)
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

    def extent(self) -> QgsRectangle:
        """Calculates the extent of the bend and returns a QgsRectangle"""
        # TODO : Replace by ST_Extent when the function is implemented

        if not self._extent:
            if not self._is_valid or not self._column_geom:
                self._extent = QgsRectangle()
            else:
                query = (
                    f"select min(st_xmin({self._column_geom})), "
                    f"min(st_ymin({self._column_geom})), "
                    f"max(st_xmax({self._column_geom})), "
                    f"max(st_ymax({self._column_geom})) "
                    f"from {self._from_clause} "
                    f"where {self._column_geom} is not null and "
                    f"ST_ASGEOJSON({self._column_geom}):type ilike '{self._geometry_type}'"
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
                        "select column_name, data_type from information_schema.columns "
                        f"WHERE table_name ilike '{self._table_name}' "
                        "AND data_type not in ('GEOMETRY', 'GEOGRAPHY')"
                    )

                    cur = self.connection_manager.execute_query(
                        connection_name=self._connection_name,
                        query=query,
                        context_information=self._context_information,
                    )

                    field_info = cur.fetchall()
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
                        if data[1] not in ["GEOMETRY", "GEOGRAPHY"]:
                            field_info.append((data[0], data[1]))

                for field_name, field_type in field_info:
                    qgs_field = QgsField(
                        field_name, mapping_snowflake_qgis_type[field_type]
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
        query = f"select distinct {column_name} from {self._from_clause} order by {column_name}"
        if limit >= 0:
            query += f" limit {limit}"

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
                    query=f"select count(*) from {self._from_clause} WHERE {subsetstring} LIMIT 0",
                    context_information=self._context_information,
                )
                cur.close()
            except Exception as e:
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