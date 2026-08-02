# Memory Triggers

## Purpose

Declarative catalog of lifecycle hook points where memory capture or retrieval can fire. Each trigger documents its event source (OpenCode Plugin API v2 hook, git event, scheduled job, or slash command), the payload it provides, the action it takes, and the bundle write target. Triggers are declarative in this change; each trigger's implementation is the subject of a follow-up change.

## Requirements

### Requirement: Trigger catalog
The `memory-triggers` capability SHALL document every lifecycle hook point where memory capture or retrieval can fire. Each trigger SHALL declare its event source (OpenCode Plugin API v2 hook, git event, scheduled job, or slash command), the payload it provides, the action it takes, and the bundle write target. Triggers are declarative in this change; each trigger's implementation is the subject of a follow-up change.

#### Scenario: Trigger catalog is queryable
- **WHEN** the user reads `openspec/specs/memory-triggers/spec.md`
- **THEN** they find one Requirement block per documented trigger with name, source, action, and target

### Requirement: session.idle checkpoint trigger
The `session.idle` OpenCode Plugin API v2 hook SHALL be available as a memory-capture trigger. When the hook fires and the session has tracked activity (at least one file edit or one bash command), the plugin SHALL run automatic capture: fetch the session transcript, write it to a temporary file, and spawn the post-session digest pipeline. The plugin SHALL NOT inject any prompt into the user's composer/input box. The plugin SHALL run the capture at most once per session (the existing `checkpointDelivered` flag SHALL be set when the capture is spawned). The plugin SHALL skip capture when no activity has been tracked.

#### Scenario: session.idle with activity runs automatic capture
- **WHEN** `session.idle` fires and the session has at least one tracked file edit or bash command
- **THEN** the plugin spawns the digest pipeline for the session transcript and sets `checkpointDelivered`

#### Scenario: session.idle does not inject into the composer
- **WHEN** `session.idle` fires with tracked activity
- **THEN** no text is appended to the user's input box via `appendPrompt`

#### Scenario: session.idle with no activity is silent
- **WHEN** `session.idle` fires and the session has no tracked activity
- **THEN** the plugin does not run capture and injects nothing

#### Scenario: Duplicate session.idle capture is suppressed
- **WHEN** `session.idle` fires a second time and capture was already spawned earlier in the session
- **THEN** the plugin does not run capture again

### Requirement: experimental.session.compacting checkpoint trigger
The `experimental.session.compacting` OpenCode Plugin API v2 hook SHALL be available as a memory-capture trigger. When the hook fires, the plugin SHALL inject a structured checkpoint prompt listing the session's tracked activity. The trigger SHALL fire even if a previous checkpoint was delivered in the session (compaction is always worth a save).

#### Scenario: Compacting checkpoint fires on compaction
- **WHEN** `experimental.session.compacting` fires
- **THEN** the plugin injects a checkpoint prompt regardless of prior `checkpointDelivered` state

#### Scenario: Compacting trigger missing from runtime is tolerated
- **WHEN** `experimental.session.compacting` is not exposed by the running OpenCode version
- **THEN** the plugin logs no error and the trigger is silently skipped

### Requirement: tool.execute.after git commit trigger
The `tool.execute.after` OpenCode Plugin API v2 hook SHALL be available as a memory-capture trigger. When a bash tool call matching the pattern `git commit*` completes, the plugin SHALL queue a structured checkpoint prompt for delivery on the next user message via the `experimental.chat.messages.transform` hook.

#### Scenario: Git commit queues checkpoint for next message
- **WHEN** a bash tool call matching `git commit*` completes
- **THEN** the plugin queues a checkpoint prompt and delivers it on the next user message via `experimental.chat.messages.transform`

#### Scenario: Non-commit bash commands do not queue a checkpoint
- **WHEN** a bash tool call that does not match `git commit*` completes
- **THEN** the plugin does not queue a checkpoint prompt

### Requirement: experimental.chat.messages.transform delivery hook
The `experimental.chat.messages.transform` OpenCode Plugin API v2 hook SHALL be used to deliver a queued checkpoint prompt on the next user message. The hook SHALL prepend the checkpoint text to the user's message so the agent sees the checkpoint as part of the next turn. This works headless and in the TUI.

#### Scenario: Checkpoint is prepended to next user prompt
- **WHEN** a checkpoint prompt is queued and the user sends a new message
- **THEN** the plugin prepends the checkpoint text to that message via `experimental.chat.messages.transform`

#### Scenario: Checkpoint queue is empty on idle after delivery
- **WHEN** the queued checkpoint has been delivered via `experimental.chat.messages.transform` and `session.idle` subsequently fires
- **THEN** the idle capture is suppressed (per the idle checkpoint trigger)

### Requirement: session.end post-session extraction trigger
The `server.instance.disposed` (plugin `dispose` hook) and `session.idle` OpenCode Plugin API v2 hooks SHALL be available as post-session memory-capture triggers. When the plugin's `dispose` hook fires (server instance disposal) or `session.idle` fires with tracked activity, the plugin SHALL invoke the `auto-session-digest` capability against the session's transcript and persist any extracted OKF entries within 30 seconds of the event. The spawned process output SHALL be redirected to `memory/logs/digest-spawn.log` instead of being discarded.

#### Scenario: Post-session extraction runs on server disposal
- **WHEN** the plugin's `dispose` hook fires and the session transcript is readable
- **THEN** the plugin invokes the digest pipeline and the extracted entries appear in the bundle within 30 seconds

#### Scenario: Post-session extraction output is captured
- **WHEN** the plugin spawns the digest at disposal or on idle
- **THEN** stdout and stderr are appended to `memory/logs/digest-spawn.log`

#### Scenario: Transcript unavailable is handled gracefully
- **WHEN** the transcript file cannot be read
- **THEN** the plugin logs a warning and exits without error, producing zero writes

### Requirement: Single-flight digest execution
The plugin SHALL spawn post-session digests detached without inter-process coordination; serialization SHALL be enforced by the digest script, which SHALL acquire an exclusive advisory lock on `memory/logs/digest.lock` before invoking the LLM (at most one digest LLM call chain per memory store at a time). A digest process that cannot acquire the lock within the bounded budget (default 600 seconds) SHALL log the lock wait expiry to `memory/logs/digest.log` and skip with zero writes.

#### Scenario: Concurrent end-of-session digests serialize
- **WHEN** a server disposal spawns digests for multiple sessions and two or more of them invoke the LLM at the same time
- **THEN** exactly one LLM call chain runs at a time and the others wait, then run in turn

#### Scenario: Lock budget exhausted is a logged skip
- **WHEN** a digest process waits longer than the bounded budget for the lock
- **THEN** it logs the lock wait expiry to `memory/logs/digest.log` and exits with zero writes

### Requirement: Digest spawn gate
The plugin SHALL skip spawning a digest for a session with no tracked activity (no file edits and no bash commands) or whose transcript is empty or shorter than 200 characters.

#### Scenario: Session with no tracked activity is not digested
- **WHEN** a session ends having tracked no file edits or bash commands
- **THEN** the plugin does not spawn a digest for it

#### Scenario: Transcript too short is not digested
- **WHEN** a session's transcript is empty or shorter than 200 characters
- **THEN** the plugin does not spawn a digest for it

#### Scenario: Session with activity is digested
- **WHEN** a session ends having tracked at least one file edit or bash command and a transcript of 200 characters or more
- **THEN** the plugin spawns a digest for it

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
