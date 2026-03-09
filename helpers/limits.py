def limit_size_for_type(
    column_type: str,
) -> int:
    """
    The limit number of rows to be fetched from a table. Currently 50k by default, and 500k for H3 columns

    Args:
        column_type (str): The type of the column

    Returns:
        int: The size limit.
    """
    if column_type in ["NUMBER", "TEXT", "H3GEO"]:
        return 500000  # 500k
    return 50000  # 50k


def limit_size_for_table(
    context_information: dict,
) -> int:
    """
    The limit number of rows to be fetched from a table. Currently based on type

    Args:
        context_information (dict): A dictionary containing context information, including the column type.

    Returns:
        int: The size limit.
    """
    return limit_size_for_type(context_information["geom_type"])
