import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import report


class ReportTest(unittest.TestCase):
    def result(self, target):
        return {
            "target": target,
            "status": "passed",
            "sourceSha": "a" * 40,
            "runtime": {"verifiedFiles": 5},
            "model": {"manifestSha256": "b" * 64},
            "durationSeconds": 12.3,
        }

    def test_all_five_targets_are_required(self):
        results = {target: self.result(target) for target in report.TARGETS}
        rendered = report.render(
            results, "https://example.test/run", "java/sdk-preview", "a" * 40
        )
        self.assertFalse(rendered["failed"])
        self.assertIn("passed on all five targets", rendered["summary"])

    def test_missing_target_fails_the_consolidated_report(self):
        results = {target: self.result(target) for target in report.TARGETS[:-1]}
        rendered = report.render(
            results, "https://example.test/run", "deadbeef", "a" * 40
        )
        self.assertTrue(rendered["failed"])
        self.assertEqual(["osx-arm64"], rendered["failures"])
        self.assertIn("No result artifact was produced", rendered["issue"])

    def test_mixed_source_commits_fail_qualification(self):
        results = {target: self.result(target) for target in report.TARGETS}
        results["linux-arm64"]["sourceSha"] = "c" * 40
        rendered = report.render(
            results, "https://example.test/run", "java/sdk-preview", "a" * 40
        )
        self.assertTrue(rendered["failed"])
        self.assertEqual(["linux-arm64"], rendered["failures"])
        self.assertIn("Expected source", rendered["issue"])

    def test_missing_source_sha_preserves_original_error(self):
        results = {target: self.result(target) for target in report.TARGETS}
        results["win-arm64"].update(
            status="failed", sourceSha=None, error="Java setup failed"
        )
        rendered = report.render(
            results, "https://example.test/run", "java/sdk-preview", "a" * 40
        )
        self.assertTrue(rendered["failed"])
        self.assertEqual(["win-arm64"], rendered["failures"])
        self.assertIn("Java setup failed", rendered["issue"])
        self.assertNotIn("target tested -", rendered["issue"])

    def test_source_mismatch_does_not_hide_original_error(self):
        results = {target: self.result(target) for target in report.TARGETS}
        results["linux-x64"].update(
            status="failed", sourceSha="c" * 40, error="Native test failed"
        )
        rendered = report.render(
            results, "https://example.test/run", "java/sdk-preview", "a" * 40
        )
        self.assertIn("Native test failed; Expected source", rendered["issue"])

    def test_loader_rejects_duplicate_target_results(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("first.json", "second.json"):
                (root / name).write_text(
                    json.dumps(self.result("win-x64")), encoding="utf-8"
                )
            with self.assertRaisesRegex(ValueError, "Duplicate result"):
                report.load_results(root)


if __name__ == "__main__":
    unittest.main()
