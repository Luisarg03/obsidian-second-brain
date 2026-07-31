## ADDED Requirements

### Requirement: MCP spawn command is directory-pinned and interpreter-resolved
The OpenCode MCP registration for the memory server SHALL use a spawn command that (a) sets the working directory to the repository root via an absolute path and (b) resolves the Python interpreter through the project's environment manager (`uv run`), so the server starts successfully regardless of the OpenCode working directory.

#### Scenario: Server starts from a foreign working directory
- **WHEN** OpenCode is started in a directory other than the memory repository
- **THEN** the memory MCP server spawns successfully and responds to `ping`

#### Scenario: No reliance on a bare `python` on PATH
- **WHEN** the system PATH has no `python` executable (only `python3` or none)
- **THEN** the spawn command still starts the server because the interpreter is resolved by `uv`
