#!/usr/bin/env bash
# ============================================================
# PocketCTF -- Script 00: Finalize the Image
# Run ONCE before the event to prepare pocket-base for cloning.
# Usage: bash 00_finalize_image.sh
# ============================================================
set -euo pipefail

TEMPLATE="${TEMPLATE:-pocket-base}"

info()    { echo "[INFO]  $*"; }
success() { echo "[OK]    $*"; }
warn()    { echo "[WARN]  $*"; }
die()     { echo "[ERROR] $*" >&2; exit 1; }

echo "PocketCTF -- Image Finalizer"
echo "Template: $TEMPLATE"
echo ""

# Sanity checks
command -v lxc >/dev/null || die "lxc not found."
lxc info "$TEMPLATE" >/dev/null 2>&1 || die "Container '$TEMPLATE' not found."

# Step 1: Boot template
info "Starting $TEMPLATE..."
lxc start "$TEMPLATE" 2>/dev/null || warn "May already be running."
info "Waiting 25s for systemd + Docker daemon to come up..."
sleep 25

for i in 1 2 3; do
  lxc exec "$TEMPLATE" -- docker info >/dev/null 2>&1 && break
  warn "Docker not ready yet, waiting 10s more... (attempt $i/3)"
  sleep 10
done
lxc exec "$TEMPLATE" -- docker info >/dev/null 2>&1 || \
  die "Docker daemon not responding inside $TEMPLATE."
success "Docker is alive inside $TEMPLATE"

# Step 2: Write Dockerfiles into the template container
info "Creating Dockerfile directories..."
lxc exec "$TEMPLATE" -- mkdir -p /opt/ctf-images/victim /opt/ctf-images/recon /opt/ctf-images/dos

# --- Victim Dockerfile ---
# Challenge 1: SYN flood target (observe with Wireshark)
# Challenge 2: Hidden flag in HTTP response header (curl -I or Wireshark)
# Challenge 3: Cron-based persistence evidence
info "Writing victim Dockerfile..."
lxc exec "$TEMPLATE" -- bash << 'OUTER'
cat > /opt/ctf-images/victim/Dockerfile << 'EOF'
FROM nginx:latest

