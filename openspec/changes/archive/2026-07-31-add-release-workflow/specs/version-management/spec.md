## ADDED Requirements

### Requirement: Bump script updates versions in both manifests

A script (`scripts/bump_version.py`) SHALL update the version number in both `pyproject.toml` and `.opencode/plugins/memory/package.json` to a specified target version. The script SHALL validate that both files were updated successfully.

#### Scenario: Bump to a new version
- **WHEN** the script is invoked with a target version (e.g., `uv run scripts/bump_version.py 0.2.0`)
- **THEN** `pyproject.toml` version is set to `0.2.0` and `package.json` version is set to `0.2.0`

#### Scenario: Dry-run mode
- **WHEN** the script is invoked with a `--dry-run` flag
- **THEN** it reports what would change without modifying any files

#### Scenario: Missing target version
- **WHEN** the script is invoked without a target version argument
- **THEN** it exits with a non-zero code and prints usage instructions

### Requirement: Changelog script generates entries from commit history

A script (`scripts/generate_changelog.py`) SHALL generate changelog entries by analyzing conventional commits between the latest tag and HEAD. Entries SHALL be grouped by commit type (`feat`, `fix`, `chore`, `docs`, `test`, `refactor`) and SHALL include the commit description.

#### Scenario: Generate changelog from commits since last tag
- **WHEN** the script is invoked and a previous tag exists
- **THEN** it outputs a markdown-formatted changelog section with commits grouped by type, using conventional commit prefixes

#### Scenario: No previous tag exists
- **WHEN** the script is invoked and no git tags exist in the repository
- **THEN** it includes all commits in the changelog with a note that this is the initial release

#### Scenario: No new commits since last tag
- **WHEN** the script is invoked and the latest tag points to HEAD
- **THEN** it reports that there are no new entries and exits successfully

#### Scenario: Dry-run mode
- **WHEN** the script is invoked with `--dry-run`
- **THEN** it prints the generated changelog to stdout without modifying CHANGELOG.md

### Requirement: Version bump infers magnitude from commits

The bump script SHALL infer the recommended semver bump magnitude (MAJOR, MINOR, or PATCH) from conventional commits since the last tag. `feat:` commits SHALL suggest a MINOR bump. `fix:` commits SHALL suggest a PATCH bump. A commit containing `BREAKING CHANGE:` or a `!` after the type SHALL suggest a MAJOR bump.

#### Scenario: Feature commits suggest minor bump
- **WHEN** the version since the last tag contains at least one `feat:` commit and no breaking changes
- **THEN** the script suggests a MINOR version bump

#### Scenario: Fix commits suggest patch bump
- **WHEN** the version since the last tag contains only `fix:`, `chore:`, `docs:`, `test:`, or `refactor:` commits
- **THEN** the script suggests a PATCH version bump

#### Scenario: Breaking change suggests major bump
- **WHEN** any commit since the last tag contains `BREAKING CHANGE:` in its body or `!:` in its type prefix
- **THEN** the script suggests a MAJOR version bump

### Requirement: pyproject.toml is the authoritative version source

The version field in the root `pyproject.toml` SHALL be the single source of truth for the project version. The `package.json` version SHALL always be kept in sync with it by the bump script.

#### Scenario: Version sync after bump
- **WHEN** the bump script updates `pyproject.toml` to a new version
- **THEN** the script also updates `package.json` to the same version
