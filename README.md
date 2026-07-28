# ObsidianSecondBrain

OKF v0.1 knowledge bundle living in an Obsidian vault, consumed by LLM agents on demand.

The `memory/` directory is the bundle. It is also an Obsidian vault. Open it in Obsidian to browse, search, and graph the brain. Everything else in this repo is implementation that agents do not read unless explicitly directed.

## Layout

```
memory/              OKF knowledge bundle (Obsidian vault)
  .obsidian/         Obsidian config (regenerated on first open)
  README.md          Bundle overview
  index.md           OKF root index
  log.md             Chronological change log
  tag-vocabulary.json Controlled tag vocabulary
  templates/         Obsidian templates with OKF frontmatter
  projects/<project> Per-project bundles

memory-server/       Python MCP server (8 tools, opt-in reads)
scripts/             OKF validator, migrator, index rebuilder, digest
openspec/            Capability specs and change tracking
tests/               Pytest suite
```

## Quick start

```bash
uv sync
uv run okf-validate                       # check OKF conformance
uv run okf-validate --strict              # exit non-zero on any error
```

See `openspec/specs/` for the full capability catalog and `openspec/changes/obsidian-second-brain-foundations/` for the in-flight foundation change.