RUN apt-get update && apt-get install -y cron && rm -rf /var/lib/apt/lists/*

# Challenge 2: Flag hidden in a custom HTTP response header
RUN printf 'server {\n    listen 80;\n    server_name localhost;\n    add_header X-Secret-Flag "CoC{http_headers_are_leaky}" always;\n    location / {\n        root /usr/share/nginx/html;\n        index index.html index.htm;\n    }\n}\n' > /etc/nginx/conf.d/default.conf

# Challenge 3: Cron job writing to a hidden log
RUN printf '* * * * * root echo "CoC{persistence_via_cron}" >> /var/log/.secret.log 2>/dev/null\n' > /etc/cron.d/maintenance && \
    chmod 0644 /etc/cron.d/maintenance

# Challenge 4: Hidden backdoor script
RUN mkdir -p /usr/lib/.hidden && \
    printf '#!/bin/bash\n# Reverse shell beacon -- CoC{never_trust_hidden_files}\nwhile true; do\n  sleep 300\ndone\n' > /usr/lib/.hidden/backdoor.sh && \
    chmod +x /usr/lib/.hidden/backdoor.sh

CMD service cron start && nginx -g 'daemon off;'
EOF
OUTER
success "Victim Dockerfile written."

# --- Recon attacker Dockerfile ---
info "Writing recon Dockerfile..."
lxc exec "$TEMPLATE" -- bash << 'OUTER'
cat > /opt/ctf-images/recon/Dockerfile << 'EOF'
FROM ubuntu:22.04
RUN apt-get update && apt-get install -y nmap curl && rm -rf /var/lib/apt/lists/*
CMD sh -c 'while true; do nmap -sS -T2 --open 172.20.0.2 2>/dev/null; sleep 60; done'
EOF
OUTER
success "Recon Dockerfile written."

# --- DoS attacker Dockerfile ---
info "Writing DoS Dockerfile..."
lxc exec "$TEMPLATE" -- bash << 'OUTER'
cat > /opt/ctf-images/dos/Dockerfile << 'EOF'
FROM ubuntu:22.04
RUN apt-get update && apt-get install -y hping3 && rm -rf /var/lib/apt/lists/*
CMD sh -c 'while true; do hping3 -S --flood -p 80 172.20.0.2 2>/dev/null; sleep 120; done'
EOF
OUTER
success "DoS Dockerfile written."

# Step 3: Build Docker images
info "Building ctf-victim image..."
lxc exec "$TEMPLATE" -- docker build -t ctf-victim:latest /opt/ctf-images/victim/
success "ctf-victim image built."

info "Building ctf-recon image..."
lxc exec "$TEMPLATE" -- docker build -t ctf-recon:latest /opt/ctf-images/recon/
success "ctf-recon image built."

info "Building ctf-dos image..."
lxc exec "$TEMPLATE" -- docker build -t ctf-dos:latest /opt/ctf-images/dos/
success "ctf-dos image built."

# Step 4: Create the attack network and spawn containers
info "Removing any old warzone..."
lxc exec "$TEMPLATE" -- bash -c 'docker rm -f victim-host attacker-recon attacker-dos 2>/dev/null; docker network rm ctf-net 2>/dev/null; true'

info "Creating isolated network: ctf-net (172.20.0.0/24)..."
lxc exec "$TEMPLATE" -- docker network create \
  --driver bridge \
  --subnet 172.20.0.0/24 \
  --gateway 172.20.0.1 \
  ctf-net

info "Spawning victim-host -> 172.20.0.2"
lxc exec "$TEMPLATE" -- docker run -d \
  --name victim-host \
  --network ctf-net \
  --ip 172.20.0.2 \
  --restart always \
  ctf-victim:latest

info "Spawning attacker-recon -> 172.20.0.3"
lxc exec "$TEMPLATE" -- docker run -d \
  --name attacker-recon \
  --network ctf-net \
  --ip 172.20.0.3 \
  --restart always \
  ctf-recon:latest

info "Spawning attacker-dos -> 172.20.0.4"
lxc exec "$TEMPLATE" -- docker run -d \
  --name attacker-dos \
  --network ctf-net \
  --ip 172.20.0.4 \
  --cap-add NET_ADMIN \
  --cap-add NET_RAW \
  --restart always \
  ctf-dos:latest

success "Warzone is live."
echo ""
lxc exec "$TEMPLATE" -- docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}"
echo ""

# Step 5: Plant Challenge 4 -- SUID binary for privilege escalation
info "Planting SUID binary (Challenge 4)..."
lxc exec "$TEMPLATE" -- bash << 'OUTER'
echo 'CoC{suid_is_dangerous}' > /root/flag.txt
chmod 600 /root/flag.txt

cat > /tmp/statuscheck.c << 'EOF'
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

int main() {
    setuid(0);
    FILE *f = fopen("/root/flag.txt", "r");
    if (f == NULL) {
        printf("System status: OK\n");
        return 0;
    }
    char buf[256];
    printf("=== System Status Report ===\n");
    while (fgets(buf, sizeof(buf), f)) {
        printf("%s", buf);
    }
    fclose(f);
    return 0;
}
EOF

apt-get install -y -qq gcc > /dev/null 2>&1 || true
gcc -o /usr/local/bin/statuscheck /tmp/statuscheck.c
chmod 4755 /usr/local/bin/statuscheck
rm /tmp/statuscheck.c
OUTER
success "SUID binary planted at /usr/local/bin/statuscheck"

# Step 6: Stop and lock the template
info "Stopping Docker containers inside template..."
lxc exec "$TEMPLATE" -- bash -c 'docker stop victim-host attacker-recon attacker-dos >/dev/null 2>&1 || true'
info "Stopping template container..."
lxc stop "$TEMPLATE"

echo ""
echo "Image is ready to clone."
echo "Next: bash 01_deploy_ctf.sh 1"
