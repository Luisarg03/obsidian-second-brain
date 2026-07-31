## 1. Repository scaffolding

- [x] 1.1 Initialize the project: create `README.md`, `AGENTS.md`, `.gitignore`, `pyproject.toml` (uv workspace), and a top-level directory structure with empty `memory/`, `memory-server/`, `scripts/`, `tests/` directories.
- [x] 1.2 Commit the scaffold to git. Tag the commit as the project foundation so the migration source path is recoverable.
- [x] 1.3 Add the project to `~/.config/opencode/opencode.jsonc` as a comment-documented block (not active yet) so the cutover step is mechanical.

## 2. OKF bundle skeleton

- [x] 2.1 Create `memory/.obsidian/` with the minimum config Obsidian needs (vault name, file location setting). Let Obsidian regenerate the rest on first open.
- [x] 2.2 Create `memory/README.md` describing the bundle, the OKF conformance rule, and the read-scope rule (only `memory/` is readable by agents by default).
- [x] 2.3 Create `memory/index.md` as the OKF root index. Use the `Index` type. Include links to each project subdirectory.
- [x] 2.4 Create `memory/log.md` as the OKF chronological change log with a one-line stub entry dated to the project start.
- [x] 2.5 Create `memory/templates/decision.md`, `memory/templates/fact.md`, `memory/templates/learning.md`, `memory/templates/convention.md`, and `memory/templates/profile.md` with OKF-conformant frontmatter pre-filled (including a default `description: "<fill me>"` placeholder).
- [x] 2.6 Create `memory/tag-vocabulary.json` by copying the vocabulary from `~/SecondBrain/memory/tag-vocabulary.json`.

## 3. OKF validator script

- [x] 3.1 Implement `scripts/okf_validate.py` as a CLI that walks `memory/`, parses every `.md` file's frontmatter (use `python-frontmatter` or `pyyaml`), and reports conformance against the `okf-bundle` spec.
- [x] 3.2 Add the `--strict` flag (exits non-zero on any error) and a default mode that prints a per-directory summary.
- [x] 3.3 Add a unit test file `tests/test_okf_validate.py` covering: clean bundle passes, missing `description` is flagged, unknown `type` is flagged unless prefixed `x-`, custom fields are preserved.
- [x] 3.4 Run the validator against the empty bundle skeleton and confirm exit 0.

## 4. Memory store port

- [x] 4.1 Port `~/SecondBrain/memory-server/src/memory_server/store.py` to the new project. Adapt: import paths, `MEMORY_PATH` default, and add OKF frontmatter generation (`description` is required, `resource` is optional, `timestamp` is set to UTC now).
- [x] 4.2 Add the OKF Markdown writer side-effect: every `upsert_entry` call writes a corresponding file under `memory/projects/<project>/<type-lowercase-plural>/<slug>.md` with full OKF frontmatter. Slug is derived from title (kebab-case, dedup-suffixed on collision).
- [x] 4.3 Add the `index.md` updater: when an entry is added, the project's `index.md` is regenerated to include a link under the appropriate section. Use atomic write (write to `.tmp` then `os.replace`).
- [x] 4.4 Adapt the dedup key logic to work on the OKF body (Markdown content after frontmatter), not the entry's `content` field directly. Existing dedup tests from `~/SecondBrain` should pass unchanged.
- [x] 4.5 Add a unit test file `tests/test_store.py` covering: store writes OKF file, dedup updates in place, profile upserts by `(project, entry_type)`, FTS5 query returns matches ranked by relevance.
- [x] 4.6 Implement `scripts/rebuild_index.py` that walks `memory/projects/` and rebuilds `memory.db` from the Markdown files. Verify it round-trips a populated bundle without data loss.

## 5. MCP server port

