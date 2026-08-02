## MODIFIED Requirements

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

## ADDED Requirements

### Requirement: Digest batch observability
When the plugin spawns digests for multiple sessions at disposal, it SHALL log a batch summary stating the number of sessions spawned. Each spawned digest process SHALL log its final result to `memory/logs/digest.log` per the `auto-session-digest` capability.

#### Scenario: Disposal batch is logged
- **WHEN** the plugin's `dispose` hook spawns digests for N sessions
- **THEN** the plugin logs a batch summary stating N sessions
