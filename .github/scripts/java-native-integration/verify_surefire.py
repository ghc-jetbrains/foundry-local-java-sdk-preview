#!/usr/bin/env python3
"""Require NativeAsrTest to execute without skips or failures."""

import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def integer_attribute(suite, name):
    value = suite.get(name)
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Invalid Surefire {name} count: {value}") from error


def verify(reports):
    matches = sorted(reports.glob("TEST-*.NativeAsrTest.xml"))
    if len(matches) != 1:
        raise ValueError(
            f"Expected one NativeAsrTest Surefire report, found {len(matches)}"
        )
    suite = ET.parse(matches[0]).getroot()
    counts = {
        name: integer_attribute(suite, name)
        for name in ("tests", "skipped", "failures", "errors")
    }
    if (
        counts["tests"] < 1
        or counts["skipped"] != 0
        or counts["failures"] != 0
        or counts["errors"] != 0
    ):
        raise ValueError(f"NativeAsrTest did not complete cleanly: {counts}")
    evidence = {"report": matches[0].name, **counts}
    print(json.dumps(evidence, sort_keys=True))
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports", required=True, type=Path)
    args = parser.parse_args()
    verify(args.reports)


if __name__ == "__main__":
    main()
