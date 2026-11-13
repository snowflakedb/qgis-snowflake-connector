import ast
import pathlib
import sys
import tempfile
import unittest
import zipfile


ROOT = pathlib.Path(__file__).resolve().parents[1]


class TestRepositoryPrecheck(unittest.TestCase):
    def test_no_merge_conflict_markers(self):
        markers = ("<" * 7, "=" * 7, ">" * 7)
        skip_dirs = {".git", ".cursor", "__pycache__", "node_modules", "vendor"}
        for path in ROOT.rglob("*"):
            if not path.is_file():
                continue
            if any(part in skip_dirs for part in path.parts):
                continue
            if path.suffix not in {".py", ".md", ".txt", ".yml", ".yaml"}:
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except Exception:
                continue
            for marker in markers:
                self.assertNotIn(marker, content, f"{path} has merge marker '{marker}'")

    def test_all_python_files_parse(self):
        for path in ROOT.rglob("*.py"):
            if ".git" in path.parts:
                continue
            content = path.read_text(encoding="utf-8")
            try:
                ast.parse(content)
            except SyntaxError as exc:
                self.fail(f"Syntax error in {path}: {exc}")

    def test_ci_workflow_runs_precheck_tests(self):
        workflow = ROOT / ".github" / "workflows" / "ci.yml"
        self.assertTrue(workflow.exists())
        content = workflow.read_text(encoding="utf-8")
        self.assertIn("pull_request:", content)
        self.assertIn("test/test_issue_regressions.py", content)
        self.assertIn("test/test_extent_mode_and_cortex.py", content)
        self.assertIn("test/test_plugin_improvements.py", content)
        self.assertIn("test/test_precheck_repo.py", content)
        self.assertIn("Compile check", content)

    def test_support_documents_exist_in_doc_folder(self):
        expected = [
            ROOT / "doc" / "open-issues-analysis.md",
            ROOT / "doc" / "manual-qa-runbook.md",
            ROOT / "doc" / "issue-validation-matrix.md",
        ]
        for path in expected:
            self.assertTrue(path.exists(), f"Missing support document: {path}")


class TestUpgradeSafePackaging(unittest.TestCase):
    """ZIP root must be qgis-snowflake-connector/ so Install from ZIP upgrades in place."""

    def test_build_package_writes_stable_root_zip(self):
        scripts = ROOT / "scripts"
        if str(scripts) not in sys.path:
            sys.path.insert(0, str(scripts))
        import build_package  # noqa: E402

        self.assertEqual(build_package.PLUGIN_DIR_NAME, "qgis-snowflake-connector")
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp)
            stable = build_package.build_package(ROOT, out)
            self.assertEqual(stable.name, "qgis-snowflake-connector.zip")
            self.assertTrue(stable.is_file())
            self.assertFalse(
                any(
                    p.name.startswith("qgis-snowflake-connector-")
                    and p.suffix == ".zip"
                    for p in out.iterdir()
                )
            )
            roots = {
                name.split("/")[0]
                for name in zipfile.ZipFile(stable).namelist()
                if name
            }
            self.assertEqual(roots, {"qgis-snowflake-connector"})

            versioned = build_package.build_package(
                ROOT, out, also_versioned=True
            )
            self.assertEqual(versioned.name, "qgis-snowflake-connector.zip")
            versioned_copies = [
                p
                for p in out.iterdir()
                if p.name.startswith("qgis-snowflake-connector-")
                and p.suffix == ".zip"
            ]
            self.assertEqual(len(versioned_copies), 1)
            roots = {
                name.split("/")[0]
                for name in zipfile.ZipFile(versioned_copies[0]).namelist()
                if name
            }
            self.assertEqual(roots, {"qgis-snowflake-connector"})


if __name__ == "__main__":
    unittest.main()
