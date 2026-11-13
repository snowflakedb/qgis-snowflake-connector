"""Capture the QGIS map canvas as a PNG and build Cortex map context."""

from __future__ import annotations

import os
import tempfile
from typing import List, Optional, Sequence, Tuple

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsMapRendererParallelJob,
    QgsMapSettings,
    QgsProject,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QSize
from qgis.PyQt.QtGui import QImage

from .cortex import build_map_context, summarize_renderer


def _extent_as_4326_wkt(canvas) -> str:
    extent = canvas.extent()
    canvas_crs = canvas.mapSettings().destinationCrs()
    wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
    if canvas_crs.isValid() and canvas_crs != wgs84:
        transform = QgsCoordinateTransform(
            canvas_crs, wgs84, QgsProject.instance()
        )
        extent = transform.transformBoundingBox(extent)
    return extent.asWktPolygon()


def layer_summary(layer) -> str:
    """One-line description of a map layer for the describe prompt."""
    name = layer.name() if hasattr(layer, "name") else str(layer)
    parts = [name]
    if isinstance(layer, QgsVectorLayer):
        try:
            parts.append(f"type={layer.geometryType()}")
        except Exception:
            pass
        try:
            parts.append(summarize_renderer(layer.renderer()))
        except Exception:
            parts.append("renderer=unavailable")
        try:
            fields = [f.name() for f in layer.fields()][:20]
            if fields:
                parts.append("fields=" + ",".join(fields))
        except Exception:
            pass
    return " | ".join(str(p) for p in parts)


def build_canvas_map_context(canvas, layers: Optional[Sequence] = None) -> str:
    """Build map context text from the canvas and its visible layers."""
    if layers is None:
        layers = list(canvas.layers())
    summaries = [layer_summary(layer) for layer in layers]
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
        layer_summaries=summaries,
    )


def render_canvas_png(
    canvas,
    max_side: int = 1600,
    output_path: Optional[str] = None,
) -> str:
    """Render the current canvas to a temporary PNG path and return that path."""
    settings: QgsMapSettings = canvas.mapSettings()
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
    job.start()
    job.waitForFinished()
    image: QImage = job.renderedImage()

    if output_path is None:
        fd, output_path = tempfile.mkstemp(prefix="qgis_sf_map_", suffix=".png")
        os.close(fd)
    if not image.save(output_path, "PNG"):
        raise RuntimeError(f"Failed to save map image to {output_path}")
    return output_path
