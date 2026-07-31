# Memory MCP Server

## Purpose

Python MCP server that exposes the memory store to LLM agents via the Model Context Protocol. Provides search, store, and health-check tools. All reads are explicit (no background polling or pre-fetching), and the server validates its storage backend at startup.

## Requirements

### Requirement: search_memory tool
The MCP server SHALL expose a `search_memory` tool that accepts `project` (required), `entry_type` (optional), `tags` (optional array), and `query` (optional, full-text search). It SHALL return a list of matching memory entries from the store.

#### Scenario: Basic project search
- **WHEN** `search_memory` is called with only a project name
- **THEN** all memory entries for that project are returned as a structured list

#### Scenario: Filtered search by type
- **WHEN** `search_memory` is called with project and `entry_type` = "Decision"
- **THEN** only decision entries for that project are returned

#### Scenario: Search with tags filter
- **WHEN** `search_memory` is called with project and `tags` = ["architecture", "backend"]
- **THEN** only entries matching both project and tags are returned

#### Scenario: Full-text query
- **WHEN** `search_memory` is called with `query` = "sqlite fts5"
- **THEN** entries whose title, description, or content matches the query are returned, ranked by FTS5 relevance

### Requirement: store_decision tool
The MCP server SHALL expose a `store_decision` tool that accepts `project`, `content`, `description` (optional), `tags` (optional), and `openspec_change_id` (optional). It SHALL persist a decision entry in the memory store and write the corresponding OKF Markdown file.

#### Scenario: Store architectural decision
- **WHEN** `store_decision` is called with project, content, and description describing a technical choice
- **THEN** an entry with `entry_type` = `Decision` is persisted, a Markdown file is written under `memory/projects/<project>/decisions/`, and a success confirmation is returned

#### Scenario: Store decision with OpenSpec reference
- **WHEN** `store_decision` is called with a valid `openspec_change_id`
- **THEN** the stored entry includes the change ID reference in the entry's custom frontmatter

### Requirement: store_fact tool
The MCP server SHALL expose a `store_fact` tool that accepts `project`, `content`, `description` (optional), `tags` (optional), and `confidence` (optional, 0.0–1.0). It SHALL persist a fact entry with deduplication support.

#### Scenario: Store new fact
- **WHEN** `store_fact` is called with project and content
- **THEN** a fact entry is persisted with `entry_type` = `Fact`

#### Scenario: Update existing fact
- **WHEN** `store_fact` is called with content that matches an existing fact's dedup key
- **THEN** the existing entry is updated rather than duplicated

### Requirement: store_learning tool
The MCP server SHALL expose a `store_learning` tool that accepts `project`, `content`, and `description` (optional). It SHALL persist a learning entry (lessons learned, errors found, solutions applied).

#### Scenario: Store lesson learned
- **WHEN** `store_learning` is called after resolving a non-obvious problem
- **THEN** a learning entry is persisted with `entry_type` = `Learning`

### Requirement: store_convention tool
The MCP server SHALL expose a `store_convention` tool that accepts `project`, `content`, and `description` (optional). It SHALL persist a convention entry (team or project-wide conventions, style rules, naming patterns).

#### Scenario: Store project convention
- **WHEN** `store_convention` is called with project and content describing a naming rule
- **THEN** a convention entry is persisted with `entry_type` = `Convention`

### Requirement: store_profile tool
The MCP server SHALL expose a `store_profile` tool that accepts `project`, `content`, and optional `tags`. It SHALL persist a profile entry (deduplicated by project).

#### Scenario: Agent stores a profile entry
- **WHEN** an agent calls `store_profile` with project and content describing user behavior patterns
- **THEN** the profile is upserted via the store and a success confirmation is returned

### Requirement: export_memories tool
The MCP server SHALL expose an `export_memories` tool that accepts `project` (required) and `entry_type` (optional). It SHALL return all memory entries for the specified project, optionally filtered by entry type.

#### Scenario: Export all memories for a project
- **WHEN** `export_memories` is called with only a project name
- **THEN** all memory entries for that project are returned as a structured list

#### Scenario: Export memories filtered by type
- **WHEN** `export_memories` is called with project and `entry_type` = "Decision"
- **THEN** only decision entries for that project are returned

### Requirement: get_profile tool
The MCP server SHALL expose a `get_profile` tool that accepts `project` (required). It SHALL return the global tech profile for the specified project.

#### Scenario: Retrieve global tech profile for a project
- **WHEN** `get_profile` is called with a project name
- **THEN** the global tech profile for that project is returned as a structured list

### Requirement: ping health-check tool
The MCP server SHALL expose a zero-argument MCP tool named `ping` that returns a JSON object with `status` and `timestamp` fields.

#### Scenario: Server is running and healthy
- **WHEN** a client calls the `ping` tool
- **THEN** the server responds with `{"status": "ok", "timestamp": "<ISO8601>"}` within 1 second

### Requirement: Tool calls are logged for observability
The MCP server SHALL log every tool call to a JSONL file for observability and adoption tracking. Each log entry SHALL include timestamp, tool name, project, and `entry_type`. Logging SHALL NOT affect tool behavior or performance.

#### Scenario: Tool call is logged on every invocation
- **WHEN** any memory tool is called
- **THEN** a JSON line is appended to the tool call log with the call details

#### Scenario: Logging does not interfere with tool response
- **WHEN** a tool call is made and logging fails (e.g., disk full)
- **THEN** the tool SHALL still return its normal response; the log error is silently suppressed

### Requirement: MCP server startup validation
The MCP server SHALL validate that the memory store's SQLite database is accessible at startup and SHALL fail with a clear error message if it is not.

#### Scenario: Missing storage directory
- **WHEN** the MCP server starts and the configured memory storage path does not exist
- **THEN** the server logs a clear error message and exits with a non-zero status code

### Requirement: MCP server uses opt-in read pattern
The MCP server SHALL NOT perform any background polling, prefetching, or proactive reads of memory content. Every read tool invocation SHALL be triggered by an explicit MCP client call from an agent or user-driven prompt. There is no warm cache.

#### Scenario: Server does not read memory on startup
- **WHEN** the MCP server starts
- **THEN** it does not load any entries into memory and does not emit any read tool results until a tool is called

#### Scenario: Server does not poll the store
- **WHEN** the MCP server is running and no tool calls arrive for an extended period
- **THEN** the server does not issue any SQL queries against the memory store

### Requirement: MCP spawn command is directory-pinned and interpreter-resolved
The OpenCode MCP registration for the memory server SHALL use a spawn command that (a) sets the working directory to the repository root via an absolute path and (b) resolves the Python interpreter through the project's environment manager (`uv run`), so the server starts successfully regardless of the OpenCode working directory.

#### Scenario: Server starts from a foreign working directory
- **WHEN** OpenCode is started in a directory other than the memory repository
- **THEN** the memory MCP server spawns successfully and responds to `ping`

#### Scenario: No reliance on a bare `python` on PATH
- **WHEN** the system PATH has no `python` executable (only `python3` or none)
- **THEN** the spawn command still starts the server because the interpreter is resolved by `uv`
