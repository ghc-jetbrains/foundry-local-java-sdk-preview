#!/usr/bin/env python3
"""Download and assemble a checksum-locked Foundry Local native runtime."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import time
import urllib.request
import zipfile


ROOT = Path(__file__).resolve().parent


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def download(package, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and sha256(destination) == package["sha256"]:
        return destination
    destination.unlink(missing_ok=True)
    delays = (0, 15, 45)
    for attempt, delay in enumerate(delays, start=1):
        if delay:
            time.sleep(delay)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=destination.parent, suffix=".part", delete=False
            ) as output:
                temporary = Path(output.name)
                request = urllib.request.Request(
                    package["url"], headers={"User-Agent": "foundry-java-native-integration"}
                )
                with urllib.request.urlopen(request, timeout=180) as response:
                    shutil.copyfileobj(response, output, 1024 * 1024)
            if sha256(temporary) != package["sha256"]:
                raise ValueError(f"SHA-256 mismatch for {package['id']} {package['version']}")
            temporary.replace(destination)
            return destination
        except (OSError, ValueError) as error:
            if attempt == len(delays):
                raise RuntimeError(
                    f"Could not download {package['id']} after {attempt} attempts"
                ) from error
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    raise AssertionError("unreachable")


def read_native_hashes(path):
    hashes = {}
    for line in path.read_text(encoding="ascii").splitlines():
        if not line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        if key in hashes or len(value) != 64:
            raise ValueError(f"Invalid native hash entry: {key}")
        hashes[key] = value
    return hashes


def safe_entry(archive, name):
    path = Path(name)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Unsafe archive entry: {name}")
    return archive.open(name)


def prepare(target, runtime_dir, download_dir):
    lock = json.loads((ROOT / "runtime-lock.json").read_text(encoding="utf-8"))
    if target not in lock["targets"]:
        raise ValueError(f"Unsupported target: {target}")
    all_hashes = read_native_hashes(ROOT / lock["nativeHashes"])
    prefix = target + "."
    expected = {
        key[len(prefix) :]: value
        for key, value in all_hashes.items()
        if key.startswith(prefix)
    }
    if not expected:
        raise ValueError(f"No native inventory for {target}")

    runtime_dir.mkdir(parents=True, exist_ok=False)
    written = set()
    archives = [
        (package, download(package, download_dir / f"{package['key']}.nupkg"))
        for package in lock["packages"]
    ]
    for package, archive_path in archives:
        with zipfile.ZipFile(archive_path) as archive:
            names = set(archive.namelist())
            for output_name, expected_hash in expected.items():
                source_name = lock["aliases"].get(output_name, output_name)
                entry = f"runtimes/{target}/native/{source_name}"
                if entry not in names:
                    continue
                if output_name in written:
                    raise ValueError(f"Multiple packages provide {output_name}")
                destination = runtime_dir / output_name
                with safe_entry(archive, entry) as source, destination.open("wb") as output:
                    shutil.copyfileobj(source, output, 1024 * 1024)
                if sha256(destination) != expected_hash:
                    raise ValueError(f"Native checksum mismatch: {output_name}")
                written.add(output_name)
    if written != expected.keys():
        raise ValueError(f"Missing native files: {sorted(expected.keys() - written)}")

    evidence = {
        "apiVersion": lock["apiVersion"],
        "packages": [
            {
                "id": package["id"],
                "version": package["version"],
                "sha256": package["sha256"],
            }
            for package in lock["packages"]
        ],
        "target": target,
        "verifiedFiles": len(written),
    }
    print(json.dumps(evidence, sort_keys=True))
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True)
    parser.add_argument("--runtime-dir", required=True, type=Path)
    parser.add_argument("--download-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    evidence = prepare(args.target, args.runtime_dir, args.download_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
