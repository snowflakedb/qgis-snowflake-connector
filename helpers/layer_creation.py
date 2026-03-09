import typing
from ..providers.sf_data_source_provider import SFDataProvider
from qgis.core import (
    QgsFeature,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsTask,
    QgsVectorLayer,
    Qgis, NULL)
from qgis.PyQt.QtCore import QVariant
from typing import Dict, Union


def get_layers(
    auth_information: dict,
    layer_pre_name: str,
    query: str,
    connection_name: str,
    geo_column_name: str,
    task: QgsTask,
    srid: int = 4326,
) -> tuple[bool, list]:
    """
    Retrieves layers from a data source based on the provided query and connection information.

    Args:
        auth_information (dict): Authentication information required to access the data source.
        layer_pre_name (str): Prefix for the layer names.
        query (str): SQL query to retrieve the data.
        connection_name (str): Name of the connection to the data source.
        geo_column_name (str): Name of the column containing geometry data.
        task (QgsTask): Task object to handle task cancellation.

    Returns:
        tuple[bool, list]: A tuple containing a boolean indicating success or failure, and a list of layers.
    """
    feature_fields_list: QgsFields = None
    sf_data_provider = SFDataProvider(auth_information)

    sf_data_provider.load_data(query, connection_name)
    feature_iterator = sf_data_provider.get_feature_iterator()

    int_count = 0

    layer_dict: Dict[str, Dict[str, Union[list, QgsVectorLayer]]] = {}
    for feat in feature_iterator:
        if task.isCanceled():
            return False, []
        if feature_fields_list is None:
            feature_fields_list = fill_feature_fields_list_no_geo(feat, geo_column_name)
        feat_index = feat.fieldNameIndex(geo_column_name)
        column_0 = feat.attribute(feat_index)
        if isinstance(column_0, QVariant):
            if column_0.isNull():
                continue
        if column_0 is None:
            continue
        qgsGeometry = QgsGeometry()
        qgsGeometry.fromWkb(column_0)
        geometry_type_obj = qgsGeometry.wkbType()
        geometry_type = get_wkb_type_name(geometry_type_obj)

        if geometry_type == "Unknown":
            continue

        feature = QgsFeature(feature_fields_list)
        type_not_supported = add_layer_for_geometry_type(
            geometry_type=geometry_type,
            layer_pre_name=layer_pre_name,
            layer_dict=layer_dict,
            srid=srid,
        )
        if type_not_supported:
            continue
        feature.setGeometry(qgsGeometry)
        set_feature_attributes_values(feat, feature, geo_column_name)
        layer_dict[geometry_type]["features"].append(feature)
        int_count += 1

    feature_iterator.close()

    if int_count == 0:
        return True, []

    return True, add_features_attributes_to_layer(
        feature_fields_list=feature_fields_list,
        geo_column_name=geo_column_name,
        layer_dict=layer_dict,
    )


def add_layer_for_geometry_type(
    geometry_type: str,
    layer_pre_name: str,
    layer_dict: Dict[str, Dict[str, Union[list, QgsVectorLayer]]],
    srid: int = 4326,
) -> bool:
    """
    Adds a new layer to the layer dictionary for the specified geometry type.

    Args:
        geometry_type (str): The type of geometry for the layer (e.g., "point", "linestring").
        layer_pre_name (str): The prefix name for the layer.
        layer_dict (Dict[str, Dict[str, Union[list, QgsVectorLayer]]]): The dictionary to store layers and their features.

    Returns:
        bool: True if the geometry type is invalid, False otherwise.
    """
    if geometry_type not in layer_dict:
        if geometry_type.lower() not in [
            "point",
            "multipoint",
            "linestring",
            "multilinestring",
            "polygon",
            "multipolygon",
        ]:
            return True
        layer_name = f"{layer_pre_name}_{geometry_type}"
        layer_dict[geometry_type] = {
            "features": [],
            "layer": QgsVectorLayer(
                f"{geometry_type}?crs=epsg:{srid}&internal_provider=snowflake",
                layer_name,
                "memory",
            ),
        }
        return False


def fill_feature_fields_list_no_geo(
    feat: QgsFeature, geo_column_name: str
) -> QgsFields:
    """
    Creates a QgsFields object containing all fields from the given QgsFeature
    except the one specified by geo_column_name.

    Args:
        feat (QgsFeature): The feature from which to extract fields.
        geo_column_name (str): The name of the field to exclude.

    Returns:
        QgsFields: A QgsFields object containing all fields except the specified one.
    """
    feature_fields_list = QgsFields()
    for field in feat.fields():
        if field.name() == geo_column_name:
            continue
        feature_fields_list.append(field)
    return feature_fields_list


