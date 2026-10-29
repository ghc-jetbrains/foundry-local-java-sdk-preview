"""Assemble an official C API 2 runtime for native SDK qualification."""
import argparse
import hashlib
from pathlib import Path
import shutil
import urllib.request
import zipfile

PACKAGES = (
    ("microsoft.ai.foundry.local.runtime", "2.1.0", "7c9bdd72bcbd606c10d4573c1ac354a7d8e0469e36647d170dab304098f7bf39"),
    ("microsoft.ml.onnxruntime", "1.30.0", "30df119bd9164eaa187666d93147448fdd4a9a1a3caf83f1505daf7af2d1c5d2"),
    ("microsoft.ml.onnxruntimegenai.foundry", "0.17.0", "1c07eaad0560858c3dc59dfb0d53f42bd2ed0107fd11eb739f65c47ddee89494"),
)

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--target", required=True, choices=("win-x64", "win-arm64", "linux-x64", "linux-arm64", "osx-arm64"))
parser.add_argument("--output", required=True, type=Path)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=False)
downloads = args.output.parent / "packages"
downloads.mkdir(exist_ok=True)
prefix = f"runtimes/{args.target}/native/"
for package, version, expected in PACKAGES:
    filename = f"{package}.{version}.nupkg"
    archive_path = downloads / filename
    with urllib.request.urlopen(f"https://api.nuget.org/v3-flatcontainer/{package}/{version}/{filename}", timeout=180) as source:
        with archive_path.open("wb") as target:
            shutil.copyfileobj(source, target)
    if hashlib.sha256(archive_path.read_bytes()).hexdigest() != expected:
        raise ValueError(f"Package checksum mismatch: {filename}")
    with zipfile.ZipFile(archive_path) as archive:
        for entry in archive.namelist():
            if not entry.startswith(prefix):
                continue
            name = entry[len(prefix):]
            if not name or "/" in name or "\\" in name or name in (".", ".."):
                continue
            destination = args.output / name
            if destination.exists():
                raise ValueError(f"Duplicate native dependency: {name}")
            destination.write_bytes(archive.read(entry))
for source, alias in (("libonnxruntime.so", "libonnxruntime.so.1"), ("libonnxruntime.dylib", "libonnxruntime.1.dylib")):
    if (args.output / source).exists() and not (args.output / alias).exists():
        shutil.copyfile(args.output / source, args.output / alias)
print(f"Prepared {args.target}: {len(list(args.output.iterdir()))} native files")
