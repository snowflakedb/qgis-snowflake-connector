"""Safe QGIS-expression -> Snowflake SQL compilation.

QGIS feature requests (filter expressions) and layer subset strings can carry
attacker-influenceable predicates that QGIS persists verbatim inside .qgs/.qgz
project files. Concatenating that text straight into SQL is a SQL-injection sink
(SNOW-3712078 / SNOW-3712093).

Instead of trusting the text, we compile it through ``QgsSqlExpressionCompiler``,
which only emits SQL for a known set of operators/functions and routes every
identifier and literal through our quoting helpers. Anything that does not
compile *completely* is refused, so raw predicate text is never pushed down to
Snowflake; the caller falls back to client-side filtering (or rejects the
subset string).
"""

from typing import Optional

from qgis.core import QgsExpression, QgsFields, QgsSqlExpressionCompiler

from .sql import quote_identifier, quote_literal


class SFExpressionCompiler(QgsSqlExpressionCompiler):
    """QgsSqlExpressionCompiler that quotes for Snowflake via the central
    helpers (so identifiers and string literals are backslash/quote safe)."""

    def __init__(self, fields: QgsFields):
        super().__init__(
            fields,
            QgsSqlExpressionCompiler.Flags(),
            False,
        )

    def quotedIdentifier(self, identifier: str) -> str:
        return quote_identifier(identifier)

    def quotedValue(self, value, ok):
        # The C++ signature passes ``ok`` by reference; the PyQGIS override
        # returns a ``(sql, ok)`` tuple instead.
        if value is None:
            return "NULL", True
        if isinstance(value, bool):
            return ("TRUE" if value else "FALSE"), True
        if isinstance(value, (int, float)):
            return str(value), True
        return quote_literal(str(value)), True


def compile_expression_to_sql(
    expression_text: str, fields: QgsFields
) -> Optional[str]:
    """Return safe Snowflake SQL for ``expression_text``, or ``None`` if it
    cannot be fully and safely compiled.

    ``None`` means the caller MUST NOT push the predicate down (filter
    client-side or reject it); it must never fall back to using the raw text.
    """
    if not expression_text or fields is None:
        return None
    try:
        expression = QgsExpression(expression_text)
        if expression.hasParserError():
            return None
        compiler = SFExpressionCompiler(fields)
        if compiler.compile(expression) == QgsSqlExpressionCompiler.Complete:
            compiled = compiler.result()
            return compiled or None
    except Exception:
        return None
    return None
