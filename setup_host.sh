#!/usr/bin/env bash
# ============================================================
# PocketCTF — Host Bootstrap: Zero to Ready on a Clean Ubuntu
# Supported: Ubuntu 22.04 / 24.04 (amd64)
#
# Usage: sudo bash setup_host.sh
#
# This script installs ALL prerequisites and builds the two
# base containers (pocket-base + scoreboard) from scratch.
# After it finishes you can go straight to:
#   bash 00_finalize_image.sh
# ============================================================
set -euo pipefail

# ── Colors / helpers ─────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
info()    { echo -e "[INFO]  $*"; }
success() { echo -e "[OK]    $*"; }
warn()    { echo -e "[WARN]  $*"; }
die()     { echo -e "[ERROR] $*" >&2; exit 1; }

# ── Must be root ─────────────────────────────────────────────
[[ $(id -u) -eq 0 ]] || die "This script must be run as root.  Use: sudo bash $0"

# PocketCTF — Host Bootstrap
# Sets up LXD + ZFS + Containers from scratch

# ── Configurable variables (override via env if needed) ──────
LXD_POOL_NAME="${LXD_POOL_NAME:-pocketctf-pool}"
LXD_POOL_SIZE="${LXD_POOL_SIZE:-30GB}"
TEMPLATE="${TEMPLATE:-pocket-base}"
SCOREBOARD="${SCOREBOARD:-scoreboard}"
CONTAINER_USER="${CONTAINER_USER:-ubuntu}"
CONTAINER_PASS="${CONTAINER_PASS:-ubuntu}"
UBUNTU_IMAGE="${UBUNTU_IMAGE:-ubuntu:22.04}"

info "Configuration:"
info "  LXD Pool:       $LXD_POOL_NAME ($LXD_POOL_SIZE)"
info "  Template:       $TEMPLATE"
info "  Scoreboard:     $SCOREBOARD"
info "  Container user: $CONTAINER_USER"
info "  Base image:     $UBUNTU_IMAGE"
echo ""

# Phase 1: Host Dependencies

info "Updating package lists..."
apt-get update -qq

info "Installing ZFS utilities..."
apt-get install -y -qq zfsutils-linux > /dev/null 2>&1
success "ZFS installed."

info "Installing snapd (for LXD)..."
apt-get install -y -qq snapd > /dev/null 2>&1
success "snapd installed."

# Install LXD via snap (the officially supported method)
if command -v lxd > /dev/null 2>&1; then
  warn "LXD is already installed, skipping snap install."
else
  info "Installing LXD via snap..."
  snap install lxd --channel=latest/stable 2>/dev/null || snap refresh lxd --channel=latest/stable 2>/dev/null || true
  # Make sure the lxd group exists and current sudo user is in it
  success "LXD installed via snap."
fi

# Ensure lxc/lxd are on PATH
export PATH="/snap/bin:$PATH"
command -v lxc > /dev/null || die "lxc command not found after installation. Try: export PATH=/snap/bin:\$PATH"

# Add the original (non-root) user to lxd group
REAL_USER="${SUDO_USER:-$USER}"
if [[ "$REAL_USER" != "root" ]]; then
  usermod -aG lxd "$REAL_USER" 2>/dev/null || true
  info "Added $REAL_USER to lxd group (re-login required for non-sudo usage)."
fi

# Install other useful host tools
info "Installing host utilities (curl, jq, python3)..."
apt-get install -y -qq curl jq python3 > /dev/null 2>&1
success "Host utilities installed."

echo ""

# Phase 2: LXD Initialization

# Check if LXD is already initialized
if lxc storage list 2>/dev/null | grep -q "$LXD_POOL_NAME"; then
  warn "LXD pool '$LXD_POOL_NAME' already exists. Skipping init."
else
  info "Initializing LXD with ZFS storage pool (${LXD_POOL_SIZE})..."
  cat <<PRESEED | lxd init --preseed
config:
  core.https_address: "[::]:8443"
networks:
- config:
    ipv4.address: auto
    ipv6.address: auto
  description: ""
  name: lxdbr0
  type: bridge
