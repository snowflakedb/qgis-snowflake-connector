"""Helpers for the Snowflake plugin toolbar and Plugins menu actions."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from qgis.core import QgsMapLayer, QgsVectorLayer


def selected_snowflake_layers(layers: List["QgsMapLayer"]) -> List["QgsVectorLayer"]:
    """Return selected layers that use the snowflakedb provider."""
    from qgis.core import QgsVectorLayer

    result: List[QgsVectorLayer] = []
    for layer in layers:
        if not isinstance(layer, QgsVectorLayer):
            continue
        provider = layer.dataProvider()
        if provider is None:
            continue
        if provider.name() != "snowflakedb":
            continue
        result.append(layer)
    return result


def connection_context_from_layer(layer: "QgsVectorLayer") -> Dict[str, Optional[str]]:
    """Build a minimal context_information dict from a Snowflake layer URI."""
    from .utils import decodeUri

    parts = decodeUri(layer.dataProvider().dataSourceUri())
    context: Dict[str, Optional[str]] = {
        "connection_name": parts.get("connection_name"),
    }
    if parts.get("schema_name"):
        context["schema_name"] = parts["schema_name"]
    if parts.get("table_name"):
        context["table_name"] = parts["table_name"]
    return context


def toggle_extent_mode_uri(uri: str) -> str:
    """Add or remove ``extent_mode=1`` from a provider URI."""
    if re.search(r"(?:^|\s)extent_mode=1(?:\s|$)", uri):
        return re.sub(r"\s*extent_mode=1", "", uri).rstrip()
    return f"{uri.rstrip()} extent_mode=1"


def uri_has_extent_mode(uri: str) -> bool:
    """Return True when the URI enables map-extent loading."""
    return bool(re.search(r"(?:^|\s)extent_mode=1(?:\s|$)", uri))
