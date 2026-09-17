import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import zipfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import prepare_runtime


class PrepareRuntimeTest(unittest.TestCase):
    def write_lock(self, root, native_lines, aliases=None):
        (root / "native-lock.properties").write_text(
            "\n".join(native_lines) + "\n", encoding="ascii"
        )
        (root / "runtime-lock.json").write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "apiVersion": 1,
                    "nativeHashes": "native-lock.properties",
                    "targets": ["linux-x64"],
                    "aliases": aliases or {},
                    "packages": [
                        {
                            "key": "runtime",
                            "id": "runtime",
                            "version": "1",
                            "url": "https://example.test/runtime.nupkg",
                            "sha256": "a" * 64,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

    def write_archive(self, path, entries):
        with zipfile.ZipFile(path, "w") as archive:
            for name, content in entries.items():
                archive.writestr(name, content)

    def test_read_native_hashes_rejects_invalid_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "hashes.properties"
            for content in (
                "linux-x64.file=short\n",
                f"linux-x64.file={'g' * 64}\n",
                "linux-x64.file\n",
                f"linux-x64.file={'a' * 64}\nlinux-x64.file={'b' * 64}\n",
            ):
                with self.subTest(content=content):
                    path.write_text(content, encoding="ascii")
                    with self.assertRaisesRegex(ValueError, "Invalid native hash entry"):
                        prepare_runtime.read_native_hashes(path)

    def test_read_native_hashes_ignores_surrounding_blank_space(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "hashes.properties"
            path.write_text(
                f"  \n  # comment\nlinux-x64.file={'a' * 64}\n\n",
                encoding="ascii",
            )
            self.assertEqual(
                {"linux-x64.file": "a" * 64},
                prepare_runtime.read_native_hashes(path),
            )

    def test_prepare_extracts_an_aliased_native_file(self):
        payload = b"native bytes"
        digest = hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_lock(
                root,
                [f"linux-x64.libonnxruntime.so.1={digest}"],
                {"libonnxruntime.so.1": "libonnxruntime.so"},
            )
            archive_path = root / "runtime.nupkg"
            self.write_archive(
                archive_path,
                {"runtimes/linux-x64/native/libonnxruntime.so": payload},
            )
            runtime_dir = root / "runtime"
            with (
                mock.patch.object(prepare_runtime, "ROOT", root),
                mock.patch.object(
                    prepare_runtime, "download", return_value=archive_path
                ),
            ):
                evidence = prepare_runtime.prepare(
                    "linux-x64", runtime_dir, root / "downloads"
                )
            self.assertEqual(payload, (runtime_dir / "libonnxruntime.so.1").read_bytes())
            self.assertEqual(1, evidence["verifiedFiles"])

    def test_prepare_rejects_missing_native_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_lock(root, [f"linux-x64.libmissing.so={'a' * 64}"])
            archive_path = root / "runtime.nupkg"
            self.write_archive(archive_path, {"unrelated": b"content"})
            with (
                mock.patch.object(prepare_runtime, "ROOT", root),
                mock.patch.object(
                    prepare_runtime, "download", return_value=archive_path
                ),
                self.assertRaisesRegex(ValueError, "Missing native files"),
            ):
                prepare_runtime.prepare(
                    "linux-x64", root / "runtime", root / "downloads"
                )


if __name__ == "__main__":
    unittest.main()
