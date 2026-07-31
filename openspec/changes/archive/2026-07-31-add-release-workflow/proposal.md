## Why

The project currently has no release process: a single `master` branch, no tags, no CI, manual version bumps across two package manifests, and no quality gates. Every deploy is ad-hoc and error-prone. As the codebase grows and the user relies on OpenCode agents for implementation, a structured workflow with automated checks and version tracking prevents regressions and makes releases reproducible.

## What Changes

- Introduce a two-branch strategy (`develop` for integration, `master` for tagged releases)
- Add GitHub Actions CI that runs tests, typechecks, and OKF validation on every PR
- Add scripts for automated semver version bumping across `pyproject.toml` and `package.json`
- Add a changelog generation script driven by conventional commit history
- Define a release workflow: version bump → changelog → release PR → merge + tag → sync back
- Define the agentic PR workflow: OpenCode orchestrator creates PRs via `gh`, delegates review to `@oracle`, and enforces quality gates

## Capabilities

### New Capabilities

- `branch-strategy`: develop/master branching model with branch protection rules for `master`
- `ci-pipeline`: GitHub Actions workflow that runs `pytest`, TypeScript typecheck/tests, and OKF strict validation on PRs to `develop` and `master`
- `version-management`: automated semver version bump across `pyproject.toml` and `.opencode/plugins/memory/package.json`, plus changelog generation from conventional commits

### Modified Capabilities

<!-- No existing capability requirements are changing. -->

## Impact

- New files: `.github/workflows/ci.yml`, `scripts/bump_version.py`, `scripts/generate_changelog.py`
- Modified files: none (existing code unchanged)
- Git configuration: branch protection rules on `master` (via GitHub repo settings)
- Dependency: `gh` CLI must be available for PR creation and merge from OpenCode orchestrator
- Dependencies: `uv` and `npm` already in use; no new runtime dependencies added by the scripts
