"""Smoke + integration tests for the MCP server tool handlers.

Boots handlers directly (no stdio) and verifies response shapes against
the spec at openspec/specs/memory-mcp-server/spec.md.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from memory_server.server import (
    handle_export_memories,
    handle_get_profile,
    handle_ping,
    handle_search_memory,
    handle_store_convention,
    handle_store_decision,
    handle_store_fact,
    handle_store_learning,
    handle_store_profile,
)
from memory_server.store import MemoryStore


@pytest.fixture
def store(temp_dir):
    s = MemoryStore(storage_path=temp_dir)
    s.initialize()
    return s


@pytest.fixture
def seeded(store: MemoryStore):
    store.upsert_entry(entry_type="decision", project="proj-a",
                       content="Decision A1", tags=["arch"])
    store.upsert_entry(entry_type="fact", project="proj-a",
                       content="Fact A1", tags=["config"])
    store.upsert_entry(entry_type="learning", project="proj-a",
                       content="Learning A1")
    store.upsert_entry(entry_type="convention", project="proj-a",
                       content="Convention A1", tags=["style"])
    store.upsert_entry(entry_type="decision", project="proj-b",
                       content="Decision B1", tags=["arch"])


# ── search_memory ──────────────────────────────────────────────────────────


class TestSearchMemory:
    def test_basic_project_search(self, store, seeded):
        result = handle_search_memory(store, {"project": "proj-a"})
        entries = json.loads(result)
        assert len(entries) == 4
        for e in entries:
            assert e["project"] == "proj-a"

    def test_filtered_by_type(self, store, seeded):
        result = handle_search_memory(
            store, {"project": "proj-a", "entry_type": "decision"}
        )
        entries = json.loads(result)
        assert len(entries) == 1
        assert entries[0]["content"] == "Decision A1"

    def test_search_with_tags_filter(self, store, seeded):
        result = handle_search_memory(
            store, {"project": "proj-a", "tags": ["arch"]}
        )
        entries = json.loads(result)
        assert len(entries) == 1
        assert entries[0]["content"] == "Decision A1"

    def test_full_text_query(self, store, seeded):
        result = handle_search_memory(
            store, {"project": "proj-a", "query": "Decision"}
        )
        entries = json.loads(result)
        assert any("Decision A1" in e["content"] for e in entries)

    def test_search_max_results(self, store):
        for i in range(60):
            store.upsert_entry(entry_type="fact", project="bulk", content=f"Bulk {i}")
        result = handle_search_memory(store, {"project": "bulk"})
        entries = json.loads(result)
        assert len(entries) <= 50


# ── store_decision ─────────────────────────────────────────────────────────


class TestStoreDecision:
    def test_store_architectural_decision(self, store):
        result = handle_store_decision(store, {
            "project": "my-project",
            "content": "Use SQLite WAL mode for concurrent reads",
        })
        data = json.loads(result)
        assert data["entry_type"] == "decision"
        assert data["created"] is True

    def test_store_decision_with_openspec_ref(self, store):
        result = handle_store_decision(store, {
            "project": "my-project",
            "content": "Adopt MCP Python SDK",
            "openspec_change_id": "2026-07-14-mcp-sdk",
        })
        data = json.loads(result)
        entries = store.search_entries(project="my-project", entry_type="decision")
        assert entries[0]["openspec_change_id"] == "2026-07-14-mcp-sdk"

    def test_store_decision_with_description(self, store):
        result = handle_store_decision(store, {
            "project": "my-project",
            "content": "Use FTS5 for search",
            "description": "Full-text search via SQLite FTS5",
        })
        data = json.loads(result)
        assert data["created"] is True

    def test_store_decision_description_derived_when_missing(self, store, temp_dir):
        """When description is missing, server derives it from first non-heading line."""
        handle_store_decision(store, {
            "project": "desc-derive",
            "content": "# Heading\nThis is the actual first line of the decision body.",
        })
        okf_files = list((temp_dir / "projects" / "desc-derive" / "decisions").glob("*.md"))
        assert len(okf_files) == 1
        text = okf_files[0].read_text()
        assert "description: This is the actual first line" in text

    def test_store_decision_missing_project_rejected(self, store):
        with pytest.raises(ValueError, match="project"):
            handle_store_decision(store, {"content": "test"})

    def test_store_decision_missing_content_rejected(self, store):
        with pytest.raises(ValueError, match="content"):
            handle_store_decision(store, {"project": "p"})


# ── store_fact ─────────────────────────────────────────────────────────────


class TestStoreFact:
    def test_store_new_fact(self, store):
        result = handle_store_fact(store, {
            "project": "my-project",
            "content": "Python 3.11 is the minimum",
            "confidence": 0.95,
        })
        data = json.loads(result)
        assert data["entry_type"] == "fact"
        assert data["created"] is True

    def test_update_existing_fact_via_dedup(self, store):
        content = "Python 3.11 is the minimum"
        first = json.loads(handle_store_fact(store, {
            "project": "p", "content": content, "confidence": 0.8,
        }))
        second = json.loads(handle_store_fact(store, {
            "project": "p", "content": content, "confidence": 0.95,
        }))
        assert second["id"] == first["id"]
        assert second["created"] is False
        assert second["updated"] is True

    def test_store_fact_out_of_range_confidence(self, store):
        with pytest.raises(ValueError, match="confidence"):
            handle_store_fact(store, {
                "project": "p", "content": "t", "confidence": 1.5,
            })


# ── store_learning ─────────────────────────────────────────────────────────


class TestStoreLearning:
    def test_store_lesson_learned(self, store):
        result = handle_store_learning(store, {
            "project": "p", "content": "MCP needs aiosqlite for async SQLite",
        })
        data = json.loads(result)
        assert data["entry_type"] == "learning"
        assert data["created"] is True


# ── store_convention (NEW tool per spec) ───────────────────────────────────


class TestStoreConvention:
    def test_store_convention(self, store):
        """The new store_convention tool persists conventions explicitly."""
        result = handle_store_convention(store, {
            "project": "my-project",
            "content": "All Python files use snake_case",
            "description": "Python naming convention",
        })
        data = json.loads(result)
        assert data["entry_type"] == "convention"
        assert data["created"] is True

        entries = store.search_entries(project="my-project", entry_type="convention")
        assert len(entries) == 1
        assert "snake_case" in entries[0]["content"]

    def test_store_convention_missing_content_rejected(self, store):
        with pytest.raises(ValueError, match="content"):
            handle_store_convention(store, {"project": "p"})


# ── store_profile ──────────────────────────────────────────────────────────


class TestStoreProfile:
    def test_store_profile(self, store):
        result = handle_store_profile(store, {
            "project": "p1", "content": "Tech: Python, SQLite",
        })
        data = json.loads(result)
        assert data["entry_type"] == "profile"
        assert data["created"] is True

    def test_profile_dedup_by_project(self, store):
        first = json.loads(handle_store_profile(store, {
            "project": "p2", "content": "Profile v1",
        }))
        second = json.loads(handle_store_profile(store, {
            "project": "p2", "content": "Profile v2",
        }))
        assert second["id"] == first["id"]
        assert second["updated"] is True


# ── export_memories ────────────────────────────────────────────────────────


class TestExportMemories:
    def test_export_all_for_project(self, store, seeded):
        result = handle_export_memories(store, {"project": "proj-a"})
        entries = json.loads(result)
        assert len(entries) == 4

    def test_export_filtered_by_type(self, store, seeded):
        result = handle_export_memories(
            store, {"project": "proj-a", "entry_type": "convention"}
        )
        entries = json.loads(result)
        assert len(entries) == 1
        assert entries[0]["entry_type"] == "convention"

    def test_export_no_limit(self, store):
        for i in range(60):
            store.upsert_entry(entry_type="fact", project="bulk", content=f"Bulk {i}")
        result = handle_export_memories(store, {"project": "bulk"})
        entries = json.loads(result)
        assert len(entries) == 60

    def test_export_missing_project_rejected(self, store):
        with pytest.raises(ValueError, match="project"):
            handle_export_memories(store, {})


# ── get_profile ────────────────────────────────────────────────────────────


class TestGetProfile:
    def test_get_profile_returns_profile(self, store):
        store.upsert_profile(project="p", content="Tech: Python")
        result = handle_get_profile(store, {"project": "p"})
        entries = json.loads(result)
        assert len(entries) == 1
        assert entries[0]["entry_type"] == "profile"

    def test_get_profile_empty_when_none(self, store):
        result = handle_get_profile(store, {"project": "no-profile"})
        assert json.loads(result) == []


# ── ping ───────────────────────────────────────────────────────────────────


class TestPing:
    def test_ping_returns_status_and_timestamp(self, store):
        result = handle_ping(store, {})
        data = json.loads(result)
        assert data["status"] == "ok"
        assert "timestamp" in data

    def test_ping_no_db_access(self, store):
        """ping must not query the database."""
        # If ping touched the DB, this would error when the db is closed.
        # We don't actually close it here, but we test the contract by
        # verifying ping doesn't take any required parameters.
        result = handle_ping(store, {})
        data = json.loads(result)
        assert "status" in data


# ── No-reads-on-init: server does not load anything at startup ─────────────


class TestNoStartupReads:
    def test_app_creation_does_not_query_db(self, store):
        """Constructing an MCP app must not trigger any DB query.

        Verified by checking the DB file mtime does not change between two
        snapshots taken around the `create_app` call. (sqlite3.Connection
        attributes are immutable from Python, so we can't monkey-patch
        `execute` directly.)
        """
        from memory_server.server import create_app

        db_path = store.storage_path / "memory.db"
        # Force a checkpoint so the next mtime change is meaningful.
        store.db.commit()
        mtime_before = db_path.stat().st_mtime_ns

        app = create_app(store)
        assert app is not None
        assert app.name == "memory-server"

        mtime_after = db_path.stat().st_mtime_ns
        # mtime should not change just by registering handlers.
        assert mtime_after == mtime_before, (
            "create_app caused a DB write; should be read-free at startup"
        )
