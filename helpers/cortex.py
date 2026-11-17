"""Pure helpers for Snowflake Cortex AI_COMPLETE prompts and response parsing."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple


DEFAULT_SQL_MODEL = "llama3.1-70b"
DEFAULT_MULTIMODAL_MODEL = "claude-3-5-sonnet"

# Used when SHOW CORTEX BASE MODELS is unavailable or returns nothing.
FALLBACK_SQL_MODELS = (
    DEFAULT_SQL_MODEL,
    "llama3.1-8b",
    "llama3.3-70b",
    "mistral-large2",
    "snowflake-arctic",
)
FALLBACK_MULTIMODAL_MODELS = (
    DEFAULT_MULTIMODAL_MODEL,
    "pixtral-large",
    "claude-sonnet-4-5",
    "openai-gpt-5",
)

# SHOW CORTEX BASE MODELS has no modality column; use name heuristics.
_MULTIMODAL_NAME_HINTS = (
    "claude",
    "pixtral",
    "gemini",
    "openai-gpt",
    "gpt-4o",
    "qwen3-vl",
    "llama4",
)
_EMBEDDING_NAME_HINTS = (
    "e5-",
    "embed",
    "nv-embed",
)
_EXCLUDED_LIFECYCLE = frozenset({"EOL", "PRIVATE PREVIEW"})

BRIEF_SECTIONS = (
    "Seen in the image",
    "From layer settings",
    "Not determinable from this view",
    "Suggested next steps",
)

_CODE_FENCE_RE = re.compile(
    r"```(?:sql)?\s*(.*?)```",
    re.IGNORECASE | re.DOTALL,
)

_HEADING_RE = re.compile(
    r"^\s{0,3}(?:#{1,6}\s*|\*\*|__)?\s*(?P<title>.+?)\s*(?:\*\*|__)?\s*$",
    re.IGNORECASE,
)


def is_likely_embedding_model(name: str) -> bool:
    """Return True when ``name`` looks like an embedding model, not AI_COMPLETE."""
    lowered = (name or "").strip().lower()
    return bool(lowered) and any(hint in lowered for hint in _EMBEDDING_NAME_HINTS)


def is_arctic_task_model(name: str) -> bool:
    """Return True for ARCTIC-* task models (not snowflake-arctic chat)."""
    return (name or "").strip().upper().startswith("ARCTIC-")


def is_likely_multimodal_model(name: str) -> bool:
    """Return True when ``name`` looks usable with image/PROMPT+TO_FILE inputs."""
    lowered = (name or "").strip().lower()
    return bool(lowered) and any(
        lowered.startswith(hint) or hint in lowered for hint in _MULTIMODAL_NAME_HINTS
    )


def normalize_cortex_text(text: Optional[str]) -> str:
    """Strip quote-wrapping that AI_COMPLETE sometimes adds around plain text.

    When the model returns a single line with literal ``\\n`` escapes (no real
    newlines), expand those escapes so Map brief section headings can parse.
    """
    if not text:
        return ""
    result = str(text).strip()
    if len(result) >= 2 and result[0] == result[-1] == '"':
        result = result[1:-1].strip()
    if result.startswith('"'):
        result = result[1:].lstrip()
    if result.endswith('"'):
        result = result[:-1].rstrip()
    # Only unescape when there are no real newlines — otherwise leave intact.
    if "\n" not in result and "\\n" in result:
        result = (
            result.replace("\\n", "\n")
            .replace("\\t", "\t")
            .replace('\\"', '"')
        )
    return result


def parse_cortex_base_model_rows(
    rows: Sequence[Sequence[Any]],
    description: Optional[Sequence[Sequence[Any]]] = None,
) -> List[str]:
    """Extract usable Cortex base model names from a SHOW result.

    Skips blank names and models whose lifecycle status is ``EOL`` or
    ``PRIVATE PREVIEW``. When ``description`` is omitted, column 1 is treated
    as ``name`` and column 6 (0-based index 6) as ``lifecycle_status``,
    matching the documented ``SHOW CORTEX BASE MODELS`` output order.
    """
    name_idx = 1
    lifecycle_idx: Optional[int] = 6
    if description:
        headers = [str(col[0]).lower() for col in description]
        if "name" in headers:
            name_idx = headers.index("name")
        lifecycle_idx = (
            headers.index("lifecycle_status")
            if "lifecycle_status" in headers
            else None
        )

    names: List[str] = []
    seen = set()
    for row in rows:
        if not row or len(row) <= name_idx:
            continue
        name = str(row[name_idx] or "").strip()
        if not name or name.lower() in seen:
            continue
        if lifecycle_idx is not None and len(row) > lifecycle_idx:
            status = str(row[lifecycle_idx] or "").strip().upper()
            if status in _EXCLUDED_LIFECYCLE:
                continue
        seen.add(name.lower())
        names.append(name)
    names.sort(key=str.lower)
    return names


def models_for_ask_snowflake(available: Sequence[str]) -> List[str]:
    """Models suitable for Ask Snowflake (text AI_COMPLETE)."""
    filtered = [
        name
        for name in available
        if name
        and not is_likely_embedding_model(name)
        and not is_arctic_task_model(name)
        and not is_likely_multimodal_model(name)
    ]
    return filtered or list(FALLBACK_SQL_MODELS)


def models_for_map_brief(available: Sequence[str]) -> List[str]:
    """Models suitable for Map brief (multimodal AI_COMPLETE)."""
    filtered = [
        name
        for name in available
        if name
        and not is_likely_embedding_model(name)
        and is_likely_multimodal_model(name)
    ]
    return filtered or list(FALLBACK_MULTIMODAL_MODELS)


def choose_model(
    available: Sequence[str],
    preferred: Optional[str],
    default: str,
) -> str:
    """Pick a model for a combo box from available names."""
    names = [n for n in available if n]
    preferred_name = (preferred or "").strip()
    if preferred_name and any(n.lower() == preferred_name.lower() for n in names):
        for n in names:
            if n.lower() == preferred_name.lower():
                return n
    if default and any(n.lower() == default.lower() for n in names):
        for n in names:
            if n.lower() == default.lower():
                return n
    return names[0] if names else default


def fetch_cortex_base_models(connection_name: str) -> List[str]:
    """List Cortex base models available to the current role on ``connection_name``.

    Runs ``SHOW CORTEX BASE MODELS IN SCHEMA SNOWFLAKE.MODELS``. Returns an
    empty list when the command fails or the account does not support it; callers
    should fall back to :data:`FALLBACK_SQL_MODELS` /
    :data:`FALLBACK_MULTIMODAL_MODELS`.
    """
    if not connection_name:
        return []
    try:
        from ..managers.sf_connection_manager import SFConnectionManager, build_op_tag

        manager = SFConnectionManager.get_instance()
        cursor = manager.execute_query(
            connection_name=connection_name,
            query="SHOW CORTEX BASE MODELS IN SCHEMA SNOWFLAKE.MODELS",
            context_information={"connection_name": connection_name},
            op_tag=build_op_tag(
                "list_cortex_models",
                connection_name=connection_name,
                kind="sql",
            ),
        )
        rows = cursor.fetchall() if cursor else []
        description = cursor.description if cursor else None
        if cursor:
            cursor.close()
        return parse_cortex_base_model_rows(rows, description)
    except Exception:
        return []


def build_schema_context(
    columns_rows: Sequence[Sequence[Any]],
    max_tables: int = 40,
    max_chars: int = 12000,
) -> Tuple[str, int]:
    """Build a compact TABLE(col TYPE, ...) listing from INFORMATION_SCHEMA rows.

    Expects rows of ``(table_name, column_name, data_type)``. Tables beyond
    ``max_tables`` or the character budget are omitted. Returns
    ``(context_text, omitted_table_count)``.
    """
    tables: dict[str, List[str]] = {}
    seen_after_cap = 0
    for row in columns_rows:
        if len(row) < 3:
            continue
        table_name, column_name, data_type = row[0], row[1], row[2]
        if not table_name or not column_name:
            continue
        table_key = str(table_name)
        if table_key not in tables:
            if len(tables) >= max_tables:
                seen_after_cap += 1
                continue
            tables[table_key] = []
        type_label = str(data_type) if data_type is not None else "UNKNOWN"
        tables[table_key].append(f"{column_name} {type_label}")

    lines = []
    omitted = seen_after_cap
    for table_name in sorted(tables.keys()):
        cols = ", ".join(tables[table_name])
        line = f"{table_name}({cols})"
        candidate = "\n".join(lines + [line])
        if lines and len(candidate) > max_chars:
            omitted += 1
            continue
        if not lines and len(line) > max_chars:
            line = line[: max_chars - 20] + "...[truncated]"
        lines.append(line)
    return "\n".join(lines), omitted


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

    if ";" in text:
        text = text.split(";", 1)[0].strip()
    text = text.rstrip(";").strip()
    # Models sometimes wrap the statement in quotes: "SELECT …"
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "'\"":
        inner = text[1:-1].strip()
        upper = inner.lstrip("(").upper()
        if upper.startswith(
            ("SELECT", "WITH", "SHOW", "DESCRIBE", "DESC ", "EXPLAIN")
        ):
            text = inner
    return text


def assess_view(
    visible_layer_count: int,
    layer_extents_intersect: bool,
    image_nearly_uniform: bool,
) -> List[str]:
    """Return short warnings about the current map view before Cortex is called.

    Pure decision logic so unit tests do not need PyQGIS. Callers collect the
    inputs from the canvas and a rendered image.
    """
    warnings: List[str] = []
    if visible_layer_count <= 0:
        warnings.append("No visible layers on the map canvas.")
    elif not layer_extents_intersect:
        warnings.append(
            "No visible layer extent intersects the current map view."
        )
    if image_nearly_uniform:
        warnings.append(
            "The rendered map image looks nearly uniform (possibly empty)."
        )
    return warnings


def format_layer_block(record: Dict[str, Any], max_chars: int = 1200) -> str:
    """Format one structured layer record into a multi-line context block."""
    name = record.get("name") or "unnamed"
    lines = [f"Layer: {name}"]
    geom = record.get("geometry_kind")
    if geom:
        lines.append(f"  geometry: {geom}")
    if record.get("draw_order") is not None:
        lines.append(f"  draw_order: {record['draw_order']}")
    if record.get("opacity") is not None:
        lines.append(f"  opacity: {record['opacity']}")
    if record.get("scale_dependent"):
        lines.append("  scale_dependent: yes")
    subset = record.get("subset_filter")
    if subset:
        subset_text = str(subset)
        if len(subset_text) > 200:
            subset_text = subset_text[:197] + "..."
        lines.append(f"  subset_filter: {subset_text}")
    renderer = record.get("renderer_kind")
    if renderer:
        lines.append(f"  renderer: {renderer}")
    field = record.get("class_field")
    if field:
        lines.append(f"  class_field: {field}")
    classes = record.get("classes") or []
    if classes:
        class_bits = []
        for item in classes[:12]:
            label = item.get("label") if isinstance(item, dict) else str(item)
            color = item.get("color") if isinstance(item, dict) else None
            if color:
                class_bits.append(f"{label} ({color})")
            else:
                class_bits.append(str(label))
        lines.append("  classes: " + "; ".join(class_bits))
    fields = record.get("fields") or []
    if fields:
        lines.append("  fields: " + ", ".join(str(f) for f in fields[:20]))
    table = record.get("snowflake_table")
    if table:
        lines.append(f"  snowflake_table: {table}")
    if record.get("extent_mode"):
        lines.append("  map_extent_loading: on")
    text = "\n".join(lines)
    if len(text) > max_chars:
        return text[: max_chars - 20] + "\n...[truncated]"
    return text


def build_map_context(
    extent_wkt: str,
    scale: float,
    crs_authid: str,
    layer_blocks: Sequence[str],
    max_chars: int = 6000,
    warnings: Optional[Sequence[str]] = None,
) -> str:
    """Build map context, dropping whole lower layers when over budget."""
    header = [
        f"CRS: {crs_authid}",
        f"Scale: 1:{int(scale)}" if scale else "Scale: unknown",
        f"Extent (EPSG:4326 WKT): {extent_wkt}",
    ]
    if warnings:
        header.append("Automatic checks:")
        header.extend(f"- {w}" for w in warnings)
    header.append("Visible layers (top to bottom):")
    header_text = "\n".join(header)

    kept: List[str] = []
    omitted = 0
    for block in layer_blocks:
        candidate = header_text
        if kept:
            candidate += "\n" + "\n".join(kept)
        candidate += "\n" + block
        remaining_after = len(layer_blocks) - len(kept) - 1
        if remaining_after > 0:
            candidate += f"\n{remaining_after} lower layers omitted"
        if len(candidate) > max_chars and kept:
            omitted = len(layer_blocks) - len(kept)
            break
        if len(candidate) > max_chars and not kept:
            # Truncate the first block so it still fits the budget.
            room = max_chars - len(header_text) - 1
            if room > 40:
                kept.append(block[: room - 20] + "\n...[truncated]")
            omitted = len(layer_blocks) - 1
            break
        kept.append(block)

    parts = [header_text]
    if kept:
        parts.append("\n".join(kept))
    if omitted:
        parts.append(f"{omitted} lower layers omitted")
    return "\n".join(parts)


def build_brief_prompt(
    focus: str,
    map_context: str,
    warnings: Optional[Sequence[str]] = None,
) -> str:
    """Prompt that forces a four-section map brief.

    Warnings are expected to already appear inside ``map_context`` when
    present; they are not repeated here.
    """
    focus_line = focus.strip() if focus else "(none)"
    headings = "\n".join(f"## {title}" for title in BRIEF_SECTIONS)
    empty_rule = ""
    if warnings:
        empty_rule = (
            "- If automatic checks warn that the view may be empty, say so "
            "clearly.\n"
        )
    return (
        "You are helping a QGIS user write a brief about the current map view.\n"
        "Respond with exactly these four Markdown headings and nothing else "
        "outside them:\n"
        f"{headings}\n\n"
        "Rules:\n"
        "- Under 'Seen in the image', describe only what is visible in the PNG.\n"
        "- Under 'From layer settings', use only names and encodings from the "
        "map context (layer names, fields, class labels).\n"
        "- Under 'Not determinable from this view', list what cannot be "
        "concluded from the image or context.\n"
        "- Do not invent place names, counts, or statistics that are not in "
        "the image or context.\n"
        f"{empty_rule}"
        f"\nFocus: {focus_line}\n\n"
        f"Map context:\n{map_context}\n"
    )


def build_followup_prompt(
    question: str,
    latest_brief: str,
    history: Optional[Sequence[tuple]] = None,
    max_brief_chars: int = 4000,
) -> str:
    """Prompt for a follow-up question about the same captured map image."""
    brief = (latest_brief or "")[:max_brief_chars]
    history_lines = []
    for item in list(history or [])[-6:]:
        if not item or len(item) < 2:
            continue
        history_lines.append(f"Q: {item[0]}\nA: {item[1]}")
    history_block = "\n\n".join(history_lines)
    parts = [
        "Answer a follow-up question about the same QGIS map image.",
        "Use the image and the prior brief. Do not invent place names or "
        "numbers that are not supported by them.",
        f"\nPrior brief:\n{brief}",
    ]
    if history_block:
        parts.append(f"\nRecent exchanges:\n{history_block}")
    parts.append(f"\nQuestion: {question.strip()}\n")
    return "\n".join(parts)


def _normalize_heading(title: str) -> Optional[str]:
    cleaned = re.sub(r"[#*_`]+", "", title or "").strip().rstrip(":").strip()
    lowered = cleaned.lower()
    for section in BRIEF_SECTIONS:
        if lowered == section.lower():
            return section
    if lowered == "other":
        return "Other"
    return None


def split_brief_sections(text: Optional[str]) -> Dict[str, str]:
    """Parse a four-section brief tolerantly.

    Missing sections become empty strings. Any preamble or unmatched content
    is kept under ``Other`` so nothing is lost.
    """
    result = {section: "" for section in BRIEF_SECTIONS}
    result["Other"] = ""
    text = normalize_cortex_text(text)
    if not text:
        return result

    current = "Other"
    buckets: Dict[str, List[str]] = {key: [] for key in result}
    for raw_line in text.splitlines():
        match = _HEADING_RE.match(raw_line)
        if match:
            normalized = _normalize_heading(match.group("title"))
            if normalized is not None:
                current = normalized
                continue
        buckets[current].append(raw_line)

    for key, lines in buckets.items():
        result[key] = "\n".join(lines).strip()
    return result


def format_brief_label_text(sections: Dict[str, str]) -> str:
    """Plain text for a print-layout label from sectioned brief content."""
    parts = []
    for section in BRIEF_SECTIONS:
        body = (sections.get(section) or "").strip()
        if body:
            parts.append(f"{section}\n{body}")
    other = (sections.get("Other") or "").strip()
    if other:
        parts.append(f"Other\n{other}")
    return "\n\n".join(parts).strip()


def format_project_notes_block(
    sections: Dict[str, str],
    when: Optional[datetime] = None,
) -> str:
    """Dated project-notes block for QgsProject metadata abstract."""
    stamp = when or datetime.now(timezone.utc)
    stamp_text = stamp.strftime("%Y-%m-%d %H:%M UTC")
    body = format_brief_label_text(sections)
    return f"Map brief ({stamp_text})\n{body}".strip()
