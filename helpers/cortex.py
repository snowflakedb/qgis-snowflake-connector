"""Pure helpers for Snowflake Cortex AI_COMPLETE prompts and response parsing."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple


DEFAULT_SQL_MODEL = "llama3.1-70b"
DEFAULT_MULTIMODAL_MODEL = "claude-3-5-sonnet"

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
    return text.rstrip(";").strip()


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
    if not text:
        return result

    current = "Other"
    buckets: Dict[str, List[str]] = {key: [] for key in result}
    for raw_line in str(text).splitlines():
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
