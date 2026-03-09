DEFAULT_ROW_LIMIT = 50_000
H3_ROW_LIMIT = 500_000
H3_COLUMN_TYPES = frozenset({"NUMBER", "TEXT", "H3GEO"})


def limit_size_for_type(
    column_type: str,
) -> int:
    """Row-fetch limit based on column type.

    H3 columns (NUMBER/TEXT/H3GEO) use H3_ROW_LIMIT, others use
    DEFAULT_ROW_LIMIT.
    """
    if column_type in H3_COLUMN_TYPES:
        return H3_ROW_LIMIT
    return DEFAULT_ROW_LIMIT


def limit_size_for_table(
    context_information: dict,
) -> int:
    """Row-fetch limit derived from context_information['geom_type']."""
    return limit_size_for_type(context_information["geom_type"])
