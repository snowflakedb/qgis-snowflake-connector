# -*- coding: utf-8 -*-

"""
/***************************************************************************
 Snowflake Connector for QGIS
 This package includes the Snowflake Connector for QGIS.
                              -------------------
        begin                : 2024-08-07
        copyright            : (C) 2024 by Snowflake
        email                : erick.cuberojimenez@snowflake.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is licensed under the MIT License. You may use, modify,  *
 *   and distribute it under the terms specified in the license.           *
 *                                                                         *
 ***************************************************************************/
"""

__author__ = "Snowflake Inc."
__date__ = "2024-08-07"
__copyright__ = "(C) 2024 by Snowflake"

__revision__ = "$Format:%H$"

import os

from qgis.core import QgsProcessingProvider
from .qgis_snowflake_connector_algorithm import QGISSnowflakeConnectorAlgorithm
from qgis.PyQt.QtGui import QIcon

_IMAGES_DIR = os.path.join(os.path.dirname(__file__), "ui", "images")


class QGISSnowflakeConnectorProvider(QgsProcessingProvider):
    def __init__(self):
        QgsProcessingProvider.__init__(self)

    def unload(self):
        pass

    def loadAlgorithms(self):
        self.addAlgorithm(QGISSnowflakeConnectorAlgorithm())

        from .processing.import_from_snowflake import ImportFromSnowflakeAlgorithm
        from .processing.execute_sql import ExecuteSQLAlgorithm
        from .processing.spatial_join import SpatialJoinAlgorithm
        from .processing.buffer_table import BufferTableAlgorithm
        from .processing.h3_index import H3IndexAlgorithm

        self.addAlgorithm(ImportFromSnowflakeAlgorithm())
        self.addAlgorithm(ExecuteSQLAlgorithm())
        self.addAlgorithm(SpatialJoinAlgorithm())
        self.addAlgorithm(BufferTableAlgorithm())
        self.addAlgorithm(H3IndexAlgorithm())

    def id(self):
        return "snowflake"

    def name(self):
        return self.tr("Snowflake")

    def icon(self):
        return QIcon(os.path.join(_IMAGES_DIR, "qgis_logo.svg"))

    def longName(self):
        return self.tr("Snowflake Geospatial Tools")
