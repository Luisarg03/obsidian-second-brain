"""Post-session LLM extraction: session transcript -> OKF entries.

Implements openspec/specs/auto-session-digest/spec.md. Extracts decisions,
facts, and learnings from a session transcript using a structured LLM call,
validates the response against a JSON schema, repairs common JSON formatting
issues, applies tag-vocabulary normalization, scores confidence, and upserts
each entry to the memory store.

Usage:
    digest-session --transcript PATH --project NAME
    digest-session --transcript PATH --project NAME --memory-path PATH
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any, Callable, Protocol, TextIO

from memory_server.store import MemoryStore, _first_non_heading_line

try:
    import fcntl
except ImportError:
    fcntl = None  # Non-POSIX: the digest lock becomes a no-op

log = logging.getLogger("digest_session")

# Retry policy: max attempts and base delays per attempt index (5s, 10s, 20s).
RETRY_MAX_ATTEMPTS = 3
RETRY_BASE_DELAYS_S = (5.0, 10.0, 20.0)
RETRYABLE_HTTP = (429, 500, 502, 503, 504)

# JSON schema for the LLM response. Validated before any upsert.
EXTRACTION_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "required": ["entry_type", "content", "tags"],
        "properties": {
            "entry_type": {
                "type": "string",
                "enum": ["decision", "fact", "learning"],
            },
            "content": {"type": "string", "minLength": 1},
            "description": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "openspec_change_id": {"type": "string"},
        },
        "additionalProperties": False,
    },
}

EXTRACTION_PROMPT = """\
You are an assistant that extracts durable knowledge from a session transcript.

For the transcript below, identify:
- **Decisions**: architectural or design choices that were made.
- **Facts**: stable, verifiable statements about the project (versions, conventions, constraints).
- **Learnings**: non-obvious lessons, debugging insights, or solutions found.

Return a JSON array. Each element must have exactly:
  - "entry_type": one of "decision" | "fact" | "learning"
  - "content": a single-paragraph statement (no headings, no lists)
  - "description": a one-sentence summary of `content` (queryable)
  - "tags": an array of lowercase-kebab tags
  - "confidence": a number 0.0-1.0
  - "openspec_change_id": (optional) the OpenSpec change name (slug like "fix-memory-store-dedup") if the transcript mentions which change is being worked on

Rules:
- Skip trivial exchanges (greetings, "ok", "thanks", or anything with no project knowledge).
- Prefer fewer, higher-signal entries over many weak ones.
- Do not include anything not present in the transcript.

Transcript:
---
{transcript}
---

