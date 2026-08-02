## Why

The post-session digest pipeline loses captures under concurrency: `dispose` in `register.ts` spawns one digest process per known session simultaneously, all hitting Ollama (CPU, serialized inference) at once. With 7 sessions ending together (observed 2026-08-02 14:17 local), every request exceeded the 60s client timeout, retries exhausted, and the sessions' knowledge was silently dropped (`LLM call failed after retries: timed out` ×5, zero upserts). A single-run digest succeeds in ~30s, so the pipeline itself works — the failure is purely a scheduling and timeout policy problem.

## What Changes

- **Serialize digest execution**: at most one digest process runs at a time (lock file); queued sessions run sequentially after the active one completes.
- **Relax LLM timeout policy**: raise the per-request timeout and retry budget so queued CPU inference has room to complete (60s → 180s default).
- **Skip empty sessions at spawn time**: the plugin stops spawning digests for sessions with no transcript or no meaningful activity (script-side <200-char heuristic stays as a second gate).
- **Reconcile trigger specs with the implemented hooks**: `session.end` is implemented as `dispose` + `session.idle`; `tui.prompt.append` is implemented as `experimental.chat.messages.transform`. Specs get updated to match reality.
- **Improve observability**: log batch spawns and per-session outcomes (including the final upsert line) so a failed batch is greppable in one place.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `auto-session-digest`: add a concurrency-serialization requirement (single digest at a time) and a new timeout/retry policy for the LLM client.
- `opencode-plugin`: reconcile post-session extraction trigger declaration (`dispose` + `session.idle` instead of `session.end`), add the spawn gate (skip sessions without activity) and the concurrency guard.
- `memory-triggers`: re-declare the post-session trigger as dispose/idle-based, and declare the single-flight constraint on digest execution.

## Impact

- `scripts/digest_session.py`: timeout defaults, retry policy, optional lock acquisition.
- `.opencode/plugins/memory/register.ts`: serialized spawn queue, activity gate before spawn, batch logging.
- `openspec/specs/`: delta specs for the three capabilities above.
- Tests: `tests/` and plugin unit tests for the new serialization/skip logic.
- No API or schema changes; no new dependencies (lock via stdlib `fcntl`/O_EXCL marker file).
