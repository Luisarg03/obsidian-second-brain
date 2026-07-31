"""One-shot cleanup: remove duplicate OKF Markdown files from the bundle.

Walks `memory/projects/<project>/<type>/` for every entry type (decisions,
facts, learnings, conventions, profiles), parses each file with
`_parse_okf_file()`, and groups files by the same content hash that
`MemoryStore._make_dedup_key()` uses. When several files hash identically
(same content, `-N` filename suffixes), only the original non-suffixed file
is kept and the rest are deleted. Each affected project's `index.md` is
regenerated afterwards.

The SQLite index is NOT touched; run `scripts/rebuild_index.py` afterwards so
the derived index matches the cleaned file tree.

Usage:
    cleanup-duplicates                  # default: ./memory
    cleanup-duplicates --memory-path PATH
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

from memory_server.store import MemoryStore, _DIR_TO_SINGULAR, _parse_okf_file


def _dedup_key(project: str, entry_type: str, content: str) -> str:
    """SHA-256 content hash, identical to MemoryStore._make_dedup_key()."""
    key_str = f"{project}:{entry_type}:{content.strip().lower()}"
    return hashlib.sha256(key_str.encode()).hexdigest()


def _has_numeric_suffix(path: Path) -> bool:
    """True when the filename carries a `-N` disambiguation suffix."""
    return bool(re.search(r"-\d+\.md$", path.name))


def _collect_files(memory_path: Path) -> list[tuple[Path, str, str, str]]:
    """Return (file_path, project, entry_type, content) for parseable files."""
    projects_dir = memory_path / "projects"
    if not projects_dir.is_dir():
        return []

    files: list[tuple[Path, str, str, str]] = []
    for proj_dir in sorted(p for p in projects_dir.iterdir() if p.is_dir()):
        project = proj_dir.name
        for tdir, entry_type in _DIR_TO_SINGULAR.items():
            tpath = proj_dir / tdir
            if not tpath.is_dir():
                continue
            for f in sorted(tpath.glob("*.md")):
                parsed = _parse_okf_file(f)
                if parsed is None:
                    print(
                        f"  skip (unparseable): {f.relative_to(memory_path)}",
                        file=sys.stderr,
                    )
                    continue
                files.append((f, project, entry_type, parsed["content"]))
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Remove duplicate OKF Markdown files from the memory "
        "bundle"
    )
    parser.add_argument(
        "--memory-path",
        type=Path,
        default=Path("./memory"),
        help="Path to the OKF bundle directory (default: ./memory)",
    )
    args = parser.parse_args(argv)

    memory_path = args.memory_path.resolve()
    if not memory_path.is_dir():
        print(f"error: {memory_path} is not a directory", file=sys.stderr)
        return 2

    files = _collect_files(memory_path)
    if not files:
        print("No entries found in bundle; nothing to do.")
        return 0

    # Group files by content hash within the same project + entry type.
    groups: dict[str, list[tuple[Path, str, str, str]]] = {}
    for file_path, project, entry_type, content in files:
        key = _dedup_key(project, entry_type, content)
        groups.setdefault(key, []).append(
            (file_path, project, entry_type, content)
        )

    store = MemoryStore(storage_path=memory_path)
    totals = {"scanned": 0, "duplicates": 0, "deleted": 0}
    affected_projects: set[str] = set()

    print(f"Scanning {memory_path} ...")
    for key, members in sorted(groups.items()):
        if len(members) == 1:
            continue
        totals["scanned"] += len(members)
        # Prefer the file without a `-N` suffix (the original), then oldest
        # by filename sort (earliest date for dated entries).
        keeper, *duplicates = sorted(
            members,
            key=lambda m: (_has_numeric_suffix(m[0]), m[0].name),
        )
        totals["duplicates"] += len(duplicates)
        totals["deleted"] += len(duplicates)

        project = keeper[1]
        affected_projects.add(project)
        print(f"\n{project}: {len(duplicates)} duplicate(s) "
              f"of {keeper[0].name}")
        for file_path, _, _, _ in duplicates:
            file_path.unlink()
            print(f"  deleted: {file_path.relative_to(memory_path)}")

    # Regenerate index.md for every project touched by a deletion.
    for project in sorted(affected_projects):
        store._regenerate_project_index(project)

    print(
        f"\nDone. Files scanned: {totals['scanned']}, "
        f"duplicates found: {totals['duplicates']}, "
        f"deleted: {totals['deleted']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
