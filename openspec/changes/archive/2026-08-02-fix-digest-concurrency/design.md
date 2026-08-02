## Context

The post-session digest pipeline extracts OKF entries from session transcripts via a structured LLM call to local Ollama (`qwen3:8b`, CPU, serialized inference). `register.ts` `dispose` → `digestSessions()` spawns one detached `uv run python scripts/digest_session.py` per known session with no concurrency control. On 2026-08-02, an instance ending 7 sessions spawned 7 concurrent digests; Ollama's queue pushed every request past the 60s client timeout (`HTTPLLMClient`, `digest_session.py:234`), retries (3, jittered) exhausted, and 5-6 sessions' captures were lost with only WARNING/ERROR log lines in `memory/logs/digest.log`.

Validation (2026-08-02): single-run digest succeeds in ~30s (upserted=1, verified end-to-end). Failure is scheduling + timeout policy, not the pipeline itself.

Constraints:
- Plugin children are `detached: true, unref()` — they survive server exit; the plugin cannot await them.
- Multiple opencode instances may dispose concurrently (two servers ending at once).
- No new dependencies allowed; stdlib only.
- Specs (`memory-triggers`, `opencode-plugin`, `auto-session-digest`) declare `session.end` and `tui.prompt.append` hooks that the implementation does not actually use (`dispose` + `session.idle`, `experimental.chat.messages.transform`).

## Goals / Non-Goals

**Goals:**
- Zero capture loss when N sessions end together: digests run one at a time.
- LLM calls succeed under queueing: timeout/retry policy matches measured CPU latency (~30s single, >60s queued).
- Specs declare the hooks that are actually implemented.
- A failed batch is greppable: batch size, per-session outcome, lock-wait events.

**Non-Goals:**
- Model change (switching digest to `qwen3:4b`) — remains a config knob via `LLM_MODEL`; not the default.
- Distributed/networked memory capture; only local Ollama.
- Re-architecting the plugin's hook surface beyond the two documented deviations.
- Recovering the 7 sessions already lost on 2026-08-02 (transcripts still exist in `/tmp/opencode-digest-*.txt`; a manual re-digest is possible but out of scope).

## Decisions

### D1: Serialize in the script with `fcntl.flock`, not in the plugin

Each digest process acquires an exclusive `flock` on `memory/logs/digest.lock` before calling the LLM; if busy, it waits (poll loop) up to a bounded budget, then runs.

- **Why flock over plugin-side queue:** plugin children are fire-and-forget; the plugin cannot coordinate them after spawn. `flock` also covers the cross-instance case (two servers disposing at once) and manual runs, for free. Kernel auto-releases on process death — no stale-lock problem (unlike an `O_EXCL` marker file, which requires staleness heuristics).
- **Alternatives considered:** plugin-side serialized queue (await one digest before spawning next) — rejected: doesn't protect against concurrent instances, and couples the plugin to child lifecycle it intentionally detaches from. `O_EXCL` lock file — rejected: stale-lock crash recovery. `socketlock`/semaphore — rejected: extra moving parts, no benefit over flock.
- **Trade-off:** N waiters sleep-poll while one runs. Bounded wait + cheap poll makes this acceptable; the common case (1-3 sessions) waits seconds.

### D2: Raise LLM timeout to 180s, widen backoff

`HTTPLLMClient` timeout 60s → 180s default; retry delays 2/4/8s → 5/10/20s (jittered, 3 attempts).

- **Why:** measured single-run ~30s; behind 2-5 queued requests, a call can exceed 60s. 180s × 3 attempts bounds worst case at ~9.5 min per session but makes queue-induced failure virtually impossible on this hardware.
- **Alternatives considered:** adaptive timeout from queue position — rejected: complexity without measured need. Keep 60s and rely on serialization only — rejected: serialization still leaves the FIRST process uncontended (fast) but later ones arrive after earlier ones have already failed; timeout must cover the queued case as defense in depth.
- **Trade-off:** worst-case tail latency per session grows; mitigated by D3 (fewer spawns) and the fact this is background work with no user waiting.

### D3: Plugin-side spawn gate (skip empty/trivial sessions)

Before spawning, `digestSession` skips when the transcript is empty or < 200 chars (mirrors the script's heuristic), and skips sessions whose `SessionState.hasActivity` is false.

- **Why:** the 35-session batch case is mostly short sessions (observed transcripts of 105-540B); gating at the source cuts spawn count and lock contention before they reach the script.
- **Alternatives considered:** rely solely on the script's <200-char gate — rejected: the spawn still costs a full `uv run` startup per session and pollutes `/tmp`.
- **Trade-off:** a session with only reads (no edits/bash) is never digested — matches the documented activity contract (`session.idle` capture already requires activity; dispose should too).

### D4: Spec reconciliation (declare reality)

- `memory-triggers`: replace the `session.end` requirement with `server.instance.disposed` (`dispose`) + `session.idle` post-session extraction; keep the "transcript unavailable" and "30-second window" semantics but bound them to the implemented hooks.
- `opencode-plugin`: post-session extraction requirement re-declared for `dispose`; `tui.prompt.append` requirement re-declared as `experimental.chat.messages.transform`.
- Both specs gain the single-flight (D1) and spawn-gate (D3) requirements.

- **Why:** the specs are the contract for tests and future work; three scenarios in them cannot pass as written. Re-declaring beats papering over with prose.
- **Alternative considered:** keeping specs aspirational and documenting deviations in design only — rejected: the verification pipeline (`openspec-verify-change`) checks scenarios against behavior.

### D5: Batch observability

At `dispose`, the plugin logs the batch: `digest batch: N sessions, spawning`. The script logs lock-wait start/finish and already logs the per-run `digest result`. `digest-spawn.log` continues to capture child stdout/stderr (exec-level failures).

## Risks / Trade-offs

- [Lock holder stuck → waiters block] → Bounded wait budget (configurable, default 10 min); on expiry, log and skip with exit 0. flock is auto-released on holder death, so the only stuck case is a hung LLM call, which D2's retry budget bounds.
- [Tail latency: 7 sessions now take up to ~20+ min serially] → Acceptable for background capture; no user waits on it; D3 reduces spawn counts; `LLM_MODEL=qwen3:4b` is the escape hatch.
- [Spec scenarios rewritten → verification churn] → Delta specs are additive/declarative; existing scenarios updated in-place with clear "changed" markers; CI `okf-validate` and `npm run typecheck` keep the change honest.
- [Lock file inside the bundle (`memory/logs/`) gets synced to Obsidian] → `.obsidian` ignore rules already exclude `logs/`; verify `.gitignore` covers `memory/logs/` for the repo copy.

## Migration Plan

1. Land script changes (D1, D2) first — independently safe, backward compatible.
2. Land plugin changes (D3, D5) — deploy by restarting opencode (plugin loads from repo path, no copy step per spec).
3. Land spec deltas (D4) last, after behavior is verified.
4. Rollback: revert commits; old plugin + old script interoperate (no lock file conflict — old script ignores the lock).

## Open Questions

- Should the digest batch retry failed sessions on the NEXT dispose (persistent pending queue)? — Deferred: adds state; the transcripts already live in `/tmp` only until reboot, so a durable queue is a separate change.
- Lock budget value (10 min) and timeout (180s) are measured estimates; confirm against a real 7-session dispose after landing.
