# standard
from __future__ import (
    annotations,  # used to manage type annotation for method that return Self in Python < 3.11
)

from typing import Any, Callable

from qgis.PyQt.QtCore import QDate, QDateTime, QMetaType, QTime

# PyQGIS
from ..helpers.limits import limit_size_for_type
from ..helpers.sql import quote_identifier, quote_literal
from ..helpers.expression_compiler import compile_expression_to_sql
from ..managers.sf_connection_manager import build_op_tag
from ..providers.sf_feature_source import SFFeatureSource
from qgis.core import (
    QgsAbstractFeatureIterator,
    QgsCoordinateTransform,
    QgsCsException,
    QgsFeature,
    QgsFeatureRequest,
    QgsGeometry,
    QgsMessageLog,
    Qgis,
)
from ..helpers.mappings import mapping_multi_single_to_geometry_type


def _rect_is_valid_lonlat(rect) -> bool:
    """Return True when every corner of ``rect`` falls inside the WGS84
    lon/lat range, so it can be safely wrapped in ``ST_GEOGRAPHYFROMWKT``
    without Snowflake rejecting it as an invalid Lng/Lat pair.
    """
    return (
        -180.0 <= rect.xMinimum() <= 180.0
        and -180.0 <= rect.xMaximum() <= 180.0
        and -90.0 <= rect.yMinimum() <= 90.0
        and -90.0 <= rect.yMaximum() <= 90.0
    )


