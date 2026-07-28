"""Tests for scripts.okf_validate."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from scripts.okf_validate import (
    OKF_TYPES,
    Report,
    _parse_value,
    parse_frontmatter,
    validate_file,
    walk,
)


def _write(tmp: Path, name: str, body: str) -> Path:
    path = tmp / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(body).lstrip("\n"), encoding="utf-8")
    return path


VALID_FM = """\
---
type: Decision
title: Use SQLite for memory storage
description: SQLite WAL + FTS5 gives us a derived search index over Markdown.
tags: [architecture, storage]
timestamp: 2026-07-28T00:00:00Z
---

Body.
"""


class TestParseFrontmatter:
    def test_parses_standard_block(self):
        fm, err = parse_frontmatter(VALID_FM)
        assert err is None
        assert fm["type"] == "Decision"
        assert fm["title"] == "Use SQLite for memory storage"
        assert fm["tags"] == ["architecture", "storage"]

    def test_missing_frontmatter(self):
        fm, err = parse_frontmatter("just a body, no frontmatter")
        assert fm is None
        assert "no frontmatter block" in err

    def test_unterminated_frontmatter(self):
        fm, err = parse_frontmatter("---\ntype: Decision\n")
        assert fm is None
        assert "unterminated" in err

    def test_handles_empty_array(self):
        fm, err = parse_frontmatter("---\ntags: []\n---\n")
        assert err is None
        assert fm["tags"] == []

    def test_handles_quoted_strings(self):
        fm, err = parse_frontmatter(
            '---\ntitle: "Hello, world"\n---\n'
        )
        assert err is None
        assert fm["title"] == "Hello, world"


class TestParseValue:
    def test_int(self):
        assert _parse_value("42") == 42

    def test_float(self):
        assert _parse_value("0.5") == 0.5

    def test_inline_array(self):
        assert _parse_value("[a, b, c]") == ["a", "b", "c"]

    def test_quoted(self):
        assert _parse_value('"x"') == "x"

    def test_empty(self):
        assert _parse_value("") == ""


class TestValidateFile:
    def test_valid_file_passes(self, tmp_path: Path):
        path = _write(tmp_path, "decision.md", VALID_FM)
        issues = validate_file(path)
        assert issues == []

    def test_missing_description_flagged(self, tmp_path: Path):
        body = """\
---
type: Fact
title: A fact
tags: [misc]
timestamp: 2026-07-28T00:00:00Z
---

Body.
"""
        path = _write(tmp_path, "fact.md", body)
        issues = validate_file(path)
        assert any(i.field == "description" for i in issues)

    def test_unknown_type_flagged(self, tmp_path: Path):
        body = """\
---
type: Mystery
title: An unknown type
description: d
tags: []
timestamp: 2026-07-28T00:00:00Z
---

Body.
"""
        path = _write(tmp_path, "x.md", body)
        issues = validate_file(path)
        assert any(i.field == "type" for i in issues)

    def test_x_prefixed_type_allowed(self, tmp_path: Path):
        body = """\
---
type: x-CustomKind
title: Custom
description: d
tags: []
timestamp: 2026-07-28T00:00:00Z
---

Body.
"""
        path = _write(tmp_path, "x.md", body)
        issues = validate_file(path)
        assert all(i.field != "type" for i in issues)

    def test_custom_fields_preserved(self, tmp_path: Path):
        body = """\
---
type: Decision
title: Decision
description: d
tags: []
timestamp: 2026-07-28T00:00:00Z
project: SecondBrain
confidence: 0.9
openspec_change_id: my-change
---

Body.
"""
        path = _write(tmp_path, "d.md", body)
        issues = validate_file(path)
        assert issues == []


class TestWalk:
    def test_walks_recursively(self, tmp_path: Path):
        _write(tmp_path, "memory/a.md", VALID_FM)
        _write(tmp_path, "memory/sub/b.md", VALID_FM)
        _write(tmp_path, "memory/sub/.hidden/c.md", VALID_FM)
        report = walk(tmp_path / "memory")
        assert report.files_checked == 2
        assert report.ok
        assert "sub" in report.by_directory

    def test_aggregates_issues(self, tmp_path: Path):
        bad = """\
---
type: Fact
title: no description
tags: []
timestamp: 2026-07-28T00:00:00Z
---

Body.
"""
        _write(tmp_path, "memory/a.md", VALID_FM)
        _write(tmp_path, "memory/b.md", bad)
        report = walk(tmp_path / "memory")
        assert report.files_checked == 2
        assert not report.ok
        assert any(i.field == "description" for i in report.issues)
