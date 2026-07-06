"""Centralized SQL quoting utilities for Snowflake identifier and literal safety."""

import re

_SIMPLE_IDENT = re.compile(r'^[A-Za-z_][A-Za-z0-9_$]*$')


def _is_wellformed_quoted_identifier(name: str) -> bool:
    """True only when ``name`` is a single, correctly-quoted Snowflake
    identifier: it is wrapped in double quotes and every interior double quote
    is doubled (escaped).  A value like ``"a""b"`` is well-formed; a value like
    ``"x" AS SELECT ...--"`` is not, because it carries un-doubled interior
    quotes that would break out of the identifier context.
    """
    if len(name) < 2 or not name.startswith('"') or not name.endswith('"'):
        return False
    return '"' not in name[1:-1].replace('""', "")


def quote_identifier(name: str) -> str:
    """Quote a Snowflake identifier only when necessary.

    Simple identifiers (letters, digits, underscores) are left unquoted so
    Snowflake applies its default uppercasing.  A value that is already a
    single well-formed quoted identifier is preserved; anything else — including
    strings that merely start and end with a double quote but hide un-doubled
    interior quotes — is fully re-escaped so it cannot break out of the
    identifier context (SNOW-3712084).
    """
    if _is_wellformed_quoted_identifier(name):
        return name
    if _SIMPLE_IDENT.match(name):
        return name
    return '"' + name.replace('"', '""') + '"'


def quote_literal(value: str) -> str:
    """Escape a string literal for use in SQL WHERE/ILIKE clauses.

    Snowflake single-quoted string constants treat the backslash as an escape
    character, so ``\\'`` is parsed as a literal apostrophe rather than a
    backslash followed by a quote.  Doubling single quotes alone is therefore
    insufficient: a value ending in a backslash would let an attacker break out
    of the literal (SNOW-3712090 / SNOW-3712092).  Escape backslashes first,
    then single quotes.
    """
    return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


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


_SQL_STATEMENT_BREAKERS = re.compile(
    r"--|/\*|\*/|;|\bUNION\b|\bINTERSECT\b|\bEXCEPT\b|\bMINUS\b",
    re.IGNORECASE,
)


def predicate_has_statement_breakers(predicate: str) -> bool:
    """Heuristic guard for a free-text SQL predicate (e.g. a Processing
    WHERE-clause parameter).

    Returns True when the text contains tokens that could terminate the
    statement (``;``), start a comment (``--`` / ``/* */``) to swallow the rest
    of the query, or splice in a set operation (``UNION`` / ``INTERSECT`` /
    ``EXCEPT`` / ``MINUS``) used for cross-table exfiltration (SNOW-3712086).
    This is an intentionally conservative blocklist for the one place that must
    accept raw SQL from the user; identifier/literal inputs use the quoting
    helpers instead.
    """
    if not predicate:
        return False
    return bool(_SQL_STATEMENT_BREAKERS.search(predicate))
