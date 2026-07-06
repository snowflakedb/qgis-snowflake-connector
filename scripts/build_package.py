#!/usr/bin/env python3
"""Build a distributable ZIP package for the Snowflake QGIS plugin.

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

PLUGIN_DIR_NAME = "qgis-snowflake-connector"

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


def build_package(repo_root, output_dir, include_tests=False, slim=False):
    version = read_version(repo_root)

    excludes = set(EXCLUDE_ALWAYS)
    if slim:
        excludes |= EXCLUDE_SLIM
    if not include_tests:
        excludes |= EXCLUDE_TESTS

    suffix = "-slim" if slim else ""
    zip_name = f"{PLUGIN_DIR_NAME}-{version}{suffix}.zip"
    zip_path = output_dir / zip_name

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
                        "__pycache__", "*.pyc", "*.pyo", ".DS_Store"
                    ),
                )
            else:
                if not should_exclude(rel, excludes):
                    shutil.copy2(item, dest)

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _dirs, files in os.walk(staging):
                for f in sorted(files):
                    full = Path(root) / f
                    arcname = str(
                        Path(PLUGIN_DIR_NAME) / full.relative_to(staging)
                    )
                    zf.write(full, arcname)

    return zip_path


def main():
    parser = argparse.ArgumentParser(
        description="Build Snowflake QGIS plugin ZIP package"
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
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    zip_path = build_package(
        repo_root,
        output_dir,
        include_tests=args.include_tests,
        slim=args.slim,
    )

    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"Package built: {zip_path} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
