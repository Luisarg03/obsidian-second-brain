#!/usr/bin/env bash
# Cutover script: point OpenCode at the new ObsidianSecondBrain project.
# READ THIS SCRIPT BEFORE RUNNING. It edits ~/.config/opencode/opencode.jsonc.
#
# Pre-conditions:
#   1. The new project's memory-server and plugin are in place (Tasks 4-7).
#   2. The bundle migration is complete (Task 8).
#   3. The full test suite passes (Task 12.1).
#
# What it does:
#   - Backs up the current opencode.jsonc to opencode.jsonc.bak.<date>
#   - Updates the MCP server path to ~/Private/Projects/ObsidianSecondBraind/memory-server
#   - Updates the OpenCode plugin path to ~/Private/Projects/ObsidianSecondBraind/.opencode/plugins
#   - Does NOT touch the old ~/SecondBrain paths; you stop that server separately.
#
# After running this:
#   - Stop the old ~/SecondBrain/memory-server process.
#   - Start a new OpenCode session. Run `/brain search "test"` to verify.

set -euo pipefail

CONFIG="$HOME/.config/opencode/opencode.jsonc"
NEW_PROJECT="$HOME/Private/Projects/ObsidianSecondBraind"
BACKUP="${CONFIG}.bak.$(date +%Y-%m-%d)"

if [[ ! -f "$CONFIG" ]]; then
    echo "error: $CONFIG not found" >&2
    exit 1
fi

if [[ ! -d "$NEW_PROJECT" ]]; then
    echo "error: $NEW_PROJECT not found" >&2
    exit 1
fi

cp "$CONFIG" "$BACKUP"
echo "Backup written to $BACKUP"

# ponytail: sed in place is fine for the single path swap the user approved.
# Manual review of the diff is the next step.
sed -i \
    -e "s|$HOME/SecondBrain/memory-server|$NEW_PROJECT/memory-server|g" \
    -e "s|$HOME/SecondBrain/.opencode|$NEW_PROJECT/.opencode|g" \
    "$CONFIG"

echo "Updated $CONFIG"
echo "Diff against the backup:"
diff --color "$BACKUP" "$CONFIG" || true
echo
echo "Next steps:"
echo "  1. Review the diff above."
echo "  2. Stop the old memory-server: pkill -f SecondBrain/memory-server"
echo "  3. Start a new OpenCode session in $NEW_PROJECT."
echo "  4. Run: /brain search \"test\""
