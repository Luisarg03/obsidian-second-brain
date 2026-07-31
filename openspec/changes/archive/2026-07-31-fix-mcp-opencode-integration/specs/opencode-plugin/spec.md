## ADDED Requirements

### Requirement: Plugin implementation has a single versioned source of truth
The OpenCode plugin implementation SHALL be versioned in this repository, and the global plugin location (`~/.config/opencode/plugins/src/obsidian-second-brain-memory/`) SHALL resolve to the repository copy (via symlink, with a scripted copy as documented fallback). There SHALL be exactly one editable copy of the plugin implementation.

#### Scenario: Edit in repo takes effect in OpenCode
- **WHEN** the plugin implementation is edited in the repository copy
- **THEN** the next OpenCode start loads the edited implementation without any manual copy step

#### Scenario: Fallback install when symlink unsupported
- **WHEN** the plugin loader fails to resolve the symlinked global location
- **THEN** `scripts/install_plugin.sh` copies the repository plugin into the global location and documents that the copy must be re-run after edits
