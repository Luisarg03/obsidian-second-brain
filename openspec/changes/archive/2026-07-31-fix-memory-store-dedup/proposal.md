## Why

The `memory-store` dedup mechanism is broken. `upsert_entry()` writes the OKF Markdown file unconditionally before checking the SQLite dedup key. Every re-run of the digest pipeline creates a duplicate `.md` file (with `-2`, `-3`, … suffixes) even when the content is identical. The project index then lists all duplicates, corrupting the bundle's readability and trustworthiness. This was discovered during post-foundations exploration when `SecondBrain/index.md` showed 8 duplicate entries for the same decision, fact, and learning.

## What Changes

- **Fix dedup ordering in `upsert_entry()`**: Check the SQLite dedup key BEFORE writing the OKF file. If a match exists, update the SQLite row in place and skip the file write entirely.
- **Clean up existing duplicates**: Write a one-shot cleanup script that scans `memory/projects/<project>/<type>/` for duplicate-content files (same content hash), deletes the duplicates, and regenerates the project `index.md`.
- **Add regression test**: A test that calls `upsert_entry()` twice with identical content and asserts exactly one `.md` file exists on disk.

No spec-level requirement changes — the dedup behavior is already specified; the implementation is wrong.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

(none — implementation fix only, no requirement changes)

## Impact

- `memory_server/store.py`: `upsert_entry()` method reordered
- `scripts/cleanup_duplicates.py`: new one-shot cleanup script
- `tests/`: regression test for dedup behavior
- `memory/projects/*/`: existing duplicate `.md` files removed
- No API changes, no dependency changes, no breaking changes
