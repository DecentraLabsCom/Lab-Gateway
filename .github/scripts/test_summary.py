#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _parse_junit(path: Path) -> dict[str, int]:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall(".//testsuite"))
    if not suites:
        suites = [root]

    totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for suite in suites:
        for key in totals:
            totals[key] += int(suite.attrib.get(key, 0) or 0)
    return totals


def _parse_coverage_xml(path: Path) -> float | None:
    root = ET.parse(path).getroot()
    line_rate = root.attrib.get("line-rate")
    if line_rate is None:
        return None
    return round(float(line_rate) * 100.0, 2)


def _parse_coverage_xml_counts(path: Path) -> tuple[int | None, int | None]:
    root = ET.parse(path).getroot()
    covered = root.attrib.get("lines-covered")
    total = root.attrib.get("lines-valid")
    if covered is None or total is None:
        return None, None
    return int(covered), int(total)


def _parse_luacov_pct(path: Path) -> float | None:
    text = _read_text(path)
    percent_matches = re.findall(r"(\d+(?:\.\d+)?)%", text)
    if not percent_matches:
        return None
    return round(float(percent_matches[-1]), 2)


def _parse_luacov_counts(path: Path) -> tuple[int | None, int | None]:
    text = _read_text(path)
    total_match = re.search(r"^Total\s+(\d+)\s+(\d+)\s+(\d+(?:\.\d+)?)%$", text, re.MULTILINE)
    if not total_match:
        return None, None
    total = int(total_match.group(1))
    missed = int(total_match.group(2))
    return total - missed, total


def _parse_shell_counts(path: Path) -> tuple[int | None, int | None]:
    text = _read_text(path)

    smoke_match = re.search(r"Smoke Test Results:\s*(\d+)\s+passed,\s*(\d+)\s+failed", text, re.IGNORECASE)
    if smoke_match:
        return int(smoke_match.group(1)), int(smoke_match.group(2))

    passed_match = re.search(r"Passed:\s*(\d+)", text, re.IGNORECASE)
    failed_match = re.search(r"Failed:\s*(\d+)", text, re.IGNORECASE)
    if passed_match and failed_match:
        return int(passed_match.group(1)), int(failed_match.group(1))

    busted_match = re.search(r"(\d+)\s+passed", text, re.IGNORECASE)
    if busted_match:
        return int(busted_match.group(1)), 0

    success_match = re.search(r"(\d+)\s+success(?:es)?", text, re.IGNORECASE)
    failure_match = re.search(r"(\d+)\s+failure(?:s)?", text, re.IGNORECASE)
    if success_match:
        return int(success_match.group(1)), int(failure_match.group(1)) if failure_match else 0

    return None, None


def _suite_status(passed: int | None, failed: int | None, fallback_failed: bool) -> str:
    if failed is not None and failed > 0:
        return "failed"
    if passed is not None:
        return "passed"
    return "failed" if fallback_failed else "passed"


