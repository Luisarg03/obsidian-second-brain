## Why

The existing `~/SecondBrain` project has matured into a working agent-memory system (SQLite + MCP server + OpenCode plugin + 10 archived changes), but the knowledge bundle is not OKF-conformant, the project is not portable (path is hard-coded to `~/SecondBrain`), and the OpenCode plugin auto-injects ~2K chars into every session context — burning tokens unconditionally even when the user has not asked for the second brain to be loaded.

This change establishes the foundations of a new project (`ObsidianSecondBraind`) that:

1. Houses the knowledge bundle inside an Obsidian vault (`memory/`) so the user can browse, edit, and graph the brain in a tool the community already supports.
2. Formally adopts the **Open Knowledge Format (OKF) v0.1** so the bundle is portable to any OKF-aware consumer (not just opencode).
3. Inverts the read/write contract: **reads are opt-in** (no auto-inject on `session.created`), **writes are mostly auto** (post-session extraction, commit-anchored capture, compaction checkpoint). The user pays tokens only when they ask for memory.
4. Documents the lifecycle hook points where memory updates can fire as the project evolves, without implementing all of them up front.

The existing `~/SecondBrain` system serves as the source of truth during migration; its specs, MCP server, and plugin become the basis of the new project, adapted (not duplicated) for the new constraints.

## What Changes

- **New project layout.** Repo root = project (code, tooling, OpenSpec). `memory/` = OKF knowledge bundle opened as an Obsidian vault. `memory-server/` = Python MCP server. `openspec/` = capability specs. `scripts/` = OKF validation and migration tooling. `tests/` = automated checks.
- **OKF v0.1 conformance.** Every bundle document carries the OKF frontmatter fields (`type`, `title`, `description`, `resource`, `tags`, `timestamp`). A `scripts/okf_validate.py` script enforces the schema on every project file.
- **Vault metadata.** `memory/.obsidian/` configures Obsidian to treat the directory as a vault. `memory/index.md` is the OKF root index. `memory/log.md` is the chronological change log (per OKF spec, optional but recommended).
- **Port the four core capabilities** from `~/SecondBrain`, adapted for the new project:
  - `memory-store` — SQLite (WAL + FTS5) persistence with OKF frontmatter as source of truth.
  - `memory-mcp-server` — MCP tools (`store_decision`, `store_fact`, `store_learning`, `store_profile`, `search_memory`, `export_memories`, `get_profile`, `ping`). All read tools are opt-in (no background polling).
  - `opencode-plugin` — OpenCode Plugin API v2 plugin. **Removes the `session.created` auto-inject** of the 2K-char summary. **Keeps** the activity-aware `session.idle` checkpoint, `tool.execute.after` git-commit detection, `session.compacting` capture, `/checkpoint` slash, and `session.end` post-extraction.
  - `auto-session-digest` — LLM-based extraction of decisions/facts/learnings from session transcripts. Reuses the existing schema-validation, retry, tag-normalization, and confidence-scoring logic.
- **Two new capabilities** specific to this project:
  - `okf-bundle` — defines the OKF bundle structure: directory layout, frontmatter schema, reserved filenames (`index.md`, `log.md`), validation rules, and the rule that bundle content under `memory/` is the only project surface that agents may read.
  - `memory-triggers` — documents the lifecycle hook points available in OpenCode Plugin API v2 (`session.created`, `session.idle`, `tool.execute.after`, `tui.prompt.append`, `experimental.session.compacting`, `session.end`) and the external triggers (git post-commit, dreamer-nightly). For each hook, declares what it does, when it fires, and what it writes. Implementation of the documented hooks is deferred to follow-up changes.
- **Migrate the 9 existing projects** (`ArchCustom`, `FilesAnalizer`, `MyCv`, `OmniRoute`, `SecondBrain`, `Travel`, and others) from `~/SecondBrain/memory/projects/` into the new `memory/projects/`, with OKF frontmatter added and project index regenerated. This is a one-shot migration; new entries follow OKF natively.
- **No breaking changes** to external consumers: the MCP tool surface stays identical to `~/SecondBrain`'s. The breaking change is internal — `session.created` no longer auto-injects — and is scoped to the OpenCode plugin only.

## Capabilities

### New Capabilities

- `okf-bundle`: OKF v0.1 knowledge bundle living under `memory/`, opened as an Obsidian vault. Covers frontmatter schema, directory layout, reserved filenames, and the read-scope rule.
- `memory-triggers`: Declarative catalog of lifecycle hook points where memory capture can fire. Each hook documents its trigger event, payload, action, and write target. Implementation of individual hooks is deferred.
- `memory-store`: SQLite storage layer with WAL mode and FTS5 full-text search. Source of truth is OKF Markdown; SQLite is a derived search index. Supports decision, fact, learning, convention, and profile entry types with content-based deduplication and per-project profile upsert.
- `memory-mcp-server`: Python MCP server exposing `search_memory`, `store_decision`, `store_fact`, `store_learning`, `store_profile`, `export_memories`, `get_profile`, `ping` as MCP tools. All calls are explicit (no background polling).
- `opencode-plugin`: OpenCode Plugin API v2 plugin. Listens to `session.idle`, `tool.execute.after`, `tui.prompt.append`, `experimental.session.compacting`, and `session.end` to surface checkpoint prompts and trigger post-session extraction. Does NOT inject context on `session.created`.
- `auto-session-digest`: Post-session LLM-based extraction pipeline. Validates output against a JSON schema, retries transient API failures with exponential backoff, normalizes tags against a controlled vocabulary, assigns confidence scores, and is idempotent via dedup keys.

### Modified Capabilities

None. The four ported capabilities (`memory-store`, `memory-mcp-server`, `opencode-plugin`, `auto-session-digest`) already exist in `~/SecondBrain/openspec/specs/` but **not in this repo**, so they are new here, not modified. Once the change is archived, those specs will live in `openspec/specs/` of this project as new main specs.

## Impact

- **Code:** New project files in `memory-server/src/memory_server/`, ported and adapted from `~/SecondBrain/memory-server/src/`. New scripts: `scripts/okf_validate.py`, `scripts/okf_migrate.py`.
- **MCP tool surface:** Identical to `~/SecondBrain` (8 tools, same names and parameters). Existing opencode configs that point at the old path need to be updated to point at the new project root.
- **OpenCode plugin config:** `~/.config/opencode/opencode.jsonc` (or equivalent) must be updated to load the plugin from `~/Private/Projects/ObsidianSecondBraind/.opencode/` instead of `~/SecondBrain/.opencode/`. The two projects cannot both serve the same session safely — old project becomes read-only / archived.
- **OpenSpec:** `openspec/specs/` gains 6 new spec files. `openspec/changes/` is the only place that references the migration while it is in progress.
- **Knowledge bundle:** 9 project directories move from `~/SecondBrain/memory/projects/` to `memory/projects/` in the new project. Frontmatter is updated to OKF v0.1 conformance during the one-shot migration.
- **Users:** The user (single-user, per project decision) is the only consumer. UX is unchanged for explicit `/brain ...` and `@brain ...` invocations; what changes is that the bundle is no longer present in the system prompt unless the user explicitly requests it.
- **Dependencies:** No new external dependencies. Python 3.11+, `uv` for package management, `sqlite3` (stdlib), and the existing OpenCode v1.17.10+ runtime are sufficient. Obsidian is optional for browsing — the bundle is plain Markdown and works in any editor.
