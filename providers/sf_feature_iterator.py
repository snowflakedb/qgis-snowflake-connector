# standard
from __future__ import (
    annotations,  # used to manage type annotation for method that return Self in Python < 3.11
)

from typing import Any, Callable, Union

from qgis.PyQt.QtCore import QDate, QDateTime, QMetaType, QTime

# PyQGIS
from ..helpers.limits import limit_size_for_type
from ..providers.sf_feature_source import SFFeatureSource
from qgis.core import (
    QgsAbstractFeatureIterator,
    QgsCoordinateTransform,
    QgsCsException,
    QgsFeature,
    QgsFeatureRequest,
    QgsGeometry,
    QgsMessageLog,
    QgsPointXY,
    Qgis,
)
import h3.api.basic_int as h3
from ..helpers.mappings import mapping_multi_single_to_geometry_type


class SFFeatureIterator(QgsAbstractFeatureIterator):
    def __init__(
        self,
        source: SFFeatureSource,
        request: QgsFeatureRequest,
    ):
        self._cursor_batch_rows = []
        super().__init__(request)
        self._provider = source.get_provider()

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
                    self._provider.fields()[idx].name().replace('"', '""')
                    for idx in idx_required
                ]
            else:
                list_field_names = [
                    field.name().replace('"', '""') for field in self._provider.fields()
                ]

            if len(list_field_names) > 0:
                fields_name_for_query = '"' + '", "'.join(list_field_names) + '"'
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
                    feature_clause = f"{primary_key_name} in ({list_feature_id_string})"

                where_clause_list.append(feature_clause)

            self._expression = ""
            # Apply the filter expression
            if self._request.filterType() == QgsFeatureRequest.FilterExpression:
                expression = self._request.filterExpression().expression()
                if expression:
                    try:
                        # Checks if the expression is valid
                        query_verify_expression = (
                            f"SELECT count(*)"
                            f" FROM {self._provider._from_clause}"
                            f" WHERE {expression}"
                            " LIMIT 0"
                        )
                        cur_verify_expression = (
                            self._provider.connection_manager.execute_query(
                                connection_name=self._provider._connection_name,
                                query=query_verify_expression,
                                context_information=self._provider._context_information,
                            )
                        )
                        cur_verify_expression.close()
                        self._expression = expression
                        where_clause_list.append(expression)
                    except Exception:
                        pass

            # Apply the subset string filter
            if self._provider.subsetString():
                subset_clause = self._provider.subsetString().replace('"', "")
                where_clause_list.append(subset_clause)

            # Apply the geometry filter
            filter_geom_clause = ""
            if not filter_rect.isNull():
                if self._provider._geometry_type == "GEOMETRY":
                    filter_geom_clause = (
                        f'ST_INTERSECTS("{geom_column}", '
                        f"ST_GEOMETRYFROMWKT('{filter_rect.asWktPolygon()}'))"
                    )
                if self._provider._geometry_type == "GEOGRAPHY":
                    filter_geom_clause = (
                        f'ST_INTERSECTS("{geom_column}", '
                        f"ST_GEOGRAPHYFROMWKT('{filter_rect.asWktPolygon()}'))"
                    )
                if self._provider._geometry_type in ["NUMBER", "TEXT"]:
                    filter_geom_clause = (
                        f'ST_INTERSECTS(H3_CELL_TO_BOUNDARY("{geom_column}"), '
                        f"ST_GEOGRAPHYFROMWKT('{filter_rect.asWktPolygon()}'))"
                    )
                if filter_geom_clause != "":
                    filter_geom_clause = f"and {filter_geom_clause}"

            # build the complete where clause
            where_clause = ""
            if where_clause_list:
                where_clause = f"where {where_clause_list[0]}"
                if len(where_clause_list) > 1:
                    for clause in where_clause_list[1:]:
                        where_clause += f" and {clause}"

            geom_query = f'ST_ASWKB("{geom_column}"), "{geom_column}", '
            if self._provider._geo_column_type in ["NUMBER", "TEXT"]:
                geom_query = f'"{geom_column}", "{geom_column}", '

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

            filter_geo_type = f"ST_ASGEOJSON(\"{geom_column}\"):type::string IN ('{self._provider._geometry_type}'"
            if mapped_type is not None:
                filter_geo_type += f", '{mapped_type}'"
            filter_geo_type += ")"
            if self._provider._geo_column_type in ["NUMBER", "TEXT"]:
                filter_geo_type = f'H3_IS_VALID_CELL("{geom_column}")'

            order_limit_clause = ""
            if self._provider._is_limited_unordered:
                order_limit_clause = f" ORDER BY RANDOM() LIMIT {limit_size_for_type(self._provider._geo_column_type)}"

            self.final_query = (
                "select * from ("
                f"select {fields_name_for_query} "
                f"{geom_query} {index} "
                f"from {self._provider._from_clause} where {filter_geo_type} {filter_geom_clause}) "
                f"{where_clause}{order_limit_clause}"
            )

            self._result = self._provider.connection_manager.execute_query(
                connection_name=self._provider._connection_name,
                query=self.final_query,
                context_information=self._provider._context_information,
            )
        self._index = 0

    def __try_to_convert_hex_to_int(self, hex_cell: Union[int, str]) -> Union[int, str]:
        """
        Tries to convert a hexadecimal string to an integer.

        Args:
            hex_cell (Union[int, str]): The value to be converted, which can be an integer or a string.

        Returns:
            Union[int, str]: The converted integer if the input is a valid hexadecimal string,
                                    otherwise returns the original input.
        """
        try:
            hex_to_int = int(hex_cell, 16)
            return hex_to_int
        except Exception:
            return hex_cell

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
                    self._cursor_batch_rows = self._result.fetchmany(5000)

                next_result = (
                    self._cursor_batch_rows.pop(0) if self._cursor_batch_rows else None
                )

                if not next_result or not self._provider.isValid():
                    f.setValid(False)
                    self._provider._features_loaded = True
                    return False

                f.setFields(self._provider.fields())

                if not self._request_no_geometry:
                    geometry = QgsGeometry()
                    if self._provider._geo_column_type in ["NUMBER", "TEXT"]:
                        cell = next_result[self.index_geom_column]
                        converted_cell = self.__try_to_convert_hex_to_int(cell)
                        hexVertexCoords = h3.cell_to_boundary(converted_cell)
                        geometry = QgsGeometry.fromPolygonXY(
                            [
                                [QgsPointXY(lon, lat) for lat, lon in hexVertexCoords],
                            ]
                        )
                    else:
                        geometry.fromWkb(next_result[self.index_geom_column])
                    f.setGeometry(geometry)
                    self.geometryToDestinationCrs(f, self._transform)

                f.setId(self._index)

                # # set attributes
                desc_result = self._result.description
                desc_result = list(
                    map(lambda desc: desc.name, self._result.description)
                )
                if self._attributes_need_conversion:
                    if (
                        self._request_sub_attributes
                        and len(self._request.subsetOfAttributes()) > 0
                    ):
                        for idx, attr_idx in enumerate(
                            self._request.subsetOfAttributes()
                        ):
                            attribute = self._attributes_converters[idx](
                                next_result[idx]
                            )
                            f.setAttribute(attr_idx, attribute)
                    else:
                        for indx, field_name in enumerate(
                            self._provider.fields().names()
                        ):
                            try:
                                if (
                                    field_name == self._provider._column_geom
                                    and self._provider._geo_column_type != "NUMBER"
                                ):
                                    continue
                                column_value = next_result[
                                    desc_result.index(field_name)
                                ]
                                converted_attribute = self._attributes_converters[indx](
                                    column_value
                                )
                                f.setAttribute(indx, converted_attribute)
                            except Exception as e:
                                print(
                                    f"Feature Iterator Error - Conversion issue: {str(e)}"
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
                                and self._provider._geo_column_type != "NUMBER"
                            ):
                                continue
                            f.setAttribute(
                                indx, next_result[desc_result.index(field_name)]
                            )
                f.setValid(True)
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
        return True
