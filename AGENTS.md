# Agent Conventions

## Read scope

The only directory in this project that agents may read by default is `memory/`. The bundle is the contract. Everything else (`memory-server/`, `scripts/`, `openspec/`, `.opencode/`, `pyproject.toml`, source code) is implementation that the user must explicitly direct the agent to read.

## Read pattern (opt-in)

There is no auto-injection of memory into session context. To pull memory into context, the user must:

- Use a slash command: `/brain search "..."`, `/brain recall`, `/brain profile`.
- Use a prompt mention: `@brain ...` or `recuerdo que ...`.

If the user issues a prompt that does not reference the bundle, the agent MUST NOT call any memory read tool.

## Write pattern (mostly auto)

Writes are automatic where the trigger is set up:

- Post-session (`session.end`): the digest pipeline runs and extracts OKF entries from the session transcript.
- Compaction (`experimental.session.compacting`): a checkpoint is offered before context is compressed.
- Idle (`session.idle`): a checkpoint reminder is offered when there is tracked activity.
- Commit (`tool.execute.after` matching `git commit*`): a checkpoint is queued for the next user message.
- Manual (`/checkpoint`): a structured end-of-session review is offered.

The full hook point catalog is in `openspec/specs/memory-triggers/spec.md`.

## MCP tools

| Tool | Purpose |
|---|---|
| `search_memory` | Query entries by project, type, tags, or full-text |
| `store_decision` | Persist a Decision entry |
| `store_fact` | Persist a Fact entry (dedup by content) |
| `store_learning` | Persist a Learning entry |
| `store_convention` | Persist a Convention entry |
| `store_profile` | Persist or update a Profile entry (dedup by project) |
| `export_memories` | Dump all entries for a project |
| `get_profile` | Retrieve the project profile |
| `ping` | Health check |

All tool calls are explicit. The server does not poll or pre-fetch.
