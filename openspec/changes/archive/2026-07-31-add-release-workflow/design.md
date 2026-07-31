## Context

Obsidian Second Brain is a solo-developer Python + TypeScript project hosted on GitHub (`Luisarg03/obsidian-second-brain`). It currently has a single `master` branch, no tags, no CI, and manual version management across two package manifests (`pyproject.toml` and `.opencode/plugins/memory/package.json`). OpenCode agents handle implementation via the orchestrator → fixer/designer delegation model.

The user wants a lightweight, agentic release workflow: develop/master branching, semver versioning driven by conventional commits, automated quality gates on PRs, and changelog generation.

## Goals / Non-Goals

**Goals:**
- Two-branch strategy (`develop` for integration, `master` for tagged releases)
- GitHub Actions CI that runs the full test suite, typechecks, and OKF validation on PRs
- Automated semver bump (MAJOR.MINOR.PATCH) driven by conventional commit analysis
- Automated changelog generation from commit history since last tag
- Agentic PR workflow: OpenCode orchestrator can create PRs via `gh` CLI and delegate review to `@oracle`
- Scripts for version bump and changelog, usable both manually and by agents
- Branch protection on `master` enforcing PR + CI

**Non-Goals:**
- Automated release triggers (release is manual for v0.x, automation deferred until project maturity)
- `git-cliff` or other external changelog tooling — use a self-contained Python script
- Multi-environment deployment (staging/production) — local deploy only
- Commit linting in CI (deferred, conventional commit discipline is enforced by agent conventions)

## Decisions

### 1. Squash merge for feature PRs

**Decision**: Feature branches → `develop` via squash merge.

**Rationale**: One clean conventional commit per feature in `develop` history. For a solo dev, granular per-commit history on feature branches adds noise without value. Squash preserves the feature's intent in a single `feat:` / `fix:` / `chore:` commit.

**Alternative considered**: Merge commits preserve individual commits but create noisy history with interleaved `WIP` and fixup commits. Rejected for solo-dev context.

### 2. Release merge uses merge commit (develop → master)

**Decision**: `develop` → `master` uses a merge commit (no squash, no fast-forward).

**Rationale**: The merge commit serves as the release boundary. `git log --first-parent master` shows exactly one commit per release, while `develop` history remains fully traceable through the second parent.

### 3. Manual release trigger

**Decision**: The developer (or orchestrator agent) manually initiates a release by running the bump script and creating the release PR.

**Rationale**: At v0.x, releases are deliberate and infrequent. Automated triggers on merge would create noise. This can be revisited when cadence increases.

**Alternative considered**: Auto-release on every merge to `develop` — rejected due to low release frequency and desire for human judgment on bump magnitude.

### 4. Python script for changelog generation

**Decision**: A self-contained Python script (`scripts/generate_changelog.py`) parses `git log` between tags and produces changelog entries grouped by conventional commit type.

**Rationale**: The project already uses Python + `uv`. No new dependency. Can parse `pyproject.toml` for current version and `git log` for commit history. Keeps the toolchain minimal.

**Alternative considered**: `git-cliff` — mature and feature-rich but adds an external dependency and configuration file. Overkill for the current project scale.

### 5. Single version source

**Decision**: The version number in `pyproject.toml` is the source of truth. `package.json` version is kept in sync by the bump script.

**Rationale**: `pyproject.toml` is the project root manifest. The plugin `package.json` is a sub-component. A single authoritative version prevents drift.

### 6. GitHub Actions uses `astral-sh/setup-uv`

**Decision**: CI installs Python via `setup-uv` (not `setup-python`).

**Rationale**: The project uses `uv` as its package manager and runner. Using `setup-uv` matches the local development workflow and avoids managing pip separately.

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| Version bump detects wrong magnitude (e.g., `feat:` commit that should be `fix:`) | Script outputs suggested bump, human/agent confirms before applying |
| develop and master diverge over time | Merge-back step after every release keeps them in sync |
| CI breaks silently because workflow file is invalid | First implementation task validates CI by opening a test PR |
| `gh` CLI auth missing in agent environment | Document `gh auth login` as prerequisite; script fails with clear error if unauthenticated |
| Squash merge loses granular history | Feature branches are short-lived and small; conventional commit message captures intent |

## Open Questions

- Branch protection on GitHub: requires repo admin access to configure via web UI or API. Document the manual setup step.
- Should `develop` also have branch protection (require PR)? For solo dev, optional — defer decision.
