## Context

The user has been operating `~/SecondBrain` as a personal agent-memory system for several months. The system has matured through 10 archived OpenSpec changes and now provides:

- A SQLite database with WAL mode and FTS5 full-text search as a derived index.
- A Python MCP server exposing 7 tools (`store_decision`, `store_fact`, `store_learning`, `store_profile`, `search_memory`, `export_memories`, `get_profile`, `ping`).
- An OpenCode Plugin API v2 plugin that auto-injects ≤2K chars of project memory into the system prompt on `session.created` and offers checkpoint reminders on `session.idle`, `session.compacting`, git commit, and `/checkpoint`.
- A post-session LLM extraction pipeline (`auto-session-digest`) that mines the conversation transcript for decisions, facts, and learnings.
- 8 active capability specs and a per-project knowledge bundle under `memory/projects/<project>/` with OKF-style frontmatter.

Despite the maturity, the system has three structural issues that motivate this change:

1. **Path is hard-coded.** Everything lives at `~/SecondBrain`. The user wants the freedom to relocate the project (this new repo lives at `~/Private/Projects/ObsidianSecondBraind`).
2. **Knowledge bundle is not OKF v0.1 conformant.** Frontmatter has `type`, `title`, `tags`, `timestamp` but lacks `description` and `resource`. There is no validator enforcing the schema. The user wants formal OKF adoption so the bundle is portable to other consumers (not just opencode).
3. **Reads are too eager.** The OpenCode plugin injects memory into every session context unconditionally. The user wants the opposite: reads are opt-in via explicit prompt or command; writes are mostly automatic. The motivation is token economy, not laziness — context is precious.

Stakeholders: the user (single-user project, no collaborators, no shared knowledge). The "stakeholder" framing is really: future-you, plus whatever LLM is currently running the session.

## Goals / Non-Goals

**Goals:**

- Establish a project layout where the knowledge bundle is an Obsidian vault (`memory/`) inside a normal repo, so the user can browse, edit, and graph the brain without leaving Obsidian.
- Achieve OKF v0.1 conformance for every document in the bundle, with an executable validator (`scripts/okf_validate.py`) the user can run in CI or pre-commit.
- Port the four working capabilities from `~/SecondBrain` (storage, MCP server, OpenCode plugin, post-session digest) into the new project, adapted for the new constraints.
- Invert the read/write contract: `session.created` does not auto-inject. Explicit user prompt or command is the only path that pulls memory into context.
- Document the lifecycle hook points (no implementation of all of them now) so the user can pick follow-up changes for each trigger.
- Migrate the 9 existing project bundles with OKF frontmatter added.
- Keep the existing MCP tool surface identical so any external consumer that knows `search_memory` keeps working without code changes.

**Non-Goals:**

- Building a full Obsidian plugin. We use Obsidian only as a vault viewer. The MCP server stays a standalone Python process.
- Multi-user / shared bundles. The user is the only consumer.
- Real-time indexing (e.g., on every keystroke). Post-session extraction is the granularity we target.
- Replacing the SQLite store with a different engine. SQLite + FTS5 is sufficient for the expected volume (single user, hundreds of entries per project, lifetime volume in the low thousands).
- Publishing the bundle publicly. Single-user means no need for OKF trust signals (v0.2 territory).
- Implementing every documented trigger in this change. The `memory-triggers` capability declares the surface; follow-up changes fill it in.

## Decisions

### Decision 1: `memory/` is the vault, the repo is the project

The repo root is the project (code, tooling, OpenSpec). `memory/` is the Obsidian vault (the knowledge bundle). The rest of the repo (MCP server, scripts, openspec/, .opencode/) is not opened by Obsidian and is invisible to LLM agents unless they are explicitly pointed at it.

**Why:** Obsidian expects a directory of Markdown. Making `memory/` the vault means the user can open the project in Obsidian and immediately browse, search, and graph the brain without any export step. The cost is that `.obsidian/` config lives inside the bundle, which Obsidian requires.

**Alternatives considered:**

- *Vault at `~/Documents/ObsidianSecondBraind/`, project at `~/Private/Projects/ObsidianSecondBraind/`.* Cleaner separation but introduces a sync problem between two locations. Rejected because the bundle is small enough that "single location" wins.
- *Repo root = vault.* Mixes code and notes, which makes the vault noisy and prevents `.obsidian/` from being a clean subdirectory. Rejected.

### Decision 2: OKF v0.1 is the frontmatter contract

Every document in the bundle carries these frontmatter fields, in this order:

```yaml
---
type: <Decision | Fact | Learning | Convention | Profile | Index>
title: <short sentence>
description: <one or two sentences, queryable summary>
resource: <optional, link to source or external context>
tags: [<lowercase-kebab>, ...]
timestamp: <ISO-8601 UTC>
---
```

Custom fields (`project`, `confidence`, `openspec_change_id`) are allowed and preserved on top of the OKF core.

