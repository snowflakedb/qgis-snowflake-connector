# Snowflake Connector for QGIS

[![License Apache-2.0](https://img.shields.io/:license-MIT-brightgreen.svg)](https://spdx.org/licenses/MIT.html)

## Introduction
This package includes the Snowflake Connector for QGIS.

The Snowflake Connector for QGIS provides an interface for open-source GIS application QGIS that can connect to Snowflake and perform all standard operations. It provides a connection via [Python connector](https://github.com/snowflakedb/snowflake-connector-python).

## Installation
The plugin can be installed using the QGIS plugin manager. 
- Go to `Plugins` > `All`, search for `Snowflake Connector for QGIS` and click `Install Plugin`.

You can try latest development versions by downloading and installing the plugin in QGIS from a zip file. These are available [here](https://github.com/snowflakedb/qgis-snowflake-connector/releases), download the zip-file "qgis-snowflake-connector.zip" for the release you want to try.

> **Upgrading an existing installation:** after updating the plugin to a new version, fully restart QGIS. QGIS registers the Snowflake vector data provider once per session and cannot replace it while running, so a running session keeps using the previously loaded provider code until QGIS is restarted. The plugin logs a warning in the `Snowflake Plugin` message log when a restart is required to finish an upgrade.

## Getting Started
1. Install the plugin with the QGIS plugin manager.

2. Go to Layer > Data Source Manager. In the list of data sources click on Snowflake and create a new connectionn
<img src ='assets/data_source_manager.png'  width=700>

3. Add connection details and choose Connection type (default or SSO)
<img src ='assets/new_connection.png'  width=500>
You can get your account locator here:
<img src ='assets/account_locator.png'  width=700>
Note: Sometimes, the account locator would look like locator.region.azure. For example snowflake.west-europe.azure or abc12345.us-east-1.

4. Use standard features for reading/writing geospatial data
<img src ='assets/snowflake_qgis.jpg'  width=800>

## Snowflake toolbar

After the plugin loads, a **Snowflake** toolbar (and Plugins → Snowflake menu) provides:

- **Execute SQL…** — open the SQL query dialog for the selected Snowflake layer’s connection (or the first saved connection).
- **Reload from Snowflake** — call `reloadData()` on selected Snowflake layers.
- **Toggle map-extent loading** — add or remove `extent_mode=1` on selected Snowflake layers.
- **Ask Snowflake (Cortex)…** — draft a read-only SELECT from a natural-language question.
- **Map brief (Cortex)…** — write a four-section brief of the current map view with a multimodal Cortex model.

## Map-extent loading (#106)

For tables too large to sample wholesale, right-click a spatial table in the Browser and choose **Add with map-extent loading**. The layer URI includes `extent_mode=1`. Each map render issues a query filtered to the current canvas rectangle with a per-request row LIMIT. Results are capped, so a dense view may show a truncated subset; selection and feature ids are per query and these layers are read-only. Warehouse cost still depends on clustering and pruning—`ADD SEARCH OPTIMIZATION ON GEO(<geom_column>)` helps. You can also toggle this mode from the toolbar for an existing Snowflake layer.

## Attribute-only tables (#105)

Tables without a GEOGRAPHY/GEOMETRY/H3 column appear under **Tables (no geometry)** in the Browser. Double-click one to open it as a Snowflake attribute layer (attribute table and filters). These layers are read-only.

## Cortex tools

Both Cortex actions use `AI_COMPLETE` on your existing Snowflake connection.

**Ask Snowflake** needs Cortex access and a text model available in your account/region (default `llama3.1-70b`). Generated SQL must pass the plugin’s read-only check before it can open in the SQL editor.

**Map brief** needs:

- Cortex access to a multimodal model (default `claude-3-5-sonnet`)
- `CREATE STAGE` on the selected schema (the plugin creates a temporary SSE-encrypted stage, PUTs the canvas PNG once per dialog session, calls `AI_COMPLETE` with `TO_FILE`, and REMOVEs the file when the dialog closes)

Before calling Cortex, the dialog runs local checks (no visible layers, layers off the current extent, nearly blank image) and shows warnings. The model returns four fixed sections: Seen in the image, From layer settings, Not determinable from this view, and Suggested next steps. You can ask follow-up questions about the same captured view, insert the brief into a print layout label, or append it to the project notes (metadata abstract). The map image and visible layer details are sent to Cortex on your connection.

## Support
If you found bugs or have suggestions for improving the plugin, please [submit](https://github.com/snowflakedb/qgis-snowflake-connector/issues) the issue or contribute by creating a pull request.

Snowflake Documentation is available at:
https://docs.snowflake.com/