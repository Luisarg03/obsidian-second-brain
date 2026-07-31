"""Rebuild the SQLite search index from the OKF Markdown bundle.

Walks `memory/projects/<project>/<type>/*.md`, parses each file, and calls
`upsert_entry` so the SQLite index reflects the current state of the bundle.
Markdown is the source of truth; this script is the bridge back to the index.

Idempotent: re-running produces the same DB state (dedup keys are stable).

Usage:
    rebuild-index                       # default: ./memory
    rebuild-index --memory-path PATH    # explicit bundle path
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from memory_server.store import MemoryStore, _TYPE_DIR_MAP, _TYPE_LABEL_MAP


def _collect_entries(memory_path: Path) -> list[dict]:
    """Walk the bundle and return a list of entry dicts ready for upsert_entry."""
    projects_dir = memory_path / "projects"
    if not projects_dir.is_dir():
        return []

    # Reverse label -> dir map (e.g., "Decision" -> "decisions").
    label_to_dir = {v: k for k, v in _TYPE_LABEL_MAP.items()}
    # dir -> singular (e.g., "decisions" -> "decision").
    dir_to_singular = {v: k for k, v in _TYPE_DIR_MAP.items()}

    entries: list[dict] = []
    for proj_dir in sorted(p for p in projects_dir.iterdir() if p.is_dir()):
        project = proj_dir.name
        for tdir, type_singular in dir_to_singular.items():
            tpath = proj_dir / tdir
            if not tpath.is_dir():
                continue
            for f in tpath.glob("*.md"):
                if f.name == "index.md":
                    continue
                # Parse with the store's own parser.
                from memory_server.store import _parse_okf_file

                parsed = _parse_okf_file(f)
                if not parsed:
                    print(
                        f"  skip (unparseable): {f.relative_to(memory_path)}",
                        file=sys.stderr,
                    )
                    continue
                if parsed["entry_type"] != type_singular:
                    # Defensive: trust the directory, not the parsed label.
                    parsed["entry_type"] = type_singular
                parsed["project"] = project
                entries.append(parsed)
    return entries


def rebuild(memory_path: Path) -> tuple[int, int]:
    """Rebuild the SQLite index. Returns (created_or_updated, skipped)."""
    store = MemoryStore(storage_path=memory_path)
    store.initialize()

    entries = _collect_entries(memory_path)
    if not entries:
        print("No entries found in bundle; nothing to do.", file=sys.stderr)
        return 0, 0

    n_upserted = 0
    n_failed = 0
    for e in entries:
        try:
            store.upsert_entry(
                entry_type=e["entry_type"],
                project=e["project"],
                content=e["content"],
                tags=json_loads_safe(e.get("tags")),
                confidence=float(e.get("confidence") or 1.0),
                openspec_change_id=e.get("openspec_change_id") or None,
                description=e.get("description") or None,
            )
            n_upserted += 1
        except Exception as exc:
            n_failed += 1
            print(f"  failed: {e['project']}/{e['entry_type']}: {exc}", file=sys.stderr)
    return n_upserted, n_failed


def json_loads_safe(raw):
    import json

    if isinstance(raw, list):
        return raw
    if not raw:
        return []
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rebuild SQLite index from OKF bundle")
    parser.add_argument(
        "--memory-path",
        type=Path,
        default=None,
        help="Path to the OKF bundle directory (default: ./memory or $MEMORY_PATH)",
    )
    args = parser.parse_args(argv)

    if args.memory_path is not None:
        memory_path = args.memory_path.resolve()
    else:
        from memory_server.cli import get_memory_path

        memory_path = get_memory_path().resolve()

    if not memory_path.is_dir():
        print(f"error: {memory_path} is not a directory", file=sys.stderr)
        return 2

    print(f"Rebuilding index from {memory_path} ...")
    n_upserted, n_failed = rebuild(memory_path)
    print(f"Upserted: {n_upserted}, failed: {n_failed}")
    return 0 if n_failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
