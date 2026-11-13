"""QGIS-native outputs for Map brief results."""

from __future__ import annotations

from typing import Dict, Optional

from qgis.core import (
    QgsLayoutItemLabel,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsPrintLayout,
    QgsProject,
    QgsUnitTypes,
)
from .cortex import format_brief_label_text, format_project_notes_block


LAYOUT_NAME = "Map brief"


def insert_brief_into_layout(
    sections: Dict[str, str],
    project: Optional[QgsProject] = None,
    layout_name: str = LAYOUT_NAME,
) -> str:
    """Add a label with the brief text to a print layout.

    Uses an existing layout named ``layout_name`` when present, otherwise
    creates one. Returns the layout name used.
    """
    project = project or QgsProject.instance()
    manager = project.layoutManager()
    layout = manager.layoutByName(layout_name)
    if layout is None:
        layout = QgsPrintLayout(project)
        layout.initializeDefaults()
        layout.setName(layout_name)
        manager.addLayout(layout)

    text = format_brief_label_text(sections)
    label = QgsLayoutItemLabel(layout)
    label.setText(text)
    label.adjustSizeToText()

    # Place below existing items when possible.
    y = 10.0
    try:
        for item in layout.items():
            if isinstance(item, QgsLayoutItemLabel):
                rect = item.rectWithFrame()
                y = max(y, rect.y() + rect.height() + 5.0)
    except Exception:
        y = 10.0

    label.attemptMove(QgsLayoutPoint(10, y, QgsUnitTypes.LayoutMillimeters))
    # Give the label a readable width; height adjusts with text.
    label.attemptResize(
        QgsLayoutSize(180, max(40.0, label.sizeWithUnits().height()), QgsUnitTypes.LayoutMillimeters)
    )
    layout.addLayoutItem(label)
    return layout_name


def append_brief_to_project_notes(
    sections: Dict[str, str],
    project: Optional[QgsProject] = None,
) -> str:
    """Append a dated Map brief block to the project metadata abstract.

    Returns the new abstract text. Marks the project dirty.
    """
    project = project or QgsProject.instance()
    metadata = project.metadata()
    existing = metadata.abstract() or ""
    block = format_project_notes_block(sections)
    if existing.strip():
        new_abstract = existing.rstrip() + "\n\n" + block
    else:
        new_abstract = block
    metadata.setAbstract(new_abstract)
    project.setMetadata(metadata)
    project.setDirty(True)
    return new_abstract
