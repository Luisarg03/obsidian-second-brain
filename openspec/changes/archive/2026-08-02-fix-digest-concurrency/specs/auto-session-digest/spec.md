## MODIFIED Requirements

### Requirement: Structured LLM extraction with schema validation
The system SHALL use a structured JSON output schema to request OKF entries from the LLM and SHALL validate the schema before any upsert attempt. The extraction SHALL include retry logic for transient API failures and timeouts. Each LLM call attempt SHALL allow up to 180 seconds (default) for the API to respond; on timeout or transient HTTP error (429, 5xx) the system SHALL retry up to 3 attempts with jittered backoff bases of 5s, 10s, and 20s before logging failure and exiting gracefully with zero entries. Before applying any repair, the system SHALL attempt to parse the raw LLM response directly with `json.loads()`. When the response cannot be parsed directly, the system SHALL apply only conservative repairs: strip code fences, remove trailing commas, and — when the document contains double quotes — SHALL NOT alter any single quotes (they are string content). When the document contains no double quotes, the system SHALL convert single-quoted strings to double-quoted strings using a state-machine scanner that respects `\'` escapes. The system SHALL accept the LLM response as either a JSON array or a single object: a single object containing `entry_type` SHALL be wrapped in an array before validation.

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
- **WHEN** the LLM API returns HTTP 429 (rate limited), 5xx (server error), or times out after 180 seconds
- **THEN** the system retries up to 3 times with jittered exponential backoff (5s, 10s, 20s bases) before logging failure

#### Scenario: Persistent API error after retries
- **WHEN** all retry attempts for the LLM API call fail
- **THEN** the system logs the failure to the digest log and exits gracefully with zero entries

## ADDED Requirements

### Requirement: Digest runs are serialized
The system SHALL run at most one digest LLM call chain at a time per memory store. Each digest process SHALL acquire an exclusive advisory lock on `memory/logs/digest.lock` before invoking the LLM. If the lock is held by another digest process, the process SHALL wait for it, polling at most once per second, for a bounded budget (default 600 seconds). If the budget is exhausted, the process SHALL log the lock wait expiry and exit with zero writes and exit code 0.

#### Scenario: Single digest run acquires the lock
- **WHEN** a digest process starts and no other digest holds the lock
- **THEN** it acquires the lock immediately and proceeds with the LLM call

#### Scenario: Concurrent digest runs serialize
- **WHEN** two or more digest processes start for the same memory store at the same time
- **THEN** exactly one runs the LLM call at a time and the others wait, then run in turn

#### Scenario: Lock wait budget exhausted
- **WHEN** a digest process waits longer than the bounded budget for the lock
- **THEN** it logs the lock wait expiry to `memory/logs/digest.log` and exits with zero writes and exit code 0
