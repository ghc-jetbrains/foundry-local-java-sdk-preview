"""Record the complete model inventory after successful native ASR qualification."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import xml.etree.ElementTree as ET

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--target", required=True)
args = parser.parse_args()
reports = list(Path("sdk_v2/java/target/surefire-reports").glob("TEST-*.xml"))
if not reports:
    raise ValueError("Missing native test reports")
for path in reports:
    suite = ET.parse(path).getroot()
    if any(int(suite.attrib.get(key, 0)) != 0 for key in ("errors", "failures", "skipped")):
        raise ValueError(f"Incomplete qualification: {path}")
model = Path(Path("model-path.txt").read_text(encoding="utf-8").strip())
entries = []
for path in sorted(model.rglob("*")):
    if path.is_file():
        relative = path.relative_to(model).as_posix()
        if "/" in relative:
            raise ValueError(f"Unexpected nested model asset: {relative}")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        entries.append(dict(name=relative, bytes=path.stat().st_size, sha256=digest.hexdigest()))
if not entries:
    raise ValueError("Empty model inventory")
entries.sort(key=lambda entry: entry["name"])
canonical = "".join(f"{e['name']}\t{e['bytes']}\t{e['sha256']}\n" for e in entries)
result = dict(
    target=args.target,
    id=os.environ["FOUNDRY_TEST_MODEL"],
    installedBytes=sum(e["bytes"] for e in entries),
    manifestSha256=hashlib.sha256(canonical.encode()).hexdigest(),
    files=entries,
    executionSha=os.environ["GITHUB_SHA"],
    sdkSourceSha="71d2afd191ef8e589de1422488754e199714f88b",
    runtimeVersion="2.1.0",
    runUrl=f"https://github.com/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}",
)
Path("qualification").mkdir(exist_ok=True)
Path(f"qualification/{args.target}.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
