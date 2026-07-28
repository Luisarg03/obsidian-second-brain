# Memory Bundle

This directory is an Obsidian vault and the OKF v0.1 knowledge bundle for the project. It is the only directory in this repository that LLM agents may read by default.

## Conventions

- Every document is OKF-conformant: frontmatter has `type`, `title`, `description`, `tags`, `timestamp` (and optionally `resource`).
- The `type` is one of: `Index`, `Decision`, `Fact`, `Learning`, `Convention`, `Profile`, or `x-<custom>`.
- `index.md` files describe a directory. `log.md` files record chronological changes.
- Tags are normalized against `tag-vocabulary.json`. Use the canonical form.

## Layout

- `index.md` — the bundle root index
- `log.md` — chronological change log
- `tag-vocabulary.json` — controlled tag vocabulary
- `templates/` — Obsidian templates with OKF frontmatter pre-filled
- `projects/<project>/` — one subdirectory per project, each with its own `index.md` and entries grouped by type

## Read scope (for agents)

If you are an LLM agent and you have not been told to read code, do not read outside this directory. Call `search_memory`, `get_profile`, or `export_memories` to satisfy a prompt; do not auto-load files.

## Edit workflow

1. Edit the Markdown file directly in Obsidian (or any editor).
2. Run `uv run rebuild-index` to refresh the SQLite search index.
3. Reads via MCP will then reflect the edit.
