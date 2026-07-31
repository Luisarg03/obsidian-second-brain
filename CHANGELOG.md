# Changelog

## [0.2.0] - 2026-07-31

### Features
- add CI workflow and release management scripts (2dc96b2)

### Bug Fixes
- un-ignore plugin package manifests for CI (7a415f3)
- install dev dependencies in CI workflow (655fc2b)

### Tests
- verify CI pipeline (v2 - dev deps fix) (#2) (4a62637)


## [0.1.0] - 2026-07-28 — Foundation change (`obsidian-second-brain-foundations`)

Initial scaffold of the new project. Establishes the OKF v0.1 knowledge bundle, the
opt-in read / mostly-auto write contract, and the lifecycle hook catalog.

### Added

- Project skeleton: `memory/` Obsidian vault, `memory-server/` Python MCP server,
  `.opencode/plugins/memory/` TypeScript plugin, `scripts/` CLI tooling, `tests/`
  pytest suite, `openspec/` capability specs and change tracking, `decisions/`
  architectural decision records.
- **memory-store** capability (`memory_server/store.py`): SQLite WAL + FTS5
  search index, OKF-conformant Markdown writer, full-content dedup, profile
  upsert by `(project, entry_type)`, atomic `index.md` regeneration.
- **memory-mcp-server** capability (`memory_server/server.py`): 8 tools
  (`search_memory`, `store_decision`, `store_fact`, `store_learning`,
  `store_convention`, `store_profile`, `export_memories`, `get_profile`, `ping`).
  All reads are explicit; JSONL observability log.
- **auto-session-digest** capability (`scripts/digest_session.py`): structured
  LLM extraction, JSON repair, exponential-backoff retry with full jitter, tag
  vocabulary normalization, confidence scoring, OKF frontmatter compliance.
- **opencode-plugin** capability (`.opencode/plugins/memory/index.ts`):
  OpenCode Plugin API v2 hooks for `session.idle`, `tool.execute.after`,
  `tui.prompt.append`, `experimental.session.compacting`, `session.end`. Slash
  commands `/brain search|recall|profile` and `/checkpoint`. Version guard for
  OpenCode < 1.17.10. **No `session.created` memory auto-injection.**
- **okf-bundle** capability (`openspec/specs/okf-bundle/spec.md`): OKF v0.1
  schema, directory layout, reserved filenames, validator
  (`scripts/okf_validate.py`), read-scope rule.
- **memory-triggers** capability (`openspec/specs/memory-triggers/spec.md`):
  declarative catalog of all lifecycle hook points (implemented triggers +
  documented-but-not-implemented external triggers).
- **Migration tooling** (`scripts/okf_migrate.py`): one-shot migration from the
  legacy `~/SecondBrain/memory/projects/` bundle to OKF v0.1.
- **Migrated 12 project bundles** from `~/SecondBrain/memory/projects/`:
  ArchCustom, FilesAnalizer, LLMBenchamarks, LinkedinSearchJobs, MyCv,
  OmniRoute, SecondBrain, Travel, free-model-benchmark-tracker, general,
  improve-models-registry-with-fallbacks, san-ibk-magic-any-catvars-script.
  142 entries migrated, all with derived `description` and normalized OKF
  frontmatter.

### Changed

- The repository is now the project (code + tooling + OpenSpec). The knowledge
  bundle lives inside the repo as an Obsidian vault under `memory/`.

### Inverted contract

- **Reads** are opt-in: no `session.created` auto-injection. The agent pulls
  memory only on explicit user prompt or command.
- **Writes** are mostly automatic: post-session extraction, compaction
  capture, idle checkpoint, commit-anchored capture.
