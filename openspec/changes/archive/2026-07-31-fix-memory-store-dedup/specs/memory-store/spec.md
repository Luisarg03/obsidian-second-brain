## MODIFIED Requirements

### Requirement: Dedup key derived from full content hash
The system SHALL generate dedup keys by hashing the full normalized content of an entry (stripped whitespace, lowercased), not a truncated prefix. Profile entries are exempt from this rule (see Profile dedup requirement). The dedup check SHALL be performed against SQLite BEFORE the OKF Markdown file is written. If a dedup match exists, the system SHALL update the existing SQLite row and SHALL NOT write a new `.md` file.

#### Scenario: Overwrite stale fact
- **WHEN** `store_fact` is called with content that matches an existing entry's dedup key
- **THEN** the existing entry is updated in-place rather than creating a duplicate

#### Scenario: Different full content with same first chars
- **WHEN** two entries share the same first 60 characters but differ after that point
- **THEN** each entry receives a distinct dedup key and both are stored independently

#### Scenario: Identical content re-upserted
- **WHEN** `upsert_entry()` is called with content identical to an existing entry
- **THEN** no new `.md` file is written to disk, the existing SQLite row is updated, and the call returns `updated: True`
