import ast
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class TestRepositoryPrecheck(unittest.TestCase):
    def test_no_merge_conflict_markers(self):
        markers = ("<" * 7, "=" * 7, ">" * 7)
        for path in ROOT.rglob("*"):
            if not path.is_file():
                continue
            if ".git" in path.parts:
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


if __name__ == "__main__":
    unittest.main()
