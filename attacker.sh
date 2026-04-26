#!/bin/bash
# ── PocketCTF Attack Loop ──────────────────────────────────────────────────────

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [ATTACK-LOOP] $*"; }

log "Attack loop initialising — target: victim"
CYCLE=0

while true; do
    CYCLE=$((CYCLE + 1))
    log "--- Cycle #$CYCLE start ---"

    log "Running TCP SYN port scan (nmap -sS victim)..."
    nmap -sS victim
    log "nmap scan complete"

    log "Running ICMP flood (ping -c 10 victim)..."
    ping -c 10 victim
    log "ping complete"

    log "--- Cycle #$CYCLE done --- sleeping 45 seconds..."
    sleep 45
done