def set_feature_attributes_values(
    iterate_feature: QgsFeature, feature: QgsFeature, geo_column_name: str
) -> None:
    """
    Sets the attribute values of a given feature based on another feature's attributes,
    excluding the geometry column.

    Args:
        iterate_feature (QgsFeature): The feature from which to copy attribute values.
        feature (QgsFeature): The feature to which attribute values will be set.
        geo_column_name (str): The name of the geometry column to be excluded from copying.

    Notes:
        - If the attribute value is a QVariant and is null, or if the attribute value is None,
          the corresponding attribute in the target feature is set to a null QVariant.
        - Attribute values are cast to their appropriate types (String, Int, Double, Bool) before
          being set in the target feature.
    """
    for field in iterate_feature.fields():
        if field.name() == geo_column_name:
            continue
        field_id = iterate_feature.fieldNameIndex(field.name())
        field_value = iterate_feature.attribute(field_id)
        if isinstance(field_value, QVariant):
            if field_value.isNull():
                feature.setAttribute(field.name(), NULL)
                continue
        if field_value is None:
            feature.setAttribute(field.name(), NULL)
            continue

        if field.type() == QMetaType.Type.QString:
            field_value = str(field_value)
        if field.type() == QMetaType.Type.Int:
            field_value = int(field_value)
        if field.type() == QMetaType.Type.Double:
            field_value = float(field_value)
        if field.type() == QMetaType.Type.Bool:
            field_value = bool(field_value)

        feature.setAttribute(field.name(), field_value)


def add_features_attributes_to_layer(
    feature_fields_list: QgsFields,
    geo_column_name: str,
    layer_dict: Dict[str, Dict[str, Union[list, QgsVectorLayer]]],
) -> list:
    """
    Adds attributes and features to layers based on the provided fields and layer dictionary.

    Args:
        feature_fields_list (QgsFields): A list of fields to be added to the layers.
        geo_column_name (str): The name of the geometry column to be excluded from the fields.
        layer_dict (Dict[str, Dict[str, Union[list, QgsVectorLayer]]]): A dictionary containing layer types as keys and
            dictionaries with 'features' (list of features) and 'layer' (QgsVectorLayer) as values.

    Returns:
        list: A list of QgsVectorLayer objects that have been updated with new attributes and features.
    """
    layers = []
    layer_fields = []
    for layer_field in feature_fields_list:
        if layer_field.name() == geo_column_name:
            continue
        layer_fields.append(
            QgsField(layer_field.name(), QMetaType.Type.QString, subType=layer_field.subType())
        )

    for layer_type in layer_dict:
        layer_dict[layer_type]["layer"].startEditing()
        layer_dict[layer_type]["layer"].dataProvider().addAttributes(layer_fields)
        layer_dict[layer_type]["layer"].updateFields()

        layer_dict[layer_type]["layer"].dataProvider().addFeatures(
            layer_dict[layer_type]["features"]
        )
        layer_dict[layer_type]["layer"].commitChanges()
        layers.append(layer_dict[layer_type]["layer"])
    return layers


def check_table_exceeds_size(
    auth_information: dict,
    table_information: dict,
    connection_name: str,
    limit_size: int = 50000,
) -> bool:
    """
    Checks if the number of rows in a specified table exceeds a given limit.

    Args:
        auth_information (dict): Authentication information required to connect to the database.
        table_information (dict): Information about the table to check, including keys 'database', 'schema', and 'table'.
        connection_name (str): The name of the connection to use for executing the query.
        limit_size (int, optional): The row count limit to check against. Defaults to 1,000,000.

    Returns:
        bool: True if the number of rows in the table exceeds the limit, False otherwise.
    """
    sf_data_provider = SFDataProvider(auth_information)
    data_base_name = table_information["database"]
    schema_name = table_information["schema"]
    table_name = table_information["table"]
    qre = f'SELECT count(*) FROM "{data_base_name}"."{schema_name}"."{table_name}"'
    cur_count = sf_data_provider.execute_query(
        query=qre,
        connection_name=connection_name,
    )

    count_tuple = cur_count.fetchone()
    cur_count.close()

    if count_tuple[0] > limit_size:
        return True
    return False


def get_wkb_type_name(type_value: int) -> str:
    """
    Returns the name of the WKB (Well-Known Binary) type given its integer value.

    Args:
        type_value (int): The integer value representing the WKB type.

    Returns:
        str: The name of the WKB type. If the type_value is not found, returns "Unknown".
    """
    value_to_name = {
        v: k for k, v in Qgis.WkbType.__dict__.items() if isinstance(v, int)
    }

    return value_to_name.get(type_value, "Unknown")


def get_srid_from_table(
    auth_information: dict,
    table_information: dict,
    connection_name: str,
    column_name: str,
    context_information: typing.Dict[str, typing.Union[str, None]] = None,
) -> int:
    """
    Retrieves the SRID (Spatial Reference Identifier) for a specified column in a table.

    Args:
        auth_information (dict): Authentication information required to connect to the database.
        table_information (dict): Information about the table, including keys 'database', 'schema', and 'table'.
        connection_name (str): The name of the connection to use for executing the query.
        column_name (str): The name of the column for which to retrieve the SRID.

    Returns:
        int: The SRID for the specified column.
    """
    sf_data_provider = SFDataProvider(auth_information)
    data_base_name = table_information["database"]
    schema_name = table_information["schema"]
    table_name = table_information["table"]
    qre = f'SELECT ANY_VALUE(ST_SRID("{column_name}")) FROM "{data_base_name}"."{schema_name}"."{table_name}"'
    cur_srid = sf_data_provider.execute_query(
        query=qre,
        connection_name=connection_name,
        context_information=context_information,
    )

    srid = cur_srid.fetchone()[0]
    cur_srid.close()

    return srid