**Why:** OKF v0.1 only requires `type` to be present. We require all six because the user wants the bundle to be portable. A consumer that knows OKF should be able to read our bundle without learning our dialect.

**Alternatives considered:**

- *Custom dialect, ignore OKF.* Rejected because OKF is becoming a de-facto standard (Google's blog post, Karpathy's LLM wiki gist, Obsidian community) and the user explicitly cited the OKF article as motivation.
- *OKF v0.1 with our additions prefixed (e.g., `xb_project`).* Possible but unnecessary. OKF v0.1's "minimally opinionated" stance means producers can extend fields; consumers that don't recognize them ignore them.

### Decision 3: Read path is opt-in, write path is mostly auto

- **Reads:** No `session.created` injection. The user must use a command (`/brain search "..."`, `/brain recall`, `/checkpoint`) or an explicit prompt mention (`@brain ...`, `recuerdo que ...`) to pull memory into context. The MCP server's read tools (`search_memory`, `get_profile`, `export_memories`) remain available and are called explicitly.
- **Writes:** Mostly automatic. Post-session extraction (`session.end` → `auto-session-digest`) runs without prompting. Compaction checkpoint (`session.compacting`) fires without prompting. Idle checkpoint (`session.idle`) fires only when there is tracked activity. Git commit detection (`tool.execute.after` matching `git commit*`) queues a checkpoint that is delivered on the next user message.

**Why:** Token economy. The user explicitly does not want the bundle sitting in every session context. The asymmetry (writes auto, reads manual) is intentional: writing is cheap (machine does it), reading is expensive (it costs context).

**Alternatives considered:**

- *Fully manual reads and writes.* Loses the automatic capture that the user values.
- *Reads and writes both auto.* Contradicts the user's stated goal.
- *Reads auto only at session start with a strict token budget.* This is the current `~/SecondBrain` behavior, and the user is moving away from it.

### Decision 4: The MCP tool surface stays identical to `~/SecondBrain`

Same 8 tool names. Same parameters. Same return shapes. The only difference is that the server is now registered to the new project path in `~/.config/opencode/opencode.jsonc`.

**Why:** The user has muscle memory and possibly external scripts that call these tools. Changing the surface would break them. The new constraints (OKF, opt-in reads) are about *behavior*, not API.

**Alternatives considered:**

- *Rename `store_decision` to `okf_store_decision` to signal the format upgrade.* Rejected; it does not add value and breaks the muscle memory.
- *Drop the `ping` tool.* Rejected; the OpenCode plugin still uses it for the health check (now only when the user requests memory).

### Decision 5: SQLite remains the derived search index

`memory.db` is a derived view of the Markdown files. The Markdown files are the source of truth. On every write, the SQLite row is updated; on read, the SQLite row is returned. A `scripts/rebuild_index.py` can rebuild the database from Markdown if the DB is lost.

**Why:** This was already the architecture in `~/SecondBrain` and the user values it. Markdown is human-readable and diffable in git; SQLite is fast and supports FTS5.

**Alternatives considered:**

- *SQLite as source of truth, Markdown as export.* Rejected; ties the user to the SQLite schema and prevents editing the brain in Obsidian.
- *Pure Markdown, no index, search via Obsidian or ripgrep.* Rejected; the MCP server needs structured queries (by project, by type, by tag) that are awkward over plain text.

### Decision 6: Hook points are documented, not implemented, in this change

`memory-triggers` spec lists every hook point that OpenCode Plugin API v2 and external triggers (git, cron) expose, and declares what each hook does when active. This change ships the spec and a stub plugin that listens on `session.end` and `/checkpoint`. The remaining triggers (`session.idle`, `session.compacting`, `tool.execute.after`, `tui.prompt.append`, git post-commit) are declared in the spec but not wired up; they are addressed in follow-up changes.

**Why:** The user said "a medida que se avance, ver los puntos donde podriamos instalar el hook / trigger de actualizacion de memoria" — the points are identified as the project progresses, not all at once. Implementing every trigger in the foundation change would inflate scope and risk.

**Alternatives considered:**

- *Implement every hook now.* Rejected for scope and risk reasons.
- *Document no hooks, implement on demand.* Rejected; the user explicitly wants the points visible so future changes can be planned.

## Risks / Trade-offs

**[R1] Two parallel systems during migration.** During the migration window, `~/SecondBrain` and the new project both exist. The OpenCode plugin config points at one or the other. If the user forgets to switch, writes go to the wrong bundle. → **Mitigation:** the migration script writes a `.migration-state.json` file the plugin reads to refuse writes to the old path; the old `~/SecondBrain/memory-server` is shut down at the end of the migration change. Document the cutover date in the project's `README.md`.

**[R2] OKF frontmatter adds two required fields (`description`, `resource`) the user has to fill in.** On existing entries, this is a one-shot migration burden. On new entries, the user must remember to write a description. → **Mitigation:** the `templates/` directory ships Obsidian templates with the OKF fields pre-filled, including a default `description: "<fill me>"` placeholder. The `okf_validate.py` script flags missing `description` but does not hard-fail (warning, not error).

