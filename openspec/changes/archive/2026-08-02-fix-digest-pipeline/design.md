## Context

The memory pipeline: plugin `dispose()`/`session.idle` → fetch session transcript → write to `/tmp` → `spawn("uv", ["run", ..., "digest_session.py", ...])` with `stdio: "ignore"` → `digest_session.py` calls a local LLM (Ollama, `qwen3:8b`) with a JSON output schema → repairs common JSON issues → validates against `EXTRACTION_SCHEMA` → upserts OKF entries into `memory/`.

Diagnosed failures (verified by reproduction with a real transcript on 2026-08-02):
1. `repair_json()` converts single quotes inside double-quoted strings to double quotes (`'cerebro'` → `"cerebro"`), producing invalid JSON → parse error → zero upserts.
2. The LLM sometimes returns a single object `{...}` instead of an array `[...]`; `validate_entries()` rejects non-list payloads → zero upserts.
3. Spawn uses `stdio: "ignore"` — all errors and warnings vanish, so the pipeline appears dead.
4. `session.idle` uses `client.tui.appendPrompt` to inject a checkpoint into the user's input box; capture only happens if the user manually sends that text (the agent then calls `store_*`). Users never send it.

## Goals / Non-Goals

**Goals:**
- The digest persists entries reliably regardless of the LLM's JSON formatting quirks.
- Every digest run leaves a trace in a persistent log file (success summary or failure reason).
- Automatic capture happens without any manual user interaction.

**Non-Goals:**
- No change to the OKF entry schema or the memory store.
- No change to the MCP server.
- No change to other triggers (git commit checkpoint, compaction checkpoint, `/checkpoint`).
- Plugin stays project-local (global install is a separate concern).

## Decisions

### D1: Repair JSON incrementally, never touch single quotes inside double-quoted documents
`repair_json` currently does one-shot regex passes. The fix:
1. Try `json.loads()` on the raw text first.
2. If that fails, apply only fence stripping and trailing-comma removal, then retry `json.loads()`.
3. If the document contains double quotes (`"` present), leave all single quotes untouched — they are string content (the actual failure mode).
4. Only when the document has no double quotes at all (LLM emitted single-quoted JSON) convert single quotes with a small state-machine scanner that toggles in/out of strings on `'` and treats `\'` as an escape.

Rationale: the observed failure is mixed usage (double-quote delimiters + single-quote content). Converting content quotes is always wrong. Alternatives considered: `ast.literal_eval` (rejected: unsafe on arbitrary LLM text), third-party tolerant parser (rejected: new dependency for a rare case).

### D2: Accept single-object responses
After parse, if the payload is a dict containing `entry_type`, wrap it in a list before validation. `validate_entries` already filters invalid items, so wrapping is safe and idempotent.

### D3: Persistent digest log
- `digest_session.py`: add a `FileHandler` on `memory/logs/digest.log` (created on demand) at `INFO` level, alongside the existing console handler. Log parse errors, LLM failures, and the final `DigestResult` summary.
- Plugin `spawnDigest`: open a file handle on `memory/logs/digest-spawn.log` and pass it as `stdio` for stdout/stderr instead of `"ignore"`.

Rationale: the bundle already contains non-OKF files (`memory.db`, `tag-vocabulary.json`, `tool-calls.log`), so a `logs/` subdirectory is consistent.

### D4: session.idle runs automatic capture
Replace `client.tui.appendPrompt(...)` in the `session.idle` handler with the same digest path used by `dispose()`: fetch transcript → write to tmp → spawn digest. Set `checkpointDelivered = true` after spawning (the flag already exists) so idle fires at most one capture per session. Keep the compaction and `/checkpoint` prompts unchanged.

Rationale: the digest is idempotent (upsert dedup), so a second run at `dispose()` is harmless. Alternatives considered: keep the composer injection (rejected: requires manual send that never happens).

## Risks / Trade-offs

- [Ollama/LLM service down when idle fires] → digest fails but is now logged in `memory/logs/digest.log`; retry policy already exists; `dispose()` runs again at session end.
- [Double digest run (idle + dispose)] → acceptable: upsert dedup makes it idempotent; cost is one extra local LLM call per session.
- [All-single-quote LLM responses remain edge-case risky] → mitigated by D1 step 4 state machine; worst case falls back to "unparseable, logged" instead of silent zero.
- [`memory/logs/` could confuse OKF validation] → `okf_validate.py` already tolerates non-OKF files in the bundle (memory.db etc.); verify with `uv run okf-validate --strict` before merge.

## Migration Plan

No data migration. Rollback: revert the change; the previous behavior (silent failures) returns.

## Open Questions

None blocking. (Global plugin install and the dreamer trigger remain out of scope.)
