#!/usr/bin/env python3
"""Generate a markdown changelog section from conventional commits.

Collects commits between the latest git tag and HEAD, groups them by
conventional commit type, and prepends the result to CHANGELOG.md.
Stdlib only — no external deps.

Usage:
    python -m scripts.generate_changelog            # update CHANGELOG.md
    python -m scripts.generate_changelog --dry-run  # print to stdout
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

COMMIT_PATTERN = re.compile(
    r"^(?P<type>[A-Za-z]+)(?:\((?P<scope>[^)]*)\))?"
    r"(?P<breaking>!)?: (?P<subject>.+)$"
)

SECTION_BY_TYPE = {
    "feat": "Features",
    "fix": "Bug Fixes",
    "chore": "Maintenance",
    "docs": "Documentation",
    "test": "Tests",
    "refactor": "Refactoring",
}

SECTION_ORDER = (
    "Features",
    "Bug Fixes",
    "Maintenance",
    "Documentation",
    "Tests",
    "Refactoring",
    "Other",
)


@dataclass(frozen=True)
class Commit:
    short_hash: str
    subject: str


def get_version(pyproject: Path) -> str | None:
    """Return the version string from pyproject.toml, or None."""
    try:
        text = pyproject.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    match = re.search(
        r"^version\s*=\s*[\"']([^\"']+)[\"']", text, re.MULTILINE
    )
    return match.group(1) if match else None


def get_last_tag() -> str | None:
    """Return the most recent git tag, or None if no tags exist."""
    proc = subprocess.run(
        ["git", "tag", "--sort=-version:refname"],
        capture_output=True,
        text=True,
        check=False,
    )
    tags = [line for line in proc.stdout.splitlines() if line.strip()]
    return tags[0] if tags else None


def get_commits(since: str | None) -> list[Commit]:
    """Return (short_hash, subject) pairs since the given tag, or all."""
    args = ["git", "log", "--pretty=format:%h%x09%s"]
    if since:
        args.append(f"{since}..HEAD")
    proc = subprocess.run(args, capture_output=True, text=True, check=False)
    commits: list[Commit] = []
    for line in proc.stdout.splitlines():
        if "\t" in line:
            short_hash, subject = line.split("\t", 1)
            commits.append(Commit(short_hash, subject))
    return commits


def parse_subject(subject: str) -> tuple[str, str]:
    """Return (commit_type, display_subject) for a commit subject."""
    match = COMMIT_PATTERN.match(subject)
    if not match:
        return "other", subject
    return match.group("type").lower(), match.group("subject")


def build_section(version: str, commits: list[Commit], initial: bool) -> str:
    """Build the markdown section for a new changelog entry."""
    groups: dict[str, list[str]] = {}
    for commit in commits:
        commit_type, subject = parse_subject(commit.subject)
        section = SECTION_BY_TYPE.get(commit_type, "Other")
        groups.setdefault(section, []).append(
            f"- {subject} ({commit.short_hash})"
        )

    lines = [f"## [{version}] - {date.today().isoformat()}", ""]
    if initial:
        lines.append("> Initial release.")
        lines.append("")
    for section in SECTION_ORDER:
        entries = groups.get(section)
        if not entries:
            continue
        lines.append(f"### {section}")
        lines.extend(entries)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def prepend_changelog(path: Path, section: str) -> None:
    """Prepend a section, preserving an existing top-level title."""
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    header = ""
    body = existing
    if body.startswith("# "):
        end = body.find("\n")
        if end != -1:
            header = body[: end + 1]
            body = body[end + 1:]
    parts = [
        part.rstrip("\n")
        for part in (header, section, body)
        if part.strip()
    ]
    path.write_text("\n\n".join(parts) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a changelog section from conventional commits "
            "since the latest git tag."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the changelog section to stdout, do not modify files",
    )
    parser.add_argument(
        "--changelog",
        type=Path,
        default=Path("CHANGELOG.md"),
        help="path to the changelog file (default: CHANGELOG.md)",
    )
    args = parser.parse_args(argv)

    version = get_version(Path("pyproject.toml"))
    if version is None:
        print(
            "error: could not parse version from pyproject.toml",
            file=sys.stderr,
        )
        return 1

    last_tag = get_last_tag()
    commits = get_commits(last_tag)

    if not commits:
        if last_tag:
            print(f"No new commits since tag {last_tag}.")
        else:
            print("No commits found.")
        return 0

    section = build_section(version, commits, initial=last_tag is None)

    if args.dry_run:
        print(section, end="")
        return 0

    prepend_changelog(args.changelog, section)
    print(f"Updated {args.changelog}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
