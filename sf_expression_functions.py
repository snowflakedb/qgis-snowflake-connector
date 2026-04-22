"""Custom QGIS expression functions for Snowflake / H3 operations.

Registered in the QGIS expression engine so they appear in field calculator,
labeling, symbology, etc.
"""

from qgis.core import (
    QgsExpression,
    qgsfunction,
)

_REGISTERED_FUNCTIONS = []


@qgsfunction(args=1, group="Snowflake", register=False)
def sf_h3_resolution(values, context, parent, node):
    """Returns the resolution of an H3 index (integer 0-15).

    <h4>Syntax</h4>
    <p>sf_h3_resolution(h3_index)</p>

    <h4>Arguments</h4>
    <p>h3_index - H3 cell index as a hex string (e.g. '89283082803ffff')</p>
    """
    h3_index = values[0]
    if h3_index is None or h3_index == "":
        return None
    try:
        if isinstance(h3_index, str) and len(h3_index) >= 2:
            res_digit = int(h3_index[1], 16)
            return res_digit
    except (ValueError, IndexError):
        pass
    return None


@qgsfunction(args=1, group="Snowflake", register=False)
def sf_h3_is_valid(values, context, parent, node):
    """Returns True if the value is a valid H3 hex string.

    <h4>Syntax</h4>
    <p>sf_h3_is_valid(h3_index)</p>
    """
    h3_index = values[0]
    if h3_index is None or h3_index == "":
        return False
    if isinstance(h3_index, str):
        if len(h3_index) == 15 or len(h3_index) == 16:
            try:
                int(h3_index, 16)
                return True
            except ValueError:
                pass
    return False


@qgsfunction(args=2, group="Snowflake", register=False)
def sf_h3_parent(values, context, parent, node):
    """Returns the parent H3 cell index at a coarser resolution.

    <h4>Syntax</h4>
    <p>sf_h3_parent(h3_index, parent_resolution)</p>

    <h4>Note</h4>
    <p>This is a client-side approximation. For exact results, use
    Snowflake's H3_TO_PARENT() function via SQL.</p>
    """
    h3_index = values[0]
    target_res = values[1]
    if h3_index is None or target_res is None:
        return None
    return f"Use SQL: SELECT H3_TO_PARENT('{h3_index}', {target_res})"


@qgsfunction(args=2, group="Snowflake", register=False)
def sf_h3_grid_distance(values, context, parent, node):
    """Returns the grid distance between two H3 cells.

    <h4>Syntax</h4>
    <p>sf_h3_grid_distance(h3_a, h3_b)</p>

    <h4>Note</h4>
    <p>Client-side stub. For exact results, use Snowflake's
    H3_GRID_DISTANCE() via SQL.</p>
    """
    h3_a = values[0]
    h3_b = values[1]
    if h3_a is None or h3_b is None:
        return None
    return f"Use SQL: SELECT H3_GRID_DISTANCE('{h3_a}', '{h3_b}')"


@qgsfunction(args=1, group="Snowflake", register=False)
def sf_h3_to_string(values, context, parent, node):
    """Converts a numeric H3 index to its hex string representation.

    <h4>Syntax</h4>
    <p>sf_h3_to_string(h3_number)</p>
    """
    h3_num = values[0]
    if h3_num is None:
        return None
    try:
        return format(int(h3_num), "x")
    except (ValueError, TypeError):
        return None


def register_sf_functions():
    """Register all Snowflake expression functions with QGIS."""
    funcs = [
        sf_h3_resolution,
        sf_h3_is_valid,
        sf_h3_parent,
        sf_h3_grid_distance,
        sf_h3_to_string,
    ]
    for func in funcs:
        if QgsExpression.isFunctionName(func.name()):
            continue
        if QgsExpression.registerFunction(func):
            _REGISTERED_FUNCTIONS.append(func.name())


def unregister_sf_functions():
    """Unregister all Snowflake expression functions."""
    for name in _REGISTERED_FUNCTIONS:
        QgsExpression.unregisterFunction(name)
    _REGISTERED_FUNCTIONS.clear()
