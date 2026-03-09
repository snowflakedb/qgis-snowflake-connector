"""Centralized SQL quoting utilities for Snowflake identifier and literal safety."""

import re

_SIMPLE_IDENT = re.compile(r'^[A-Za-z_][A-Za-z0-9_$]*$')


def quote_identifier(name: str) -> str:
    """Quote a Snowflake identifier only when necessary.

    Simple identifiers (letters, digits, underscores) are left unquoted so
    Snowflake applies its default uppercasing.  Names that contain spaces,
    special characters, or are already double-quoted are wrapped/preserved.
    """
    if name.startswith('"') and name.endswith('"'):
        return name
    if _SIMPLE_IDENT.match(name):
        return name
    return '"' + name.replace('"', '""') + '"'


def quote_literal(value: str) -> str:
    """Escape a string literal for use in SQL WHERE/ILIKE clauses.

    Wraps in single quotes and escapes internal single quotes.
    """
    return "'" + value.replace("'", "''") + "'"


def quote_json_literal_for_parse_json(value: str) -> str:
    """Quote JSON text for PARSE_JSON input safely.

    Prefer Snowflake dollar-quoting to avoid conflicts with apostrophes inside
    JSON strings. Strict mode: if payload contains "$$", raise an error.
    """
    delimiter = "$$"
    if delimiter not in value:
        return f"{delimiter}{value}{delimiter}"
    raise ValueError('JSON payload contains "$$" delimiter; cannot use strict $$ quoting')


def qualified_table_name(database: str, schema: str, table: str) -> str:
    """Return a fully qualified and quoted Snowflake table reference."""
    return f"{quote_identifier(database)}.{quote_identifier(schema)}.{quote_identifier(table)}"
