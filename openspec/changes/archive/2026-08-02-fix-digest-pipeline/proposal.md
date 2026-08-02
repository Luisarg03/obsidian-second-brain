# Fix Digest Pipeline

## Why

The automatic memory-capture pipeline (post-session digest) has been silently broken since 2026-07-31: it runs but never persists entries because the JSON repair pass corrupts valid LLM responses, the LLM sometimes returns a single object instead of an array, and every failure is discarded via `stdio: "ignore"` on the spawned process. Additionally, the `session.idle` checkpoint injects text into the composer input box and requires the user to manually send it, which never happens — so no memory has been captured for weeks.

## What Changes

- Fix `repair_json` so it no longer corrupts single quotes that are string *content* inside a double-quoted JSON document (the root cause: `'cerebro'` inside a content string was rewritten to `"cerebro"`, breaking the JSON).
- Accept an LLM response that is a single object instead of an array by wrapping it in an array.
- Make digest failures observable: log the digest run (parse errors, LLM failures, result summary) to a persistent log file instead of discarding output.
- Change the `session.idle` checkpoint from "inject prompt into composer" to "run automatic capture" (spawn the digest) when the session has tracked activity, once per session.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `auto-session-digest`: structured extraction becomes robust to single-quote content and single-object responses; failures are logged to a persistent file.
- `memory-triggers`: `session.idle` checkpoint runs automatic capture instead of injecting a prompt into the composer; `session.end` extraction output is redirected to a persistent log.

## Impact

- `scripts/digest_session.py`: `repair_json`, `validate_entries`, logging configuration.
- `.opencode/plugins/memory/register.ts`: `spawnDigest` stdio redirection, `session.idle` handler.
- `tests/`: unit tests for repair/parse robustness and trigger behavior.
- No changes to the OKF bundle schema, the MCP server, or the memory store.
