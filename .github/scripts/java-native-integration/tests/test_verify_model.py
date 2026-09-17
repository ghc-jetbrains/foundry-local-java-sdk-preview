import hashlib
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import verify_model


def item(name, data):
    return {
        "name": name,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


class VerifyModelTest(unittest.TestCase):
    def fixture(self, root, marker):
        model = root / "Microsoft" / "model-3"
        model.mkdir(parents=True)
        common = {"genai_config.json": b"config", "weights.bin": b"weights"}
        for name, data in {**common, "inference_model.json": marker}.items():
            (model / name).write_bytes(data)
        expected = [item(name, data) for name, data in common.items()]
        marker_item = item("inference_model.json", marker)
        lines = [
            f"{entry['name']}\t{entry['bytes']}\t{entry['sha256']}\n"
            for entry in sorted([*expected, marker_item], key=lambda value: value["name"])
        ]
        lock = {
            "id": "model:3",
            "commonFiles": expected,
            "targetMarkers": {"linux-x64": marker_item},
            "manifestSha256": {
                "linux-x64": hashlib.sha256("".join(lines).encode()).hexdigest()
            },
        }
        return lock

    def test_verifies_exact_target_inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lock = self.fixture(root, b"linux")
            evidence = verify_model.verify(root, lock, "linux-x64")
            self.assertEqual("model:3", evidence["id"])
            self.assertEqual(len(b"configweightslinux"), evidence["installedBytes"])

    def test_rejects_unexpected_model_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lock = self.fixture(root, b"linux")
            next(root.rglob("genai_config.json")).parent.joinpath("unexpected").write_bytes(b"x")
            with self.assertRaisesRegex(ValueError, "exactly one complete"):
                verify_model.verify(root, lock, "linux-x64")


if __name__ == "__main__":
    unittest.main()
