"""Capture the QGIS map canvas as a PNG and build Map brief context."""

from __future__ import annotations

import os
import tempfile
from typing import Any, Dict, List, Optional, Sequence, Tuple

from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsMapRendererParallelJob,
    QgsMapSettings,
    QgsProject,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QSize
from qgis.PyQt.QtGui import QColor, QImage

from .cortex import assess_view, build_map_context, format_layer_block
from .toolbar import uri_has_extent_mode


def _extent_as_4326_wkt(canvas) -> str:
    extent = canvas.extent()
    canvas_crs = canvas.mapSettings().destinationCrs()
    wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
    if canvas_crs.isValid() and canvas_crs != wgs84:
        try:
            transform = QgsCoordinateTransform(
                canvas_crs, wgs84, QgsProject.instance()
            )
            extent = transform.transformBoundingBox(extent)
        except Exception:
            return "extent unavailable"
    return extent.asWktPolygon()


def _geometry_kind(layer: QgsVectorLayer) -> str:
    try:
        gtype = layer.geometryType()
        mapping = {
            Qgis.GeometryType.Point: "points",
            Qgis.GeometryType.Line: "lines",
            Qgis.GeometryType.Polygon: "polygons",
            Qgis.GeometryType.Null: "none",
            Qgis.GeometryType.Unknown: "unknown",
        }
        return mapping.get(gtype, str(gtype))
    except Exception:
        return "unknown"


def _symbol_color_hex(symbol) -> Optional[str]:
    if symbol is None:
        return None
    try:
        color = symbol.color()
        if isinstance(color, QColor) and color.isValid():
            return color.name()
    except Exception:
        pass
    return None


def _renderer_details(renderer) -> Tuple[str, Optional[str], List[Dict[str, str]]]:
    if renderer is None:
        return "none", None, []
    try:
        kind = str(renderer.type())
    except Exception:
        kind = renderer.__class__.__name__

    class_field = None
    class_attr = getattr(renderer, "classAttribute", None)
    if callable(class_attr):
        try:
            class_field = class_attr() or None
        except Exception:
            class_field = None

    classes: List[Dict[str, str]] = []
    for attr in ("ranges", "categories"):
        getter = getattr(renderer, attr, None)
        if not callable(getter):
            continue
        try:
            items = list(getter())
        except Exception:
            continue
        for item in items[:12]:
            label = ""
            if hasattr(item, "label") and callable(item.label):
                label = str(item.label() or "")
            elif hasattr(item, "label"):
                label = str(item.label or "")
            color = None
            symbol = getattr(item, "symbol", None)
            if callable(symbol):
                try:
                    color = _symbol_color_hex(symbol())
                except Exception:
                    color = None
            entry: Dict[str, str] = {"label": label or "(unnamed)"}
            if color:
                entry["color"] = color
            classes.append(entry)
        break

    if not classes:
        root = getattr(renderer, "rootRule", None)
        if callable(root):
            try:
                rule = root()
                children = getattr(rule, "children", lambda: [])()
                for child in list(children)[:12]:
                    label = ""
                    if hasattr(child, "label") and callable(child.label):
                        label = str(child.label() or "")
                    if label:
                        classes.append({"label": label})
            except Exception:
                pass

    return kind, class_field, classes


def collect_layer_record(layer, draw_order: int) -> Dict[str, Any]:
    """Build a structured layer record for Map brief context."""
    record: Dict[str, Any] = {
        "name": layer.name() if hasattr(layer, "name") else str(layer),
        "draw_order": draw_order,
    }
    if not isinstance(layer, QgsVectorLayer):
        record["geometry_kind"] = "raster_or_other"
        return record

    record["geometry_kind"] = _geometry_kind(layer)
    try:
        record["opacity"] = round(float(layer.opacity()), 2)
    except Exception:
        pass
    try:
        record["scale_dependent"] = bool(
            layer.hasScaleBasedVisibility()
        )
    except Exception:
        record["scale_dependent"] = False
    try:
        subset = layer.subsetString()
        if subset:
            record["subset_filter"] = subset
    except Exception:
        pass

    try:
        kind, class_field, classes = _renderer_details(layer.renderer())
        record["renderer_kind"] = kind
        if class_field:
            record["class_field"] = class_field
        if classes:
            record["classes"] = classes
    except Exception:
        record["renderer_kind"] = "unavailable"

    try:
        record["fields"] = [f.name() for f in layer.fields()][:20]
    except Exception:
        record["fields"] = []

    try:
        provider = layer.dataProvider()
        if provider is not None and provider.name() == "snowflakedb":
            from .utils import decodeUri

            uri = provider.dataSourceUri()
            parts = decodeUri(uri)
            schema = parts.get("schema_name") or ""
            table = parts.get("table_name") or ""
            if schema and table:
                record["snowflake_table"] = f"{schema}.{table}"
            elif table:
                record["snowflake_table"] = table
            record["extent_mode"] = uri_has_extent_mode(uri)
    except Exception:
        pass

    return record


