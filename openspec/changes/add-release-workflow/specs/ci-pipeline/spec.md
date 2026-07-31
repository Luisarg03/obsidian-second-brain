## ADDED Requirements

### Requirement: CI runs on pull requests to develop and master

A GitHub Actions workflow SHALL automatically execute on every pull request opened against `develop` or `master`. The workflow SHALL run the project's full quality suite: Python tests, TypeScript typecheck, TypeScript tests, and OKF strict validation.

#### Scenario: PR to develop triggers CI
- **WHEN** a pull request is opened against `develop`
- **THEN** GitHub Actions runs `uv run pytest`, `npm run typecheck`, `npm test`, and `uv run okf-validate --strict`

#### Scenario: PR to master triggers CI
- **WHEN** a pull request is opened against `master`
- **THEN** GitHub Actions runs the same quality suite as for `develop`

#### Scenario: CI failure blocks merge
- **WHEN** any step in the CI workflow fails
- **THEN** the PR status is marked as failed and merge is blocked (when branch protection enforces required checks)

### Requirement: CI uses the project's standard toolchain

The CI workflow SHALL use `uv` for Python dependency management and execution, matching the local development workflow. Node.js SHALL be available for TypeScript plugin tests.

#### Scenario: CI installs dependencies via uv
- **WHEN** the CI workflow runs
- **THEN** Python dependencies are installed using `uv sync` and commands are executed with `uv run`

#### Scenario: CI installs Node dependencies via npm
- **WHEN** the CI workflow runs
- **THEN** TypeScript plugin dependencies are installed using `npm ci` in the plugin directory

### Requirement: CI is defined in the repository

The CI workflow definition SHALL be stored in `.github/workflows/ci.yml` within the repository, making it version-controlled and reproducible.

#### Scenario: Workflow file location
- **WHEN** the change is implemented
- **THEN** `.github/workflows/ci.yml` exists and contains the full CI pipeline definition
