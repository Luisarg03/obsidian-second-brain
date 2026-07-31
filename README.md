# Obsidian Second Brain

**AI-powered memory system for developers.**

Obsidian Second Brain captures, stores, and retrieves knowledge across coding
sessions. It works as a persistent second brain that remembers decisions,
facts, learnings, and conventions across projects — so you never re-derive what
you already figured out.

- **Opt-in reads.** Memory is pulled into context only when you ask (`/brain
  search`). No automatic context injection, no token waste.
- **Mostly-auto writes.** Post-session digests, checkpoint prompts, and
  commit-anchored captures run without prompting.
- **Human-friendly vault.** The knowledge store is an Obsidian-compatible
  Markdown vault (OKF format) — browse, search, and graph it like any notes
  database.

## How it works

```
                          OpenCode
   ┌───────────────────────────────────────────────┐
   │  .opencode/plugins/memory/                    │
   │  Plugin API v2: hooks, /brain, /checkpoint,   │
   │  digest pipeline                              │
   │                      │ MCP calls              │
   │                      ▼                        │
   │  memory_server/                               │
   │  Python MCP server (SQLite + FTS5 index)      │
   └──────────────────────┬────────────────────────┘
                          │ read / write
                          ▼
              ┌───────────────────────────┐
              │  memory/                  │
              │  OKF knowledge vault      │
              │  (Obsidian-compatible)    │
              └───────────▲───────────────┘
                          │
              ┌───────────┴───────────────┐
              │  scripts/                 │
              │  digest · validate ·      │
              │  rebuild · cleanup        │
              └───────────────────────────┘
```

Markdown is the source of truth; SQLite is a derived full-text search index
that can always be rebuilt from the bundle.

## Architecture

| Component | Role |
|---|---|
| `memory_server/` | Python MCP server. Stores and retrieves OKF entries via SQLite (WAL + FTS5). Exposes `search_memory`, `store_decision`, `store_fact`, `store_learning`, `store_convention`, `store_profile`, `export_memories`, `get_profile`, `ping`. |
| `.opencode/plugins/memory/` | OpenCode Plugin API v2 plugin. Wires lifecycle hooks (`session.end`, `session.idle`, compaction, commit detection), the `/brain` and `/checkpoint` slash commands, and the post-session digest pipeline. |
| `memory/` | The knowledge bundle: an Obsidian-compatible vault in OKF format, organized per project (`decisions/`, `facts/`, `learnings/`, `conventions/`, `profiles/`). |
| `scripts/` | CLI tooling: session digest, OKF validation, SQLite index rebuild, duplicate cleanup, legacy migration. |

## Requirements

- Python 3.14+
- [uv](https://docs.astral.sh/uv/)
- OpenCode 1.17.10+ (Plugin API v2)

## Setup

1. Install dependencies:

   ```bash
   uv sync
   ```

2. Register the MCP server in your OpenCode configuration (e.g.
   `opencode.json`), pointing at this repository:

   ```jsonc
   {
     "mcp": {
       "memory": {
         "command": [
           "uv", "run", "--directory", "/path/to/obsidian-second-brain",
           "python", "memory_server/server.py"
         ],
         "enabled": true
       }
     }
   }
   ```

   The server resolves the memory bundle path from the `MEMORY_PATH`
   environment variable, defaulting to `<repo>/memory`.

3. Load the plugin. The implementation lives in `.opencode/plugins/memory/`.
   Link or copy it into your OpenCode plugin directory (or reference it in
   your plugin config), keeping the repo copy as the single source of truth.

## Usage

- **`/brain search "<query>"`** — pull matching memories into the session
  context. Reads are always opt-in.
- **`/checkpoint`** — manually trigger an end-of-session review; the agent
  writes OKF entries for anything notable.
- **Session digest** — when a session ends, the digest pipeline automatically
  extracts decisions, facts, and learnings from the transcript into the bundle.
- **Obsidian** — open `memory/` as a vault in Obsidian to browse, search, and
  graph the brain interactively.

## Development

```bash
uv run pytest                # test suite
uv run okf-validate          # OKF conformance check
uv run okf-validate --strict # fail on any error
uv run rebuild-index         # rebuild SQLite index from Markdown
```

<!-- ci-test: 2026-07-31 -->
