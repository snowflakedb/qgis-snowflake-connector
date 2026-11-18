#!/usr/bin/env python3
"""Build a distributable ZIP package for the Snowflake QGIS plugin.

Upgrade-safe packaging rule (always enforced):
  The ZIP must contain exactly one top-level folder named
  ``qgis-snowflake-connector`` (no version suffix). QGIS Install from ZIP
  replaces that folder in place. A versioned root (e.g.
  ``qgis-snowflake-connector-1.0.27``) installs a *second* plugin.

Usage:
    python scripts/build_package.py                    # default: ~/Downloads
    python scripts/build_package.py -o /tmp            # custom output dir
    python scripts/build_package.py --include-tests    # include test/ folder
    python scripts/build_package.py --slim             # exclude docs/assets/help
"""

import argparse
import configparser
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

# Stable plugin folder / QGIS plugin id. Never append a version to this name.
PLUGIN_DIR_NAME = "qgis-snowflake-connector"
STABLE_ZIP_NAME = f"{PLUGIN_DIR_NAME}.zip"

EXCLUDE_ALWAYS = {
    ".git",
    ".github",
    ".cursor",
    ".pytest_cache",
    "__pycache__",
    ".DS_Store",
    ".gitignore",
    ".gitattributes",
    ".editorconfig",
    ".tool-versions",
    "scripts",
    "doc",
    "skill",
    "zip_build",
    "Makefile",
    "pb_tool.cfg",
    "pylintrc",
    "plugin_upload.py",
}

EXCLUDE_SLIM = {
    "assets",
    "help",
    "CONTRIBUTING.md",
    "README.md",
}

EXCLUDE_TESTS = {
    "test",
}

EXCLUDE_PATTERNS = {
    ".pyc",
    ".pyo",
}


def read_version(repo_root: Path) -> str:
    cfg = configparser.ConfigParser()
    cfg.read(repo_root / "metadata.txt")
    return cfg.get("general", "version", fallback="0.0.0")


def should_exclude(rel_path: str, exclude_names: set) -> bool:
    parts = Path(rel_path).parts
    for part in parts:
        if part in exclude_names:
            return True
    for pattern in EXCLUDE_PATTERNS:
        if rel_path.endswith(pattern):
            return True
    return False


def zip_top_level_roots(zip_path: Path) -> set:
    """Return distinct top-level entry names inside ``zip_path``."""
    roots = set()
    with zipfile.ZipFile(zip_path, "r") as zf:
        for name in zf.namelist():
            if not name or name.startswith("/"):
                continue
            roots.add(Path(name).parts[0])
    return roots


def assert_upgrade_safe_zip(zip_path: Path) -> None:
    """Fail if the ZIP would install as a second plugin (versioned root)."""
    roots = zip_top_level_roots(zip_path)
    if roots != {PLUGIN_DIR_NAME}:
        raise SystemExit(
            f"Refusing to ship {zip_path}: top-level entries are {sorted(roots)!r}, "
            f"expected exactly {PLUGIN_DIR_NAME!r}. "
            "A versioned or multi-root ZIP installs a second plugin instead of "
            "upgrading the existing one."
        )


def build_package(
    repo_root,
    output_dir,
    include_tests=False,
    slim=False,
    also_versioned=False,
):
    """Build an Install-from-ZIP package with a fixed plugin root folder.

    By default writes only ``qgis-snowflake-connector.zip`` (or
    ``…-slim.zip``). Pass ``also_versioned=True`` to also write
    ``qgis-snowflake-connector-<version>.zip`` for release archives.

    Returns:
        Path: path to the stable Install-from-ZIP archive
    """
    version = read_version(repo_root)

    excludes = set(EXCLUDE_ALWAYS)
    if slim:
        excludes |= EXCLUDE_SLIM
    if not include_tests:
        excludes |= EXCLUDE_TESTS

    suffix = "-slim" if slim else ""
    stable_name = f"{PLUGIN_DIR_NAME}-slim.zip" if slim else STABLE_ZIP_NAME
    stable_path = Path(output_dir) / stable_name
    versioned_path = Path(output_dir) / f"{PLUGIN_DIR_NAME}-{version}{suffix}.zip"

    with tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp) / PLUGIN_DIR_NAME
        staging.mkdir()

        for item in sorted(repo_root.iterdir()):
            if item.name in excludes:
                continue
            rel = item.name
            dest = staging / rel
            if item.is_dir():
                shutil.copytree(
                    item,
                    dest,
                    ignore=shutil.ignore_patterns(
                        "__pycache__", "*.pyc", "*.pyo", ".DS_Store", "*.bat"
                    ),
                )
            else:
                if not should_exclude(rel, excludes):
                    shutil.copy2(item, dest)

        with zipfile.ZipFile(stable_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _dirs, files in os.walk(staging):
                for f in sorted(files):
                    full = Path(root) / f
                    arcname = str(
                        Path(PLUGIN_DIR_NAME) / full.relative_to(staging)
                    )
                    # Guard against accidentally writing a versioned arc root.
                    if Path(arcname).parts[0] != PLUGIN_DIR_NAME:
                        raise SystemExit(
                            f"Internal packaging error: arcname {arcname!r} "
                            f"does not start with {PLUGIN_DIR_NAME!r}"
                        )
                    zf.write(full, arcname)

    assert_upgrade_safe_zip(stable_path)
    if also_versioned:
        shutil.copy2(stable_path, versioned_path)
        assert_upgrade_safe_zip(versioned_path)
    return stable_path


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Build Snowflake QGIS plugin ZIP (stable root "
            f"{PLUGIN_DIR_NAME}/ for in-place upgrades)"
        )
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        default=os.path.expanduser("~/Downloads"),
        help="Output directory (default: ~/Downloads)",
    )
    parser.add_argument(
        "--include-tests",
        action="store_true",
        help="Include the test/ directory in the package",
    )
    parser.add_argument(
        "--slim",
        action="store_true",
        help="Exclude docs, assets, and help for a minimal package",
    )
    parser.add_argument(
        "--also-versioned",
        action="store_true",
        help=(
            "Also write qgis-snowflake-connector-<version>.zip "
            "(used by the GitHub release workflow)"
        ),
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    zip_path = build_package(
        repo_root,
        output_dir,
        include_tests=args.include_tests,
        slim=args.slim,
        also_versioned=args.also_versioned,
    )

    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"Package built: {zip_path} ({size_mb:.1f} MB)")
    print(
        f"Upgrade-safe root folder: {PLUGIN_DIR_NAME}/ "
        "(do not use GitHub Source code archives)"
    )


if __name__ == "__main__":
    main()
