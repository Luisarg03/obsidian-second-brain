# OpenCode Plugin

## Purpose

OpenCode Plugin API v2 plugin that orchestrates memory capture and retrieval for the project. Inverts the read/write contract relative to the prior `~/SecondBrain` plugin: **no auto-injection on session start** (reads are opt-in via `/brain` or `@brain`), and **writes are mostly auto** via lifecycle hooks (idle checkpoint, commit-anchored capture, compaction checkpoint, post-session extraction).

## Requirements

### Requirement: No auto-injection on session.created
The plugin SHALL NOT listen to the `session.created` OpenCode Plugin API v2 hook for the purpose of injecting project memory into the agent context. The plugin MAY still listen to `session.created` for non-injection purposes (e.g., project name resolution, MCP health check), but no memory content is injected at session start.

#### Scenario: Session starts with empty memory context
- **WHEN** a new OpenCode session starts
- **THEN** the agent's system prompt does not contain any content from `memory/`

#### Scenario: Plugin still resolves project name on session.created
- **WHEN** a new OpenCode session starts
- **THEN** the plugin resolves the project name from the working directory (per the project name resolution requirement) for use by other hooks

### Requirement: MCP server reachability check on demand
The plugin SHALL expose a `/brain` slash command and a `recuerdo que ...` prompt trigger that, when invoked, performs a 2-second timeout health check against the MCP server's `ping` tool. If the check fails, the plugin SHALL inject a visible warning into the agent's context. The check SHALL NOT be performed at session start.

#### Scenario: /brain invoked, server reachable
- **WHEN** the user types `/brain search "X"` and the MCP server responds to `ping` within 2 seconds
- **THEN** the plugin forwards the search call to the server and returns the result

#### Scenario: /brain invoked, server unreachable
- **WHEN** the user types `/brain search "X"` and the MCP server does not respond within 2 seconds
- **THEN** the plugin injects "> ⚠️ Memory server unreachable — search cannot be completed." into the context

### Requirement: Project name resolution
The plugin SHALL derive the project name from the working directory using the following priority:

1. OpenSpec context: if `openspec/` directory exists in the working directory, the plugin uses the working directory basename (OpenSpec presence makes directory identity authoritative).
2. `package.json` → `name` field.
3. `pyproject.toml` → `[project]` → `name` field.
4. `README.md` content inference: scan the first 5 lines for a heading pattern like `# <ProjectName>`.
5. Fallback: basename of the working directory.

#### Scenario: Resolve project from OpenSpec presence
- **WHEN** the working directory contains an `openspec/` directory
- **THEN** the plugin uses the basename of the working directory as the project name

#### Scenario: Resolve project from package.json
- **WHEN** the working directory contains a `package.json` with a `name` field and no `openspec/` directory
- **THEN** the plugin uses that value as the project name

#### Scenario: Fallback to directory basename
- **WHEN** no resolution method above yields a name
- **THEN** the plugin uses the basename of the working directory as the project name

### Requirement: Plugin version guard
The plugin SHALL check the OpenCode version at startup and SHALL log a warning if the running version is older than v1.17.10 (minimum version for Plugin API v2).

#### Scenario: Older OpenCode version detected
- **WHEN** the plugin initializes and detects OpenCode < v1.17.10
- **THEN** the plugin logs a warning and disables itself gracefully without crashing the session

### Requirement: Reminder injection at session.idle
The plugin SHALL listen to `session.idle` and run automatic memory capture when meaningful work was done in the session. When the hook fires with tracked activity (at least one file edit or bash command) and no checkpoint was delivered yet in the session, the plugin SHALL fetch the session transcript, write it to a temporary file, and spawn the post-session digest pipeline against it, and SHALL set the `checkpointDelivered` flag when the capture is spawned. The plugin SHALL NOT inject any prompt into the user's composer on `session.idle`. The plugin SHALL skip capture when no activity has been tracked. A checkpoint queued by a git commit SHALL be delivered on the next user message via `experimental.chat.messages.transform`, not via `session.idle`.

#### Scenario: Idle capture with activity
- **WHEN** `session.idle` fires during a session with at least one tracked file edit or bash command and `checkpointDelivered` is false
- **THEN** the plugin spawns the digest pipeline for the session transcript and sets `checkpointDelivered`

#### Scenario: No activity — silent
- **WHEN** `session.idle` fires during a session with no tracked file edits or bash commands
- **THEN** the plugin does not run capture and injects nothing

#### Scenario: No composer injection on idle
- **WHEN** `session.idle` fires with tracked activity
- **THEN** the plugin does not append any prompt text to the user's messages

#### Scenario: Idle capture skipped after delivered checkpoint
- **WHEN** `session.idle` fires and `checkpointDelivered` is true
- **THEN** the plugin is silent

#### Scenario: Commit checkpoint delivered on next message
- **WHEN** a git commit was detected, the user did not send a follow-up message, and `session.idle` subsequently fires
- **THEN** the plugin runs idle capture (if not already delivered) and the queued commit checkpoint remains queued for the next user message

