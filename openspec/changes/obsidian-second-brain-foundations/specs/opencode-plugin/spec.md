## ADDED Requirements

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
The plugin SHALL listen to `session.idle` and inject a structured checkpoint prompt when meaningful work was done in the session. The prompt SHALL include a summary of tracked session activity (files edited, bash commands run) to make the checkpoint actionable. The plugin SHALL skip the idle checkpoint only if a checkpoint prompt was already delivered in the current session. The `checkpointDelivered` flag SHALL be set only when a prompt is actually appended to the agent's context.

#### Scenario: Idle reminder with activity summary
- **WHEN** `session.idle` fires during a session where at least one file edit or bash command occurred
- **THEN** the plugin appends a structured prompt listing the tracked activity and asks the agent to write OKF entries for any notable items

#### Scenario: No activity — silent
- **WHEN** `session.idle` fires during a session with no file edits or bash commands
- **THEN** the plugin does not inject any reminder

#### Scenario: Idle reminder fires after git commit where checkpoint was NOT yet delivered
- **WHEN** `session.idle` fires and a git commit was detected but the user never sent a follow-up message (pending checkpoint not yet delivered)
- **THEN** the plugin injects the checkpoint prompt (delivering it via `session.idle`) and sets `checkpointDelivered = true`

#### Scenario: Idle reminder skipped after delivered checkpoint
- **WHEN** `session.idle` fires and `checkpointDelivered` is true
- **THEN** the plugin is silent

### Requirement: Git commit checkpoint trigger
The plugin SHALL detect `git commit` commands via `tool.execute.after` and queue a structured checkpoint prompt for delivery on the next user message. The prompt SHALL be delivered via the `tui.prompt.append` hook, not returned from `tool.execute.after` (which is `Promise<void>`).

#### Scenario: Checkpoint delivered on next user message after git commit
- **WHEN** a bash tool call matching `git commit*` completes and the user sends the next message
- **THEN** the plugin prepends the checkpoint prompt to that user message via `tui.prompt.append`

#### Scenario: No double-prompt on idle after delivered commit checkpoint
- **WHEN** `session.idle` fires in the same session where the commit checkpoint was already delivered via `tui.prompt.append`
- **THEN** the plugin does not inject the idle reminder

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
After every session, the plugin SHALL automatically extract and persist memory entries (decisions, facts, learnings) from the session transcript without requiring any explicit agent or user action.

#### Scenario: Session ends with conversation content
- **WHEN** a session ends and its transcript contains meaningful technical content
- **THEN** the system extracts OKF entries and upserts them into the memory store within 30 seconds of session end

#### Scenario: Transcript unavailable at session end
- **WHEN** a session ends but the transcript file cannot be read
- **THEN** the system logs a warning to the sync log and exits without error, producing zero store writes

#### Scenario: Extraction is idempotent
- **WHEN** the sync script is called twice with the same session ID
- **THEN** the second run produces no new rows in the DB
