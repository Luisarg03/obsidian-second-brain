# Branch Strategy

## Purpose

The repository follows a two-branch Git Flow-lite model: `develop` for ongoing integration and `master` for tagged semver releases. Feature work branches from `develop` and squash-merges back; releases flow from `develop` to `master` via a merge commit that serves as the release boundary. `master` is protected on GitHub against direct pushes, and `develop` is re-synced with `master` after every release.

## Requirements

### Requirement: Repository has develop and master branches

The repository SHALL maintain two long-lived branches: `master` for tagged releases and `develop` for ongoing integration. Feature work SHALL branch from and merge back to `develop`.

#### Scenario: Feature branch workflow
- **WHEN** a developer starts new work
- **THEN** they create a feature branch from `develop`, implement the change, and open a PR targeting `develop`

#### Scenario: Release flows through master
- **WHEN** a release is ready
- **THEN** a PR is opened from `develop` to `master`, and upon merge a semver tag is created on the merge commit

### Requirement: Master branch is protected

The `master` branch SHALL be protected against direct pushes. All changes to `master` MUST go through a pull request with required CI checks passing.

#### Scenario: Direct push rejected
- **WHEN** a developer attempts to push directly to `master`
- **THEN** the push is rejected by GitHub branch protection

#### Scenario: PR merge requires CI
- **WHEN** a PR targeting `master` is opened
- **THEN** the merge button is blocked until all required CI checks pass

### Requirement: Develop is synced after release

After a release merge to `master`, the `develop` branch SHALL be updated with a merge from `master` to keep both branches in sync.

#### Scenario: Post-release sync
- **WHEN** a release is merged to `master` and tagged
- **THEN** `develop` receives a merge commit from `master` so both branches share the release commit