storage_pools:
- config:
    size: "${LXD_POOL_SIZE}"
  description: "PocketCTF ZFS pool"
  driver: zfs
  name: "${LXD_POOL_NAME}"
profiles:
- config: {}
  description: "Default LXD profile"
  devices:
    eth0:
      name: eth0
      network: lxdbr0
      type: nic
    root:
      path: /
      pool: "${LXD_POOL_NAME}"
      type: disk
  name: default
cluster: null
PRESEED
  success "LXD initialized with ZFS pool: $LXD_POOL_NAME"
fi

echo ""

# Phase 3: Build Template Container

if lxc info "$TEMPLATE" > /dev/null 2>&1; then
  warn "'$TEMPLATE' already exists. Skipping creation."
  warn "Delete it first if you want a fresh build: lxc delete $TEMPLATE --force"
else
  info "Launching $TEMPLATE from $UBUNTU_IMAGE..."
  lxc launch "$UBUNTU_IMAGE" "$TEMPLATE"

  # Enable nesting (Docker inside LXC) and privileged mode
  info "Configuring container security for Docker-in-LXC..."
  lxc config set "$TEMPLATE" security.nesting true
  lxc config set "$TEMPLATE" security.privileged true
  lxc config set "$TEMPLATE" raw.lxc "lxc.apparmor.profile=unconfined"

  # Restart to apply security config
  lxc restart "$TEMPLATE"
  info "Waiting 15s for container to fully boot..."
  sleep 15

  # ── Install Docker inside the container ──
  info "Installing Docker inside $TEMPLATE (this takes 2-3 minutes)..."
  lxc exec "$TEMPLATE" -- bash -c "
    set -e
    apt-get update -qq
    apt-get install -y -qq ca-certificates curl gnupg lsb-release > /dev/null 2>&1

    # Docker official GPG key
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
      gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg

    # Docker repo
    echo \"deb [arch=\$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
      https://download.docker.com/linux/ubuntu \$(lsb_release -cs) stable\" > \
      /etc/apt/sources.list.d/docker.list

    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin > /dev/null 2>&1
    systemctl enable docker
    systemctl start docker
  "
  success "Docker installed inside $TEMPLATE."

  # ── Install Desktop + RDP ──
  info "Installing XFCE4 desktop + xRDP (this takes 3-5 minutes)..."
  lxc exec "$TEMPLATE" -- bash -c "
    set -e
    export DEBIAN_FRONTEND=noninteractive
    apt-get install -y -qq xfce4 xfce4-terminal xfce4-goodies xrdp > /dev/null 2>&1

    # Configure xrdp to use xfce4
    echo 'xfce4-session' > /etc/skel/.xsession
    sed -i 's|^test -x /etc/X11/Xsession.*|xfce4-session|' /etc/xrdp/startwm.sh 2>/dev/null || true
    # Ensure startwm.sh uses xfce4
    cat > /etc/xrdp/startwm.sh << 'STARTWM'
#!/bin/sh
if [ -r /etc/default/locale ]; then
  . /etc/default/locale
  export LANG LANGUAGE
fi
exec /usr/bin/xfce4-session
STARTWM
    chmod +x /etc/xrdp/startwm.sh
    systemctl enable xrdp
    systemctl restart xrdp
  "
  success "XFCE4 + xRDP installed."

  # ── Install Security / Analysis Tools ──
  info "Installing Wireshark, tcpdump, net-tools, and other analysis tools..."
  lxc exec "$TEMPLATE" -- bash -c "
    set -e
    export DEBIAN_FRONTEND=noninteractive
    # Pre-answer wireshark's 'should non-root users capture?' question
    echo 'wireshark-common wireshark-common/install-setuid boolean true' | debconf-set-selections
    apt-get install -y -qq wireshark tshark tcpdump net-tools nmap curl wget \
      iputils-ping dnsutils file less vim nano > /dev/null 2>&1
  "
  success "Analysis tools installed."

  # ── Create the user account ──
  info "Creating user '$CONTAINER_USER' with password '$CONTAINER_PASS'..."
  lxc exec "$TEMPLATE" -- bash -c "
    set -e
    # Create user if it doesn't exist
    id '$CONTAINER_USER' > /dev/null 2>&1 || useradd -m -s /bin/bash '$CONTAINER_USER'
    echo '${CONTAINER_USER}:${CONTAINER_PASS}' | chpasswd
    usermod -aG sudo,docker,wireshark '$CONTAINER_USER'
    # Create .xsession for xrdp
    echo 'xfce4-session' > /home/${CONTAINER_USER}/.xsession
    chown ${CONTAINER_USER}:${CONTAINER_USER} /home/${CONTAINER_USER}/.xsession
  "
  success "User '$CONTAINER_USER' created."

  # Stop the template
  info "Stopping $TEMPLATE..."
  lxc stop "$TEMPLATE"
  success "$TEMPLATE is built and ready."
