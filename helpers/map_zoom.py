"""Zoom the map canvas to one or more layers with a small buffer."""

from __future__ import annotations

from typing import Iterable, Optional, Sequence


def zoom_canvas_to_layers(
    layers: Sequence,
    iface=None,
    buffer_scale: float = 1.1,
) -> bool:
    """Zoom the canvas to the combined extent of ``layers``.

    Returns True when the canvas was updated. Skips null/empty extents
    (attribute-only layers, failed extent queries).
    """
    if iface is None:
        try:
            from qgis.utils import iface as qgis_iface

            iface = qgis_iface
        except Exception:
            return False
    if iface is None or iface.mapCanvas() is None:
        return False

    from qgis.core import (
        QgsCoordinateTransform,
        QgsProject,
        QgsRectangle,
    )

    canvas = iface.mapCanvas()
    canvas_crs = canvas.mapSettings().destinationCrs()
    combined: Optional[QgsRectangle] = None

    for layer in layers:
        if layer is None:
            continue
        try:
            if hasattr(layer, "isValid") and not layer.isValid():
                continue
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
            if combined is None:
                combined = QgsRectangle(extent)
            else:
                combined.combineExtentWith(extent)
        except Exception:
            continue

    if combined is None or combined.isEmpty() or combined.isNull():
        return False

    try:
        combined.scale(float(buffer_scale))
    except Exception:
        pass
    canvas.setExtent(combined)
    canvas.refresh()
    return True


def zoom_canvas_to_layer(layer, iface=None, buffer_scale: float = 1.1) -> bool:
    """Convenience wrapper for a single layer."""
    if layer is None:
        return False
    return zoom_canvas_to_layers([layer], iface=iface, buffer_scale=buffer_scale)
