#!/usr/bin/env bash
# ============================================================
# PocketCTF — Script 02: Teardown (Post-Event Cleanup)
# Usage: bash 02_teardown_ctf.sh
# ============================================================
set -euo pipefail

SCOREBOARD="${SCOREBOARD:-scoreboard}"
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
info()    { echo -e "[INFO]  $*"; }
success() { echo -e "[OK]    $*"; }
warn()    { echo -e "[WARN]  $*"; }

echo "PocketCTF — Post-Event Teardown"
echo ""

# ── Find all player containers ───────────────────────────────
PLAYERS=$(lxc list --format csv -c n | grep '^player-' || true)

if [[ -z "$PLAYERS" ]]; then
  warn "No player-* containers found. Nothing to clean up."
else
  echo -e "${BOLD}Containers to delete:${RESET}"
  echo "$PLAYERS" | while read -r p; do echo "  - $p"; done
  echo ""

  echo "$PLAYERS" | while read -r PLAYER; do
    info "Stopping & deleting $PLAYER..."
    lxc stop "$PLAYER" --force 2>/dev/null || true
    lxc delete "$PLAYER" 2>/dev/null || true
    success "$PLAYER removed."
  done
fi

# ── Stop the scoreboard ───────────────────────────────────────
info "Stopping scoreboard..."
lxc stop "$SCOREBOARD" --force 2>/dev/null || warn "Scoreboard was not running."
success "Scoreboard stopped."

# ── Print storage status ──────────────────────────────────────
echo ""
info "Storage pool status after cleanup:"
lxc storage list 2>/dev/null || true
zpool list 2>/dev/null || true

echo ""
echo "Teardown complete."