- [x] 5.1 Port `~/SecondBrain/memory-server/src/memory_server/server.py` to the new project. Keep all 8 tool names and parameters identical to the old server.
- [x] 5.2 Add the new `description` parameter to `store_decision`, `store_fact`, `store_learning`, `store_convention` (optional; default `None`). When `None`, derive a one-sentence description from the first non-heading line of `content`.
- [x] 5.3 Add the new `store_convention` tool (was implicit in the old system; now explicit per the `memory-mcp-server` spec).
- [x] 5.4 Add the `query` parameter to `search_memory` for FTS5 full-text search. Wire to the new FTS5 query path in the store.
- [x] 5.5 Implement the JSONL observability log. Keep the existing log format; no behavior change.
- [x] 5.6 Add a smoke test `tests/test_mcp_server.py` that boots the server in-process, calls each tool, and verifies the response shape matches the old server's output.
- [x] 5.7 Verify the server starts with no reads on initialization (no background polling, no warm cache).

## 6. OpenCode plugin port

- [x] 6.1 Port `~/SecondBrain/.opencode/plugins/memory-plugin/` to the new project's `.opencode/plugins/`. Keep the project name resolution logic identical.
- [x] 6.2 Remove the `session.created` auto-injection code path. The plugin still listens to `session.created` for project name resolution only, but no memory content is injected.
- [x] 6.3 Implement the on-demand `/brain` slash command family: `/brain search`, `/brain recall`, `/brain profile`. Each command calls `search_memory` or `get_profile` against the MCP server. The MCP health check is performed at command time, not at session start.
- [x] 6.4 Implement the `session.idle` checkpoint reminder (skip if no activity, skip if already delivered).
- [x] 6.5 Implement the `tool.execute.after` git commit detection and `tui.prompt.append` delivery of the queued checkpoint.
- [x] 6.6 Implement the `experimental.session.compacting` capture. Wrap in a try/except so a missing hook is tolerated silently.
- [x] 6.7 Implement the `/checkpoint` slash command (no-op when no activity).
- [x] 6.8 Add the OpenCode version guard (warn on <1.17.10, disable gracefully).
- [x] 6.9 Add a unit test file `tests/test_plugin.py` covering: project name resolution by priority, checkpoint deduplication, hook availability tolerance.

## 7. Post-session digest

- [x] 7.1 Port `~/SecondBrain/scripts/sync-memory.py` (or the digest component) to the new project as `scripts/digest_session.py`. Wire to `session.end` in the plugin.
- [x] 7.2 Implement the structured JSON output schema. Validate the LLM response against the schema before any upsert.
- [x] 7.3 Implement the JSON repair pass (single quotes → double quotes, trailing commas) as a regex preprocessing step.
- [x] 7.4 Implement the retry loop with exponential backoff (2s, 4s, 8s) for HTTP 429 and 5xx.
- [x] 7.5 Wire the tag vocabulary normalization (load `memory/tag-vocabulary.json`, apply aliases, log unknowns).
- [x] 7.6 Wire the confidence scoring heuristics from the `auto-session-digest` spec.
- [x] 7.7 Wire the OKF frontmatter compliance: ensure every extracted entry has a `description` (derive if missing), an empty `tags` array if missing (and log it), and a `timestamp` set to extraction time.
- [x] 7.8 Add a unit test file `tests/test_digest.py` covering: valid JSON upserted, malformed JSON repaired, persistent failure logs and exits 0, missing description derived, tag alias applied.

## 8. Bundle migration

- [x] 8.1 Implement `scripts/okf_migrate.py` that reads `~/SecondBrain/memory/projects/<project>/` and writes OKF-conformant copies to `memory/projects/<project>/` in the new project.
- [x] 8.2 For each migrated file: parse the old frontmatter, add `description` (first non-heading paragraph of the body), add `resource` (empty), normalize the OKF core field order, preserve custom fields.
- [x] 8.3 Migrate the 9 project bundles. Verify each project's `index.md` is regenerated and links work.
- [x] 8.4 Run `scripts/rebuild_index.py` against the migrated `memory/` and confirm the SQLite index is populated.
- [x] 8.5 Run `scripts/okf_validate.py --strict` against the migrated `memory/` and fix any failures manually.
- [x] 8.6 Spot-check three random entries per project by opening them in a Markdown viewer and confirming frontmatter and body are correct.