Return only the JSON array. No prose, no markdown fences.
"""


# ── JSON repair ───────────────────────────────────────────────────────────


def _convert_single_quotes(text: str) -> str:
    """Convert single-quoted strings to double-quoted strings.

    State-machine scanner: toggles in/out of a string on ``'`` outside a
    string, emits ``"`` for delimiters, and treats ``\\'`` inside a string as
    an escaped quote (emitted as a plain ``'``, since JSON does not need to
    escape it). Newlines inside strings are preserved; other escape sequences
    are copied verbatim.
    """
    out: list[str] = []
    in_string = False
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if in_string and ch == "\\":
            if i + 1 < n and text[i + 1] == "'":
                out.append("'")
                i += 2
            else:
                out.append(ch)
                if i + 1 < n:
                    out.append(text[i + 1])
                    i += 2
                else:
                    i += 1
            continue
        if ch == "'":
            in_string = not in_string
            out.append('"')
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def repair_json(text: str) -> str:
    """Best-effort repair of common LLM JSON output issues.

    Tries progressively more aggressive repairs and returns the first string
    that ``json.loads()`` accepts:

    1. Raw text, unchanged (after stripping surrounding whitespace).
    2. Code fences (`````json```` / ````` `````) stripped.
    3. Trailing commas before ``]`` or ``}`` removed.
    4. Single-quoted strings converted to double-quoted strings — only when
       the document contains no double quotes at all. Single quotes inside a
       double-quoted document are string content and are never altered.

    If no repair parses, returns the last transformed string.
    """
    s = text.strip()
    candidates = [s]

    # Strip code fences
    fenced = re.sub(r"^```(?:json)?\s*", "", s)
    fenced = re.sub(r"\s*```$", "", fenced).strip()
    candidates.append(fenced)

    # Trailing commas: `,]` or `,}` -> `]` / `}`
    no_trailing = re.sub(r",(\s*[\]}])", r"\1", fenced)
    candidates.append(no_trailing)

    # Single-quote to double-quote conversion: only when no double quotes are
    # present anywhere (otherwise single quotes are string content).
    if "'" in no_trailing and '"' not in no_trailing:
        candidates.append(_convert_single_quotes(no_trailing))

    for candidate in candidates:
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            continue
    return candidates[-1]


# ── JSON validation ───────────────────────────────────────────────────────


def validate_entries(payload: Any) -> list[dict] | None:
    """Validate `payload` against EXTRACTION_SCHEMA. Returns list of dicts or None."""
    if not isinstance(payload, list):
        return None
    valid: list[dict] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        et = item.get("entry_type")
        if et not in ("decision", "fact", "learning"):
            continue
        content = item.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        tags = item.get("tags", [])
        if not isinstance(tags, list):
            tags = []
        tags = [str(t) for t in tags if t]
        conf = item.get("confidence", 1.0)
        try:
            conf = float(conf)
        except (TypeError, ValueError):
            conf = 1.0
        conf = max(0.0, min(1.0, conf))
        description = item.get("description")
        if description is not None and not isinstance(description, str):
            description = str(description)
        valid.append({
            "entry_type": et,
            "content": content.strip(),
            "description": (description or "").strip(),
            "tags": tags,
            "confidence": conf,
            "openspec_change_id": item.get("openspec_change_id") or None,
        })
    return valid


# ── LLM client (HTTP, pluggable for tests) ────────────────────────────────


class LLMClient(Protocol):
    def complete(self, prompt: str, *, response_format: str = "json") -> str: ...


class HTTPLLMClient:
    """OpenAI-compatible HTTP client with retry on transient errors.

    Defaults match the project's Ollama setup. Configure via env vars:
        LLM_BASE_URL  (default: http://localhost:11434/v1)
        LLM_MODEL     (default: qwen3:8b)
        LLM_API_KEY   (default: empty)
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434/v1",
        model: str = "qwen3:8b",
        api_key: str = "",
        timeout: float = 180.0,
        rng: random.Random | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self._rng = rng or random.Random()
        self._sleep = sleep

    def complete(self, prompt: str, *, response_format: str = "json") -> str:
        url = f"{self.base_url}/chat/completions"
        body = json.dumps({
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "response_format": {"type": "json_object"} if response_format == "json" else None,
        }).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        last_exc: Exception | None = None
        for attempt in range(RETRY_MAX_ATTEMPTS):
            try:
                req = urllib.request.Request(
                    url, data=body, headers=headers, method="POST"
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                return payload["choices"][0]["message"]["content"]
            except urllib.error.HTTPError as e:
                if e.code in RETRYABLE_HTTP and attempt < RETRY_MAX_ATTEMPTS - 1:
                    delay = self._full_jitter(RETRY_BASE_DELAYS_S[attempt])
                    log.warning(
                        "LLM call HTTP %s, retry %d/%d in %.2fs",
                        e.code, attempt + 1, RETRY_MAX_ATTEMPTS, delay,
                    )
                    self._sleep(delay)
                    last_exc = e
                    continue
                raise
            except (urllib.error.URLError, TimeoutError) as e:
                if attempt < RETRY_MAX_ATTEMPTS - 1:
                    delay = self._full_jitter(RETRY_BASE_DELAYS_S[attempt])
                    log.warning(
                        "LLM call error %r, retry %d/%d in %.2fs",
                        e, attempt + 1, RETRY_MAX_ATTEMPTS, delay,
                    )
                    self._sleep(delay)
                    last_exc = e
                    continue
                raise
        # If we exit the loop without returning/raising, re-raise last.
        if last_exc:
            raise last_exc
        raise RuntimeError("LLM client exhausted retries without exception")

    def _full_jitter(self, base: float) -> float:
        """Full jitter: sleep in [0, base]."""
        return self._rng.uniform(0.0, base)


# ── Tag vocabulary ────────────────────────────────────────────────────────


@dataclass
class TagVocabulary:
    canonical: set[str]
    aliases: dict[str, str]
    raw: dict

    @classmethod
    def load(cls, path: Path) -> "TagVocabulary":
        if not path.is_file():
            return cls(canonical=set(), aliases={}, raw={})
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return cls(canonical=set(), aliases={}, raw={})
        canonical = set(data.get("canonical", []))
        aliases = {str(k).lower(): str(v) for k, v in data.get("aliases", {}).items()}
        return cls(canonical=canonical, aliases=aliases, raw=data)

    def normalize(self, tags: list[str]) -> tuple[list[str], list[str]]:
        """Return (normalized_tags, unknown_tags)."""
        normalized: list[str] = []
        unknown: list[str] = []
        for t in tags:
            key = t.lower()
            if key in self.aliases:
                normalized.append(self.aliases[key])
            elif key in self.canonical:
                normalized.append(key)
            else:
                unknown.append(key)
        # Dedup, preserve order
        seen = set()
        out = []
        for t in normalized:
            if t not in seen:
                seen.add(t)
                out.append(t)
        return out, unknown


# ── Project alias resolution ──────────────────────────────────────────────


def load_project_aliases(path: Path) -> dict[str, str]:
    """Load project alias mapping from a JSON file (alias -> canonical)."""
    if not path.is_file():
        return {}
    try:
        return {str(k): str(v) for k, v in json.loads(path.read_text()).items()}
    except (json.JSONDecodeError, OSError):
        return {}


# ── Confidence scoring heuristics ─────────────────────────────────────────


def score_confidence(
    *,
    content: str,
    response_time_s: float,
    transcript_truncated: bool,
) -> float:
    """Score confidence based on content quality heuristics (per spec)."""
    if transcript_truncated:
        return 0.5
    if len(content) < 50:
        return 0.7
    if response_time_s < 10.0:
        return 1.0
    return 0.9


# ── OKF frontmatter compliance ────────────────────────────────────────────


def ensure_okf_compliance(
    entry: dict,
    *,
    default_confidence: float,
) -> dict:
    """Return a copy of `entry` with all OKF-required fields populated."""
    out = dict(entry)
    # description: derive from first non-heading line of content if missing
    if not out.get("description"):
        out["description"] = _first_non_heading_line(out.get("content", ""))
    # tags: empty list is fine; log if missing in caller
    if "tags" not in out or out["tags"] is None:
        out["tags"] = []
    # confidence: respect caller's value; fall back to default
    if out.get("confidence") is None:
        out["confidence"] = default_confidence
    return out


# ── Main extraction pipeline ──────────────────────────────────────────────


@dataclass
class DigestResult:
    upserted: int
    skipped: int
    unknown_tags: list[str]
    raw_response: str

    def __str__(self) -> str:
        return (
            f"upserted={self.upserted} skipped={self.skipped} "
            f"unknown_tags={self.unknown_tags}"
        )


def extract_entries(
    transcript: str,
    project: str,
    llm: LLMClient,
    store: MemoryStore,
    *,
    tag_vocab: TagVocabulary | None = None,
    project_aliases: dict[str, str] | None = None,
    now: datetime | None = None,
) -> DigestResult:
    """Run the full extraction pipeline. Never raises on parse/retry failure;
    logs and returns zero-upsert result instead."""
    if not transcript or not transcript.strip():
        log.info("empty transcript; zero writes")
        return DigestResult(0, 0, [], "")

    # Resolve project alias
    project_aliases = project_aliases or {}
    project = project_aliases.get(project, project)

    # Trivial-content heuristic: short transcripts with no project content
    if len(transcript.strip()) < 200:
        log.info("transcript too short for memorable content; zero writes")
        return DigestResult(0, 0, [], "")

    # LLM call (with retry handled inside HTTPLLMClient)
    prompt = EXTRACTION_PROMPT.format(transcript=transcript[:50_000])
    truncated = len(transcript) > 50_000

    t0 = time.monotonic()
    try:
        raw = llm.complete(prompt, response_format="json")
    except Exception as e:
        log.error("LLM call failed after retries: %s", e)
        return DigestResult(0, 0, [], "")
    response_time = time.monotonic() - t0

    # Repair + parse
    repaired = repair_json(raw)
    try:
        payload = json.loads(repaired)
    except json.JSONDecodeError as e:
        log.error("LLM response could not be parsed as JSON: %s\nraw=%s", e, raw)
        return DigestResult(0, 0, [], raw)

    # Validate against schema
    # Accept a single object instead of an array: wrap it before validation.
    if isinstance(payload, dict) and payload.get("entry_type") in (
        "decision", "fact", "learning",
    ):
        payload = [payload]
    entries = validate_entries(payload)
    if entries is None:
        log.error("LLM response did not match schema; raw=%s", raw)
        return DigestResult(0, 0, [], raw)
    if not entries:
        log.info("no memorable content found")
        return DigestResult(0, 0, [], raw)

    # Apply tag vocabulary + confidence scoring + OKF compliance + upsert
    vocab = tag_vocab or TagVocabulary(set(), {}, {})
    unknown_all: list[str] = []
    timestamp = (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    upserted = 0
    skipped = 0

    for entry in entries:
        # Tag normalization
        normalized, unknown = vocab.normalize(entry.get("tags", []))
        unknown_all.extend(unknown)
        if unknown:
            log.info("unknown tags for review: %s", unknown)

        # Confidence scoring
        confidence = score_confidence(
            content=entry["content"],
            response_time_s=response_time,
            transcript_truncated=truncated,
        )
        # Caller's confidence wins if explicitly set and in range
        caller_conf = entry.get("confidence")
        if caller_conf is not None and 0.0 <= caller_conf <= 1.0:
            confidence = caller_conf

        okf_entry = ensure_okf_compliance(
            {
                **entry,
                "tags": normalized,
                "confidence": confidence,
            },
            default_confidence=confidence,
        )
        if not okf_entry["description"]:
            log.info("description derived for entry: %s", okf_entry["content"][:60])
        if not okf_entry["tags"]:
            log.info("tags missing for entry: %s", okf_entry["content"][:60])

        try:
            store.upsert_entry(
                entry_type=okf_entry["entry_type"],
                project=project,
                content=okf_entry["content"],
                tags=okf_entry["tags"],
                confidence=okf_entry["confidence"],
                description=okf_entry["description"],
                openspec_change_id=okf_entry.get("openspec_change_id"),
            )
            upserted += 1
        except Exception as e:
            log.error("upsert failed for %s: %s", okf_entry["entry_type"], e)
            skipped += 1

    return DigestResult(
        upserted=upserted,
        skipped=skipped,
        unknown_tags=unknown_all,
        raw_response=raw,
    )


# ── Digest lock (serialization) ─────────────────────────────────────────


def acquire_digest_lock(
    lock_path: Path, budget_seconds: float
) -> TextIO | None:
    """Acquire an exclusive advisory flock on ``lock_path``.

    Polls at most once per second until ``budget_seconds`` elapses. Returns
    the open file handle (kept open while the lock is held), or None if the
    budget expired. No-op on platforms without ``fcntl`` (returns a dummy
    handle so callers can always release).
    """
    if fcntl is None:
        log.info("digest lock disabled: fcntl unavailable (non-POSIX)")
        return StringIO()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(lock_path, "a+")  # O_CREAT; stays open while held
    deadline = time.monotonic() + budget_seconds
    waiting = False
    while True:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except OSError:
            if time.monotonic() >= deadline:
                handle.close()
                log.warning(
                    "digest lock wait expired after %.0fs; skipping "
                    "(zero writes)",
                    budget_seconds,
                )
                return None
            if not waiting:
                log.info(
                    "digest lock busy, waiting up to %.0fs: %s",
                    budget_seconds,
                    lock_path,
                )
                waiting = True
            time.sleep(min(1.0, deadline - time.monotonic()))
    log.info("digest lock acquired: %s", lock_path)
    return handle


def release_digest_lock(handle: TextIO | None) -> None:
    """Release the digest lock; closing the handle drops the flock."""
    if handle is None:
        return
    try:
        handle.close()
    except OSError:
        pass


# ── CLI ───────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Digest a session transcript into OKF entries")
    parser.add_argument("--transcript", type=Path, required=True,
                        help="Path to session transcript file")
    parser.add_argument("--project", required=True, help="Project name (or alias)")
    parser.add_argument("--memory-path", type=Path, default=None,
                        help="Path to the OKF bundle (default: $MEMORY_PATH or ./memory)")
    parser.add_argument("--tag-vocab", type=Path, default=None,
                        help="Path to tag vocabulary JSON (default: <memory>/tag-vocabulary.json)")
    parser.add_argument("--project-aliases", type=Path, default=None,
                        help="Path to project aliases JSON (default: <memory>/project-aliases.json)")
    parser.add_argument("--model", default=os.environ.get("LLM_MODEL", "qwen3:8b"))
    parser.add_argument("--base-url", default=os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1"))
    parser.add_argument("--api-key", default=os.environ.get("LLM_API_KEY", ""))
    parser.add_argument("--timeout", type=int, default=180,
                        help="Per-request LLM timeout in seconds")
    default_lock_timeout = int(os.environ.get("DIGEST_LOCK_TIMEOUT", "600"))
    parser.add_argument("--lock-timeout", type=int,
                        default=default_lock_timeout,
                        help="Max seconds to wait for the digest lock "
                             "(env: DIGEST_LOCK_TIMEOUT)")
    parser.add_argument("--log", default="WARNING", help="Logging level (DEBUG, INFO, WARNING, ERROR)")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log.upper(), logging.WARNING),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if not args.transcript.is_file():
        log.error("transcript not found: %s", args.transcript)
        return 2

    # Resolve memory path
    if args.memory_path is not None:
        memory_path = args.memory_path.resolve()
    else:
        from memory_server.cli import get_memory_path
        memory_path = get_memory_path().resolve()
    if not memory_path.is_dir():
        log.error("memory path is not a directory: %s", memory_path)
        return 2

    # Persistent digest log: every run leaves a trace next to the bundle.
    log_dir = memory_path / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_dir / "digest.log", encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    logging.getLogger().addHandler(file_handler)

    store = MemoryStore(storage_path=memory_path)
    store.initialize()

    # Load vocab and aliases
    tag_vocab_path = args.tag_vocab or (memory_path / "tag-vocabulary.json")
    tag_vocab = TagVocabulary.load(tag_vocab_path)
    project_aliases_path = args.project_aliases or (memory_path / "project-aliases.json")
    project_aliases = load_project_aliases(project_aliases_path)

    # LLM client
    llm = HTTPLLMClient(
        base_url=args.base_url,
        model=args.model,
        api_key=args.api_key,
        timeout=args.timeout,
    )

    # Serialize digest runs: at most one LLM call chain per memory store.
    lock_handle = acquire_digest_lock(
        log_dir / "digest.lock", budget_seconds=float(args.lock_timeout)
    )
    if lock_handle is None:
        # Lock wait expired; skip with zero writes and exit 0 per spec.
        return 0

    try:
        transcript = args.transcript.read_text(encoding="utf-8", errors="replace")
        result = extract_entries(
            transcript=transcript,
            project=args.project,
            llm=llm,
            store=store,
            tag_vocab=tag_vocab,
            project_aliases=project_aliases,
        )
        log.info("digest result: %s", result)
    finally:
        release_digest_lock(lock_handle)
    # Always exit 0 per spec: failures are logged, not raised.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
