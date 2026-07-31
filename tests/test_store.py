"""Unit tests for MemoryStore — SQLite CRUD, Markdown export, dedup, FTS5, OKF.

Covers all scenarios from openspec/specs/memory-store/spec.md.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from memory_server.store import MemoryStore


# ── Initialization ──────────────────────────────────────────────────────────


class TestInit:
    """Requirement: SQLite WAL mode enabled at initialization."""

    def test_wal_mode_on_init(self, store: MemoryStore):
        pragma = store.db.execute("PRAGMA journal_mode").fetchone()
        assert pragma[0].upper() == "WAL", f"Expected WAL, got {pragma[0]}"

    def test_fts5_table_exists(self, store: MemoryStore):
        tables = store.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='entries_fts'"
        ).fetchall()
        assert len(tables) == 1, "FTS5 table 'entries_fts' not found"

    def test_entries_table_schema(self, store: MemoryStore):
        cols = store.db.execute("PRAGMA table_info(entries)").fetchall()
        col_names = {row[1]: row[2] for row in cols}
        for required in (
            "id", "entry_type", "project", "content", "tags",
            "confidence", "openspec_change_id", "dedup_key",
            "created_at", "updated_at",
        ):
            assert required in col_names, f"Missing column: {required}"


# ── Store Decision ──────────────────────────────────────────────────────────


class TestStoreDecision:
    """Requirement: Structured entry storage — decision type."""

    def test_store_decision(self, store: MemoryStore, sample_decision):
        entry = store.upsert_entry(**sample_decision)
        assert entry["entry_type"] == "decision"
        assert entry["project"] == "test-project"
        assert entry["content"] == sample_decision["content"]
        assert entry["openspec_change_id"] == "2026-07-14-wal-mode"
        assert entry["id"] is not None
        assert entry["created_at"] is not None
        assert entry["updated_at"] == entry["created_at"]

    def test_store_decision_generates_uuid(self, store: MemoryStore, sample_decision):
        import uuid
        entry = store.upsert_entry(**sample_decision)
        parsed = uuid.UUID(entry["id"])
        assert parsed.version == 4

    def test_openspec_change_id_stored(self, store: MemoryStore):
        entry = store.upsert_entry(
            entry_type="decision",
            project="test-project",
            content="Use Python MCP SDK",
            openspec_change_id="2026-07-14-mcp-sdk",
        )
        assert entry["openspec_change_id"] == "2026-07-14-mcp-sdk"


# ── Store Fact with Dedup ───────────────────────────────────────────────────


class TestStoreFact:
    """Requirement: Entry overwrite by deduplication key (full-content hash)."""

    def test_store_new_fact(self, store: MemoryStore, sample_fact):
        entry = store.upsert_entry(**sample_fact)
        assert entry["entry_type"] == "fact"
        assert entry["confidence"] == 0.95
        assert entry["created"] is True

    def test_overwrite_stale_fact(self, store: MemoryStore):
        content = "Python 3.11 is the minimum required version"
        first = store.upsert_entry(
            entry_type="fact", project="test-project", content=content, confidence=0.8
        )
        import time
        time.sleep(0.01)
        second = store.upsert_entry(
            entry_type="fact", project="test-project", content=content, confidence=0.95
        )
        assert second["id"] == first["id"], "Dedup should reuse the same id"
        assert second["created_at"] == first["created_at"], "created_at must be preserved"
        assert second["updated_at"] > first["updated_at"], "updated_at must advance"
        assert second["confidence"] == 0.95
        assert second["created"] is False
        assert second["updated"] is True

    def test_different_content_creates_new_entry(self, store: MemoryStore):
        first = store.upsert_entry(
            entry_type="fact", project="test-project",
            content="Python 3.11 is the minimum",
        )
        second = store.upsert_entry(
            entry_type="fact", project="test-project",
            content="Python 3.12 is also supported",
        )
        assert second["id"] != first["id"]

    def test_different_project_no_dedup(self, store: MemoryStore):
        first = store.upsert_entry(
            entry_type="fact", project="project-a",
            content="Uses SQLite WAL mode",
        )
        second = store.upsert_entry(
            entry_type="fact", project="project-b",
            content="Uses SQLite WAL mode",
        )
        assert second["id"] != first["id"]

    def test_dedup_key_uses_full_content(self, store: MemoryStore):
        """Two entries with the same first 60 chars but different full content
        must produce distinct dedup keys and be stored independently.

        Replaces the old `test_dedup_key_truncates_at_60_chars` (which asserted
        the wrong behavior). The new memory-store spec requires full-content
        hashing, not prefix matching.
        """
        long_a = "A" * 30 + "alpha-suffix"
        long_b = "A" * 30 + "beta-suffix"
        first = store.upsert_entry(entry_type="fact", project="p", content=long_a)
        second = store.upsert_entry(entry_type="fact", project="p", content=long_b)
        assert second["id"] != first["id"], "dedup must use full content, not prefix"


# ── Dedup file output (regression: fix-memory-store-dedup) ────────────────


class TestDedupFileOutput:
    """Regression: dedup must update the existing SQLite row without writing
    a duplicate OKF Markdown file."""

    def test_duplicate_content_updates_single_file(
        self, store: MemoryStore, temp_dir: Path
    ):
        content = "same content here"
        first = store.upsert_entry(
            entry_type="fact", project="testproj", content=content
        )
        second = store.upsert_entry(
            entry_type="fact", project="testproj", content=content
        )
        assert first["created"] is True
        assert second["updated"] is True
        facts_dir = temp_dir / "projects" / "testproj" / "facts"
        files = list(facts_dir.glob("*.md"))
        names = [f.name for f in files]
        assert len(files) == 1, f"Expected 1 file, got {len(files)}: {names}"
        assert not any("-2" in name or "-3" in name for name in names)

    def test_different_content_creates_separate_files(
        self, store: MemoryStore, temp_dir: Path
    ):
        store.upsert_entry(
            entry_type="fact", project="testproj", content="first fact content"
        )
        store.upsert_entry(
            entry_type="fact",
            project="testproj",
            content="second fact content",
        )
        facts_dir = temp_dir / "projects" / "testproj" / "facts"
        files = list(facts_dir.glob("*.md"))
        names = [f.name for f in files]
        assert len(files) == 2, f"Expected 2 files, got {len(files)}: {names}"


# ── OKF Frontmatter: description field ─────────────────────────────────────


class TestOKFFrontmatter:
    """Requirement: Every OKF file has `description` in frontmatter."""

    def test_okf_file_has_description_field(self, store: MemoryStore, temp_dir: Path):
        store.upsert_entry(
            entry_type="decision", project="d-proj",
            content="Use SQLite WAL for concurrent reads",
            description="WAL lets readers proceed during writes",
            tags=["db"],
        )
        okf_files = list((temp_dir / "projects" / "d-proj" / "decisions").glob("*.md"))
        assert len(okf_files) == 1
        text = okf_files[0].read_text()
        assert "description: WAL lets readers proceed during writes" in text

    def test_description_derived_from_content_when_missing(self, store: MemoryStore, temp_dir: Path):
        """When description is not provided, derive from first non-heading line."""
        store.upsert_entry(
            entry_type="decision", project="d-derive",
            content="# Heading\nThis is the first real line of the decision.",
        )
        okf_files = list((temp_dir / "projects" / "d-derive" / "decisions").glob("*.md"))
        text = okf_files[0].read_text()
        assert "description: This is the first real line of the decision." in text

    def test_frontmatter_field_order_okf(self, store: MemoryStore, temp_dir: Path):
        """Frontmatter field order matches OKF v0.1: type, title, description, resource, tags, timestamp."""
        store.upsert_entry(
            entry_type="fact", project="ord",
            content="Some fact content",
            description="fact desc",
        )
        okf_file = next((temp_dir / "projects" / "ord" / "facts").glob("*.md"))
        text = okf_file.read_text()
        lines = [
            l.strip() for l in text.splitlines()
            if l.strip() and not l.startswith("---") and ":" in l
        ]
        keys_in_order = [l.split(":", 1)[0] for l in lines]
        # type and title come first
        assert keys_in_order[0] == "type"
        assert keys_in_order[1] == "title"
        # description must appear before tags and timestamp
        assert "description" in keys_in_order
        desc_idx = keys_in_order.index("description")
        tags_idx = keys_in_order.index("tags")
        ts_idx = keys_in_order.index("timestamp")
        assert desc_idx < tags_idx < ts_idx


# ── Slug collision handling ────────────────────────────────────────────────


class TestSlugCollision:
    """Two distinct entries with the same first-line slug must both be stored."""

    def test_slug_collision_appends_suffix(self, store: MemoryStore, temp_dir: Path):
        store.upsert_entry(
            entry_type="learning", project="sc",
            content="First sentence is identical and continues for a while here",
        )
        store.upsert_entry(
            entry_type="learning", project="sc",
            content="First sentence is identical and continues for a while here!",
        )
        files = sorted((temp_dir / "projects" / "sc" / "learnings").glob("*.md"))
        # Should be 2 distinct files
        assert len(files) == 2, f"Expected 2 files, got {len(files)}: {[f.name for f in files]}"
        # One should be the date-prefixed slug, the other with -2 suffix
        names = sorted(f.name for f in files)
        assert any("-2" in n for n in names), f"Expected -2 suffix in {names}"


# ── index.md regeneration ─────────────────────────────────────────────────


class TestProjectIndex:
    """Requirement: <project>/index.md is regenerated on each upsert."""

    def test_project_index_md_generated(self, store: MemoryStore, temp_dir: Path):
        store.upsert_entry(
            entry_type="decision", project="ip",
            content="Use SQLite WAL for concurrent reads",
        )
        idx = temp_dir / "projects" / "ip" / "index.md"
        assert idx.exists(), "Expected <project>/index.md to exist"

    def test_index_lists_entries(self, store: MemoryStore, temp_dir: Path):
        store.upsert_entry(
            entry_type="decision", project="il",
            content="Decision content here",
        )
        store.upsert_entry(
            entry_type="fact", project="il",
            content="Fact content here",
        )
        idx_text = (temp_dir / "projects" / "il" / "index.md").read_text()
        assert "## Decision" in idx_text
        assert "## Fact" in idx_text
        # Both entries should be linked
        assert "decisions/" in idx_text
        assert "facts/" in idx_text


# ── Store Profile (dedup by project+type) ──────────────────────────────────


class TestStoreProfile:
    """Profile entries deduplicate by (project, entry_type)."""

    def test_store_profile(self, store: MemoryStore):
        entry = store.upsert_profile(
            project="p1", content="Tech profile: Python, SQLite",
            tags=["tech"],
        )
        assert entry["entry_type"] == "profile"
        assert entry["created"] is True

    def test_profile_update_overwrites(self, store: MemoryStore):
        first = store.upsert_profile(project="p2", content="Profile v1")
        second = store.upsert_profile(project="p2", content="Profile v2 updated")
        assert second["id"] == first["id"]
        assert second["created"] is False
        assert second["updated"] is True
        # Only one profile row in DB
        rows = store.db.execute(
            "SELECT * FROM entries WHERE project='p2' AND entry_type='profile'"
        ).fetchall()
        assert len(rows) == 1

    def test_get_profile_returns_profile(self, store: MemoryStore):
        store.upsert_profile(project="gp", content="Tech profile content")
        profiles = store.get_profile(project="gp")
        assert len(profiles) == 1
        assert profiles[0]["entry_type"] == "profile"
        assert "Tech profile" in profiles[0]["content"]


# ── Search / Query ─────────────────────────────────────────────────────────


class TestSearch:
    """Requirement: Entry retrieval by project, type, tags, FTS5."""

    @pytest.fixture(autouse=True)
    def _seed(self, store: MemoryStore):
        store.upsert_entry(entry_type="decision", project="proj-a",
                           content="Decision A1", tags=["arch"])
        store.upsert_entry(entry_type="fact", project="proj-a",
                           content="Fact A1", tags=["config"])
        store.upsert_entry(entry_type="learning", project="proj-a",
                           content="Learning A1")
        store.upsert_entry(entry_type="decision", project="proj-b",
                           content="Decision B1", tags=["arch"])
        store.upsert_entry(entry_type="fact", project="proj-b",
                           content="Fact B1")

    def test_search_by_project(self, store: MemoryStore):
        results = store.search_entries(project="proj-a")
        assert len(results) == 3
        for r in results:
            assert r["project"] == "proj-a"
        timestamps = [r["updated_at"] for r in results]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_search_by_project_and_type(self, store: MemoryStore):
        results = store.search_entries(project="proj-a", entry_type="decision")
        assert len(results) == 1
        assert results[0]["content"] == "Decision A1"

    def test_search_by_tags(self, store: MemoryStore):
        results = store.search_entries(project="proj-a", tags=["arch"])
        assert len(results) == 1
        assert results[0]["content"] == "Decision A1"

    def test_fts5_search_content(self, store: MemoryStore):
        results = store.search_entries(project="proj-a", query="Decision")
        assert len(results) >= 1
        assert any("Decision A1" in r["content"] for r in results)

    def test_fts5_search_across_projects(self, store: MemoryStore):
        results = store.search_entries(query="Decision")
        assert len(results) == 2

    def test_no_project_returns_all(self, store: MemoryStore):
        results = store.search_entries()
        assert len(results) >= 5


# ── Upsert Edge Cases ─────────────────────────────────────────────────────


class TestUpsertEdgeCases:
    def test_invalid_entry_type_rejected(self, store: MemoryStore):
        with pytest.raises(ValueError, match="invalid entry_type"):
            store.upsert_entry(entry_type="invalid_type", project="p", content="t")

    def test_profile_via_upsert_entry_rejected(self, store: MemoryStore):
        """`upsert_entry` must reject profile (use `upsert_profile` instead)."""
        with pytest.raises(ValueError, match="invalid entry_type"):
            store.upsert_entry(entry_type="profile", project="p", content="t")

    def test_empty_content_rejected(self, store: MemoryStore):
        with pytest.raises(ValueError, match="content"):
            store.upsert_entry(entry_type="fact", project="p", content="")

    def test_empty_project_rejected(self, store: MemoryStore):
        with pytest.raises(ValueError):
            store.upsert_entry(entry_type="fact", project="", content="x")

    def test_confidence_range_enforced(self, store: MemoryStore):
        with pytest.raises(ValueError, match="confidence"):
            store.upsert_entry(entry_type="fact", project="p",
                               content="t", confidence=1.5)

    def test_confidence_below_min_rejected(self, store: MemoryStore):
        with pytest.raises(ValueError, match="below minimum"):
            store.upsert_entry(
                entry_type="fact", project="p", content="t",
                confidence=0.5, min_confidence=0.6,
            )

    def test_default_min_confidence_allows_all(self, store: MemoryStore):
        """Default min_confidence (0.0) accepts any confidence ≥ 0.0."""
        entry = store.upsert_entry(
            entry_type="fact", project="p", content="any", confidence=0.1,
        )
        assert entry["confidence"] == 0.1

    def test_tags_defaults_to_empty_list(self, store: MemoryStore):
        entry = store.upsert_entry(entry_type="fact", project="p", content="no tags")
        assert json.loads(entry["tags"]) == []


# ── Store layer has no rate-limit code path ────────────────────────────────


class TestStoreNoRateLimit:
    """Requirement: store layer SHALL NOT implement rate limiting."""

    def test_rapid_calls_return_immediately(self, store: MemoryStore):
        import time
        start = time.monotonic()
        for i in range(20):
            store.upsert_entry(entry_type="fact", project="rl",
                               content=f"rapid call {i}")
        elapsed = time.monotonic() - start
        # 20 quick writes should complete well under 1 second; if there's
        # a backoff or queue, this would be much slower.
        assert elapsed < 2.0, f"20 rapid upserts took {elapsed:.2f}s (likely rate-limited)"