class SFFeatureIterator(QgsAbstractFeatureIterator):
    def __init__(
        self,
        source: SFFeatureSource,
        request: QgsFeatureRequest,
    ):
        self._cursor_batch_rows = []
        super().__init__(request)
        self._provider = source.get_provider()
        # Initialized unconditionally: nextFeatureFilterExpression() reads
        # self._expression even when the provider's features are already cached
        # (the block below that would otherwise set it is skipped). See issue #119.
        self._expression = ""
        # Only a full, unfiltered load may populate the provider-shared cache
        # and mark the layer loaded. A per-request filter (spatial rect, fid,
        # pushed-down expression) must stream one-shot, otherwise the first
        # filtered render would permanently cap the layer to that subset.
        self._should_cache_features = False

        self._request = request if request is not None else QgsFeatureRequest()
        self._transform = QgsCoordinateTransform()

        if (
            self._request.destinationCrs().isValid()
            and self._request.destinationCrs() != source._provider.crs()
        ):
            self._transform = QgsCoordinateTransform(
                source._provider.crs(),
                self._request.destinationCrs(),
                self._request.transformContext(),
            )

        try:
            filter_rect = self.filterRectToSourceCrs(self._transform)
        except QgsCsException:
            self.close()
            return

        if not self._provider.isValid():
            return

        if getattr(self._provider, "_load_all_rows", False):
            self._provider._features_loaded = False
            self._provider._features = []

        if not self._provider._features_loaded:
            geom_column = self._provider.get_geometry_column()

            # Mapping between the field type and the conversion function
            attributes_conversion_functions: dict[QMetaType, Callable[[Any], Any]] = {
                QMetaType.Type.QDate: QDate,
                QMetaType.Type.QTime: QTime,
                QMetaType.Type.QDateTime: QDateTime,
                QMetaType.Type.Double: float,
            }

            self._attributes_converters = {}
            for idx in range(len(self._provider.fields())):
                self._attributes_converters[idx] = lambda x: x

            # Check if field needs to be converted
            self._attributes_need_conversion = False
            for field_type, converter in attributes_conversion_functions.items():
                for index in self._provider.get_field_index_by_type(field_type):
                    self._attributes_need_conversion = True
                    self._attributes_converters[index] = converter

            # Fields list that needs to be retrieved
            self._request_sub_attributes = (
                self._request.flags() & QgsFeatureRequest.Flag.SubsetOfAttributes
            )
            if (
                self._request_sub_attributes
                and not self._provider.subsetString()
                and len(self._request.subsetOfAttributes()) > 0
            ):
                idx_required = [idx for idx in self._request.subsetOfAttributes()]

                # The primary key column must be added if it is not present in the field list.
                if (
                    self._provider.primary_key() != ""
                    and self._provider.primary_key() not in idx_required
                ):
                    idx_required.append(self._provider.primary_key())

                list_field_names = [
                    self._provider.fields()[idx].name()
                    for idx in idx_required
                ]
            else:
                list_field_names = [
                    field.name() for field in self._provider.fields()
                ]

            if len(list_field_names) > 0:
                fields_name_for_query = ", ".join(quote_identifier(n) for n in list_field_names)
            else:
                fields_name_for_query = ""

            if fields_name_for_query:
                fields_name_for_query += ","
            self.index_geom_column = len(list_field_names)

            # Create fid/fids list
            feature_id_list = None
            if (
                self._request.filterType() == QgsFeatureRequest.FilterFid
                or self._request.filterType() == QgsFeatureRequest.FilterFids
            ):
                feature_id_list = (
                    [self._request.filterFid()]
                    if self._request.filterType() == QgsFeatureRequest.FilterFid
                    else self._request.filterFids()
                )

            where_clause_list = []
            if feature_id_list is not None:
                list_feature_id_string = ", ".join(str(x) for x in feature_id_list)
                if self._provider.primary_key() == "":
                    feature_clause = (
                        f"sfindexsfrownumberauto in ({list_feature_id_string})"
                    )
                else:
                    primary_key_name = list_field_names[self._provider.primary_key()]
                    feature_clause = f"{quote_identifier(primary_key_name)} in ({list_feature_id_string})"

                where_clause_list.append(feature_clause)

            self._expression = ""
            # Apply the filter expression. The raw QGIS expression text is
            # attacker-influenceable (persisted in project files), so it is
            # compiled to SQL through a whitelist compiler; anything that does
            # not fully compile is NOT pushed down (QGIS filters client-side).
            if self._request.filterType() == QgsFeatureRequest.FilterExpression:
                expression = self._request.filterExpression().expression()
                if expression:
                    compiled = compile_expression_to_sql(
                        expression, self._provider._fields
                    )
                    if compiled:
                        self._expression = compiled
                        where_clause_list.append(compiled)
                    else:
                        QgsMessageLog.logMessage(
                            "Filter expression could not be safely compiled to "
                            "SQL; running without pushdown.",
                            "Snowflake Plugin",
                            Qgis.MessageLevel.Info,
                        )

            # Apply the subset string filter. setSubsetString() only stores a
            # compiler-validated, fully-quoted predicate, so it is safe to
            # append verbatim here.
            if self._provider.subsetString():
                where_clause_list.append(self._provider.subsetString())

            # Apply the geometry filter
            quoted_geom = quote_identifier(geom_column)
            filter_geom_clause = ""
            if not filter_rect.isNull():
                if self._provider._geo_column_type == "GEOMETRY":
                    filter_geom_clause = (
                        f'ST_INTERSECTS({quoted_geom}, '
                        f"ST_GEOMETRYFROMWKT('{filter_rect.asWktPolygon()}'))"
                    )
                elif self._provider._geo_column_type == "GEOGRAPHY":
                    # ST_GEOGRAPHYFROMWKT requires valid WGS84 lon/lat. If the
                    # rect from QGIS is outside that range (e.g. the transform
                    # from the canvas CRS silently failed), skip the pushdown
                    # rather than erroring on every fetch.
                    if _rect_is_valid_lonlat(filter_rect):
                        filter_geom_clause = (
                            f'ST_INTERSECTS({quoted_geom}, '
                            f"ST_GEOGRAPHYFROMWKT('{filter_rect.asWktPolygon()}'))"
                        )
                    else:
                        QgsMessageLog.logMessage(
                            f"Skipping spatial filter pushdown: rect "
                            f"{filter_rect.toString()} is outside WGS84 lon/lat "
                            f"range (GEOGRAPHY column {quoted_geom}).",
                            "Snowflake Plugin",
                            Qgis.MessageLevel.Warning,
                        )
                elif self._provider._geo_column_type in ["NUMBER", "TEXT"]:
                    if _rect_is_valid_lonlat(filter_rect):
                        filter_geom_clause = (
                            f'ST_INTERSECTS(H3_CELL_TO_BOUNDARY({quoted_geom}), '
                            f"ST_GEOGRAPHYFROMWKT('{filter_rect.asWktPolygon()}'))"
                        )
                    else:
                        QgsMessageLog.logMessage(
                            f"Skipping spatial filter pushdown: rect "
                            f"{filter_rect.toString()} is outside WGS84 lon/lat "
                            f"range (H3 column {quoted_geom}).",
                            "Snowflake Plugin",
                            Qgis.MessageLevel.Warning,
                        )
                if filter_geom_clause != "":
                    filter_geom_clause = f"and {filter_geom_clause}"

            # A query is only safe to cache into the provider-shared feature
            # list when it carried no per-request row filter. Otherwise a
            # filtered render/identify would poison the cache and cap every
            # later full-extent request to that subset. subsetString() is a
            # stable provider-level filter (reloadData() clears the cache when
            # it changes), so it is intentionally not part of this check.
            self._should_cache_features = (
                not getattr(self._provider, "_load_all_rows", False)
                and feature_id_list is None
                and self._expression == ""
                and filter_geom_clause == ""
            )

            # build the complete where clause
            where_clause = ""
            if where_clause_list:
                where_clause = f"where {where_clause_list[0]}"
                if len(where_clause_list) > 1:
                    for clause in where_clause_list[1:]:
                        where_clause += f" and {clause}"

            geom_query = f'ST_ASWKB({quoted_geom}), '
            if self._provider._geo_column_type == "TEXT":
                geom_query = f'ST_ASWKB(H3_CELL_TO_BOUNDARY({quoted_geom})), {quoted_geom}, '
            elif self._provider._geo_column_type == "NUMBER":
                geom_query = (
                    f'ST_ASWKB(H3_CELL_TO_BOUNDARY({quoted_geom})), '
                    f'H3_INT_TO_STRING({quoted_geom}), '
                )

            self._request_no_geometry = (
                self._request.flags() & QgsFeatureRequest.Flag.NoGeometry
            )
            if self._request_no_geometry:
                geom_query = ""

            if self._provider.primary_key() == "":
                index = "ROW_NUMBER() OVER (order by 1) as sfindexsfrownumberauto "
            else:
                index = self._provider._fields[self._provider.primary_key()].name()

            mapped_type = mapping_multi_single_to_geometry_type.get(
                self._provider._geometry_type
            )

            filter_geo_type = f"ST_ASGEOJSON({quoted_geom}):type::string IN ({quote_literal(self._provider._geometry_type)}"  # nosec B608 - geometry_type escaped via quote_literal
            if mapped_type is not None:
                filter_geo_type += f", {quote_literal(mapped_type)}"
            filter_geo_type += ")"
            if self._provider._geo_column_type in ["NUMBER", "TEXT"]:
                filter_geo_type = f'H3_IS_VALID_CELL({quoted_geom})'

            base_query = (
                "select * from ("  # nosec B608 - from_clause pre-quoted; fragments built from quoted identifiers and validated fragments
                f"select {fields_name_for_query} "
                f"{geom_query} {index} "
                f"from {self._provider._from_clause} where {filter_geo_type} {filter_geom_clause}) "
                f"{where_clause}"
            )

            if self._provider._is_limited_unordered:
                # A7: let Snowflake's TABLESAMPLE do the random-sample work
                # on the already-filtered set instead of sorting the entire
                # resultset with ORDER BY RANDOM().
                sample_n = limit_size_for_type(self._provider._geo_column_type)
                self.final_query = (
                    f"select * from ({base_query}) SAMPLE ({sample_n} ROWS)"  # nosec B608 - base_query is built from quoted identifiers / validated fragments; sample_n is an int
                )
            else:
                self.final_query = base_query

            self._result = self._provider.connection_manager.execute_query(
                connection_name=self._provider._connection_name,
                query=self.final_query,
                context_information=self._provider._context_information,
                op_tag=build_op_tag(
                    "layer-load",
                    connection_name=self._provider._connection_name,
                    schema=self._provider._schema_name,
                    table=self._provider._table_name,
                ),
            )
            self._col_index_by_name = {
                desc.name: idx
                for idx, desc in enumerate(self._result.description)
            }
            self._fetch_batch_size = (
                50_000
                if getattr(self._provider, "_load_all_rows", False)
                else 5_000
            )
        self._index = 0

    def fetchFeature(self, f: QgsFeature) -> bool:
        """fetch next feature, return true on success

        :param f: Next feature
        :type f: QgsFeature
        :return: True if success
        :rtype: bool
        """
        try:
            if self._provider._features_loaded:
                if (
                    self._index < 0
                    or self._index >= len(self._provider._features)
                    or not self._provider.isValid()
                ):
                    f.setValid(False)
                    return False

                if self._request.filterType() == QgsFeatureRequest.FilterFid:
                    _indx = self._request.filterFid()
                else:
                    _indx = self._index
                local_feature: QgsFeature = self._provider._features[_indx]

                while (
                    self._request.filterRect()
                    and not self._request.filterRect().isNull()
                    and not local_feature.geometry().intersects(
                        self._request.filterRect()
                    )
                ):
                    self._index += 1
                    if self._index >= len(self._provider._features):
                        f.setValid(False)
                        return False
                    local_feature = self._provider._features[self._index]

                f.setFields(self._provider.fields())
                f.setGeometry(local_feature.geometry())
                f.setId(local_feature.id())
                f.setAttributes(local_feature.attributes())
                f.setValid(True)

            else:
                if not self._cursor_batch_rows:
                    self._cursor_batch_rows = self._result.fetchmany(
                        self._fetch_batch_size
                    )

                next_result = (
                    self._cursor_batch_rows.pop(0) if self._cursor_batch_rows else None
                )

                if not next_result or not self._provider.isValid():
                    f.setValid(False)
                    if self._should_cache_features:
                        self._provider._features_loaded = True
                    return False

                f.setFields(self._provider.fields())

                if not self._request_no_geometry:
                    geometry = QgsGeometry()
                    geometry.fromWkb(next_result[self.index_geom_column])
                    f.setGeometry(geometry)
                    self.geometryToDestinationCrs(f, self._transform)

                # Feature ids are the 0-based iteration order of this result
                # set, NOT the table primary key. QGIS selection/editing use
                # these fids to index the provider's cached feature list; edits
                # then map fid -> cached feature -> primary key for the DML.
                f.setId(self._index)

                col_index_by_name = self._col_index_by_name
                if self._attributes_need_conversion:
                    if (
                        self._request_sub_attributes
                        and len(self._request.subsetOfAttributes()) > 0
                    ):
                        for idx, attr_idx in enumerate(
                            self._request.subsetOfAttributes()
                        ):
                            raw = next_result[idx]
                            attribute = (
                                None if raw is None
                                else self._attributes_converters[idx](raw)
                            )
                            f.setAttribute(attr_idx, attribute)
                    else:
                        for indx, field_name in enumerate(
                            self._provider.fields().names()
                        ):
                            try:
                                if (
                                    field_name == self._provider._column_geom
                                    and self._provider._geo_column_type
                                    not in ("NUMBER", "TEXT")
                                ):
                                    continue
                                col_idx = col_index_by_name.get(field_name)
                                if col_idx is None:
                                    continue
                                column_value = next_result[col_idx]
                                converted_attribute = (
                                    None if column_value is None
                                    else self._attributes_converters[indx](column_value)
                                )
                                f.setAttribute(indx, converted_attribute)
                            except Exception as e:
                                QgsMessageLog.logMessage(
                                    f"Feature Iterator Error - Conversion issue: {str(e)}",
                                    "Snowflake Plugin",
                                    Qgis.MessageLevel.Warning,
                                )

                else:
                    if (
                        self._request_sub_attributes
                        and len(self._request.subsetOfAttributes()) > 0
                    ):
                        for idx, attr_idx in enumerate(
                            self._request.subsetOfAttributes()
                        ):
                            f.setAttribute(attr_idx, next_result[idx])
                    else:
                        for indx, field_name in enumerate(
                            self._provider.fields().names()
                        ):
                            if (
                                field_name == self._provider._column_geom
                                and self._provider._geo_column_type
                                not in ("NUMBER", "TEXT")
                            ):
                                continue
                            col_idx = col_index_by_name.get(field_name)
                            if col_idx is None:
                                continue
                            f.setAttribute(indx, next_result[col_idx])
                f.setValid(True)
                if self._should_cache_features:
                    self._provider._features.append(QgsFeature(f))

            self._index += 1
        except Exception as e:
            QgsMessageLog.logMessage(
                f"Error fetching feature: {str(e)}",
                "Snowflake Plugin",
                Qgis.MessageLevel.Critical,
            )
        return True

    def nextFeatureFilterExpression(self, f: QgsFeature) -> bool:
        if not self._expression:
            return super().nextFeatureFilterExpression(f)
        else:
            return self.fetchFeature(f)

    def __iter__(self) -> SFFeatureIterator:
        """Returns self as an iterator object"""
        self._index = 0
        return self

    def __next__(self) -> QgsFeature:
        """Returns the next value till current is lower than high"""
        if self._provider._features_loaded:
            if self._index < 0 or self._index > len(self._provider._features):
                f = QgsFeature()
                f.setValid(False)
                return f
            f = self._provider._features[self._index]
            self._index += 1
            return f
        else:
            f = QgsFeature()
            if not self.nextFeature(f):
                raise StopIteration
            else:
                return f

    def rewind(self) -> bool:
        """reset the iterator to the starting position"""
        self._result = self._provider.connection_manager.execute_query(
            connection_name=self._provider._connection_name,
            query=self.final_query,
            context_information=self._provider._context_information,
        )
        self._provider._features = []
        self._provider._features_loaded = False
        self._index = 0
        return True

    def close(self) -> bool:
        """end of iterating: free the resources / lock"""
        self._index = -1
        # SNOW-3712076: release the server-side cursor so an abandoned/cancelled
        # render does not leak an open SnowflakeCursor on the singleton
        # connection.
        result = getattr(self, "_result", None)
        if result is not None:
            try:
                result.close()
            except Exception:
                pass
            self._result = None
        return True
