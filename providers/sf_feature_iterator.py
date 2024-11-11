# standard
from __future__ import (
    annotations,  # used to manage type annotation for method that return Self in Python < 3.11
)

from typing import Any, Callable

from PyQt5.QtCore import QDate, QDateTime, QMetaType, QTime

# PyQGIS
from qgis.core import (
    QgsAbstractFeatureIterator,
    QgsCoordinateTransform,
    QgsCsException,
    QgsFeature,
    QgsFeatureRequest,
    QgsGeometry,
)

from ..providers.sf_feature_source import SFFeatureSource


class SFFeatureIterator(QgsAbstractFeatureIterator):
    def __init__(
        self,
        source: SFFeatureSource,
        request: QgsFeatureRequest,
    ):
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

        geom_column = self._provider.get_geometry_column()

        # Mapping between the field type and the conversion function
        attributes_conversion_functions: dict[QMetaType, Callable[[Any], Any]] = {
            QMetaType.QDate: QDate,
            QMetaType.QTime: QTime,
            QMetaType.QDateTime: QDateTime,
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
        if self._request_sub_attributes and not self._provider.subsetString():
            idx_required = [idx for idx in self._request.subsetOfAttributes()]

            # The primary key column must be added if it is not present in the field list.
            if (
                self._provider.primary_key() != -1
                and self._provider.primary_key() not in idx_required
            ):
                idx_required.append(self._provider.primary_key())

            list_field_names = [
                self._provider.fields()[idx].name() for idx in idx_required
            ]
        else:
            list_field_names = [field.name() for field in self._provider.fields()]

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
        if feature_id_list:
            list_feature_id_string = ", ".join(str(x) for x in feature_id_list)
            if self._provider.primary_key() == -1:
                feature_clause = f"sfindexsfrownumberauto in ({list_feature_id_string})"
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
        self._request_no_geometry = (
            self._request.flags() & QgsFeatureRequest.Flag.NoGeometry
        )
        if self._request_no_geometry:
            geom_query = ""

        if self._provider.primary_key() == -1:
            index = "ROW_NUMBER() OVER (order by 1) as sfindexsfrownumberauto "
        else:
            index = self._provider._fields[self._provider.primary_key()].name()

        filter_geo_type = f"ST_ASGEOJSON(\"{geom_column}\"):type ILIKE '{self._provider._geometry_type}'"

        final_query = (
            "select * from ("
            f"select {fields_name_for_query} "
            f"{geom_query} {index} "
            f"from {self._provider._from_clause} where {filter_geo_type} {filter_geom_clause}) "
            f"{where_clause} "
            "ORDER BY RANDOM() LIMIT 10000"
        )

        self._result = self._provider.connection_manager.execute_query(
            connection_name=self._provider._connection_name,
            query=final_query,
            context_information=self._provider._context_information,
        )
        self._index = 0

    def fetchFeature(self, f: QgsFeature) -> bool:
        """fetch next feature, return true on success

        :param f: Next feature
        :type f: QgsFeature
        :return: True if success
        :rtype: bool
        """
        next_result = self._result.fetchone()

        if not next_result or not self._provider.isValid():
            f.setValid(False)
            return False

        f.setFields(self._provider.fields())
        f.setValid(True)

        if not self._request_no_geometry:
            geometry = QgsGeometry()
            geometry.fromWkb(next_result[self.index_geom_column])
            f.setGeometry(geometry)
            self.geometryToDestinationCrs(f, self._transform)

        f.setId(next_result[-1])

        # set attributes
        if self._attributes_need_conversion:
            if self._request_sub_attributes:
                for idx, attr_idx in enumerate(self._request.subsetOfAttributes()):
                    attribute = self._attributes_converters[idx](next_result[idx])
                    f.setAttribute(attr_idx, attribute)
            else:
                for idx, attribute in enumerate(next_result[: self.index_geom_column]):
                    converted_attribute = self._attributes_converters[idx](attribute)
                    f.setAttribute(idx, converted_attribute)
        else:
            if self._request_sub_attributes:
                for idx, attr_idx in enumerate(self._request.subsetOfAttributes()):
                    f.setAttribute(attr_idx, next_result[idx])
            else:
                f.setAttributes(list(next_result[: self.index_geom_column]))

        self._index += 1
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
        f = QgsFeature()
        if not self.nextFeature(f):
            raise StopIteration
        else:
            return f

    def rewind(self) -> bool:
        """reset the iterator to the starting position"""
        if self._index < 0:
            return False
        self._index = 0
        return True

    def close(self) -> bool:
        """end of iterating: free the resources / lock"""
        self._index = -1
        return True