**[R3] Obsidian version drift.** Obsidian's `.obsidian/` config schema is internal to Obsidian and may change between versions. → **Mitigation:** commit only the minimum `.obsidian/` config needed (vault name, file location setting). Let Obsidian regenerate the rest on first open. No Obsidian plugin config is committed in this change.

**[R4] SQLite index drift from Markdown.** If the user edits a Markdown file directly in Obsidian, the SQLite row is not updated. Subsequent reads via `search_memory` may return stale content. → **Mitigation:** add a `scripts/rebuild_index.py` that walks `memory/` and rebuilds the DB. Document the workflow: edits in Obsidian → run `rebuild_index.py` → reads via MCP are fresh. A follow-up change could add a file-watcher hook (Obsidian doesn't expose one, but a sidecar process can watch `memory/`).

**[R5] `~/SecondBrain` and the new project diverging.** Once the new project ships, the user may still occasionally add entries to the old one. → **Mitigation:** archive the old `~/SecondBrain` repo's memory bundle (move it to `archive/` or a separate git tag) at the end of this change. The old `memory-server` is shut down. New entries go only to the new project.

**[R6] OpenCode Plugin API v2 hooks may not be stable across versions.** The spec already calls out the minimum version (1.17.10). Hook names like `experimental.session.compacting` are explicitly experimental. → **Mitigation:** the `memory-triggers` spec explicitly marks experimental hooks as such and includes a fallback: if the hook does not exist, the trigger is silently skipped. The plugin version guard (already in the existing spec) prevents crashes on older OpenCode versions.

## Migration Plan

The migration is a one-shot event at the end of the implementation tasks. Steps:

1. **Pre-flight:** verify `~/SecondBrain` is the current source of truth. Run `openspec validate` on the new project's specs.
2. **Port code:** copy `memory-server/src/memory_server/` from `~/SecondBrain` to the new project's `memory-server/`. Adapt imports, paths, and config (env var `MEMORY_PATH` defaults to `<new-project>/memory`).
3. **Port specs:** copy the four relevant specs from `~/SecondBrain/openspec/specs/` into the new project's `openspec/changes/obsidian-second-brain-foundations/specs/` as the new-capability specs.
4. **Bundle migration:** run `scripts/okf_migrate.py` which:
    - Reads each `~/SecondBrain/memory/projects/<project>/` directory.
    - For each `.md` file, parses frontmatter, adds missing `description` (using the first non-heading paragraph of the body) and `resource` (omitted, empty).
    - Writes the updated file to `<new-project>/memory/projects/<project>/`.
    - Re-orders frontmatter fields to OKF order.
5. **Index rebuild:** run `scripts/rebuild_index.py` against the new project's `memory/` directory to populate `memory.db` from the migrated Markdown.
6. **Validation:** run `scripts/okf_validate.py` against the new `memory/`. Fix any failures manually.
7. **OpenCode config cutover:** update `~/.config/opencode/opencode.jsonc` to point at the new project. Stop the old `~/SecondBrain/memory-server` process.
8. **Smoke test:** start a new OpenCode session in any directory under the new project. Run `/brain search "test"` and verify a known entry is returned.
9. **Archive the old:** tag the old `~/SecondBrain` repo at the migration commit. Move `~/SecondBrain/memory/` to `~/SecondBrain/memory.archived/`. Document the cutover in both `README.md` files.

**Rollback:** if step 8 fails, revert `~/.config/opencode/opencode.jsonc` to the old path and restart the old `memory-server`. The new project's `memory.db` is a fresh build; no rollback needed there.

## Open Questions

- **Q1: Project naming.** The new project directory is `ObsidianSecondBraind` (typo or intentional?). The bundle's root project is still `SecondBrain`. Should the new bundle rename the root project to match the directory, or keep `SecondBrain`? *(Resolved during the proposal review: keep `SecondBrain` as the root project in the bundle, since the 9 existing projects in the old bundle are all stored as `memory/projects/<project>/` and the root index is a separate concept.)*

- **Q2: Tag vocabulary.** The old `~/SecondBrain/memory/tag-vocabulary.json` is the source of truth. Does the new project ship a copy, or reference the old one? *(Lean: ship a copy at `memory/tag-vocabulary.json` so the bundle is self-contained. The validator script reads from this path.)*

- **Q3: Obsidian plugins.** Which community plugins does the user want enabled? Dataview, Templater, and Periodic Notes are candidates for an OKF-friendly vault. *(Open — the user said "no me importa por ahora" about how the model discovers the bundle, but Obsidian plugins are a different concern: they help the human browse. Decide before the smoke test.)*

- **Q4: Compaction trigger stability.** `experimental.session.compacting` is marked experimental by OpenCode. If it changes name or semantics in a future OpenCode release, the plugin will need an update. *(Acceptable risk; spec marks the trigger as best-effort with a silent fallback.)*
