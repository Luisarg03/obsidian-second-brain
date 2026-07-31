# Memory Store

## Purpose

SQLite-based persistence layer for memory entries (Decision, Fact, Learning, Convention, Profile). Uses WAL mode for concurrent reads and FTS5 for full-text search. The OKF Markdown files under `memory/projects/<project>/` are the source of truth; SQLite is a derived search index that can be rebuilt from the Markdown at any time.

## Requirements

### Requirement: Structured entry storage
The system SHALL persist memory entries with the following fields: `id` (UUID), `entry_type` (Decision | Fact | Learning | Convention | Profile), `project` (project name or slug), `content` (text body), `tags` (array of strings), `confidence` (0.0–1.0, default 1.0), `openspec_change_id` (optional, references an OpenSpec change), `created_at`, `updated_at`. The system SHALL additionally persist the OKF frontmatter fields for each entry: `description`, `resource`, `timestamp`. Each in-memory write SHALL also produce an OKF-conformant Markdown file under `memory/projects/<project>/` whose content reflects the entry.

#### Scenario: Store a decision entry
- **WHEN** a decision entry is stored with a project name, content, description, tags, and optional `openspec_change_id`
- **THEN** the entry is persisted in SQLite with a generated UUID, `entry_type` = `Decision`, `created_at` timestamp, and a corresponding Markdown file is written under `memory/projects/<project>/decisions/`

#### Scenario: Store entry with openspec reference
- **WHEN** a memory entry is stored with a valid `openspec_change_id`
- **THEN** the entry stores the change ID as a foreign reference without duplicating the change content

### Requirement: Human-readable Markdown export
The system SHALL maintain OKF-conformant Markdown files under `memory/projects/<project>/` that reflect all entries for that project, updated on every write. Markdown is the source of truth; SQLite is a derived search index. A `scripts/rebuild_index.py` script SHALL be able to reconstruct the SQLite database from the Markdown files alone.

#### Scenario: Project file created on first entry
- **WHEN** the first entry for a new project is stored
- **THEN** a directory `memory/projects/<project>/` is created with an `index.md` and the entry rendered as a Markdown file under the appropriate subdirectory (`decisions/`, `facts/`, `learnings/`, `conventions/`, or `profiles/`)

#### Scenario: Project file updated on new entry
- **WHEN** a subsequent entry is added for an existing project
- **THEN** the new entry's Markdown file is created and the project's `index.md` is updated to include a link to the new entry under the appropriate section

#### Scenario: Index can be rebuilt from Markdown
- **WHEN** `scripts/rebuild_index.py` runs against `memory/projects/<project>/`
- **THEN** the SQLite database is repopulated from the Markdown files with no data loss

### Requirement: Entry retrieval by project, type, and tags
The system SHALL support querying entries by `project`, `entry_type`, and `tags`. Results SHALL be returned sorted by `updated_at` descending. The system SHALL additionally support a FTS5 full-text search mode that matches against `title`, `description`, and `content`.

#### Scenario: Query by project
- **WHEN** `search_memory` is called with a project name
- **THEN** all entries for that project are returned, sorted by `updated_at` descending

#### Scenario: Query by type and project
- **WHEN** `search_memory` is called with project and `entry_type` filters
- **THEN** only entries matching both filters are returned

#### Scenario: FTS5 full-text search
- **WHEN** `search_memory` is called with a `query` parameter
- **THEN** entries whose `title`, `description`, or `content` matches the query are returned, ranked by FTS5 relevance

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

### Requirement: SQLite WAL mode
The storage layer SHALL initialize SQLite in WAL (Write-Ahead Logging) mode to support concurrent read access during write operations.

#### Scenario: WAL mode enabled at initialization
- **WHEN** the memory store is initialized for the first time
- **THEN** SQLite is configured with `PRAGMA journal_mode=WAL`

### Requirement: Store supports profile entry type
The memory store SHALL accept `Profile` as a valid entry type alongside `Decision`, `Fact`, `Learning`, and `Convention`.

#### Scenario: Profile entry stored successfully
- **WHEN** `store_profile` is called with project and content
- **THEN** an entry with `entry_type` = `Profile` is persisted

#### Scenario: Profile entry rejects invalid type
- **WHEN** `store_profile` is called with an empty project
- **THEN** the operation fails with a validation error

### Requirement: Entries below minimum confidence are rejected
The store SHALL accept a `min_confidence` parameter (default 0.0) in `upsert_entry()`. If an entry's confidence is below the threshold, the upsert SHALL be rejected with a descriptive error.

#### Scenario: Entry confidence below threshold
- **WHEN** `upsert_entry()` is called with `confidence` = 0.5 and `min_confidence` = 0.6
- **THEN** the entry is rejected and a `ValueError` is raised with message "confidence 0.5 is below minimum 0.6"

#### Scenario: Default min_confidence allows all entries
- **WHEN** `upsert_entry()` is called without specifying `min_confidence`
- **THEN** the default (0.0) is used and all entries are accepted

### Requirement: Rate-limit backoff uses full jitter
The store layer SHALL NOT implement rate limiting (this is the caller's responsibility). The sync layer SHALL use full jitter for API retry backoff.

#### Scenario: Store has no rate-limit code path
- **WHEN** the store layer is invoked repeatedly in rapid succession
- **THEN** the store does not block, queue, or back off; calls return immediately

#### Scenario: Sync layer uses full jitter
- **WHEN** the sync layer retries an API call after a 429 or 5xx response
- **THEN** the wait between attempts is randomized within the exponential backoff window (full jitter), not a fixed interval

### Requirement: Profile entries deduplicate by project+type, not content
Profile entries SHALL use `(project, entry_type)` as the unique key rather than a content-based dedup key. Each project has at most one profile entry; storing a new profile overwrites the existing one.

#### Scenario: First profile for a project
- **WHEN** a profile is stored for a project with no existing profile
- **THEN** a new profile entry is created

#### Scenario: Profile update overwrites previous content
- **WHEN** a profile is stored for a project that already has a profile entry
- **THEN** the existing profile's content, tags, and `updated_at` are replaced; `created_at` is preserved
