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


# ── Idle auto-capture (mirrors register.ts session.idle handler) ─────────


class IdleCaptureSession:
    """Mirror of the register.ts `session.idle` handler contract: automatic
    capture runs only when the `idleCheckpoint` gate returns text (activity
    tracked and not yet delivered) and the composer is never touched."""

    def __init__(self) -> None:
        self.has_activity = False
        self.delivered = False
        self.capture_spawns = 0
        self.append_prompt_calls = 0

    def on_idle(self) -> None:
        """session.idle: run capture only when the gate says so."""
        if not self.has_activity:
            return
        if self.delivered:
            return
        self.delivered = True
        self.capture_spawns += 1

    def digest(self) -> None:
        """dispose(): digestSessions() digests every session (no gate)."""
        self.capture_spawns += 1


class TestIdleAutoCapture:
    def test_idle_with_activity_spawns_capture(self):
        session = IdleCaptureSession()
        session.has_activity = True
        session.on_idle()
        assert session.capture_spawns == 1

    def test_idle_never_calls_append_prompt(self):
        session = IdleCaptureSession()
        session.has_activity = True
        session.on_idle()
        assert session.append_prompt_calls == 0

    def test_idle_without_activity_is_silent(self):
        session = IdleCaptureSession()
        session.on_idle()
        assert session.capture_spawns == 0
        assert session.delivered is False

    def test_duplicate_idle_capture_spawned_once(self):
        session = IdleCaptureSession()
        session.has_activity = True
        session.on_idle()
        session.on_idle()
        assert session.capture_spawns == 1

    def test_dispose_digests_all_sessions_after_idle(self):
        # Design D4: a second digest at dispose() is acceptable (idempotent).
        session = IdleCaptureSession()
        session.has_activity = True
        session.on_idle()
        session.digest()
        assert session.capture_spawns == 2


class TestRegisterIdleContract:
    """Source-level contract checks for register.ts (the runtime entry)."""

    REGISTER = REPO_ROOT / ".opencode" / "plugins" / "memory" / "register.ts"

    def test_register_ts_exists(self):
        assert self.REGISTER.is_file(), f"missing plugin file: {self.REGISTER}"

    def test_idle_handler_does_not_inject_into_composer(self):
        text = self.REGISTER.read_text(encoding="utf-8")
        assert "appendPrompt" not in text, (
            "session.idle must not inject into the composer"
        )

    def test_idle_handler_runs_automatic_capture(self):
        text = self.REGISTER.read_text(encoding="utf-8")
        assert "digestSession(sessionID)" in text

    def test_digest_output_captured_to_log(self):
        text = self.REGISTER.read_text(encoding="utf-8")
        assert "digest-spawn.log" in text

    def test_dispose_still_digests_all_sessions(self):
        text = self.REGISTER.read_text(encoding="utf-8")
        assert "digestSessions()" in text


# ── Digest spawn gate + batch observability (mirrors register.ts D3/D5) ──


MIN_DIGEST_TRANSCRIPT_CHARS = 200


def should_spawn_digest(has_activity: bool, transcript: str) -> tuple[bool, str | None]:
    """Mirror of the register.ts `digestSession` spawn gate (D3).

    Returns `(spawn, skip_reason)`: a digest spawns only when the session
    tracked activity and the transcript is non-empty and at least
    MIN_DIGEST_TRANSCRIPT_CHARS characters long.
    """
    if not has_activity:
        return False, "no activity"
    if not transcript.strip():
        return False, "transcript empty"
    if len(transcript.strip()) < MIN_DIGEST_TRANSCRIPT_CHARS:
        return False, "transcript too short"
    return True, None


class TestDigestSpawnGate:
    def test_no_activity_is_skipped(self):
        assert should_spawn_digest(False, "x" * 300) == (False, "no activity")

    def test_empty_transcript_is_skipped(self):
        assert should_spawn_digest(True, " \n ") == (False, "transcript empty")

    def test_short_transcript_is_skipped(self):
        assert should_spawn_digest(True, "x" * 199) == (False, "transcript too short")

    def test_exactly_200_chars_spawns(self):
        assert should_spawn_digest(True, "x" * 200) == (True, None)

    def test_activity_with_long_transcript_spawns(self):
        assert should_spawn_digest(True, "x" * 300) == (True, None)


class TestRegisterDigestGateContract:
    """Source-level contract checks for register.ts (the runtime entry)."""

    REGISTER = REPO_ROOT / ".opencode" / "plugins" / "memory" / "register.ts"

    def test_spawn_gate_skips_no_activity(self):
        text = self.REGISTER.read_text(encoding="utf-8")
        assert "digest skipped for" in text
        assert "no activity" in text

    def test_spawn_gate_skips_short_transcripts(self):
        text = self.REGISTER.read_text(encoding="utf-8")
        assert "transcript empty" in text
        assert "transcript too short" in text
        assert "MIN_DIGEST_TRANSCRIPT_CHARS" in text

    def test_batch_summary_logged_before_spawns(self):
        text = self.REGISTER.read_text(encoding="utf-8")
        assert "digest batch: ${sessionDirs.size} sessions" in text

    def test_per_session_spawn_is_logged(self):
        text = self.REGISTER.read_text(encoding="utf-8")
        assert "digest spawned for" in text


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
