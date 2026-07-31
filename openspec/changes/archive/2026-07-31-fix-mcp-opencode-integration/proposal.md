## Why

The memory system backend is complete and verified (store with dedup fix, clean bundle, MCP server, digest scripts), but its integration with OpenCode is broken in two ways:

1. **MCP spawn is fragile.** `~/.config/opencode/opencode.json` registers the memory MCP as `["python", "memory_server/server.py"]` — a **relative path** that only resolves when OpenCode starts in this repo. From any other project directory the MCP fails to spawn, so `/brain` has no backend. The command also uses `python`, which may not exist on systems that only ship `python3`. This defeats the whole point of a second brain: it must work **cross-project**.

2. **Plugin has two divergent copies.** OpenCode loads the global copy (`~/.config/opencode/plugins/src/obsidian-second-brain-memory/`, ~36K, full hook wiring), while the repo's `.opencode/plugins/memory/index.ts` (9.3K) is a development copy of pure functions whose own comment says the real integration lives in a `register.ts` **that does not exist**. Iterating in the repo does not affect what OpenCode runs — changes drift silently.

## What Changes

- **Fix MCP spawn command**: use an absolute, interpreter-resolved invocation (`uv run --directory <repo> python memory_server/server.py`) so the MCP starts from any working directory.
- **Establish plugin source of truth**: decide whether the repo or the global copy is canonical; add a sync/install step so the two cannot drift silently.
- **Complete the deferred validations** from `fix-memory-store-dedup`: full test suite, `okf_validate.py --strict`, digest idempotency (run twice, no duplicate `-N` files).

## Capabilities

### New Capabilities
(none)

### Modified Capabilities
- `memory-mcp-server`: spawn invocation becomes interpreter-resolved and directory-pinned (was relative path + bare `python`); behavior from any cwd is now specified.
- `opencode-plugin`: single source of truth for the plugin entry point is specified (was: unspecified, two copies exist).

## Impact

- `~/.config/opencode/opencode.json` — MCP `memory.command` updated.
- Plugin files: repo `.opencode/plugins/memory/` and/or `~/.config/opencode/plugins/src/obsidian-second-brain-memory/` depending on chosen source of truth.
- Validation: `tests/` full suite green; `memory/` bundle passes strict OKF validation; digest idempotency confirmed.
- No changes to the memory store, OKF format, or MCP tool surface — this change is integration/config + validation only.
