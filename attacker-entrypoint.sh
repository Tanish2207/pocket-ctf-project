#!/bin/bash
# ── PocketCTF Attacker Entrypoint ─────────────────────────────────────────────
# Note: no 'set -e' — we don't want a failed diagnostic command to kill
# the entrypoint before ttyd gets a chance to start.

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [ATTACKER] $*"; }

log "============================================"
log "  PocketCTF Attacker Container Starting"
log "============================================"

log "Hostname       : $(hostname 2>/dev/null || echo unknown)"
log "Container IP   : $(hostname -I 2>/dev/null | tr -d ' ' || echo unknown)"
log "Network ifaces : $(ip link show 2>/dev/null | grep -E '^[0-9]+:' | awk '{print $2}' | tr -d ':' | tr '\n' ' ' || echo unknown)"

# Run the background attack loop if attacker.sh is present
if [ -f /attacker.sh ]; then
    log "Found /attacker.sh — launching attack loop in background..."
    bash /attacker.sh &
    ATTACK_PID=$!
    log "Attack loop started with PID: $ATTACK_PID"
else
    log "WARNING: /attacker.sh not found — no background attack loop started"
fi

log "Target hostname on this network: victim"
log "Tools available: nmap, hping3, ping"
log "============================================"

# Start ttyd — exposes this bash session as a web terminal on port 7681
log "Starting ttyd (web terminal) on 0.0.0.0:7681 ..."
exec ttyd --port 7681 --interface 0.0.0.0 --writable bash
