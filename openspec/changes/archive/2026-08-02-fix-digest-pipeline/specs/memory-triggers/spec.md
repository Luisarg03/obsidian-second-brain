## MODIFIED Requirements

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

### Requirement: session.end post-session extraction trigger
The `session.end` OpenCode Plugin API v2 hook SHALL be available as a memory-capture trigger. When the hook fires, the plugin SHALL invoke the `auto-session-digest` capability against the session's transcript and persist any extracted OKF entries within 30 seconds of session end. The spawned process output SHALL be redirected to `memory/logs/digest-spawn.log` instead of being discarded.

#### Scenario: Post-session extraction runs on session end
- **WHEN** `session.end` fires and the session transcript is readable
- **THEN** the plugin invokes the digest pipeline and the extracted entries appear in the bundle within 30 seconds

#### Scenario: Post-session extraction output is captured
- **WHEN** the plugin spawns the digest at session end
- **THEN** stdout and stderr are appended to `memory/logs/digest-spawn.log`

#### Scenario: Transcript unavailable is handled gracefully
- **WHEN** `session.end` fires and the transcript file cannot be read
- **THEN** the plugin logs a warning and exits without error, producing zero writes
