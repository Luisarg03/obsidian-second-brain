## MODIFIED Requirements

### Requirement: tui.prompt.append delivery hook
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

## ADDED Requirements

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
