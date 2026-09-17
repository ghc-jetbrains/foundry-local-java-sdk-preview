from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import verify_surefire


class VerifySurefireTest(unittest.TestCase):
    def write_report(self, directory, **counts):
        attributes = " ".join(f'{name}="{value}"' for name, value in counts.items())
        (directory / "TEST-com.microsoft.foundry.local.NativeAsrTest.xml").write_text(
            f"<testsuite {attributes}></testsuite>", encoding="utf-8"
        )

    def test_accepts_executed_native_test(self):
        with tempfile.TemporaryDirectory() as directory:
            reports = Path(directory)
            self.write_report(
                reports, tests=1, skipped=0, failures=0, errors=0
            )
            evidence = verify_surefire.verify(reports)
            self.assertEqual(1, evidence["tests"])

    def test_rejects_skipped_native_test(self):
        with tempfile.TemporaryDirectory() as directory:
            reports = Path(directory)
            self.write_report(
                reports, tests=1, skipped=1, failures=0, errors=0
            )
            with self.assertRaisesRegex(ValueError, "did not complete cleanly"):
                verify_surefire.verify(reports)

    def test_rejects_missing_native_test_report(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "Expected one"):
                verify_surefire.verify(Path(directory))

    def test_rejects_invalid_test_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            reports = Path(directory)
            self.write_report(
                reports, tests="unknown", skipped=0, failures=0, errors=0
            )
            with self.assertRaisesRegex(ValueError, "Invalid Surefire tests count"):
                verify_surefire.verify(reports)


if __name__ == "__main__":
    unittest.main()
