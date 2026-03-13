#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════
#  TA Automation — Mac / Linux Launcher
#  Usage: double-click in Finder, or: bash run.sh
# ═══════════════════════════════════════════════════════

set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

# ── First-run: create config from template ─────────────────────────────────
if [ ! -f "config.local.yaml" ]; then
    echo ""
    echo "  ┌─────────────────────────────────────────┐"
    echo "  │  First-time setup                       │"
    echo "  │                                         │"
    echo "  │  1. config.local.yaml has been created  │"
    echo "  │  2. Fill in your API keys               │"
    echo "  │  3. Run this script again               │"
    echo "  └─────────────────────────────────────────┘"
    echo ""
    cp config.yaml config.local.yaml
    # Try to open in a text editor
    if command -v open &>/dev/null; then
        open -e config.local.yaml          # macOS TextEdit
    elif command -v xdg-open &>/dev/null; then
        xdg-open config.local.yaml         # Linux default editor
    else
        echo "  Edit config.local.yaml and re-run this script."
    fi
    exit 0
fi

# ── Make exe executable (Mac: quarantine may strip this) ──────────────────
chmod +x ./ta_automation 2>/dev/null || true

# Mac Gatekeeper: if blocked, user must right-click → Open once
if [[ "$OSTYPE" == "darwin"* ]]; then
    xattr -d com.apple.quarantine ./ta_automation 2>/dev/null || true
fi

# ── Launch ─────────────────────────────────────────────────────────────────
echo ""
echo "  Starting TA Automation..."
echo "  Opening http://localhost:8501 in your browser."
echo "  Press Ctrl+C to stop."
echo ""

./ta_automation &
APP_PID=$!

# Give Streamlit ~3 seconds to start before opening browser
sleep 3
if command -v open &>/dev/null; then
    open http://localhost:8501          # macOS
elif command -v xdg-open &>/dev/null; then
    xdg-open http://localhost:8501      # Linux
fi

wait "$APP_PID"
