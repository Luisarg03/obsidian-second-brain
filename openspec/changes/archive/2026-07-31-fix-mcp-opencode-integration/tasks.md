## 1. Plugin source of truth

- [x] 1.1 Diff `~/.config/opencode/plugins/src/obsidian-second-brain-memory/` against `.opencode/plugins/memory/`; identify what the global copy has that the repo copy lacks (entry point / register wiring) and any repo-only improvements to preserve.
- [x] 1.2 Adopt the global implementation into `.opencode/plugins/memory/` (preserving repo-only improvements found in 1.1) so the repo copy is complete, including the entry point OpenCode loads.
- [x] 1.3 Replace the global plugin directory with a symlink to the repo plugin directory; verify OpenCode still loads the plugin (plugin listed, version guard silent on a supported version). If the symlink breaks resolution, implement `scripts/install_plugin.sh` as the documented fallback instead.

## 2. MCP spawn fix

- [x] 2.1 Update `~/.config/opencode/opencode.json` memory MCP command to `["uv", "run", "--directory", "/home/hiro03/Private/Projects/ObsidianSecondBraind", "python", "memory_server/server.py"]`.
- [x] 2.2 Verify the server spawns from a foreign working directory (start OpenCode in another project, run `/brain search "SQLite"` and confirm results from the bundle).

## 3. Deferred validations from fix-memory-store-dedup

- [x] 3.1 Run the full pytest suite (`PYTHONPATH=. uv run pytest tests/ -q`) and confirm all tests pass.
- [x] 3.2 Run `PYTHONPATH=. python3 scripts/okf_validate.py --strict --memory-path memory` and confirm exit 0.
- [x] 3.3 Digest idempotency: copy `memory/` + `memory.db` to a temp dir, run `digest_session.py` twice against the copy with a tiny transcript, and confirm identical `.md` file count, identical SQLite entry count, and no `-N` suffixed files.
