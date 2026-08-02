## MODIFIED Requirements

### Requirement: Structured LLM extraction with schema validation
The system SHALL use a structured JSON output schema to request OKF entries from the LLM and SHALL validate the schema before any upsert attempt. The extraction SHALL include retry logic for transient API failures. Before applying any repair, the system SHALL attempt to parse the raw LLM response directly with `json.loads()`. When the response cannot be parsed directly, the system SHALL apply only conservative repairs: strip code fences, remove trailing commas, and — when the document contains double quotes — SHALL NOT alter any single quotes (they are string content). When the document contains no double quotes, the system SHALL convert single-quoted strings to double-quoted strings using a state-machine scanner that respects `\'` escapes. The system SHALL accept the LLM response as either a JSON array or a single object: a single object containing `entry_type` SHALL be wrapped in an array before validation.

#### Scenario: LLM returns valid structured output
- **WHEN** the LLM responds with a JSON array of OKF entries matching the expected schema
- **THEN** all valid entries are upserted via the memory store

#### Scenario: LLM returns malformed output with fixable issues
- **WHEN** the LLM response uses trailing commas or code fences, or uses single quotes as string content inside a double-quoted document (e.g. content containing `'cerebro'`)
- **THEN** the system repairs the JSON without altering single quotes inside string content and parses the repaired output

#### Scenario: LLM returns a single object instead of an array
- **WHEN** the LLM responds with one JSON object containing `entry_type` instead of an array
- **THEN** the system wraps the object in an array and processes it normally

#### Scenario: LLM returns irretrievably malformed output
- **WHEN** the conservative repair pass fails and `json.loads()` still raises an error
- **THEN** the system logs the raw LLM response to the digest log and upserts zero entries

#### Scenario: Transient API error triggers retry
- **WHEN** the LLM API returns HTTP 429 (rate limited) or 5xx (server error)
- **THEN** the system retries up to 3 times with exponential backoff (2s, 4s, 8s) before logging failure

#### Scenario: Persistent API error after retries
- **WHEN** all retry attempts for the LLM API call fail
- **THEN** the system logs the failure to the digest log and exits gracefully with zero entries

## ADDED Requirements

### Requirement: Digest runs are observable
The system SHALL write digest run output to a persistent log file at `memory/logs/digest.log` (created on demand). The log SHALL include parse failures (with the raw LLM response), LLM call failures, and the final result summary (`upserted`, `skipped`, `unknown_tags`). The spawned digest process output SHALL be captured to `memory/logs/digest-spawn.log` rather than discarded.

#### Scenario: Parse failure is recorded
- **WHEN** the LLM response cannot be parsed after repair
- **THEN** the raw response and the parse error are appended to `memory/logs/digest.log`

#### Scenario: Successful run is recorded
- **WHEN** a digest run completes with any result (including zero upserts)
- **THEN** the result summary is appended to `memory/logs/digest.log`

#### Scenario: Spawned process output is captured
- **WHEN** the plugin spawns the digest process
- **THEN** stdout and stderr of the process are appended to `memory/logs/digest-spawn.log`