def layers_intersect_canvas(canvas, layers: Sequence) -> bool:
    """True when at least one visible layer extent intersects the canvas view."""
    canvas_extent = canvas.extent()
    canvas_crs = canvas.mapSettings().destinationCrs()
    for layer in layers:
        try:
            extent = layer.extent()
            if extent is None or extent.isEmpty() or extent.isNull():
                continue
            layer_crs = layer.crs()
            if (
                layer_crs.isValid()
                and canvas_crs.isValid()
                and layer_crs != canvas_crs
            ):
                transform = QgsCoordinateTransform(
                    layer_crs, canvas_crs, QgsProject.instance()
                )
                extent = transform.transformBoundingBox(extent)
            if extent.intersects(canvas_extent):
                return True
        except Exception:
            continue
    return False


def image_is_nearly_uniform(image: QImage, sample_step: int = 8) -> bool:
    """Heuristic: sampled pixels are all the same color.

    Uses a denser default grid so thin features on a flat background are not
    mistaken for an empty view.
    """
    if image is None or image.isNull():
        return True
    width = image.width()
    height = image.height()
    if width <= 0 or height <= 0:
        return True
    first = image.pixel(0, 0)
    step = max(1, int(sample_step))
    for y in range(0, height, step):
        for x in range(0, width, step):
            if image.pixel(x, y) != first:
                return False
    # Also check a few edge midpoints that a coarse grid can skip.
    for x, y in (
        (width // 2, 0),
        (width // 2, height - 1),
        (0, height // 2),
        (width - 1, height // 2),
        (width // 2, height // 2),
    ):
        if image.pixel(x, y) != first:
            return False
    return True


def collect_view_warnings(canvas, layers: Optional[Sequence] = None, image: Optional[QImage] = None) -> List[str]:
    """Run local canvas/image checks and return warning strings."""
    if layers is None:
        layers = list(canvas.layers())
    visible = list(layers)
    intersects = layers_intersect_canvas(canvas, visible) if visible else False
    uniform = image_is_nearly_uniform(image) if image is not None else False
    return assess_view(len(visible), intersects, uniform)


def build_canvas_map_context(
    canvas,
    layers: Optional[Sequence] = None,
    warnings: Optional[Sequence[str]] = None,
    max_chars: int = 6000,
) -> str:
    """Build Map brief context from the canvas and its visible layers."""
    if layers is None:
        layers = list(canvas.layers())
    records = [
        collect_layer_record(layer, draw_order=idx)
        for idx, layer in enumerate(layers)
    ]
    blocks = [format_layer_block(record) for record in records]
    scale = 0.0
    try:
        scale = float(canvas.scale())
    except Exception:
        scale = 0.0
    crs = canvas.mapSettings().destinationCrs()
    authid = crs.authid() if crs.isValid() else "unknown"
    return build_map_context(
        extent_wkt=_extent_as_4326_wkt(canvas),
        scale=scale,
        crs_authid=authid,
        layer_blocks=blocks,
        max_chars=max_chars,
        warnings=warnings,
    )


def render_canvas_png(
    canvas,
    max_side: int = 1600,
    output_path: Optional[str] = None,
) -> Tuple[str, QImage]:
    """Render the current canvas to a temporary PNG and return path + image."""
    settings: QgsMapSettings = canvas.mapSettings()
    # Keep the upload size predictable on HiDPI screens.
    try:
        settings.setDevicePixelRatio(1)
    except Exception:
        pass
    size = settings.outputSize()
    width = max(size.width(), 1)
    height = max(size.height(), 1)
    longest = max(width, height)
    if longest > max_side:
        scale = max_side / float(longest)
        width = max(1, int(width * scale))
        height = max(1, int(height * scale))
        settings.setOutputSize(QSize(width, height))

    job = QgsMapRendererParallelJob(settings)
    try:
        cache = canvas.mapRendererCache()
        if cache is not None and hasattr(job, "setCache"):
            job.setCache(cache)
    except Exception:
        pass
    job.start()
    job.waitForFinished()
    image: QImage = job.renderedImage()

    created_temp = False
    if output_path is None:
        fd, output_path = tempfile.mkstemp(prefix="qgis_sf_map_", suffix=".png")
        os.close(fd)
        created_temp = True
    if not image.save(output_path, "PNG"):
        if created_temp and os.path.isfile(output_path):
            try:
                os.remove(output_path)
            except Exception:
                pass
        raise RuntimeError(f"Failed to save map image to {output_path}")
    return output_path, image