### Requirement: Git commit checkpoint trigger
The plugin SHALL detect `git commit` commands via `tool.execute.after` and queue a structured checkpoint prompt for delivery on the next user message. The prompt SHALL be delivered via the `experimental.chat.messages.transform` hook (prepended to the next user message), not returned from `tool.execute.after` (which is `Promise<void>`).

#### Scenario: Checkpoint delivered on next user message after git commit
- **WHEN** a bash tool call matching `git commit*` completes and the user sends the next message
- **THEN** the plugin prepends the checkpoint prompt to that user message via `experimental.chat.messages.transform`

#### Scenario: No double-prompt on idle after delivered commit checkpoint
- **WHEN** `session.idle` fires in the same session where the commit checkpoint was already delivered via `experimental.chat.messages.transform`
- **THEN** the plugin does not run idle capture again

### Requirement: /checkpoint slash command
The plugin SHALL support a `/checkpoint` slash command that triggers a structured end-of-session review. When invoked, the plugin SHALL list all tracked session activity and prompt the agent to write OKF entries for all notable items before finishing.

#### Scenario: User invokes /checkpoint
- **WHEN** the user types `/checkpoint`
- **THEN** the plugin injects a prompt listing tracked session activity and instructs the agent to write OKF entries for each notable item

#### Scenario: /checkpoint with no activity
- **WHEN** the user types `/checkpoint` in a session with no tracked activity
- **THEN** the plugin responds: "No tracked activity in this session. Nothing to checkpoint."

### Requirement: Compaction checkpoint
The plugin SHALL listen to `experimental.session.compacting` and inject a structured checkpoint prompt whenever session activity exists. This trigger fires when the conversation context is about to be compressed, which is the highest-reliability moment for memory capture.

#### Scenario: Checkpoint injected before compaction
- **WHEN** `experimental.session.compacting` fires and the session has tracked activity
- **THEN** the plugin returns a checkpoint prompt listing the session activity

#### Scenario: Compaction checkpoint fires even if a previous checkpoint was delivered
- **WHEN** `experimental.session.compacting` fires and `checkpointDelivered` is true
- **THEN** the plugin still injects the checkpoint prompt

#### Scenario: No activity — silent on compaction
- **WHEN** `experimental.session.compacting` fires and no session activity has been tracked
- **THEN** the plugin does not inject any prompt

### Requirement: Automatic post-session memory extraction
After a session, the plugin SHALL automatically extract and persist memory entries (decisions, facts, learnings) from the session transcript without requiring any explicit agent or user action. Post-session extraction SHALL be triggered by the plugin's `dispose` hook (server instance disposal) covering every session tracked by that instance, and by `session.idle` per the idle-capture requirement. For each session, the plugin SHALL fetch the transcript, write it to a temporary file, and spawn the digest pipeline with output redirected to `memory/logs/digest-spawn.log`. The plugin SHALL skip sessions with no tracked activity or whose transcript is empty or shorter than 200 characters.

#### Scenario: Session ends with conversation content
- **WHEN** the server instance is disposed and a tracked session's transcript contains meaningful technical content
- **THEN** the system extracts OKF entries and upserts them into the memory store within 30 seconds of disposal

#### Scenario: Transcript unavailable at session end
- **WHEN** a session's transcript cannot be read at disposal
- **THEN** the system logs a warning and exits without error, producing zero store writes

#### Scenario: Extraction is idempotent
- **WHEN** the sync script is called twice with the same session ID
- **THEN** the second run produces no new rows in the DB

#### Scenario: Trivial sessions are skipped at spawn
- **WHEN** a tracked session has no activity or its transcript is shorter than 200 characters
- **THEN** the plugin does not spawn a digest for it

### Requirement: Digest batch observability
When the plugin spawns digests for multiple sessions at disposal, it SHALL log a batch summary stating the number of sessions spawned. Each spawned digest process SHALL log its final result to `memory/logs/digest.log` per the `auto-session-digest` capability.

#### Scenario: Disposal batch is logged
- **WHEN** the plugin's `dispose` hook spawns digests for N sessions
- **THEN** the plugin logs a batch summary stating N sessions

### Requirement: Plugin implementation has a single versioned source of truth
The OpenCode plugin implementation SHALL be versioned in this repository, and the global plugin location (`~/.config/opencode/plugins/src/obsidian-second-brain-memory/`) SHALL resolve to the repository copy (via symlink, with a scripted copy as documented fallback). There SHALL be exactly one editable copy of the plugin implementation.

#### Scenario: Edit in repo takes effect in OpenCode
- **WHEN** the plugin implementation is edited in the repository copy
- **THEN** the next OpenCode start loads the edited implementation without any manual copy step

#### Scenario: Fallback install when symlink unsupported
- **WHEN** the plugin loader fails to resolve the symlinked global location
- **THEN** `scripts/install_plugin.sh` copies the repository plugin into the global location and documents that the copy must be re-run after edits
