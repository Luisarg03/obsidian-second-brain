## ADDED Requirements

### Requirement: Trigger catalog
The `memory-triggers` capability SHALL document every lifecycle hook point where memory capture or retrieval can fire. Each trigger SHALL declare its event source (OpenCode Plugin API v2 hook, git event, scheduled job, or slash command), the payload it provides, the action it takes, and the bundle write target. Triggers are declarative in this change; each trigger's implementation is the subject of a follow-up change.

#### Scenario: Trigger catalog is queryable
- **WHEN** the user reads `openspec/specs/memory-triggers/spec.md`
- **THEN** they find one Requirement block per documented trigger with name, source, action, and target

### Requirement: session.idle checkpoint trigger
The `session.idle` OpenCode Plugin API v2 hook SHALL be available as a memory-capture trigger. When the hook fires and the session has tracked activity (at least one file edit or one bash command), the plugin SHALL inject a structured checkpoint prompt listing the tracked activity and asking the agent to write OKF entries for any notable decisions, facts, or learnings. The plugin SHALL skip the injection when no activity has been tracked. The plugin SHALL also skip when a checkpoint has already been delivered in the current session.

#### Scenario: session.idle with activity delivers checkpoint
- **WHEN** `session.idle` fires and the session has at least one tracked file edit or bash command
- **THEN** the plugin appends a checkpoint prompt to the agent context

#### Scenario: session.idle with no activity is silent
- **WHEN** `session.idle` fires and the session has no tracked activity
- **THEN** the plugin does not inject any prompt

#### Scenario: Duplicate session.idle checkpoint is suppressed
- **WHEN** `session.idle` fires a second time and a checkpoint was already delivered earlier in the session
- **THEN** the plugin does not inject another checkpoint

### Requirement: experimental.session.compacting checkpoint trigger
The `experimental.session.compacting` OpenCode Plugin API v2 hook SHALL be available as a memory-capture trigger. When the hook fires, the plugin SHALL inject a structured checkpoint prompt listing the session's tracked activity. The trigger SHALL fire even if a previous checkpoint was delivered in the session (compaction is always worth a save).

#### Scenario: Compacting checkpoint fires on compaction
- **WHEN** `experimental.session.compacting` fires
- **THEN** the plugin injects a checkpoint prompt regardless of prior `checkpointDelivered` state

#### Scenario: Compacting trigger missing from runtime is tolerated
- **WHEN** `experimental.session.compacting` is not exposed by the running OpenCode version
- **THEN** the plugin logs no error and the trigger is silently skipped

### Requirement: tool.execute.after git commit trigger
The `tool.execute.after` OpenCode Plugin API v2 hook SHALL be available as a memory-capture trigger. When a bash tool call matching the pattern `git commit*` completes, the plugin SHALL queue a structured checkpoint prompt for delivery on the next user message via the `tui.prompt.append` hook.

#### Scenario: Git commit queues checkpoint for next message
- **WHEN** a bash tool call matching `git commit*` completes
- **THEN** the plugin queues a checkpoint prompt and delivers it on the next user message via `tui.prompt.append`

#### Scenario: Non-commit bash commands do not queue a checkpoint
- **WHEN** a bash tool call that does not match `git commit*` completes
- **THEN** the plugin does not queue a checkpoint prompt

### Requirement: tui.prompt.append delivery hook
The `tui.prompt.append` OpenCode Plugin API v2 hook SHALL be used to deliver a queued checkpoint prompt on the next user message. The hook SHALL prepend the checkpoint text to the user's prompt so the agent sees the checkpoint as part of the next turn.

#### Scenario: Checkpoint is prepended to next user prompt
- **WHEN** a checkpoint prompt is queued and the user sends a new message
- **THEN** the plugin prepends the checkpoint text to that message via `tui.prompt.append`

#### Scenario: Checkpoint queue is empty on idle after delivery
- **WHEN** the queued checkpoint has been delivered via `tui.prompt.append` and `session.idle` subsequently fires
- **THEN** the idle checkpoint is suppressed

### Requirement: session.end post-session extraction trigger
The `session.end` OpenCode Plugin API v2 hook SHALL be available as a memory-capture trigger. When the hook fires, the plugin SHALL invoke the `auto-session-digest` capability against the session's transcript file and persist any extracted OKF entries within 30 seconds of session end.

#### Scenario: Post-session extraction runs on session end
- **WHEN** `session.end` fires and the session transcript file is readable
- **THEN** the plugin invokes the digest pipeline and the extracted entries appear in the bundle within 30 seconds

#### Scenario: Transcript unavailable is handled gracefully
- **WHEN** `session.end` fires and the transcript file cannot be read
- **THEN** the plugin logs a warning and exits without error, producing zero writes

### Requirement: /checkpoint slash command trigger
The OpenCode Plugin API v2 slash command surface SHALL be available as a manual memory-capture trigger. When the user types `/checkpoint`, the plugin SHALL inject a structured end-of-session review prompt listing the session's tracked activity and asking the agent to write OKF entries.

#### Scenario: /checkpoint with activity delivers review prompt
- **WHEN** the user types `/checkpoint` in a session with at least one tracked activity item
- **THEN** the plugin injects a review prompt listing the activity

#### Scenario: /checkpoint with no activity is a no-op
- **WHEN** the user types `/checkpoint` in a session with no tracked activity
- **THEN** the plugin responds "No tracked activity in this session. Nothing to checkpoint."

### Requirement: Git post-commit external trigger
A git `post-commit` hook (configurable per project) SHALL be available as an external memory-capture trigger. When the hook fires, the plugin SHALL inspect the commit message and diff and propose a candidate OKF entry (typically a `Decision` or `Fact`). The proposal SHALL be reviewed by the user before being written to the bundle. This trigger is documented but not implemented in this change.

#### Scenario: Post-commit hook proposes candidate entry
- **WHEN** a `git commit` completes and the post-commit hook is installed
- **THEN** the hook reads the commit message and diff, and the plugin proposes a candidate OKF entry for user review

### Requirement: Nightly dreamer external trigger
A scheduled background job (the "dreamer") SHALL be available as a periodic memory-consolidation trigger. When the job runs, the plugin SHALL inspect the bundle for low-confidence entries, orphan tags, and stale facts, and propose a consolidation pass. This trigger is documented but not implemented in this change.

#### Scenario: Dreamer job proposes consolidation
- **WHEN** the scheduled dreamer job runs against a bundle
- **THEN** the job identifies low-confidence entries and stale facts and surfaces a consolidation proposal to the user

### Requirement: Explicit retrieval trigger
A user-issued prompt or slash command (e.g. `/brain search "..."`, `/brain recall`, or a prompt containing `@brain ...` or `recuerdo que ...`) SHALL be the only path that pulls bundle content into the agent's context. There is no automatic context loading.

#### Scenario: User prompt pulls bundle content
- **WHEN** the user issues a prompt that explicitly references the bundle (slash command, `@brain`, or similar)
- **THEN** the agent MAY call `search_memory`, `get_profile`, or `export_memories` to satisfy the prompt

#### Scenario: No prompt means no bundle in context
- **WHEN** the user issues a prompt that does not reference the bundle
- **THEN** the agent SHALL NOT call any memory read tool and the bundle content is not loaded into context
