## Context

The memory store (`memory_server/store.py`) persists entries as OKF Markdown files (source of truth) and indexes them in SQLite (derived search index). The `upsert_entry()` method currently writes the `.md` file unconditionally, then checks SQLite for a dedup match. When the digest pipeline re-processes the same session, identical content generates a new `.md` file with a `-N` suffix each time.

The dedup key is a SHA-256 hash of `project:entry_type:content.strip().lower()`. It is correct and unique per content. The problem is ordering: file write precedes the dedup check.

## Goals / Non-Goals

**Goals:**
- `upsert_entry()` called twice with identical content produces exactly one `.md` file
- Existing duplicates are cleaned up from all projects in `memory/projects/`
- `rebuild_index.py` continues to work correctly after the fix
- No changes to the dedup key algorithm, SQLite schema, or OKF frontmatter format

**Non-Goals:**
- Content-addressable filenames (hash-based slugs) — considered and rejected for this fix
- Cross-project dedup (entries with same content in different projects are valid)
- Profile entry dedup (already uses `(project, entry_type)` key, not content hash)

## Decisions

### Decision 1: Check dedup before file write

Move the SQLite `SELECT dedup_key` query before `_write_okf_file()`. If a match exists, update the SQLite row and return early — no file write.

**Why not content-addressable filenames (Option B)?** Using a content hash as the filename would make duplicates naturally overwrite. But it destroys human-readable filenames (`a3f2b1c4.md` vs `sqlite-wal-fts5.md`), hurting Obsidian navigation. The check-first approach fixes the bug with ~5 lines moved and preserves readability.

**Why not pass dedup to _write_okf_file (Option C)?** More code, more coupling, same outcome. The check-first approach is simpler.

### Decision 2: Cleanup script strategy

One-shot `scripts/cleanup_duplicates.py` that:
1. Walks `memory/projects/<project>/<type>/` for all `.md` files
2. Parses each file's content via `_parse_okf_file()`
3. Groups by content hash (`_make_dedup_key()`)
4. For each group with >1 file: keeps the first (oldest by filename), deletes the rest
5. Regenerates the project `index.md` via `_regenerate_project_index()`

This is a maintenance script, not a permanent feature. It runs once, then is kept for future use if duplicates recur.

### Decision 3: Regression test

A pytest test that:
1. Creates a temporary `MemoryStore`
2. Calls `upsert_entry()` twice with identical content
3. Asserts exactly one `.md` file exists in the temp directory
4. Asserts the second call returns `updated: True` (not `created: True`)

## Risks / Trade-offs

- **Race condition**: Two concurrent digests could both check, both miss, and both write. → Mitigation: SQLite WAL mode serializes writes; the dedup_key UNIQUE constraint would catch a true race on the SQLite side. The file write race is benign (worst case: one extra file).
- **SQLite lost, duplicates return**: If `memory.db` is deleted and rebuilt from `.md` files that still have duplicates, the rebuild re-inserts them. → Mitigation: The cleanup script removes existing duplicates. Future duplicates are prevented by the fix.
- **Cleanup script deletes wrong file**: The "keep first by filename" heuristic could theoretically keep a corrupt file. → Mitigation: All files in a duplicate group have identical content (verified by hash), so any choice is equivalent.