fi

echo ""

# Phase 4: Build Scoreboard Container

if lxc info "$SCOREBOARD" > /dev/null 2>&1; then
  warn "'$SCOREBOARD' already exists. Skipping creation."
else
  info "Launching $SCOREBOARD from $UBUNTU_IMAGE..."
  lxc launch "$UBUNTU_IMAGE" "$SCOREBOARD"
  lxc config set "$SCOREBOARD" security.nesting true

  info "Waiting 15s for container to boot..."
  sleep 15

  # Install Docker inside scoreboard
  info "Installing Docker inside $SCOREBOARD..."
  lxc exec "$SCOREBOARD" -- bash -c "
    set -e
    apt-get update -qq
    apt-get install -y -qq ca-certificates curl gnupg lsb-release > /dev/null 2>&1
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
      gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    echo \"deb [arch=\$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
      https://download.docker.com/linux/ubuntu \$(lsb_release -cs) stable\" > \
      /etc/apt/sources.list.d/docker.list
    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin > /dev/null 2>&1
    systemctl enable docker
    systemctl start docker
  "
  success "Docker installed inside $SCOREBOARD."

  # Pull and set up CTFd
  info "Setting up CTFd inside $SCOREBOARD..."
  lxc exec "$SCOREBOARD" -- bash -c "
    set -e
    mkdir -p /opt/ctfd
    cd /opt/ctfd
    # Create a docker-compose for CTFd
    cat > docker-compose.yml << 'COMPOSE'
version: '3.8'
services:
  ctfd:
    image: ctfd/ctfd:latest
    ports:
      - \"8000:8000\"
    volumes:
      - ctfd-data:/opt/CTFd/CTFd/uploads
      - ctfd-logs:/opt/CTFd/CTFd/logs
    environment:
      - DATABASE_URL=sqlite:////opt/CTFd/CTFd/ctfd.db
      - SECRET_KEY=pocketctf-secret-change-me
    restart: always
volumes:
  ctfd-data:
  ctfd-logs:
COMPOSE
    docker compose pull
  "
  success "CTFd pulled and configured."

  # Create systemd service so CTFd starts on container boot
  info "Creating CTFd auto-start service..."
  lxc exec "$SCOREBOARD" -- bash -c "
    cat > /etc/systemd/system/ctfd.service << 'SVC'
[Unit]
Description=CTFd Scoreboard
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/ctfd
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down

[Install]
WantedBy=multi-user.target
SVC
    systemctl daemon-reload
    systemctl enable ctfd.service
  "
  success "CTFd auto-start service created."

  info "Stopping $SCOREBOARD..."
  lxc stop "$SCOREBOARD"
  success "$SCOREBOARD is built and ready."
fi

echo ""

# Phase 5: Verification

info "LXD containers:"
lxc list

info "Storage pool:"
lxc storage list

echo "Host Bootstrap Complete"
echo "LXD and containers are ready."
echo ""
echo "Next steps:"
echo "1. bash 00_finalize_image.sh"
echo "2. Set up CTFd admin"
echo "3. bash 03_seed_ctfd.sh <url> <token>"
echo "4. bash 01_deploy_ctf.sh <N>"
echo ""
