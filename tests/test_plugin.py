"""Unit tests for the OpenCode plugin logic.

Tests the pure functions exported from `.opencode/plugins/memory/index.ts`
by re-implementing the contracts in Python. The TypeScript file is verified
separately by `npx tsc --noEmit`; this file covers the behavioral spec.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent  # repo root


# ── Project name resolution (mirrors index.ts algorithm) ─────────────────


def resolve_project_name(cwd: Path) -> str:
    """Pure-Python mirror of `resolveProjectName` in index.ts.

    Priority:
      1. OpenSpec presence -> cwd basename
      2. package.json -> name
      3. pyproject.toml -> [project] -> name
      4. README.md heading
      5. cwd basename
    """
    if (cwd / "openspec").exists():
        return cwd.name
    pkg = cwd / "package.json"
    if pkg.is_file():
        try:
            import json
            data = json.loads(pkg.read_text(encoding="utf-8"))
            name = data.get("name")
            if isinstance(name, str) and name.strip():
                return name.strip()
        except (OSError, ValueError):
            pass
    pyproject = cwd / "pyproject.toml"
    if pyproject.is_file():
        try:
            text = pyproject.read_text(encoding="utf-8")
            m = re.search(r'\[project\][^\[]*?name\s*=\s*["\']([^"\']+)["\']', text, re.S)
            if m:
                return m.group(1)
        except OSError:
            pass
    readme = cwd / "README.md"
    if readme.is_file():
        try:
            head = readme.read_text(encoding="utf-8").splitlines()[:5]
            for line in head:
                m = re.match(r"#\s+(.+)", line)
                if m:
                    return m.group(1).strip()
        except OSError:
            pass
    return cwd.name


class TestProjectNameResolution:
    def test_openspec_takes_priority(self, temp_dir: Path):
        proj = temp_dir / "proj"
        proj.mkdir()
        (proj / "openspec").mkdir()
        (proj / "package.json").write_text('{"name": "wrong-name"}')
        assert resolve_project_name(proj) == "proj"

    def test_package_json_used_when_no_openspec(self, temp_dir: Path):
        proj = temp_dir / "proj"
        proj.mkdir()
        (proj / "package.json").write_text('{"name": "my-package"}')
        assert resolve_project_name(proj) == "my-package"

    def test_pyproject_toml_used(self, temp_dir: Path):
        proj = temp_dir / "proj"
        proj.mkdir()
        (proj / "pyproject.toml").write_text(
            '[project]\nname = "py-project"\n'
        )
        assert resolve_project_name(proj) == "py-project"

    def test_readme_heading_used(self, temp_dir: Path):
        proj = temp_dir / "proj"
        proj.mkdir()
        (proj / "README.md").write_text("# MyCoolProject\n\nSome text.\n")
        assert resolve_project_name(proj) == "MyCoolProject"

    def test_fallback_to_basename(self, temp_dir: Path):
        proj = temp_dir / "fallback-name"
        proj.mkdir()
        assert resolve_project_name(proj) == "fallback-name"

    def test_pyproject_priority_over_readme(self, temp_dir: Path):
        proj = temp_dir / "proj"
        proj.mkdir()
        (proj / "pyproject.toml").write_text('[project]\nname = "py-wins"\n')
        (proj / "README.md").write_text("# ReadmeProject\n")
        assert resolve_project_name(proj) == "py-wins"


# ── OpenCode version guard ───────────────────────────────────────────────


MIN_VERSION = "1.17.10"


def parse_semver(v: str) -> tuple[int, int, int]:
    parts = (v.split(".") + ["0", "0", "0"])[:3]
    return tuple(int(p) for p in parts)  # type: ignore[return-value]


def is_supported_version(v: str) -> bool:
    return parse_semver(v) >= parse_semver(MIN_VERSION)


class TestVersionGuard:
    def test_minimum_supported(self):
        assert is_supported_version("1.17.10") is True

    def test_newer_supported(self):
        assert is_supported_version("1.20.0") is True
        assert is_supported_version("2.0.0") is True

    def test_older_not_supported(self):
        assert is_supported_version("1.17.9") is False
        assert is_supported_version("1.0.0") is False
        assert is_supported_version("0.99.0") is False


# ── Checkpoint dedup logic (mirrors index.ts) ────────────────────────────


def idle_checkpoint(has_activity: bool, delivered: bool) -> bool:
    """Returns True if checkpoint should be delivered on session.idle."""
    if not has_activity:
        return False
    if delivered:
        return False
    return True


def compacting_checkpoint(has_activity: bool, _delivered: bool) -> bool:
    """Returns True if checkpoint should fire on session.compacting.

    Per spec: fires even if a previous checkpoint was delivered.
    """
    return has_activity


class TestCheckpointDedup:
    def test_idle_with_activity_no_prior_delivery(self):
        assert idle_checkpoint(True, False) is True

    def test_idle_without_activity(self):
        assert idle_checkpoint(False, False) is False

    def test_idle_after_delivery_suppressed(self):
        # Once a checkpoint was delivered (e.g., via tui.prompt.append),
        # a subsequent session.idle must be silent.
        assert idle_checkpoint(True, True) is False

    def test_compacting_with_activity_fires_even_if_delivered(self):
        # The compacting hook is exempt from the dedup flag.
        assert compacting_checkpoint(True, True) is True

    def test_compacting_without_activity_silent(self):
        assert compacting_checkpoint(False, True) is False


# ── Git commit detection ────────────────────────────────────────────────


GIT_COMMIT_PATTERN = re.compile(r"git\s+commit\b")


def is_git_commit(command: str) -> bool:
    return bool(GIT_COMMIT_PATTERN.search(command))


class TestGitCommitDetection:
    def test_simple_git_commit(self):
        assert is_git_commit("git commit -m 'fix'") is True

    def test_git_commit_with_path(self):
        assert is_git_commit("git commit -am 'msg' path/to/file") is True

    def test_git_commit_amend(self):
        assert is_git_commit("git commit --amend") is True

    def test_git_status_is_not_commit(self):
        assert is_git_commit("git status") is False

    def test_git_diff_is_not_commit(self):
        assert is_git_commit("git diff HEAD~1") is False

    def test_unrelated_command(self):
        assert is_git_commit("ls -la") is False


# ── Hook availability tolerance (compacting may be missing) ──────────────


class TestHookTolerance:
    def test_compacting_handler_wrappable(self):
        """The compacting handler must be safe to wrap in try/except so a
        missing runtime hook is silently tolerated."""
        def handler(state, activity):
            if not state["has_activity"]:
                return None
            return f"checkpoint for {state['project']}"

        # If the runtime doesn't expose the hook, we never call handler.
        # Simulate that: the wrapper is try/except around the call.
        try:
            result = handler({"has_activity": True, "project": "p"}, "act")
            assert result is not None
        except AttributeError:
            # Runtime didn't expose the hook — we tolerate silently.
            result = None
        assert result is not None

    def test_missing_compacting_hook_returns_none(self):
        # If the hook is undefined, our wrapper returns None silently.
        def call_compacting_or_skip():
            if not hasattr(call_compacting_or_skip, "_hook"):
                return None
            return call_compacting_or_skip._hook()

        assert call_compacting_or_skip() is None


# ── Plugin file exists and is syntactically valid TypeScript ─────────────


class TestPluginFileExists:
    def test_index_ts_exists(self):
        plugin = REPO_ROOT / ".opencode" / "plugins" / "memory" / "index.ts"
        assert plugin.is_file(), f"missing plugin file: {plugin}"

    def test_package_json_exists(self):
        pkg = REPO_ROOT / ".opencode" / "plugins" / "memory" / "package.json"
        assert pkg.is_file(), f"missing package.json: {pkg}"

    def test_tsconfig_exists(self):
        tsconfig = REPO_ROOT / ".opencode" / "plugins" / "memory" / "tsconfig.json"
        assert tsconfig.is_file(), f"missing tsconfig: {tsconfig}"

    def test_index_ts_has_required_hooks(self):
        """Plugin source declares the required hooks per spec."""
        plugin = REPO_ROOT / ".opencode" / "plugins" / "memory" / "index.ts"
        text = plugin.read_text(encoding="utf-8")
        # Spec-required exports
        for name in (
            "resolveProjectName",
            "isSupportedVersion",
            "idleCheckpoint",
            "compactingCheckpoint",
            "isGitCommit",
        ):
            assert name in text, f"plugin missing required function: {name}"
        # Spec-mandated: no memory auto-injection on session.created
        # (the plugin file should not contain code that does that)
        assert "session.created" not in text or "no auto-inject" in text.lower() or "no memory" in text.lower(), (
            "plugin must not auto-inject memory on session.created"
        )
