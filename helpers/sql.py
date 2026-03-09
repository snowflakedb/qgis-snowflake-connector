"""Centralized SQL quoting utilities for Snowflake identifier and literal safety."""


def quote_identifier(name: str) -> str:
    """Quote a Snowflake identifier (database, schema, table, or column name).

    Wraps in double quotes and escapes internal double quotes per Snowflake
    identifier quoting rules.
    """
    return '"' + name.replace('"', '""') + '"'


def quote_literal(value: str) -> str:
    """Escape a string literal for use in SQL WHERE/ILIKE clauses.

    Wraps in single quotes and escapes internal single quotes.
    """
    return "'" + value.replace("'", "''") + "'"


def qualified_table_name(database: str, schema: str, table: str) -> str:
    """Return a fully qualified and quoted Snowflake table reference."""
    return f"{quote_identifier(database)}.{quote_identifier(schema)}.{quote_identifier(table)}"
