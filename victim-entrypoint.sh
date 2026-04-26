#!/bin/bash
# ── PocketCTF Victim Entrypoint ───────────────────────────────────────────────
# Note: no 'set -e' — we don't want a failed diagnostic command to kill
# the entrypoint before ttyd gets a chance to start.

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [VICTIM] $*"; }

log "============================================"
log "  PocketCTF Victim Container Starting"
log "============================================"

log "Hostname       : $(hostname 2>/dev/null || echo unknown)"
log "Container IP   : $(hostname -I 2>/dev/null | tr -d ' ' || echo unknown)"
log "Network ifaces : $(ip link show 2>/dev/null | grep -E '^[0-9]+:' | awk '{print $2}' | tr -d ':'| tr '\n' ' ' || echo unknown)"

# Place any victim-side setup commands here
# e.g. start a vulnerable service, drop flags into specific paths, etc.

# Example: write a flag file the defender can find and protect
# echo "FLAG{defender_spotted_the_intruder}" > /root/.hidden_flag
# log "Hidden flag written to /root/.hidden_flag"

log "Environment ready — starting Suricata in background via /start.sh..."
bash /start.sh &
SURICATA_PID=$!
log "Suricata script launched with PID: $SURICATA_PID"
log "Waiting 3 seconds for Suricata to initialise..."
sleep 3
log "  Attacker hostname on this network: attacker"
log "  Watch your logs at: /var/log/suricata/fast.log"
log "============================================"

# Start ttyd on port 7682 — this becomes PID 1 via exec
log "Starting ttyd (web terminal) on 0.0.0.0:7682 ..."
exec ttyd --port 7682 --interface 0.0.0.0 --writable bash
