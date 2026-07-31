## 1. Fix dedup ordering in memory store

- [x] 1.1 Reorder `upsert_entry()` in `memory_server/store.py`: move SQLite `SELECT dedup_key` before `_write_okf_file()`. If match exists, update SQLite row and return early (no file write).
- [x] 1.2 Verify `rebuild_index.py` still works correctly after the fix (run against existing `memory/` bundle).

## 2. Cleanup script for existing duplicates

- [x] 2.1 Create `scripts/cleanup_duplicates.py`: walk all `memory/projects/<project>/<type>/` directories, parse each `.md` via `_parse_okf_file()`, group by content hash, delete duplicates (keep oldest by filename), regenerate project `index.md`.
- [x] 2.2 Run cleanup script against the live `memory/` bundle and verify duplicates are removed.
- [x] 2.3 Re-run `rebuild_index.py` after cleanup to ensure SQLite index matches the cleaned file tree.

## 3. Regression test

- [x] 3.1 Add test: `upsert_entry()` called twice with identical content produces exactly one `.md` file and second call returns `updated: True`.
- [ ] 3.2 Run full test suite to confirm no regressions.

## 4. Validation

- [ ] 4.1 Run `scripts/okf_validate.py --strict` against the cleaned bundle to confirm conformance.
- [ ] 4.2 Verify `digest_session.py` can be run twice on the same transcript without producing duplicate files.
