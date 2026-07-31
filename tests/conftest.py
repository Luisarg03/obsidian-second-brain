"""Shared fixtures for memory store and MCP server tests."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from memory_server.store import MemoryStore


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test storage."""
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


@pytest.fixture
def store(temp_dir):
    """Create a MemoryStore backed by a temp directory, with WAL + FTS5 init."""
    s = MemoryStore(storage_path=temp_dir)
    s.initialize()
    return s


@pytest.fixture
def sample_decision():
    return {
        "entry_type": "decision",
        "project": "test-project",
        "content": "Use SQLite WAL mode for concurrent reads",
        "tags": ["database", "performance"],
        "openspec_change_id": "2026-07-14-wal-mode",
    }


@pytest.fixture
def sample_fact():
    return {
        "entry_type": "fact",
        "project": "test-project",
        "content": "Python 3.11 is the minimum required version",
        "tags": ["python", "requirements"],
        "confidence": 0.95,
    }


@pytest.fixture
def sample_learning():
    return {
        "entry_type": "learning",
        "project": "test-project",
        "content": "MCP Python SDK requires aiosqlite for async SQLite access",
        "tags": ["mcp", "sqlite"],
    }


@pytest.fixture
def sample_convention():
    return {
        "entry_type": "convention",
        "project": "test-project",
        "content": "All memory entries use ISO 8601 for timestamps",
        "tags": ["convention", "formatting"],
    }