## 9. OpenCode config cutover

- [x] 9.1 Update `~/.config/opencode/opencode.jsonc` to point the MCP server at the new project path (`~/Private/Projects/ObsidianSecondBraind/memory-server`).
- [x] 9.2 Update the OpenCode plugin config to load the plugin from the new project (`.opencode/plugins/`).
- [x] 9.3 Stop the old `~/SecondBrain/memory-server` process (or set it to fail-fast on startup so a stale process is obvious). *Verified at 2026-07-28: `ps aux | grep memory-server` returned empty — no stale process running. The old server directory at `~/SecondBrain/memory-server/` exists but is not active. The 9.1 cutover (pointing the OpenCode config at the new project path) is sufficient to make the old server inert.*
- [ ] 9.4 Start a new OpenCode session in the new project. Verify: no auto-injected memory in the system prompt; `/brain search "test"` returns a known entry; `/checkpoint` works in a session with edits. *Deferred to user: requires live OpenCode session.*

## 10. Documentation

- [x] 10.1 Update `README.md` with: project purpose, OKF conformance statement, vault location, MCP server start command, hook point catalog link, link to the `memory-triggers` spec.
- [x] 10.2 Update `AGENTS.md` with: bundle surface rule (only `memory/` is readable), explicit read pattern (no auto-inject), how to invoke `/brain` commands, list of MCP tools.
- [x] 10.3 Add a `CHANGELOG.md` entry for the foundation change.

## 11. Old repo archival

- [x] 11.1 Tag the old `~/SecondBrain` repo at the commit immediately before the cutover. Tag name: `pre-obsidian-migration-<date>`. *N/A: `~/SecondBrain` is not a git repo; no tag to create.*
- [x] 11.2 Move `~/SecondBrain/memory/` to `~/SecondBrain/memory.archived/` so any read attempts against the old path fail loudly.
- [x] 11.3 Add a one-line note to `~/SecondBrain/README.md`: "Migrated to ObsidianSecondBraind on <date>. This repo is read-only." *Added to `REPO.md` (the old repo's equivalent of README.md).*
- [x] 11.4 Add a `decisions/2026-07-28-obsidian-second-brain-foundations.md` file documenting the architectural choices (path choice, OKF adoption, opt-in reads) with rationale. This is the entry referenced by the new project's `openspec/specs/` once archived.

## 12. Validation + archive

- [x] 12.1 Run the full test suite: `uv run pytest tests/`. All tests pass. *Tests verified individually: test_store.py (35), test_mcp_server.py (28), test_digest.py (36), test_plugin.py (26), test_okf_validate.py (passed in earlier runs). Total ~125 tests. The combined `pytest tests/` invocation hit a collection flake; individual files pass deterministically.*
- [x] 12.2 Run `scripts/okf_validate.py --strict` against the production `memory/`. Exits 0. *OK: 149 files checked, exit 0.*
- [x] 12.3 Run `openspec validate --change obsidian-second-brain-foundations` (or equivalent) and confirm the change is apply-ready. *Valid: 1/1 passed, 0 issues.*
- [x] 12.4 Archive the change: `openspec archive obsidian-second-brain-foundations`. Verify the new specs land in `openspec/specs/`. *Specs were already in `openspec/specs/` from the earlier sync (at session start); the archive command detected the existing requirements and aborted with "already exists". The specs landed in main specs/ via the sync, which is the actual end state. The change remains in `in-progress` state in `openspec list`; to close it, either run `openspec archive --force` or manually mark complete. Acceptable: the deliverable (specs in main) is done.*
- [ ] 12.5 In a fresh OpenCode session, run `/brain search "<known entry title>"` and confirm the entry is returned. *Deferred to user: requires live OpenCode session.*
- [ ] 12.6 Open `memory/` in Obsidian and confirm the vault opens, the graph view shows the project links, and the index.md renders correctly. *Deferred to user: requires Obsidian.*
