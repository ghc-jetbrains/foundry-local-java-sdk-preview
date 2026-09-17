#!/usr/bin/env python3
"""Create the five-platform summary and issue text from target result files."""

import argparse
import json
from pathlib import Path


TARGETS = ("win-x64", "win-arm64", "linux-x64", "linux-arm64", "osx-arm64")
TITLE = "[Dictation integration] Java native qualification failed"


def load_results(directory):
    results = {}
    if directory.exists():
        for path in directory.rglob("*.json"):
            value = json.loads(path.read_text(encoding="utf-8-sig"))
            target = value.get("target")
            if target in results:
                raise ValueError(f"Duplicate result for {target}")
            if target in TARGETS:
                results[target] = value
    return results


def cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ") if value is not None else "-"


def render(results, run_url, source_ref, expected_source_sha):
    rows = []
    failures = []
    source_shas = set()
    for target in TARGETS:
        result = results.get(target)
        if result is None:
            status = "FAILED"
            source_sha = "-"
            runtime_files = "-"
            model_manifest = "-"
            duration = "-"
            error = "No result artifact was produced"
        else:
            status = "PASSED" if result.get("status") == "passed" else "FAILED"
            source_sha = result.get("sourceSha") or "-"
            if source_sha != "-":
                source_shas.add(source_sha)
            runtime = result.get("runtime") or {}
            model = result.get("model") or {}
            runtime_files = runtime.get("verifiedFiles", "-")
            model_manifest = model.get("manifestSha256", "-")
            duration = result.get("durationSeconds", "-")
            error = result.get("error") or "-"
            if source_sha == "-":
                status = "FAILED"
                if error == "-":
                    error = "Result did not record a source SHA"
            elif source_sha != expected_source_sha:
                status = "FAILED"
                mismatch = (
                    f"Expected source {expected_source_sha}, but target tested {source_sha}"
                )
                error = mismatch if error == "-" else f"{error}; {mismatch}"
        if status == "FAILED":
            failures.append(target)
        rows.append(
            f"| `{target}` | {status} | `{cell(source_sha)}` | {cell(runtime_files)} | "
            f"`{cell(model_manifest)}` | {cell(duration)} | {cell(error)} |"
        )

    table = "\n".join(
        [
            "| Target | Status | Source SHA | Runtime files | Model manifest | Seconds | Error |",
            "|---|---|---|---:|---|---:|---|",
            *rows,
        ]
    )
    exact_source = next(iter(source_shas)) if len(source_shas) == 1 else "mixed or unavailable"
    failed = bool(failures)
    headline = (
        f"Java native Dictation integration failed on {len(failures)} target(s)."
        if failed
        else "Java native Dictation integration passed on all five targets."
    )
    common = f"""<!-- java-native-dictation-integration -->
{headline}

- Requested source: `{source_ref}`
- Resolved source: `{exact_source}`
- Workflow run: {run_url}
- Schedule: 01:00 China Standard Time

{table}
"""
    issue = f"""## Integration failure

Owner/contact: @jiec-msft

@jiec-msft introduced this integration test to detect regressions in the public
Java SDK, native runtime, model installation, and speech recognition path.

Potential impact:

- Dictation may fail to initialize on one or more native targets.
- The model may fail to download, verify, load, or produce a transcription.
- Native cancellation or cleanup may leave the runtime unusable for later requests.

{common}
"""
    comment = f"""## Integration update

{common}
"""
    return {
        "comment": comment,
        "failed": failed,
        "failures": failures,
        "issue": issue,
        "summary": common,
        "title": TITLE,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--run-url", required=True)
    parser.add_argument("--source-ref", required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--github-summary", type=Path)
    args = parser.parse_args()

    rendered = render(
        load_results(args.results),
        args.run_url,
        args.source_ref,
        args.expected_source_sha,
    )
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "summary.md").write_text(rendered["summary"], encoding="utf-8")
    (args.output / "issue.md").write_text(rendered["issue"], encoding="utf-8")
    (args.output / "comment.md").write_text(rendered["comment"], encoding="utf-8")
    (args.output / "report.json").write_text(
        json.dumps(
            {
                "failed": rendered["failed"],
                "failures": rendered["failures"],
                "title": rendered["title"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as output:
            output.write(f"failed={str(rendered['failed']).lower()}\n")
    if args.github_summary:
        with args.github_summary.open("a", encoding="utf-8") as summary:
            summary.write(rendered["summary"])


if __name__ == "__main__":
    main()
