## 1. Branch Setup

- [x] 1.1 Create `develop` branch from `master` and push to remote
- [x] 1.2 Configure branch protection on `master`: require PR before merging, require CI checks to pass, block direct pushes

## 2. CI Pipeline

- [x] 2.1 Create `.github/workflows/ci.yml` with jobs for Python tests (`uv run pytest`), TypeScript typecheck (`npm run typecheck`), TypeScript tests (`npm test`), and OKF validation (`uv run okf-validate --strict`)
- [x] 2.2 Verify CI triggers on a test PR to `develop` (open a dummy PR, confirm workflow runs and passes)

## 3. Version Management Scripts

- [x] 3.1 Create `scripts/bump_version.py`: accepts target version argument, updates `pyproject.toml` and `.opencode/plugins/memory/package.json`, supports `--dry-run`, infers bump magnitude from conventional commits when no version given
- [x] 3.2 Create `scripts/generate_changelog.py`: parses `git log` between latest tag and HEAD, groups entries by conventional commit type (`feat`, `fix`, etc.), supports `--dry-run` to stdout, handles the no-tags and no-new-commits edge cases
- [x] 3.3 Verify scripts with dry-run: run `bump_version.py --dry-run` with a sample version, run `generate_changelog.py --dry-run` and inspect output

## 4. Integration Validation

- [x] 4.1 End-to-end test: create a feature branch from `develop`, make a dummy `feat:` commit, open a PR to `develop`, verify CI passes
- [x] 4.2 Release test: run bump script, generate changelog, open release PR from `develop` to `master`, verify CI passes, merge, create tag `v0.2.0`, verify `develop` is synced
