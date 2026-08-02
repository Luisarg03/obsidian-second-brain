## 1. Digest script: serialization lock (D1)

- [x] 1.1 Add a lock module to `scripts/digest_session.py`: acquire exclusive advisory lock on `memory/logs/digest.lock` via `fcntl.flock` (non-blocking try + poll loop, 1s interval, bounded budget default 600s, configurable via `--lock-timeout` / env).
- [x] 1.2 Acquire the lock in `main()` before the LLM call chain; log lock acquired / lock wait start / lock wait expiry; on expiry, log and exit 0 with zero writes.
- [x] 1.3 Add tests in `tests/test_digest.py`: two concurrent runs serialize (second waits then completes); lock budget expiry logs and skips; lock is released on process exit.
- [x] 1.4 Run `uv run python -m pytest tests/test_digest.py` — all pass.

## 2. Digest script: timeout / retry policy (D2)

- [x] 2.1 Change `HTTPLLMClient` default timeout from 60s to 180s (constructor + CLI `--timeout`).
- [x] 2.2 Change retry backoff bases from (2, 4, 8) to (5, 10, 20) seconds, jittered, 3 attempts.
- [x] 2.3 Update existing retry/backoff assertions in `tests/test_digest.py` to the new policy; add a test that a call timing out at 60s+ still succeeds within the 180s window (simulated sleep/fake client).
- [x] 2.4 Run `uv run python -m pytest tests/test_digest.py` — all pass.

## 3. Plugin: spawn gate + batch observability (D3, D5)

- [x] 3.1 In `.opencode/plugins/memory/register.ts`, `digestSession()`: skip when transcript is empty or < 200 chars, or when the session's `SessionState.hasActivity` is false; log the skip reason.
- [x] 3.2 In `dispose`/`digestSessions()`: log a batch summary `digest batch: N sessions` before spawning; log per-session spawn/skip lines.
- [x] 3.3 Add unit tests in `tests/test_plugin.py` for the spawn gate (no activity → skip; short transcript → skip; activity + long transcript → spawn) and batch logging.
- [x] 3.4 Run `uv run python -m pytest tests/test_plugin.py` and the plugin's `npm test` / `npm run typecheck` — all pass.

## 4. Hygiene

- [x] 4.1 Add `memory/logs/` to `.gitignore` (runtime digest logs; currently untracked by accident).

## 5. Spec deltas finalization

- [x] 5.1 Run `openspec validate --change fix-digest-concurrency` — clean (no missing requirements, all headers/scenarios well-formed).
- [x] 5.2 Run full CI gates locally: `uv run python -m pytest`, `npm run typecheck`, `npm test`, `uv run okf-validate --strict`.

## 6. End-to-end verification

- [x] 6.1 Reproduce the failure scenario: spawn 6+ concurrent digest runs against real transcripts (e.g. `/tmp/opencode-digest-*.txt`) pointing at a throwaway memory path — verify exactly one LLM call chain runs at a time and all runs complete with upserts (no `LLM call failed after retries`).
- [x] 6.2 Simulate disposal: run the plugin batch path against a temp session list — verify batch log lines and that no digest is spawned for trivial sessions.
- [x] 6.3 Verify `memory/logs/digest.log` shows lock events + per-run results; `digest-spawn.log` captures exec-level failures only.
- [x] 6.4 Confirm `memory/projects/<project>/` gains entries and `search_memory` returns them.
