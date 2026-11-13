"""Pure helpers for Snowflake Cortex AI_COMPLETE prompts and response parsing."""

from __future__ import annotations

import re
from typing import Any, Iterable, List, Optional, Sequence, Tuple


DEFAULT_SQL_MODEL = "llama3.1-70b"
DEFAULT_MULTIMODAL_MODEL = "claude-3-5-sonnet"

_CODE_FENCE_RE = re.compile(
    r"```(?:sql)?\s*(.*?)```",
    re.IGNORECASE | re.DOTALL,
)


def build_schema_context(
    columns_rows: Sequence[Sequence[Any]],
    max_tables: int = 40,
) -> str:
    """Build a compact TABLE(col TYPE, ...) listing from INFORMATION_SCHEMA rows.

    Expects rows of ``(table_name, column_name, data_type)``. Tables beyond
    ``max_tables`` are omitted so the prompt stays within model context limits.
    """
    tables: dict[str, List[str]] = {}
    for row in columns_rows:
        if len(row) < 3:
            continue
        table_name, column_name, data_type = row[0], row[1], row[2]
        if not table_name or not column_name:
            continue
        table_key = str(table_name)
        if table_key not in tables:
            if len(tables) >= max_tables:
                continue
            tables[table_key] = []
        type_label = str(data_type) if data_type is not None else "UNKNOWN"
        tables[table_key].append(f"{column_name} {type_label}")

    lines = []
    for table_name in sorted(tables.keys()):
        cols = ", ".join(tables[table_name])
        lines.append(f"{table_name}({cols})")
    return "\n".join(lines)


def build_sql_prompt(
    question: str,
    schema_context: str,
    database: str,
    schema: str,
) -> str:
    """Prompt for generating a single read-only Snowflake SELECT."""
    return (
        "You are a Snowflake SQL assistant for QGIS.\n"
        "Write exactly one read-only SELECT statement that answers the question.\n"
        "Rules:\n"
        "- Output only SQL, no commentary.\n"
        "- Use fully qualified names: "
        f'"{database}"."{schema}"."<TABLE>" (or unquoted uppercase identifiers).\n'
        "- Prefer GEOGRAPHY/GEOMETRY columns for spatial results; for H3 cell "
        "ids return the cell id column as-is.\n"
        "- Do not use INSERT, UPDATE, DELETE, MERGE, CREATE, DROP, ALTER, "
        "COPY, PUT, GET, CALL, or EXECUTE.\n"
        "- Prefer LIMIT 50000 when the result may be large.\n"
        f"\nDatabase: {database}\nSchema: {schema}\n"
        f"Tables:\n{schema_context}\n"
        f"\nQuestion: {question}\n"
    )


def extract_sql(response_text: Optional[str]) -> str:
    """Extract the first SQL statement from a model response.

    Strips Markdown code fences and trailing semicolons. Returns an empty
    string when nothing usable is found.
    """
    if not response_text:
        return ""
    text = str(response_text).strip()
    fence = _CODE_FENCE_RE.search(text)
    if fence:
        text = fence.group(1).strip()

    # Drop leading commentary lines until a SELECT-like keyword.
    lines = text.splitlines()
    start = 0
    for idx, line in enumerate(lines):
        stripped = line.strip().lstrip("(").upper()
        if stripped.startswith(
            ("SELECT", "WITH", "SHOW", "DESCRIBE", "DESC ", "EXPLAIN")
        ):
            start = idx
            break
    text = "\n".join(lines[start:]).strip()

    # Keep only the first statement.
    if ";" in text:
        text = text.split(";", 1)[0].strip()
    return text.rstrip(";").strip()


def build_map_context(
    extent_wkt: str,
    scale: float,
    crs_authid: str,
    layer_summaries: Sequence[str],
    max_chars: int = 6000,
) -> str:
    """Build plain-text map context for a multimodal describe prompt."""
    parts = [
        f"CRS: {crs_authid}",
        f"Scale: 1:{int(scale)}" if scale else "Scale: unknown",
        f"Extent (EPSG:4326 WKT): {extent_wkt}",
        "Visible layers (top to bottom):",
    ]
    parts.extend(f"- {summary}" for summary in layer_summaries)
    text = "\n".join(parts)
    if len(text) > max_chars:
        return text[: max_chars - 20] + "\n...[truncated]"
    return text


def summarize_renderer(renderer) -> str:
    """Return a short plain-text summary of a QGIS vector renderer.

    Accepts duck-typed renderer objects so unit tests can pass simple stubs
    without importing PyQGIS.
    """
    if renderer is None:
        return "renderer=none"
    type_name = ""
    if hasattr(renderer, "type"):
        try:
            type_name = str(renderer.type())
        except Exception:
            type_name = renderer.__class__.__name__
    else:
        type_name = renderer.__class__.__name__

    bits = [f"renderer={type_name}"]
    class_attr = getattr(renderer, "classAttribute", None)
    if callable(class_attr):
        try:
            field = class_attr()
            if field:
                bits.append(f"field={field}")
        except Exception:
            pass

    # Graduated / categorized style ranges or categories.
    for attr in ("ranges", "categories", "rootRule"):
        getter = getattr(renderer, attr, None)
        if not callable(getter):
            continue
        try:
            items = getter()
        except Exception:
            continue
        labels: List[str] = []
        if attr == "rootRule":
            children = getattr(items, "children", lambda: [])()
            for child in children[:12]:
                label = getattr(child, "label", lambda: "")()
                if label:
                    labels.append(str(label))
        else:
            for item in list(items)[:12]:
                label = None
                if hasattr(item, "label") and callable(item.label):
                    label = item.label()
                elif hasattr(item, "label"):
                    label = item.label
                if label:
                    labels.append(str(label))
        if labels:
            bits.append("classes=" + "; ".join(labels))
        break

    return ", ".join(bits)


def default_describe_prompt() -> str:
    """Neutral default user prompt for Describe map."""
    return (
        "Describe this map for a GIS analyst. Cover the area shown, what each "
        "visible layer represents, notable patterns or clusters, and one or two "
        "sensible next analysis steps. Use the real layer and field names from "
        "the context."
    )


def build_describe_prompt(user_prompt: str, map_context: str) -> str:
    """Combine the user prompt with structured map context."""
    return (
        f"{user_prompt.strip()}\n\n"
        "Map context:\n"
        f"{map_context}\n"
    )
