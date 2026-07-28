## ADDED Requirements

### Requirement: Bundle directory layout
The OKF knowledge bundle SHALL live under `memory/` in the repository root. The bundle SHALL contain one `index.md` at the root, optionally one `log.md` for chronological change history, and one subdirectory per project at `memory/projects/<project>/`. Each project subdirectory SHALL contain its own `index.md` and the project's entries grouped into optional subdirectories by entry type (`decisions/`, `facts/`, `learnings/`, `conventions/`, `profiles/`).

#### Scenario: Bundle root is the only vault entry point
- **WHEN** the user opens the project in Obsidian
- **THEN** Obsidian treats `memory/` as the vault root and lists `index.md`, `log.md`, and the project subdirectories as navigable items

#### Scenario: Project subdirectory follows the OKF convention
- **WHEN** a project subdirectory is created at `memory/projects/<project>/`
- **THEN** it contains an `index.md` and any number of entry subdirectories or flat entry files

### Requirement: OKF frontmatter schema
Every Markdown document in the bundle SHALL carry a YAML frontmatter block with the fields `type`, `title`, `description`, `resource`, `tags`, and `timestamp`, in that order. Custom fields (`project`, `confidence`, `openspec_change_id`) MAY be appended after the OKF core fields. The `type` field SHALL be one of: `Index`, `Decision`, `Fact`, `Learning`, `Convention`, `Profile`, or a producer-defined type prefixed with `x-`.

#### Scenario: Document with all OKF core fields is conformant
- **WHEN** a Markdown file is parsed and its frontmatter contains `type`, `title`, `description`, `tags`, and `timestamp`
- **THEN** `scripts/okf_validate.py` reports the file as OKF-conformant

#### Scenario: Document missing description is non-conformant
- **WHEN** a Markdown file's frontmatter lacks the `description` field
- **THEN** `scripts/okf_validate.py` reports a missing-field error and the file path

#### Scenario: Document with unknown type is rejected
- **WHEN** a Markdown file's frontmatter has `type: Foo` and `Foo` is not in the OKF type vocabulary
- **THEN** `scripts/okf_validate.py` reports an unknown-type error unless the type starts with `x-`

#### Scenario: Custom fields are preserved
- **WHEN** a Markdown file's frontmatter has the OKF core fields plus a custom `project: SecondBrain` field
- **THEN** `scripts/okf_validate.py` reports the file as conformant and the custom field is not modified

### Requirement: Reserved filenames
The bundle SHALL treat `index.md` and `log.md` as reserved filenames. `index.md` is allowed at any directory level and serves as the OKF index for that directory. `log.md` is allowed at any directory level and serves as a chronological log of changes for that directory. No other filename is reserved.

#### Scenario: index.md at the root describes the bundle
- **WHEN** the user opens `memory/index.md`
- **THEN** the file contains a top-level heading, a description of the bundle, and links to each project subdirectory

#### Scenario: log.md at the root records chronological changes
- **WHEN** a memory entry is added or modified
- **THEN** a one-line entry is appended to `memory/log.md` with the timestamp, project, entry type, and slug

### Requirement: Read scope is the bundle only
The project repository SHALL be partitioned into a bundle surface (the `memory/` directory) and an implementation surface (everything else: `memory-server/`, `scripts/`, `openspec/`, `.opencode/`, `pyproject.toml`, etc.). LLM agents operating on the project SHALL NOT read, cite, or reason about the implementation surface unless explicitly directed by the user. The bundle surface is the only context the agents consume by default.

#### Scenario: Agent only consumes the bundle by default
- **WHEN** an LLM agent is invoked on the project without explicit user direction to read code
- **THEN** the agent's context includes only entries from `memory/` and the agent does not auto-read files outside `memory/`

#### Scenario: User explicitly directs agent to read code
- **WHEN** the user issues a prompt that explicitly references code, scripts, or non-bundle paths
- **THEN** the agent may read those paths to satisfy the prompt, but no read scope is assumed on subsequent turns

### Requirement: Validator script
The project SHALL ship `scripts/okf_validate.py` as a CLI tool that walks `memory/`, parses every `.md` file's frontmatter, and reports conformance against this spec. The script SHALL support a `--strict` flag that exits non-zero on any conformance error, and a default mode that prints a summary report.

#### Scenario: Validator passes a clean bundle
- **WHEN** `scripts/okf_validate.py` runs against a bundle where every file has conformant frontmatter
- **THEN** the script prints a per-directory summary and exits with status 0

#### Scenario: Validator reports a missing description
- **WHEN** `scripts/okf_validate.py` runs and finds a file missing the `description` field
- **THEN** the script prints the file path and the missing field, and exits non-zero under `--strict`
