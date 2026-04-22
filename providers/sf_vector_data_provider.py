import copy
import typing
from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsDataProvider,
    QgsFeature,
    QgsFeatureIterator,
    QgsFeatureRequest,
    QgsField,
    QgsFields,
    QgsMessageLog,
    QgsRectangle,
    QgsVectorDataProvider,
    QgsWkbTypes,
    QgsGeometry,
)
from qgis.PyQt.QtCore import QMetaType, QVariant

from .sf_feature_iterator import SFFeatureIterator

from ..helpers.data_base import (
    alter_table_add_columns,
    alter_table_drop_columns,
    check_from_clause_exceeds_size,
    delete_table_features,
    get_next_primary_key_value,
    insert_table_feature,
    limit_size_for_type,
    update_table_attributes,
    update_table_feature,
)

from .sf_feature_source import SFFeatureSource

from ..helpers.utils import get_authentification_information, get_qsettings
from ..managers.sf_connection_manager import SFConnectionManager

from ..helpers.wrapper import parse_uri
from ..helpers.sql import quote_identifier, quote_literal
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
        self.filter_where_clause = None
        self._load_all_rows = False
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
                self._primary_key,
                self._load_all_rows,
            ) = parse_uri(uri)

        except Exception as e:
            QgsMessageLog.logMessage(
                f"Provider init failed: URI parse error: {e}",
                "Snowflake Plugin",
                Qgis.MessageLevel.Warning,
            )
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
        if self._table_name:
            self._context_information["table_name"] = self._table_name
        self._auth_information = get_authentification_information(
            self._settings, self._context_information["connection_name"]
        )
        if self._auth_information.get("database"):
            self._context_information["database_name"] = self._auth_information["database"]

        self.connect_database()
        self._is_limited_unordered = False

        if self._sql_query and not self._table_name:
            self._from_clause = f"({self._sql_query})"
        else:
            self._from_clause = quote_identifier(self._table_name)
            if self._load_all_rows:
                self._is_limited_unordered = False
            else:
                self._is_limited_unordered = check_from_clause_exceeds_size(
                    from_clause=self._from_clause,
                    context_information=self._context_information,
                    limit_size=limit_size_for_type(self._geo_column_type),
                )

        self.get_geometry_column()

        self.setNativeTypes([
            QgsVectorDataProvider.NativeType("Text", "TEXT", QMetaType.Type.QString),
            QgsVectorDataProvider.NativeType("Integer", "INTEGER", QMetaType.Type.Int),
            QgsVectorDataProvider.NativeType("Decimal", "DOUBLE", QMetaType.Type.Double),
            QgsVectorDataProvider.NativeType("Boolean", "BOOLEAN", QMetaType.Type.Bool),
            QgsVectorDataProvider.NativeType("Date", "DATE", QMetaType.Type.QDate),
            QgsVectorDataProvider.NativeType("Time", "TIME", QMetaType.Type.QTime),
            QgsVectorDataProvider.NativeType("Date & Time", "TIMESTAMP", QMetaType.Type.QDateTime),
        ])

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
        base_capabilities = (
            QgsVectorDataProvider.CreateSpatialIndex | QgsVectorDataProvider.SelectAtId
        )

        # An empty string used as a primary key signifies the absence of a defined primary key.
        if (
            self._primary_key == ""
            or self._geo_column_type not in ("GEOGRAPHY", "GEOMETRY")
            or (self._sql_query is not None and self._sql_query != "")
        ):
            reasons = []
            if self._primary_key == "":
                reasons.append("no primary key")
            if self._geo_column_type not in ("GEOGRAPHY", "GEOMETRY"):
                reasons.append(f"column type '{self._geo_column_type}' is not editable")
            if self._sql_query is not None and self._sql_query != "":
                reasons.append("custom SQL query layer")
            QgsMessageLog.logMessage(
                f"Layer read-only: {', '.join(reasons)} "
                f"(table={getattr(self, '_table_name', '?')})",
                "Snowflake Plugin",
                Qgis.MessageLevel.Info,
            )
            return base_capabilities

        return (
            base_capabilities
            | QgsVectorDataProvider.AddFeatures
            | QgsVectorDataProvider.DeleteFeatures
            | QgsVectorDataProvider.ChangeAttributeValues
            | QgsVectorDataProvider.AddAttributes
            | QgsVectorDataProvider.DeleteAttributes
            | QgsVectorDataProvider.ChangeGeometries
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
        if self._extent is not None:
            self._extent.setNull()

    def get_geometry_column(self) -> str:
        """Returns the name of the geometry column"""
        return self._column_geom

    def primary_key(self) -> str:
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
                    # Filter by TABLE_CATALOG / TABLE_SCHEMA / TABLE_NAME so
                    # same-named tables in other DBs or schemas cannot bleed
                    # their columns into this layer's field list. DISTINCT is
                    # a belt-and-braces guard against any residual duplicates.
                    schema_filter = ""
                    if self._schema_name:
                        schema_filter = (
                            f" AND table_schema ILIKE"
                            f" {quote_literal(self._schema_name)}"
                        )
                    catalog_filter = ""
                    database_name = self._context_information.get("database_name")
                    if database_name:
                        catalog_filter = (
                            f" AND table_catalog ILIKE"
                            f" {quote_literal(database_name)}"
                        )
                    query = (
                        "SELECT DISTINCT column_name, data_type, ordinal_position"
                        " FROM information_schema.columns "
                        f"WHERE table_name ILIKE {quote_literal(self._table_name)}"
                        f"{catalog_filter}"
                        f"{schema_filter}"
                        " AND data_type NOT IN ('GEOMETRY', 'GEOGRAPHY')"
                        " ORDER BY ordinal_position"
                    )

                    cur = self.connection_manager.execute_query(
                        connection_name=self._connection_name,
                        query=query,
                        context_information=self._context_information,
                    )

                    field_info = cur.fetchall()
                    cur.close()
                    for row in field_info:
                        field_name, field_type = row[0], row[1]
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
                                    SNOWFLAKE_METADATA_TYPE_CODE_DICT[2],
                                ).get("qvariant_type"),
                            )
                            self._fields.append(qgs_field)

        return self._fields

    def defaultValue(self, fieldIndex, context=None):
        """Auto-generate the next sequential value for numeric primary key columns."""
        fields = self.fields()
        if fieldIndex < 0 or fieldIndex >= fields.count():
            return QVariant()
        field = fields.field(fieldIndex)
        if field.name() != self._primary_key:
            return QVariant()
        if field.type() not in (QMetaType.Type.Int, QMetaType.Type.Double, QMetaType.Type.LongLong):
            return QVariant()
        next_val = get_next_primary_key_value(
            self._context_information, self._table_name, self._primary_key,
        )
        if next_val is not None:
            # Wrap in QVariant for Qt6 consistency; some QGIS paths check
            # QVariant.isNull() and reject raw Python ints when a null-check
            # is expected.
            return QVariant(next_val)
        return QVariant()

    def defaultValueClause(self, fieldIndex):
        """Advertise an auto-increment default for the PK column.

        Returning a non-empty string tells QGIS' attribute form to treat the
        field as having a server-generated default, which triggers
        defaultValue() to populate the actual next ID on form open.
        """
        fields = self.fields()
        if fieldIndex < 0 or fieldIndex >= fields.count():
            return ""
        field = fields.field(fieldIndex)
        if field.name() != self._primary_key:
            return ""
        if field.type() not in (QMetaType.Type.Int, QMetaType.Type.Double, QMetaType.Type.LongLong):
            return ""
        return "Autogenerated"

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
        quoted_col = quote_identifier(column_name)
        query = (
            f"SELECT DISTINCT {quoted_col} FROM {self._from_clause} "
            f"ORDER BY {quoted_col}"
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
        self._feature_count = None
        self._extent = None
        self.connect_database()
        # Notify QGIS so the layer-level feature cache (QgsVectorLayerCache)
        # and the attribute table model refresh without requiring the user
        # to close and reopen the layer.
        self.dataChanged.emit()

    # -- QGIS QMetaType -> Snowflake DDL type mapping for addAttributes ------
    _QGIS_TO_SF_TYPE = {
        QMetaType.Type.QString: "TEXT",
        QMetaType.Type.Int: "INTEGER",
        QMetaType.Type.Double: "DOUBLE",
        QMetaType.Type.QDate: "DATE",
        QMetaType.Type.QTime: "TIME",
        QMetaType.Type.QDateTime: "TIMESTAMP",
        QMetaType.Type.Bool: "BOOLEAN",
    }

    def changeGeometryValues(self, geometry_map: typing.Any) -> bool:
        if isinstance(geometry_map, dict) and geometry_map:
            all_ok = True
            for f_key, geometry in geometry_map.items():
                geometry: QgsGeometry
                feature: QgsFeature = self._features[f_key]
                context = copy.deepcopy(self._context_information)
                context["geometry_wkt"] = geometry.asWkt()
                context["column_geom"] = self._column_geom
                context["primary_key_value"] = feature.attribute(self.primary_key())
                context["primary_key_name"] = self.primary_key()
                context["table_name"] = self._table_name
                if not update_table_feature(context):
                    all_ok = False
            self.reloadData()
            return all_ok
        return False

    @staticmethod
    def _unwrap_value(val):
        """Convert QVariant / NULL sentinel to plain Python type for Snowflake."""
        if isinstance(val, QVariant):
            return None if val.isNull() else val.value()
        return val

    def changeAttributeValues(self, attr_map: typing.Dict[int, typing.Dict[int, typing.Any]]) -> bool:
        if not isinstance(attr_map, dict) or not attr_map:
            return False
        try:
            all_ok = True
            fields = self.fields()
            pk_name = self.primary_key()
            for fid, field_map in attr_map.items():
                if fid < 0 or fid >= len(self._features):
                    all_ok = False
                    continue
                feature: QgsFeature = self._features[fid]
                set_clauses = []
                values = []
                for field_idx, new_value in field_map.items():
                    col_name = fields.field(field_idx).name()
                    set_clauses.append(f"{quote_identifier(col_name)} = %s")
                    values.append(self._unwrap_value(new_value))
                pk_value = self._unwrap_value(feature.attribute(pk_name))
                values.append(pk_value)
                context = copy.deepcopy(self._context_information)
                context["primary_key_name"] = pk_name
                context["table_name"] = self._table_name
                err = update_table_attributes(context, set_clauses, tuple(values))
                if err:
                    self.pushError(err)
                    all_ok = False
            if all_ok:
                self.reloadData()
            return all_ok
        except Exception as e:
            self.pushError(f"changeAttributeValues: {e}")
            return False

    def addFeatures(self, flist: typing.List[QgsFeature], flags=None) -> typing.Tuple[bool, typing.List[QgsFeature]]:
        if not flist:
            return False, []
        try:
            fields = self.fields()
            all_ok = True
            for feat in flist:
                col_names = [self._column_geom]
                values = [feat.geometry().asWkt() if feat.hasGeometry() else None]
                for i in range(fields.count()):
                    col_names.append(fields.field(i).name())
                    values.append(self._unwrap_value(feat.attribute(i)))
                context = copy.deepcopy(self._context_information)
                context["table_name"] = self._table_name
                err = insert_table_feature(context, col_names, tuple(values))
                if err:
                    self.pushError(err)
                    all_ok = False
                else:
                    # Stamp the inserted feature with the PK value as its fid so
                    # QGIS' edit buffer / attribute table correlates it with the
                    # row that lands in Snowflake after reloadData().
                    if self._primary_key:
                        pk_val = self._unwrap_value(feat.attribute(self._primary_key))
                        if pk_val is not None:
                            try:
                                feat.setId(int(pk_val))
                            except (ValueError, TypeError):
                                pass
            self.reloadData()
            return all_ok, flist
        except Exception as e:
            self.pushError(f"addFeatures: {e}")
            return False, []

    def deleteFeatures(self, fids: typing.List[int]) -> bool:
        if not fids:
            return False
        try:
            pk_values = []
            for fid in fids:
                feature: QgsFeature = self._features[fid]
                pk_values.append(self._unwrap_value(feature.attribute(self.primary_key())))
            context = copy.deepcopy(self._context_information)
            context["primary_key_name"] = self.primary_key()
            context["table_name"] = self._table_name
            err = delete_table_features(context, pk_values)
            self.reloadData()
            if err:
                self.pushError(err)
                return False
            return True
        except Exception as e:
            self.pushError(f"deleteFeatures: {e}")
            return False

    def addAttributes(self, attrs: typing.List[QgsField]) -> bool:
        if not attrs:
            return False
        columns = []
        for field in attrs:
            sf_type = self._QGIS_TO_SF_TYPE.get(field.type(), "TEXT")
            columns.append((field.name(), sf_type))
        context = copy.deepcopy(self._context_information)
        context["table_name"] = self._table_name
        err = alter_table_add_columns(context, columns)
        if err:
            self.pushError(err)
            return False
        if self._fields:
            for field in attrs:
                self._fields.append(QgsField(field))
        for feat in self._features:
            cur_attrs = feat.attributes()
            cur_attrs.extend([None] * len(columns))
            feat.setAttributes(cur_attrs)
        return True

    def deleteAttributes(self, attrs: typing.List[int]) -> bool:
        if not attrs:
            return False
        fields = self.fields()
        col_names = [fields.field(idx).name() for idx in attrs]
        context = copy.deepcopy(self._context_information)
        context["table_name"] = self._table_name
        err = alter_table_drop_columns(context, col_names)
        if err:
            self.pushError(err)
            return False
        if self._fields:
            new_fields = QgsFields()
            for i in range(self._fields.count()):
                if i not in attrs:
                    new_fields.append(self._fields.field(i))
            self._fields = new_fields
        indices_to_drop = sorted(attrs, reverse=True)
        for feat in self._features:
            cur_attrs = feat.attributes()
            for idx in indices_to_drop:
                if idx < len(cur_attrs):
                    del cur_attrs[idx]
            feat.setAttributes(cur_attrs)
        return True

    def extent(self) -> QgsRectangle:
        """Returns the extent of the layer.

        Currently, this method returns an empty QgsRectangle,
        indicating that the extent is unknown or not applicable.

        Returns:
            QgsRectangle: An empty QgsRectangle.
        """
        return QgsRectangle()

    def featureCount(self) -> int:
        """
        Returns the number of features in the layer.

        In this specific implementation, it always returns 0.

        Returns:
            int: The feature count, which is 0.
        """
        return 0


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
                qgeom = quote_identifier(self._column_geom)
                query = (
                    f'SELECT MIN(ST_XMIN({qgeom})), '
                    f'MIN(ST_YMIN({qgeom})), '
                    f'MAX(ST_XMAX({qgeom})), '
                    f'MAX(ST_YMAX({qgeom})) '
                    f"FROM {self._from_clause} "
                    f'WHERE {qgeom} IS NOT NULL AND '
                    f"ST_ASGEOJSON({qgeom}):type ILIKE '{self._geometry_type}'"
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
        qgeom = quote_identifier(self._column_geom)
        query = f'SELECT H3_IS_VALID_CELL({qgeom}) FROM {self._from_clause} WHERE {qgeom} IS NOT NULL LIMIT 1'

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
                if self._is_limited_unordered:
                    self._feature_count = limit_size_for_type(self._geo_column_type)
                    return self._feature_count

                query = f"SELECT COUNT(*) FROM {self._from_clause}"
                query += f' WHERE H3_IS_VALID_CELL({quote_identifier(self._column_geom)})'
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
                qgeom = quote_identifier(self._column_geom)
                query = (
                    f'SELECT MIN(ST_XMIN(H3_CELL_TO_BOUNDARY({qgeom}))), '
                    f'MIN(ST_YMIN(H3_CELL_TO_BOUNDARY({qgeom}))), '
                    f'MAX(ST_XMAX(H3_CELL_TO_BOUNDARY({qgeom}))), '
                    f'MAX(ST_YMAX(H3_CELL_TO_BOUNDARY({qgeom}))) '
                    f"FROM {self._from_clause} "
                    f'WHERE H3_IS_VALID_CELL({qgeom})'
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
