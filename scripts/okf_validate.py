"""OKF v0.1 bundle validator.

Walks a directory of Markdown files, parses YAML frontmatter, and reports
conformance against the OKF core schema. Stdlib only — no external deps.

Usage:
    python -m scripts.okf_validate [PATH]            # default: ./memory
    python -m scripts.okf_validate --strict          # exit 1 on any error
    python -m scripts.okf_validate --json            # machine-readable output
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ponytail: OKF v0.1 core types plus the project-defined extras.
OKF_TYPES = frozenset(
    {"Index", "Decision", "Fact", "Learning", "Convention", "Profile"}
)

REQUIRED_FIELDS = ("type", "title", "description", "tags", "timestamp")
OPTIONAL_FIELDS = ("resource",)


@dataclass
class Issue:
    path: str
    field: str | None
    message: str

    def to_dict(self) -> dict:
        return {"path": self.path, "field": self.field, "message": self.message}


@dataclass
class Report:
    files_checked: int = 0
    issues: list[Issue] = field(default_factory=list)
    by_directory: dict[str, int] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.issues

    def to_dict(self) -> dict:
        return {
            "files_checked": self.files_checked,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
            "by_directory": self.by_directory,
        }


def parse_frontmatter(text: str) -> tuple[dict | None, str | None]:
    """Return (frontmatter_dict, error). Error is None on success.

    Handles the small subset of YAML we use: flat key: value pairs, inline
    arrays [a, b, c], quoted strings, and numbers. No nested structures.
    """
    lines = text.splitlines()
    if not lines or lines[0].rstrip() != "---":
        return None, "no frontmatter block (file must start with `---`)"

    end = None
    for i in range(1, len(lines)):
        if lines[i].rstrip() == "---":
            end = i
            break
    if end is None:
        return None, "unterminated frontmatter block (missing closing `---`)"

    fm: dict = {}
    for raw in lines[1:end]:
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            return None, f"malformed frontmatter line: {raw!r}"
        key, _, value = stripped.partition(":")
        key = key.strip()
        value = value.strip()
        fm[key] = _parse_value(value)
    return fm, None


def _parse_value(raw: str):
    """Parse a single YAML value (subset)."""
    if not raw:
        return ""
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        if not inner:
            return []
        return [item.strip().strip('"').strip("'") for item in inner.split(",")]
    if (raw.startswith('"') and raw.endswith('"')) or (
        raw.startswith("'") and raw.endswith("'")
    ):
        return raw[1:-1]
    if re.fullmatch(r"-?\d+(\.\d+)?", raw):
        return float(raw) if "." in raw else int(raw)
    return raw


def validate_file(path: Path) -> list[Issue]:
    issues: list[Issue] = []
    text = path.read_text(encoding="utf-8")
    fm, err = parse_frontmatter(text)
    if err is not None:
        issues.append(Issue(str(path), None, err))
        return issues
    if fm is None:
        issues.append(Issue(str(path), None, "frontmatter is empty"))
        return issues

    for required in REQUIRED_FIELDS:
        if required not in fm:
            issues.append(Issue(str(path), required, f"missing required field"))
        elif fm[required] in (None, ""):
            if required == "description":
                issues.append(
                    Issue(
                        str(path),
                        required,
                        "missing or empty description (OKF requires a one-sentence description)",
                    )
                )

    type_value = fm.get("type")
    if isinstance(type_value, str):
        if type_value not in OKF_TYPES and not type_value.startswith("x-"):
            issues.append(
                Issue(
                    str(path),
                    "type",
                    f"unknown OKF type {type_value!r} (must be one of "
                    f"{sorted(OKF_TYPES)} or start with `x-`)",
                )
            )

    return issues


def walk(root: Path) -> Report:
    report = Report()
    for md in sorted(root.rglob("*.md")):
        if any(part.startswith(".") and part != "." for part in md.parts):
            continue
        if md.name == "README.md":
            continue
        report.files_checked += 1
        issues = validate_file(md)
        report.issues.extend(issues)
        rel_dir = str(md.parent.relative_to(root)) if md.parent != root else "."
        report.by_directory[rel_dir] = report.by_directory.get(rel_dir, 0) + 1
    return report


def print_human(report: Report, root: Path) -> None:
    if report.ok:
        print(f"OK: {report.files_checked} files checked in {root}")
        return
    print(f"FAIL: {len(report.issues)} issue(s) in {report.files_checked} files\n")
    by_path: dict[str, list[Issue]] = {}
    for issue in report.issues:
        by_path.setdefault(issue.path, []).append(issue)
    for path, issues in by_path.items():
        print(f"  {path}")
        for issue in issues:
            field = f" [{issue.field}]" if issue.field else ""
            print(f"    {field} {issue.message}")
    print(f"\nDirectory coverage:")
    for d, count in sorted(report.by_directory.items()):
        print(f"  {d}: {count} file(s)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OKF v0.1 bundle validator")
    parser.add_argument(
        "path",
        nargs="?",
        default="memory",
        help="Path to the OKF bundle directory (default: ./memory)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with non-zero status on any conformance issue",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON report",
    )
    args = parser.parse_args(argv)

    root = Path(args.path).resolve()
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 2

    report = walk(root)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print_human(report, root)

    if not report.ok and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
