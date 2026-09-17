#!/usr/bin/env python3
"""Verify the exact downloaded Dictation model inventory for one target."""

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify(cache, lock, target):
    if target not in lock["targetMarkers"]:
        raise ValueError(f"Unsupported model target: {target}")
    expected = [*lock["commonFiles"], lock["targetMarkers"][target]]
    candidates = []
    expected_names = {item["name"] for item in expected}
    for marker in cache.rglob("genai_config.json"):
        directory = marker.parent
        actual_names = {
            path.relative_to(directory).as_posix()
            for path in directory.rglob("*")
            if path.is_file()
        }
        if actual_names == expected_names:
            candidates.append(directory)
    if len(candidates) != 1:
        raise ValueError("Expected exactly one complete checksum-locked model directory")

    directory = candidates[0]
    manifest_lines = []
    installed_bytes = 0
    for item in sorted(expected, key=lambda value: value["name"]):
        path = directory / item["name"]
        if path.stat().st_size != item["bytes"] or sha256(path) != item["sha256"]:
            raise ValueError(f"Model checksum or size mismatch: {item['name']}")
        installed_bytes += item["bytes"]
        manifest_lines.append(
            f"{item['name']}\t{item['bytes']}\t{item['sha256']}\n"
        )
    manifest = hashlib.sha256("".join(manifest_lines).encode("utf-8")).hexdigest()
    if manifest != lock["manifestSha256"][target]:
        raise ValueError("Model manifest checksum mismatch")
    return {
        "id": lock["id"],
        "installedBytes": installed_bytes,
        "manifestSha256": manifest,
        "target": target,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", required=True, type=Path)
    parser.add_argument("--target", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--lock", type=Path, default=ROOT / "model-lock.json")
    args = parser.parse_args()
    lock = json.loads(args.lock.read_text(encoding="utf-8"))
    evidence = verify(args.cache, lock, args.target)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence, sort_keys=True))


if __name__ == "__main__":
    main()
