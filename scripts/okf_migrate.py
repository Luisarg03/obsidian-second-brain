"""Migrate the legacy SecondBrain bundle to OKF v0.1 in the new project.

Reads each .md file under `<source>/<project>/<type>/`, parses the legacy
frontmatter, adds missing OKF v0.1 fields (`description` derived from the
body, `resource` empty), reorders the OKF core fields, and writes the
updated file to `<target>/<project>/<type>/<name>.md`.

Idempotent: files that already have a `description` field are left as-is.

Usage:
    okf-migrate                              # defaults
    okf-migrate --source PATH --target PATH
    okf-migrate --dry-run                    # show what would change
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

# Tiny YAML frontmatter parser, same dialect as scripts/okf_validate.py.
def _parse_value(raw: str):
    raw = raw.strip()
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


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Return (frontmatter_dict, body). Body is everything after the closing `---`."""
    lines = text.splitlines()
    if not lines or lines[0].rstrip() != "---":
        return {}, text
    end = None
    for i in range(1, len(lines)):
        if lines[i].rstrip() == "---":
            end = i
            break
    if end is None:
        return {}, text
    fm: dict = {}
    for raw in lines[1:end]:
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        fm[key.strip()] = _parse_value(value)
    body = "\n".join(lines[end + 1 :])
    return fm, body


def first_non_heading_paragraph(body: str, max_chars: int = 200) -> str:
    """Return the first non-heading paragraph of `body`, trimmed."""
    lines = body.splitlines()
    out: list[str] = []
    for line in lines:
        s = line.strip()
        if not s:
            if out:
                break
            continue
        if s.startswith("#"):
            continue
        out.append(s)
        if sum(len(x) for x in out) > max_chars:
            break
    para = " ".join(out).strip()
    if len(para) > max_chars:
        para = para[: max_chars - 1].rstrip() + "…"
    return para


# OKF v0.1 core field order. Custom fields are appended after.
OKF_CORE_FIELDS = ("type", "title", "description", "resource", "tags", "timestamp")


def render_frontmatter(fm: dict, body_has_description: bool) -> str:
    """Render the frontmatter block in OKF v0.1 order.

    `body_has_description` is True if the source already had a `description`
    field — in that case we preserve it as-is.
    """
    out_lines = ["---"]
    for key in OKF_CORE_FIELDS:
        if key == "description" and not body_has_description:
            continue  # we add it later, derived
        if key in fm:
            out_lines.append(f"{key}: {format_value(fm[key])}")
    # Ensure all OKF core fields are present (with empty defaults if missing).
    for key in OKF_CORE_FIELDS:
        if key not in [l.split(":", 1)[0] for l in out_lines if ":" in l]:
            if key == "resource":
                out_lines.append(f"resource: ")
            elif key == "description":
                # Caller will set this after we know the body.
                pass
    return "\n".join(out_lines)


def format_value(v) -> str:
    if isinstance(v, list):
        return "[" + ", ".join(str(x) for x in v) + "]"
    if v is None:
        return ""
    s = str(v)
    if any(c in s for c in [",", "[", "]", '"', "'", ":", "#"]) or s.strip() != s:
        return f'"{s}"'
    return s


@dataclass
class MigrationStats:
    files_seen: int = 0
    files_written: int = 0
    files_skipped: int = 0
    descriptions_added: int = 0
    projects: set[str] = None  # type: ignore

    def __post_init__(self):
        if self.projects is None:
            self.projects = set()


def migrate_file(src: Path, dst: Path, *, dry_run: bool) -> tuple[str, str]:
    """Migrate one file. Returns (status, message) where status is one of
    'written' | 'skipped' | 'error'."""
    try:
        text = src.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        return "error", f"read failed: {e}"

    fm, body = parse_frontmatter(text)
    has_description = bool(fm.get("description"))

    if has_description and not fm.get("resource") is None and dst.exists():
        # Already migrated in a prior run; idempotent skip.
        return "skipped", "already has description"

    if has_description:
        # Preserve the existing description verbatim, just normalize order.
        description = str(fm["description"]).strip()
    else:
        description = first_non_heading_paragraph(body)
        if not description:
            # Fall back to the first 120 chars of body
            description = body.strip().replace("\n", " ")[:120]

    # Build the new frontmatter.
    new_lines = ["---"]
    seen: set[str] = set()
    for key in OKF_CORE_FIELDS:
        if key == "description":
            new_lines.append(f"description: {format_value(description)}")
        elif key == "resource":
            new_lines.append("resource: ")
        else:
            val = fm.get(key, "")
            new_lines.append(f"{key}: {format_value(val)}")
        seen.add(key)
    # Custom fields after OKF core.
    for key, val in fm.items():
        if key in seen:
            continue
        if key in OKF_CORE_FIELDS:
            continue
        new_lines.append(f"{key}: {format_value(val)}")
    new_lines.append("---")
    new_lines.append("")
    new_lines.append(body.rstrip())
    new_text = "\n".join(new_lines)

    if not dry_run:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists() and dst.read_text(encoding="utf-8") == new_text:
            return "skipped", "no change"
        dst.write_text(new_text, encoding="utf-8")

    return "written", description if not has_description else "(preserved)"


def migrate_bundle(
    source: Path, target: Path, *, dry_run: bool = False
) -> MigrationStats:
    stats = MigrationStats()
    if not source.is_dir():
        raise FileNotFoundError(f"source not found: {source}")
    for project_dir in sorted(p for p in source.iterdir() if p.is_dir()):
        stats.projects.add(project_dir.name)
        for md in project_dir.rglob("*.md"):
            if md.name == "index.md":
                # Don't migrate project-level index.md; the store regenerates it.
                continue
            stats.files_seen += 1
            rel = md.relative_to(source)
            dst = target / rel
            status, msg = migrate_file(md, dst, dry_run=dry_run)
            if status == "written":
                stats.files_written += 1
                if "preserved" not in msg:
                    stats.descriptions_added += 1
            elif status == "skipped":
                stats.files_skipped += 1
    return stats


def main(argv: list[str] | None = None) -> int:
    default_source = Path.home() / "SecondBrain" / "memory" / "projects"
    default_target = Path(__file__).resolve().parent.parent / "memory" / "projects"

    parser = argparse.ArgumentParser(description="Migrate legacy SecondBrain bundle to OKF v0.1")
    parser.add_argument("--source", type=Path, default=default_source,
                        help=f"Source bundle path (default: {default_source})")
    parser.add_argument("--target", type=Path, default=default_target,
                        help=f"Target bundle path (default: {default_target})")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would change without writing")
    args = parser.parse_args(argv)

    source = args.source.expanduser().resolve()
    target = args.target.expanduser().resolve()

    if not source.is_dir():
        print(f"error: source not found: {source}", file=sys.stderr)
        return 2

    print(f"Migrating {source} -> {target}")
    if args.dry_run:
        print("(dry run; no files will be written)")

    stats = migrate_bundle(source, target, dry_run=args.dry_run)
    print(
        f"projects={len(stats.projects)} seen={stats.files_seen} "
        f"written={stats.files_written} skipped={stats.files_skipped} "
        f"descriptions_added={stats.descriptions_added}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
