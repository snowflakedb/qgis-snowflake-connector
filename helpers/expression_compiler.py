"""Safe QGIS-expression -> Snowflake SQL compilation.

QGIS feature requests (filter expressions) and layer subset strings can carry
attacker-influenceable predicates that QGIS persists verbatim inside .qgs/.qgz
project files. Concatenating that text straight into SQL is a SQL-injection sink
(SNOW-3712078 / SNOW-3712093).

Instead of trusting the text, we parse it with ``QgsExpression`` and walk the
resulting AST ourselves, emitting Snowflake SQL only for a small whitelist of
node types and operators and routing every identifier and literal through our
quoting helpers. Anything outside that whitelist makes the whole compilation
fail (returns ``None``), so raw predicate text is never pushed down to
Snowflake; the caller falls back to client-side filtering (or rejects the
subset string).

Note: QGIS' own C++ SQL expression compiler is deliberately *not* exposed in
the Python bindings, so we cannot subclass it; the ``QgsExpression`` AST node
API used here is the supported PyQGIS surface.
"""

from typing import Optional

from qgis.core import (
    QgsExpression,
    QgsExpressionNodeBinaryOperator,
    QgsExpressionNodeColumnRef,
    QgsExpressionNodeInOperator,
    QgsExpressionNodeLiteral,
    QgsExpressionNodeUnaryOperator,
    QgsFields,
)

from .sql import quote_identifier, quote_literal


def _resolve_enum(owner, nested_name: str, member: str):
    """Resolve an enum member that may be exposed unscoped on ``owner`` or
    scoped under ``owner.<nested_name>`` depending on the PyQGIS build."""
    if hasattr(owner, member):
        return getattr(owner, member)
    nested = getattr(owner, nested_name, None)
    if nested is not None and hasattr(nested, member):
        return getattr(nested, member)
    return None


# Map the safe subset of QGIS binary operators to their Snowflake SQL spelling.
# Arithmetic / concat / regexp / power / integer-div are intentionally omitted
# so only boolean predicates ever compile.
_BINARY_SQL = {}
for _member, _sql in (
    ("boEQ", "="),
    ("boNE", "<>"),
    ("boLE", "<="),
    ("boGE", ">="),
    ("boLT", "<"),
    ("boGT", ">"),
    ("boAnd", "AND"),
    ("boOr", "OR"),
    ("boLike", "LIKE"),
    ("boILike", "ILIKE"),
    ("boNotLike", "NOT LIKE"),
    ("boNotILike", "NOT ILIKE"),
    ("boIs", "IS"),
    ("boIsNot", "IS NOT"),
):
    _key = _resolve_enum(QgsExpressionNodeBinaryOperator, "BinaryOperator", _member)
    if _key is not None:
        _BINARY_SQL[_key] = _sql

_UO_NOT = _resolve_enum(QgsExpressionNodeUnaryOperator, "UnaryOperator", "uoNot")


def _compile_column(node, fields: QgsFields) -> Optional[str]:
    if fields is None:
        return None
    idx = fields.lookupField(node.name())
    if idx < 0:
        return None
    # Emit the canonical field name from the layer, not the raw reference.
    return quote_identifier(fields.at(idx).name())


def _compile_literal(node) -> Optional[str]:
    value = node.value()
    if value is None:
        return "NULL"
    # bool must be checked before int (bool is a subclass of int).
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(value)
    if isinstance(value, str):
        return quote_literal(value)
    return None


def _compile_unary(node, fields: QgsFields) -> Optional[str]:
    if _UO_NOT is None or node.op() != _UO_NOT:
        return None
    operand = _compile_node(node.operand(), fields)
    if operand is None:
        return None
    return f"(NOT {operand})"


def _compile_binary(node, fields: QgsFields) -> Optional[str]:
    sql_op = _BINARY_SQL.get(node.op())
    if sql_op is None:
        return None
    left = _compile_node(node.opLeft(), fields)
    right = _compile_node(node.opRight(), fields)
    if left is None or right is None:
        return None
    return f"({left} {sql_op} {right})"


def _compile_in(node, fields: QgsFields) -> Optional[str]:
    left = _compile_node(node.node(), fields)
    if left is None:
        return None
    node_list = node.list()
    if node_list is None:
        return None
    members = node_list.list()
    if not members:
        return None
    compiled_members = []
    for member in members:
        compiled = _compile_node(member, fields)
        if compiled is None:
            return None
        compiled_members.append(compiled)
    keyword = "NOT IN" if node.isNotIn() else "IN"
    return f"({left} {keyword} ({', '.join(compiled_members)}))"


def _compile_node(node, fields: QgsFields) -> Optional[str]:
    if node is None:
        return None
    if isinstance(node, QgsExpressionNodeColumnRef):
        return _compile_column(node, fields)
    if isinstance(node, QgsExpressionNodeLiteral):
        return _compile_literal(node)
    if isinstance(node, QgsExpressionNodeUnaryOperator):
        return _compile_unary(node, fields)
    if isinstance(node, QgsExpressionNodeBinaryOperator):
        return _compile_binary(node, fields)
    if isinstance(node, QgsExpressionNodeInOperator):
        return _compile_in(node, fields)
    # Functions, CASE/condition, BETWEEN, index operators, etc. are refused.
    return None


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
        root = expression.rootNode()
        if root is None:
            return None
        return _compile_node(root, fields) or None
    except Exception:
        return None
