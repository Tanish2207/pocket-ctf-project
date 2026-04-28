#!/usr/bin/env bash
# ============================================================
# PocketCTF — Script 01: Deploy CTF Event
# Usage: bash 01_deploy_ctf.sh [N]   (default N=3)
# ============================================================
set -euo pipefail

TEMPLATE="${TEMPLATE:-pocket-base}"
SCOREBOARD="${SCOREBOARD:-scoreboard}"
N=${1:-3}
BASE_RDP_PORT=${BASE_RDP_PORT:-3388}   # player-1 → 3389, player-2 → 3390, ...
CTFD_HOST_PORT=${CTFD_HOST_PORT:-8000}
CTFD_CONTAINER_PORT=${CTFD_CONTAINER_PORT:-8000}

# ── Colors ───────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
info()    { echo -e "[INFO]  $*"; }
success() { echo -e "[OK]    $*"; }
warn()    { echo -e "[WARN]  $*"; }
die()     { echo -e "[ERROR] $*" >&2; exit 1; }

echo "PocketCTF — Event Deployer"
echo ""

# ── Sanity checks ────────────────────────────────────────────
command -v lxc >/dev/null || die "lxc not found."
[[ "$N" =~ ^[0-9]+$ ]] || die "N must be a number. Usage: $0 <N>"
[[ "$N" -lt 1 || "$N" -gt 50 ]] && die "N must be between 1 and 50."
lxc info "$TEMPLATE" >/dev/null 2>&1 || die "Template '$TEMPLATE' not found."
lxc info "$SCOREBOARD" >/dev/null 2>&1 || die "Scoreboard '$SCOREBOARD' not found."

# ── Auto-detect host IP (dynamic — no hardcoded interface) ────
# Strategy: find the default route interface, then get its IP
detect_host_ip() {
  local iface ip

  # Method 1: Get the interface used for the default route
  iface=$(ip route show default 2>/dev/null | awk '{print $5}' | head -1)

  if [[ -n "$iface" ]]; then
    ip=$(ip addr show "$iface" 2>/dev/null | grep 'inet ' | awk '{print $2}' | cut -d/ -f1 | head -1)
    if [[ -n "$ip" && "$ip" != "127.0.0.1" ]]; then
      echo "$ip"
      return 0
    fi
  fi

  # Method 2: Fallback — find any non-loopback, non-docker, non-veth interface
  for iface in $(ip -o link show up | awk -F': ' '{print $2}' | grep -vE '^(lo|docker|veth|br-|lxd)'); do
    ip=$(ip addr show "$iface" 2>/dev/null | grep 'inet ' | awk '{print $2}' | cut -d/ -f1 | head -1)
    if [[ -n "$ip" && "$ip" != "127.0.0.1" ]]; then
      echo "$ip"
      return 0
    fi
  done

  # Method 3: Last resort — hostname -I
  ip=$(hostname -I 2>/dev/null | awk '{print $1}')
  if [[ -n "$ip" ]]; then
    echo "$ip"
    return 0
  fi

  return 1
}

HOST_IP=$(detect_host_ip) || die "Could not detect host IP. Are you connected to a network?"
info "Host IP detected: ${BOLD}$HOST_IP${RESET}"

# Allow override via env
HOST_IP="${OVERRIDE_HOST_IP:-$HOST_IP}"
if [[ -n "${OVERRIDE_HOST_IP:-}" ]]; then
  info "Using override IP: ${BOLD}$HOST_IP${RESET}"
fi

info "Deploying $N player containers..."
echo ""

# ── Step 1: Start the scoreboard (CTFd) ──────────────────────
info "Starting scoreboard (CTFd)..."
SCOREBOARD_STATE=$(lxc list "$SCOREBOARD" --format csv -c s)
if [[ "$SCOREBOARD_STATE" != "RUNNING" ]]; then
  lxc start "$SCOREBOARD"
  info "Waiting 15s for CTFd to come up..."
  sleep 15
fi

# Add proxy for CTFd if not already added
if ! lxc config device show "$SCOREBOARD" | grep -q "ctfd-proxy" 2>/dev/null; then
  lxc config device add "$SCOREBOARD" ctfd-proxy proxy \
    listen=tcp:0.0.0.0:${CTFD_HOST_PORT} \
    connect=tcp:127.0.0.1:${CTFD_CONTAINER_PORT} 2>/dev/null || warn "CTFd proxy already exists."
fi
success "Scoreboard is UP → http://${HOST_IP}:${CTFD_HOST_PORT}"
echo ""

# ── Step 2: Clone & start player containers ───────────────────
declare -A PLAYER_PORTS

for i in $(seq 1 "$N"); do
  PLAYER="player-$i"
  RDP_PORT=$((BASE_RDP_PORT + i))
  PLAYER_PORTS[$i]=$RDP_PORT

  info "[$i/$N] Setting up $PLAYER (RDP port: $RDP_PORT)..."

  # Delete existing container if present
  if lxc info "$PLAYER" >/dev/null 2>&1; then
    warn "  $PLAYER already exists — deleting and re-creating..."
    lxc stop "$PLAYER" --force 2>/dev/null || true
    lxc delete "$PLAYER" 2>/dev/null || true
  fi

  # ZFS CoW clone — nearly instant
  lxc copy "$TEMPLATE" "$PLAYER"

  # Add RDP proxy BEFORE starting (listen on 0.0.0.0 for external Wi-Fi access)
  lxc config device add "$PLAYER" rdp-proxy proxy \
    listen=tcp:0.0.0.0:${RDP_PORT} \
    connect=tcp:127.0.0.1:3389

  # Start the container
  lxc start "$PLAYER"
  success "  $PLAYER started. Docker attackers will auto-launch in ~30s."
done

echo ""
info "Waiting 30s for all containers to fully initialize Docker..."
sleep 30

# ── Step 3: Print the Assignment Table ───────────────────────
echo "STUDENT ASSIGNMENT TABLE"
echo "------------------------------------------------------------------"
echo "CONTAINER | HOST IP | PORT | REMMINA CONNECTION"
echo "------------------------------------------------------------------"
for i in $(seq 1 "$N"); do
  PLAYER="player-$i"
  RDP_PORT=${PLAYER_PORTS[$i]}
  printf "%-10s | %-16s | %-5s | %-22s\n" \
    "$PLAYER" "$HOST_IP" "$RDP_PORT" "${HOST_IP}:${RDP_PORT}"
done
echo "------------------------------------------------------------------"
echo "CTFd Scoreboard: http://${HOST_IP}:${CTFD_HOST_PORT}"
echo "Username: ubuntu | Password: ubuntu"
echo "------------------------------------------------------------------"

# ── Step 4: Verify Docker inside player containers ────────────
echo ""
info "Quick sanity check — Docker containers inside each player:"
for i in $(seq 1 "$N"); do
  PLAYER="player-$i"
  echo -e "  ${CYAN}$PLAYER:${RESET}"
  lxc exec "$PLAYER" -- docker ps --format "    {{.Names}} → {{.Status}}" 2>/dev/null || \
    warn "    Docker not yet ready in $PLAYER (normal if < 30s). Give it another minute."
done

echo "Deployment complete."
echo "Teardown: bash 02_teardown_ctf.sh"
