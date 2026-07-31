# Auto Session Digest

## Purpose

Post-session LLM-based extraction pipeline that converts a session transcript into structured OKF entries (decisions, facts, learnings, conventions) and persists them to the memory store. Handles schema validation, transient API failures with exponential backoff and full jitter, tag normalization against a controlled vocabulary, confidence scoring, and project alias resolution. Idempotent: re-running on the same session produces no duplicates.

## Requirements

### Requirement: Structured LLM extraction with schema validation
The system SHALL use a structured JSON output schema to request OKF entries from the LLM and SHALL validate the schema before any upsert attempt. The extraction SHALL include retry logic for transient API failures and SHALL attempt to repair common JSON formatting issues in LLM responses.

#### Scenario: LLM returns valid structured output
- **WHEN** the LLM responds with a JSON array of OKF entries matching the expected schema
- **THEN** all valid entries are upserted via the memory store

#### Scenario: LLM returns malformed output with fixable issues
- **WHEN** the LLM response uses single quotes instead of double quotes, or has trailing commas
- **THEN** the system repairs the JSON using regex preprocessing and attempts to parse the repaired output

#### Scenario: LLM returns irretrievably malformed output
- **WHEN** the JSON repair pass fails and `json.loads()` still raises an error
- **THEN** the system logs the raw LLM response to the sync log and upserts zero entries

#### Scenario: Transient API error triggers retry
- **WHEN** the LLM API returns HTTP 429 (rate limited) or 5xx (server error)
- **THEN** the system retries up to 3 times with exponential backoff (2s, 4s, 8s) before logging failure

#### Scenario: Persistent API error after retries
- **WHEN** all retry attempts for the LLM API call fail
- **THEN** the system logs the failure to the sync log and exits gracefully with zero entries

### Requirement: No memorable content is handled gracefully
If the transcript contains only trivial exchanges, the extraction SHALL produce zero store writes.

#### Scenario: Session with no memorable content
- **WHEN** a session ends and the transcript contains only trivial exchanges
- **THEN** the system writes zero entries and logs "no memorable content found" to the sync log

### Requirement: Extractions include confidence scoring
The system SHALL assign a confidence score (0.0–1.0) to each extracted entry based on content quality heuristics.

#### Scenario: High-confidence extraction
- **WHEN** the LLM responds promptly (<10s) with content >50 chars that matches known facts
- **THEN** the entry is stored with `confidence` = 1.0

#### Scenario: Medium-confidence extraction
- **WHEN** content is >50 chars but no known-fact match exists
- **THEN** the entry is stored with `confidence` = 0.9

#### Scenario: Low-confidence extraction
- **WHEN** extracted content is <50 chars or vaguely phrased
- **THEN** the entry is stored with `confidence` = 0.7

#### Scenario: Extraction from truncated transcript
- **WHEN** the session transcript was truncated before reaching the character limit for the LLM prompt
- **THEN** the entry is stored with `confidence` = 0.5

### Requirement: Tags are normalized against a controlled vocabulary
The system SHALL maintain a tag vocabulary file at `memory/tag-vocabulary.json` that defines canonical tags and aliases. Extracted entries SHALL have their tags normalized against this vocabulary before upsert.

#### Scenario: Tag matches a canonical entry
- **WHEN** an extracted tag matches a canonical tag in the vocabulary
- **THEN** it is kept as-is

#### Scenario: Tag matches an alias
- **WHEN** an extracted tag matches an alias defined in the vocabulary
- **THEN** it is replaced with the canonical tag

#### Scenario: Tag does not match vocabulary
- **WHEN** an extracted tag is not found in the vocabulary or aliases
- **THEN** the tag is still accepted but logged to the sync log for vocabulary review

### Requirement: Project name uses alias mapping
The system SHALL support a project alias configuration so that multiple session directory names map to a single canonical project name.

#### Scenario: Session directory matches a project alias
- **WHEN** a session's working directory is not the canonical project name but is defined as an alias
- **THEN** the entry is stored under the canonical project name

#### Scenario: No alias match
- **WHEN** no alias is configured for the session directory
- **THEN** the existing resolution logic applies (basename, package.json, pyproject.toml)

### Requirement: Extraction respects OKF frontmatter
When the LLM returns extracted entries, the system SHALL ensure each entry has OKF-conformant frontmatter before upsert. If `description` is missing from the LLM output, the system SHALL derive a one-sentence description from the entry's content. If `tags` is missing, the system SHALL leave the array empty and log the omission.

#### Scenario: Extracted entry with description
- **WHEN** the LLM returns an entry with a `description` field
- **THEN** the entry is stored with the LLM-provided description

#### Scenario: Extracted entry without description
- **WHEN** the LLM returns an entry without a `description` field
- **THEN** the system derives a one-sentence description from the first non-heading line of `content` and stores the entry

#### Scenario: Extracted entry without tags
- **WHEN** the LLM returns an entry without a `tags` field
- **THEN** the entry is stored with an empty `tags` array and the omission is logged
