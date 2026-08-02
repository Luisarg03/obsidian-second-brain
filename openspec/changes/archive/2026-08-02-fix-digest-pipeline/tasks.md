## 1. Digest JSON robustness

- [x] 1.1 Rewrite `repair_json` in `scripts/digest_session.py`: try `json.loads()` on raw text first; apply fence/trailing-comma repairs only when needed; never alter single quotes when the document contains double quotes; add a state-machine scanner for all-single-quoted documents
- [x] 1.2 Accept a single-object LLM response in `extract_entries`/`validate_entries`: wrap a dict containing `entry_type` in a list
- [x] 1.3 Add unit tests in `tests/` covering: content with single quotes inside double-quoted JSON, single-object response, trailing commas, code fences, all-single-quoted document

## 2. Digest observability

- [x] 2.1 Add a `FileHandler` to `digest_session.py` writing to `memory/logs/digest.log` (create dir on demand) with INFO level, keeping the console handler
- [x] 2.2 In `.opencode/plugins/memory/register.ts` `spawnDigest`, open `memory/logs/digest-spawn.log` and pass it as `stdio` for stdout/stderr instead of `"ignore"`
- [x] 2.3 Verify a manual digest run appends parse errors and result summaries to the log files

## 3. session.idle automatic capture

- [x] 3.1 In `.opencode/plugins/memory/register.ts`, replace the `session.idle` handler's `client.tui.appendPrompt(...)` call with the same digest path used by `dispose()` (fetch transcript → write tmp file → spawn digest)
- [x] 3.2 Ensure `checkpointDelivered` is set when the idle capture is spawned (at most one capture per session) and that compaction/`/checkpoint` prompts remain unchanged
- [x] 3.3 Update plugin unit tests for the new idle behavior (capture spawned, no composer injection, no-activity silent, duplicate suppressed)

## 4. Verification

- [x] 4.1 Reproduce the original failure: run `digest_session.py` against `/tmp/opencode-digest-ses_03cb57a66ffegHYYnLr4y2x25O.txt` (or a current transcript) and confirm entries are upserted now
- [x] 4.2 Run `uv run pytest` and `uv run okf-validate --strict` and confirm green
- [x] 4.3 Confirm `memory/logs/digest.log` and `memory/logs/digest-spawn.log` exist after a session end