def _write_suite_summary(args: argparse.Namespace) -> int:
    output = Path(args.output)
    passed = None
    failed = None
    skipped = None
    total = None
    coverage_pct = None
    coverage_covered = None
    coverage_total = None

    if args.kind == "pytest":
        junit = _parse_junit(Path(args.junit))
        total = junit["tests"]
        failed = junit["failures"] + junit["errors"]
        skipped = junit["skipped"]
        passed = total - failed - skipped
        if args.coverage_xml:
            coverage_pct = _parse_coverage_xml(Path(args.coverage_xml))
            coverage_covered, coverage_total = _parse_coverage_xml_counts(Path(args.coverage_xml))
    elif args.kind == "shell":
        passed, failed = _parse_shell_counts(Path(args.log))
        if passed is not None and failed is not None:
            total = passed + failed
        if args.coverage_report:
            cov_path = Path(args.coverage_report)
            if cov_path.exists():
                coverage_pct = _parse_luacov_pct(cov_path)
                coverage_covered, coverage_total = _parse_luacov_counts(cov_path)
    else:
        raise ValueError(f"Unsupported kind: {args.kind}")

    payload = {
        "suite_id": args.suite_id,
        "suite_name": args.suite_name,
        "status": _suite_status(passed, failed, args.exit_code != 0),
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "total": total,
        "coverage_pct": coverage_pct,
        "coverage_covered": coverage_covered,
        "coverage_total": coverage_total,
        "coverage_label": args.coverage_label,
        "exit_code": args.exit_code,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0


def _format_result(passed: int | None, failed: int | None, skipped: int | None, total: int | None) -> str:
    if passed is None and failed is None:
        return "n/a"
    parts = []
    if passed is not None:
        parts.append(f"{passed} passed")
    if failed is not None:
        parts.append(f"{failed} failed")
    if skipped:
        parts.append(f"{skipped} skipped")
    if total is not None:
        parts.append(f"{total} total")
    return ", ".join(parts)


def _format_coverage(value: float | None, label: str | None) -> str:
    if value is None:
        return "n/a"
    if label:
        return f"{value:.2f}% ({label})"
    return f"{value:.2f}%"


def _combined_coverage(payloads: list[dict], suite_ids: set[str] | None = None) -> tuple[float | None, int, int]:
    covered = 0
    total = 0
    for payload in payloads:
        if suite_ids is not None and payload["suite_id"] not in suite_ids:
            continue
        item_covered = payload.get("coverage_covered")
        item_total = payload.get("coverage_total")
        if item_covered is None or item_total is None:
            continue
        covered += int(item_covered)
        total += int(item_total)
    if total == 0:
        return None, covered, total
    return round((covered / total) * 100.0, 2), covered, total


def _render_summary(args: argparse.Namespace) -> int:
    input_dir = Path(args.input_dir)
    payloads = []
    for path in sorted(input_dir.glob("*.json")):
        payloads.append(json.loads(path.read_text(encoding="utf-8")))

    order = {
        "python-unit": 1,
        "lua-unit": 2,
        "integration": 3,
        "fmu-integration": 4,
        "smoke": 5,
    }
    payloads.sort(key=lambda item: (order.get(item["suite_id"], 999), item["suite_name"]))

    suite_passed = sum(1 for payload in payloads if payload["status"] == "passed")
    total_suites = len(payloads)
    known_test_total = sum(payload["total"] or 0 for payload in payloads)
    known_test_passed = sum(payload["passed"] or 0 for payload in payloads)
    combined_pct, combined_covered, combined_total = _combined_coverage(payloads, {"python-unit", "lua-unit"})

    lines = [
        "## Test Summary",
        "",
        f"- Suite status: {suite_passed}/{total_suites} passed",
        f"- Known test pass count: {known_test_passed}/{known_test_total}",
        (
            f"- Combined code coverage (Python + Lua): {combined_pct:.2f}% "
            f"({combined_covered}/{combined_total} covered lines)"
            if combined_pct is not None
            else "- Combined code coverage (Python + Lua): n/a"
        ),
        "",
        "| Suite | Status | Result | Coverage |",
        "| --- | --- | --- | --- |",
    ]

    for payload in payloads:
        lines.append(
            "| {suite} | {status} | {result} | {coverage} |".format(
                suite=payload["suite_name"],
                status=payload["status"],
                result=_format_result(payload["passed"], payload["failed"], payload["skipped"], payload["total"]),
                coverage=_format_coverage(payload["coverage_pct"], payload.get("coverage_label")),
            )
        )

    markdown = "\n".join(lines) + "\n"
    if args.output:
        Path(args.output).write_text(markdown, encoding="utf-8")
    else:
        sys.stdout.write(markdown)
    return 0


def _gate_summary(args: argparse.Namespace) -> int:
    input_dir = Path(args.input_dir)
    payloads = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(input_dir.glob("*.json"))]
    suite_ids = set(args.suite_ids.split(","))
    combined_pct, covered, total = _combined_coverage(payloads, suite_ids)
    if combined_pct is None:
        print("No coverage data available for consolidated gate.", file=sys.stderr)
        return 1
    print(f"Combined coverage for {','.join(sorted(suite_ids))}: {combined_pct:.2f}% ({covered}/{total})")
    return 0 if combined_pct >= args.min_coverage else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate CI test summary artifacts")
    subparsers = parser.add_subparsers(dest="command", required=True)

    suite_parser = subparsers.add_parser("suite", help="Create one suite JSON summary")
    suite_parser.add_argument("--suite-id", required=True)
    suite_parser.add_argument("--suite-name", required=True)
    suite_parser.add_argument("--kind", choices=("pytest", "shell"), required=True)
    suite_parser.add_argument("--junit")
    suite_parser.add_argument("--coverage-xml")
    suite_parser.add_argument("--coverage-report")
    suite_parser.add_argument("--coverage-label")
    suite_parser.add_argument("--log")
    suite_parser.add_argument("--exit-code", type=int, default=0)
    suite_parser.add_argument("--output", required=True)
    suite_parser.set_defaults(func=_write_suite_summary)

    render_parser = subparsers.add_parser("render", help="Render Markdown from suite JSON files")
    render_parser.add_argument("--input-dir", required=True)
    render_parser.add_argument("--output")
    render_parser.set_defaults(func=_render_summary)

    gate_parser = subparsers.add_parser("gate", help="Fail if consolidated coverage is below threshold")
    gate_parser.add_argument("--input-dir", required=True)
    gate_parser.add_argument("--suite-ids", required=True, help="Comma-separated suite ids with coverage data")
    gate_parser.add_argument("--min-coverage", required=True, type=float)
    gate_parser.set_defaults(func=_gate_summary)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
