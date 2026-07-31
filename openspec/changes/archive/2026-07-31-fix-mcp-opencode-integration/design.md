## Context

The memory system works in this repo but its OpenCode integration has two fragilities (see proposal): a relative-path MCP spawn and two divergent plugin copies. This change is integration/config only — no changes to the store, OKF format, or MCP tool surface.

## Goals / Non-Goals

**Goals:**
- MCP server spawns successfully regardless of the OpenCode working directory
- Exactly one canonical plugin implementation, versioned in git
- Deferred validations from `fix-memory-store-dedup` completed (suite, okf_validate, digest idempotency)

**Non-Goals:**
- Publishing the plugin to a package registry
- Changing MCP tool signatures or plugin hook behavior
- Supporting non-uv environments

## Decisions

### Decision 1: MCP spawn via `uv run --directory`

Replace `["python", "memory_server/server.py"]` in `~/.config/opencode/opencode.json` with:

```json
"command": ["uv", "run", "--directory", "/home/hiro03/Private/Projects/ObsidianSecondBraind", "python", "memory_server/server.py"]
```

- `uv run --directory <repo>` sets cwd to the repo, so the script path resolves and `memory_server` is importable.
- `uv` resolves the project environment (the `mcp` dependency), so no bare-`python` ambiguity.
- Absolute repo path is hardcoded: the global opencode config is already per-user, per-machine. Portability across machines is a non-goal.

**Rejected:** absolute `python3` + absolute script path — leaves package imports and the venv unresolved. **Rejected:** `PYTHONPATH=... python3 ...` — same env problem, more fragile.

### Decision 2: Repo is the plugin source of truth; global location becomes a symlink

1. Diff the global copy (`~/.config/opencode/plugins/src/obsidian-second-brain-memory/`) against the repo copy (`.opencode/plugins/memory/`). The global copy is what OpenCode actually runs (~36.7K, full wiring), so it is the more complete one: adopt the global implementation into the repo, including the entry point the repo copy lacks (its `register.ts` equivalent).
2. Replace the global directory with a symlink pointing at the repo plugin directory. The global `package.json` already maps `"obsidian-second-brain": "file:./plugins/src/obsidian-second-brain-memory"`; resolving through a symlink keeps one source of truth with zero copy logic.
3. Fallback: if plugin resolution through the symlink breaks, replace the symlink with a tiny `scripts/install_plugin.sh` that copies the repo plugin into the global location.

**Rejected:** global copy stays canonical and the repo copy is deleted — the plugin source would leave version control and be invisible to this project's history. **Rejected:** a permanent two-way sync script — drift risk remains by design.

### Decision 3: Complete deferred validations

- Full pytest suite green.
- `scripts/okf_validate.py --strict` on the live bundle exits 0.
- Digest idempotency: run `digest_session.py` twice against a temp copy of the bundle with a tiny transcript; file count and SQLite entry count must be identical between runs and no `-N` suffixed files may appear.

## Risks / Trade-offs

- **Symlink unsupported by plugin loader**: opencode/bun may not follow symlinks for `file:` deps. → Mitigation: Decision 2 fallback install script.
- **Adopting global over repo loses repo-only improvements**: the repo copy may contain newer pure functions than the global copy. → Mitigation: task 1 requires a diff first; any repo-only improvements must be preserved during adoption, not blindly overwritten.
- **uv not installed**: command fails on spawn. → Low risk: the project already uses `uv run` for its own tooling.
