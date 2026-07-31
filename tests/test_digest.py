"""Unit tests for scripts.digest_session.

Covers openspec/specs/auto-session-digest/spec.md scenarios.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from memory_server.store import MemoryStore
from scripts.digest_session import (
    DigestResult,
    EXTRACTION_PROMPT,
    HTTPLLMClient,
    TagVocabulary,
    ensure_okf_compliance,
    extract_entries,
    load_project_aliases,
    repair_json,
    score_confidence,
    validate_entries,
)


# ── Mock LLM client ───────────────────────────────────────────────────────


class MockLLM:
    def __init__(self, response: str = "", fail: bool = False, delay: float = 0.0):
        self.response = response
        self.fail = fail
        self.delay = delay
        self.calls: list[str] = []

    def complete(self, prompt: str, *, response_format: str = "json") -> str:
        self.calls.append(prompt)
        if self.fail:
            raise RuntimeError("simulated LLM failure")
        if self.delay:
            import time as _time
            _time.sleep(self.delay)
        return self.response


# ── JSON repair ───────────────────────────────────────────────────────────


class TestRepairJson:
    def test_strips_code_fences(self):
        text = "```json\n[{\"a\": 1}]\n```"
        assert repair_json(text) == '[{"a": 1}]'

    def test_strips_code_fences_no_lang(self):
        text = "```\n[{\"a\": 1}]\n```"
        assert repair_json(text) == '[{"a": 1}]'

    def test_removes_trailing_comma_in_array(self):
        text = '[{"a": 1}, {"b": 2},]'
        assert repair_json(text) == '[{"a": 1}, {"b": 2}]'

    def test_removes_trailing_comma_in_object(self):
        text = '{"a": 1, "b": 2,}'
        assert repair_json(text) == '{"a": 1, "b": 2}'

    def test_replaces_single_quotes_when_no_double(self):
        text = "[{'entry_type': 'decision', 'content': 'Use X'}]"
        repaired = repair_json(text)
        parsed = json.loads(repaired)
        assert parsed[0]["entry_type"] == "decision"


# ── JSON validation ───────────────────────────────────────────────────────


class TestValidateEntries:
    def test_valid_array(self):
        payload = [{
            "entry_type": "decision",
            "content": "Use X for Y",
            "description": "Decision description",
            "tags": ["x"],
            "confidence": 0.9,
        }]
        result = validate_entries(payload)
        assert result is not None
        assert len(result) == 1
        assert result[0]["entry_type"] == "decision"
        assert result[0]["confidence"] == 0.9

    def test_invalid_type_rejected(self):
        payload = [{"entry_type": "unknown", "content": "x", "tags": []}]
        assert validate_entries(payload) == []

    def test_empty_content_rejected(self):
        payload = [{"entry_type": "fact", "content": "  ", "tags": []}]
        assert validate_entries(payload) == []

    def test_non_list_rejected(self):
        assert validate_entries({"entry_type": "fact"}) is None
        assert validate_entries("not a list") is None

    def test_confidence_clamped(self):
        payload = [{
            "entry_type": "fact",
            "content": "x",
            "tags": [],
            "confidence": 5.0,
        }]
        result = validate_entries(payload)
        assert result[0]["confidence"] == 1.0

    def test_invalid_confidence_defaults_to_1(self):
        payload = [{
            "entry_type": "fact",
            "content": "x",
            "tags": [],
            "confidence": "not-a-number",
        }]
        result = validate_entries(payload)
        assert result[0]["confidence"] == 1.0


# ── Tag vocabulary ────────────────────────────────────────────────────────


class TestTagVocabulary:
    def test_canonical_kept_as_is(self):
        vocab = TagVocabulary({"python", "sqlite"}, {}, {})
        normalized, unknown = vocab.normalize(["python", "sqlite"])
        assert normalized == ["python", "sqlite"]
        assert unknown == []

    def test_alias_replaced(self):
        vocab = TagVocabulary({"python"}, {"py": "python"}, {})
        normalized, unknown = vocab.normalize(["py", "Python"])
        assert "python" in normalized
        assert "py" not in normalized
        assert unknown == []

    def test_unknown_logged(self):
        vocab = TagVocabulary({"python"}, {}, {})
        normalized, unknown = vocab.normalize(["unknown-tag"])
        assert normalized == []
        assert unknown == ["unknown-tag"]


# ── Project aliases ───────────────────────────────────────────────────────


class TestProjectAliases:
    def test_load_from_file(self, temp_dir: Path):
        p = temp_dir / "aliases.json"
        p.write_text(json.dumps({"my-project": "CanonicalProject"}))
        aliases = load_project_aliases(p)
        assert aliases == {"my-project": "CanonicalProject"}

    def test_missing_file(self, temp_dir: Path):
        assert load_project_aliases(temp_dir / "missing.json") == {}


# ── Confidence scoring ───────────────────────────────────────────────────


class TestScoreConfidence:
    def test_truncated_low(self):
        assert score_confidence(
            content="x" * 100, response_time_s=1.0, transcript_truncated=True
        ) == 0.5

    def test_short_content_low(self):
        assert score_confidence(
            content="short", response_time_s=1.0, transcript_truncated=False
        ) == 0.7

    def test_fast_response_high(self):
        assert score_confidence(
            content="x" * 100, response_time_s=2.0, transcript_truncated=False
        ) == 1.0

    def test_slow_response_medium(self):
        assert score_confidence(
            content="x" * 100, response_time_s=15.0, transcript_truncated=False
        ) == 0.9


# ── OKF compliance ────────────────────────────────────────────────────────


class TestOKFCompliance:
    def test_description_derived_when_missing(self):
        entry = {"content": "Real content line", "tags": ["x"], "confidence": 1.0}
        out = ensure_okf_compliance(entry, default_confidence=0.9)
        assert out["description"] == "Real content line"

    def test_description_kept_when_provided(self):
        entry = {"content": "x", "description": "custom", "tags": [], "confidence": 1.0}
        out = ensure_okf_compliance(entry, default_confidence=0.9)
        assert out["description"] == "custom"

    def test_tags_default_to_empty(self):
        entry = {"content": "x", "description": "d"}
        out = ensure_okf_compliance(entry, default_confidence=0.9)
        assert out["tags"] == []

    def test_confidence_filled_with_default(self):
        entry = {"content": "x", "description": "d", "tags": []}
        out = ensure_okf_compliance(entry, default_confidence=0.8)
        assert out["confidence"] == 0.8


# ── Full extract pipeline ─────────────────────────────────────────────────


class TestExtractPipeline:
    @pytest.fixture
    def store(self, temp_dir: Path):
        s = MemoryStore(storage_path=temp_dir)
        s.initialize()
        return s

    def test_valid_json_upserted(self, store: MemoryStore):
        llm = MockLLM(response=json.dumps([{
            "entry_type": "decision",
            "content": "Use X for the storage layer",
            "description": "X is the storage choice",
            "tags": ["storage"],
            "confidence": 0.95,
        }]))
        result = extract_entries(
            transcript="x" * 500 + " discussion about storage choices",
            project="test-proj",
            llm=llm,
            store=store,
        )
        assert result.upserted == 1
        entries = store.search_entries(project="test-proj")
        assert len(entries) == 1
        assert entries[0]["content"].startswith("Use X")

    def test_malformed_json_repaired(self, store: MemoryStore):
        # Single quotes + trailing comma: should be repaired.
        bad = "[{'entry_type': 'fact', 'content': 'Python 3.11 is required', 'tags': [],},]"
        llm = MockLLM(response=bad)
        result = extract_entries(
            transcript="x" * 500 + " Python 3.11 fact",
            project="test-proj",
            llm=llm,
            store=store,
        )
        assert result.upserted == 1

    def test_persistent_failure_logs_and_exits_zero(self, store: MemoryStore):
        llm = MockLLM(fail=True)
        result = extract_entries(
            transcript="x" * 500 + " content",
            project="test-proj",
            llm=llm,
            store=store,
        )
        assert result.upserted == 0
        # Caller (main) exits 0 per spec.

    def test_empty_transcript_zero_writes(self, store: MemoryStore):
        llm = MockLLM()
        result = extract_entries(
            transcript="",
            project="test-proj",
            llm=llm,
            store=store,
        )
        assert result.upserted == 0
        # LLM should not have been called
        assert llm.calls == []

    def test_trivial_transcript_zero_writes(self, store: MemoryStore):
        llm = MockLLM()
        result = extract_entries(
            transcript="ok",  # too short
            project="test-proj",
            llm=llm,
            store=store,
        )
        assert result.upserted == 0
        assert llm.calls == []

    def test_no_memorable_content_zero_writes(self, store: MemoryStore):
        # LLM returns an empty array.
        llm = MockLLM(response="[]")
        result = extract_entries(
            transcript="x" * 500 + " trivial session",
            project="test-proj",
            llm=llm,
            store=store,
        )
        assert result.upserted == 0

    def test_missing_description_derived(self, store: MemoryStore):
        llm = MockLLM(response=json.dumps([{
            "entry_type": "learning",
            "content": "The MCP SDK needs aiosqlite",
            "tags": [],
        }]))
        result = extract_entries(
            transcript="x" * 500 + " learning content",
            project="test-proj",
            llm=llm,
            store=store,
        )
        assert result.upserted == 1
        # OKF file should have a description
        okf_files = list(
            (store.storage_path / "projects" / "test-proj" / "learnings").glob("*.md")
        )
        text = okf_files[0].read_text()
        assert "description: The MCP SDK needs aiosqlite" in text

    def test_tag_alias_applied(self, store: MemoryStore, temp_dir: Path):
        vocab_path = temp_dir / "tag-vocabulary.json"
        vocab_path.write_text(json.dumps({
            "canonical": ["python"],
            "aliases": {"py": "python"},
        }))
        vocab = TagVocabulary.load(vocab_path)
        llm = MockLLM(response=json.dumps([{
            "entry_type": "fact",
            "content": "Python 3.11 is the minimum",
            "tags": ["py"],
            "confidence": 1.0,
        }]))
        result = extract_entries(
            transcript="x" * 500 + " Python fact",
            project="test-proj",
            llm=llm,
            store=store,
            tag_vocab=vocab,
        )
        assert result.upserted == 1
        # Verify the stored entry has normalized tag
        entries = store.search_entries(project="test-proj", entry_type="fact")
        assert json.loads(entries[0]["tags"]) == ["python"]

    def test_project_alias_resolved(self, store: MemoryStore, temp_dir: Path):
        aliases = {"alias-name": "CanonicalProject"}
        llm = MockLLM(response=json.dumps([{
            "entry_type": "fact",
            "content": "Some fact content",
            "tags": [],
        }]))
        result = extract_entries(
            transcript="x" * 500 + " content",
            project="alias-name",
            llm=llm,
            store=store,
            project_aliases=aliases,
        )
        assert result.upserted == 1
        # Stored under canonical name
        entries = store.search_entries(project="CanonicalProject")
        assert len(entries) == 1

    def test_extraction_idempotent(self, store: MemoryStore):
        """Re-running on the same content produces no new rows."""
        llm = MockLLM(response=json.dumps([{
            "entry_type": "fact",
            "content": "Python 3.11 is the minimum",
            "tags": [],
            "confidence": 1.0,
        }]))
        kwargs = dict(
            transcript="x" * 500 + " content",
            project="test-proj",
            llm=llm,
            store=store,
        )
        first = extract_entries(**kwargs)
        second = extract_entries(**kwargs)
        assert first.upserted == 1
        assert second.upserted == 1  # upsert updates, doesn't create
        # But DB row count is 1
        rows = store.db.execute("SELECT COUNT(*) FROM entries").fetchone()
        assert rows[0] == 1


# ── HTTPLLMClient retry ──────────────────────────────────────────────────


class TestHTTPLLMClient:
    def test_full_jitter_in_range(self):
        rng = random.Random(42)
        client = HTTPLLMClient(rng=rng, sleep=lambda _s: None)
        for _ in range(50):
            d = client._full_jitter(4.0)
            assert 0.0 <= d <= 4.0

    def test_retryable_http_codes(self):
        from scripts.digest_session import RETRYABLE_HTTP
        assert 429 in RETRYABLE_HTTP
        assert 500 in RETRYABLE_HTTP
        assert 503 in RETRYABLE_HTTP
        assert 404 not in RETRYABLE_HTTP  # not transient
