#!/usr/bin/env python3
"""Bump the project version in pyproject.toml and package.json files.

With a target version, both files are updated to that version. Without one, the
next version is inferred from conventional commits since the latest git tag:
feat -> MINOR, fix -> PATCH, BREAKING CHANGE / "!:" -> MAJOR (highest wins,
default PATCH when no conventional commits are found).

Usage:
    uv run scripts/bump_version.py 0.2.0       # explicit target
    uv run scripts/bump_version.py            # infer next from commits
    uv run scripts/bump_version.py --dry-run  # preview, no writes
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"
PACKAGE_JSON = REPO_ROOT / ".opencode" / "plugins" / "memory" / "package.json"

PYPROJECT_VERSION_RE = re.compile(
    r'(^version = ")(?P<version>[^"]+)(")', re.MULTILINE
)
PACKAGE_JSON_VERSION_RE = re.compile(r'("version": ")(?P<version>[^"]+)(")')

BREAKING_BODY_RE = re.compile(r"^BREAKING CHANGE:", re.MULTILINE)
SUBJECT_RE = re.compile(r"^(?P<type>[a-z]+)(\([^)]+\))?(?P<breaking>!)?: ")

VERSION_FIELDS = (
    (PYPROJECT, PYPROJECT_VERSION_RE),
    (PACKAGE_JSON, PACKAGE_JSON_VERSION_RE),
)


def sync_uv_lock() -> None:
    """Regenerate uv.lock so the editable install version matches pyproject.toml."""
    result = subprocess.run(
        ["uv", "lock"], cwd=REPO_ROOT, capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"uv lock failed: {result.stderr.strip()}")


def parse_version(text: str) -> tuple[int, int, int]:
    """Parse a semver string into (major, minor, patch)."""
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", text.strip())
    if not match:
        raise ValueError(f"Invalid semver version: {text!r}")
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch)


def format_version(version: tuple[int, int, int]) -> str:
    """Format a (major, minor, patch) tuple as a semver string."""
    return ".".join(str(part) for part in version)


def bump_version(
    version: tuple[int, int, int], level: str
) -> tuple[int, int, int]:
    """Return the next version for the given bump level (MAJOR/MINOR/PATCH)."""
    major, minor, patch = version
    if level == "MAJOR":
        return major + 1, 0, 0
    if level == "MINOR":
        return major, minor + 1, 0
    return major, minor, patch + 1


def latest_tag() -> str | None:
    """Return the most recent tag reachable from HEAD, or None if untagged."""
    result = subprocess.run(
        ["git", "describe", "--tags", "--abbrev=0", "HEAD"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return result.stdout.strip() or None


def fetch_commits(rev_range: str) -> list[tuple[str, str]]:
    """Return (subject, body) pairs for every commit in the given range."""
    result = subprocess.run(
        ["git", "log", rev_range, "--format=%s%n%b%x1e"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    commits: list[tuple[str, str]] = []
    for entry in result.stdout.split("\x1e"):
        if not entry.strip():
            continue
        lines = entry.strip().split("\n", 1)
        subject = lines[0]
        body = lines[1] if len(lines) > 1 else ""
        commits.append((subject, body))
    return commits


def infer_bump_level(commits: list[tuple[str, str]]) -> str:
    """Return the highest-precedence bump level implied by the commits.

    PATCH is the default floor; fix: never raises above it, feat: raises to
    MINOR, and a breaking change (BREAKING CHANGE: in the body or "!:" after
    the type) wins outright with MAJOR.
    """
    highest = "PATCH"
    for subject, body in commits:
        if BREAKING_BODY_RE.search(body):
            return "MAJOR"
        match = SUBJECT_RE.match(subject)
        if match and match.group("breaking"):
            return "MAJOR"
        if match and match.group("type") == "feat":
            highest = "MINOR"
    return highest


def read_version(path: Path, pattern: re.Pattern) -> str:
    """Read the current version string from a file's version field."""
    match = pattern.search(path.read_text(encoding="utf-8"))
    if not match:
        raise RuntimeError(f"No version field found in {path}")
    return match.group("version")


def update_version(path: Path, pattern: re.Pattern, version: str) -> None:
    """Replace the version field in a file with the given version, in place."""
    content = path.read_text(encoding="utf-8")
    new_content, count = pattern.subn(
        f"\\g<1>{version}\\g<3>", content, count=1
    )
    if count == 0:
        raise RuntimeError(f"No version field found in {path}")
    path.write_text(new_content, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Bump the project version in pyproject.toml and the memory "
            "plugin's package.json."
        )
    )
    parser.add_argument(
        "target_version",
        nargs="?",
        default=None,
        help="Explicit semver target (e.g. 0.2.0); default: infer.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would change without modifying any files.",
    )
    args = parser.parse_args(argv)

    try:
        current = parse_version(read_version(PYPROJECT, PYPROJECT_VERSION_RE))
        if args.target_version:
            target = parse_version(args.target_version)
        else:
            tag = latest_tag()
            rev_range = f"{tag}..HEAD" if tag else "HEAD"
            commits = fetch_commits(rev_range)
            level = infer_bump_level(commits)
            target = bump_version(current, level)
            since = tag or "the beginning of history (no tags)"
            print(
                f"Inferred {level} bump from {len(commits)} commit(s) "
                f"since {since}."
            )
        new_version = format_version(target)
        current_text = format_version(current)

        if args.dry_run:
            print(f"Would update version to {new_version}:")
            for path, _ in VERSION_FIELDS:
                print(
                    f"  {path.relative_to(REPO_ROOT)}: "
                    f"{current_text} -> {new_version}"
                )
            print("  uv.lock: would sync via `uv lock`")
            return 0

        for path, pattern in VERSION_FIELDS:
            update_version(path, pattern, new_version)
            if read_version(path, pattern) != new_version:
                raise RuntimeError(f"Failed to update version in {path}")
        sync_uv_lock()
        print(
            f"Version bumped to {new_version} in "
            f"{len(VERSION_FIELDS)} file(s); uv.lock synced."
        )
    except (ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
