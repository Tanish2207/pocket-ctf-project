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

# ── Write the defender challenge check script ─────────────────────────────────
cat > /check_defender.sh << 'CHECKSCRIPT'
#!/bin/bash
echo ""
echo "========================================"
echo "  Defender Challenge: Block the Attacker"
echo "========================================"

# Resolve attacker's live IP via Docker internal DNS
ATTACKER_IP=$(getent hosts attacker 2>/dev/null | awk '{print $1}')

if [ -z "$ATTACKER_IP" ]; then
    echo "[-] ERROR: Cannot resolve 'attacker' hostname."
    echo "    Are you on the right network?"
    exit 1
fi

echo "[*] Attacker's IP on this network : $ATTACKER_IP"
echo "[*] Checking your iptables rules  ..."
echo ""

# Check if a DROP rule exists for the attacker's IP in the INPUT chain
if iptables -L INPUT -n 2>/dev/null | grep -q "DROP.*$ATTACKER_IP"; then
    echo "[+] ✓  iptables DROP rule found for $ATTACKER_IP"
    echo ""
    if [ -f /root/.defender_flag ]; then
        echo "[+] ★  HERE IS YOUR FLAG:"
        cat /root/.defender_flag
        echo ""
    else
        echo "[-] Flag file not found — ask your teacher to check the session setup."
    fi
else
    echo "[-] No DROP rule found for $ATTACKER_IP in your INPUT chain."
    echo ""
    echo "    HINTS:"
    echo "    1. Watch Suricata alerts : tail -f /var/log/suricata/fast.log"
    echo "    2. The attacker's IP is  : $ATTACKER_IP"
    echo "    3. Block them with       : iptables -A INPUT -s $ATTACKER_IP -j DROP"
    echo "    4. Verify the rule       : iptables -L INPUT -n"
    echo "    5. Then re-run this script to claim your flag."
fi
echo "========================================"
CHECKSCRIPT
chmod +x /check_defender.sh
log "Defender check script written to /check_defender.sh — run it after blocking the attacker"
# ──────────────────────────────────────────────────────────────────────────────


# ── Start vulnerable web app (RCE challenge) ──────────────────────────────────
log "Starting VJTI IntraNet Monitor (port 5000)..."
python3 /vulnerable_server.py > /var/log/webapp.log 2>&1 &
WEBAPP_PID=$!
log "Web app started with PID: $WEBAPP_PID  (logs: /var/log/webapp.log)"
# ─────────────────────────────────────────────────────────────────────────────

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
