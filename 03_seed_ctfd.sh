#!/usr/bin/env bash
# ============================================================
# PocketCTF — Script 03: Seed CTFd with Challenges via API
# Usage: bash 03_seed_ctfd.sh <CTFD_URL> <API_TOKEN>
#
# How to get your API token:
#   1. Go to http://<host-ip>:8000/settings
#   2. Click "Access Tokens" → Generate
#   3. Copy the token and paste it below or pass as argument
# ============================================================
set -euo pipefail

CTFD_URL="${1:-http://localhost:8000}"
API_TOKEN="${2:-}"

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
info()    { echo -e "[INFO]  $*"; }
success() { echo -e "[OK]    $*"; }
die()     { echo -e "[ERROR] $*" >&2; exit 1; }

[[ -z "$API_TOKEN" ]] && die "Usage: $0 <ctfd_url> <api_token>\nGet token from: ${CTFD_URL}/settings → Access Tokens"

echo "PocketCTF — CTFd Challenge Seeder"
echo "12 Challenges | 2375 Points"
echo ""
info "Target CTFd: $CTFD_URL"
echo ""

# ── Helper to create a challenge and return its ID ───────────
create_challenge() {
  local name="$1" desc="$2" category="$3" value="$4"
  local response
  response=$(curl -sf \
    -H "Authorization: Token ${API_TOKEN}" \
    -H "Content-Type: application/json" \
    -X POST "${CTFD_URL}/api/v1/challenges" \
    -d "{\"name\":\"${name}\",\"description\":\"${desc}\",\"value\":${value},\"category\":\"${category}\",\"type\":\"standard\",\"state\":\"visible\"}")
  echo "$response" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['id'])"
}

# ── Helper to add a flag to a challenge ──────────────────────
add_flag() {
  local challenge_id="$1" flag="$2"
  curl -sf \
    -H "Authorization: Token ${API_TOKEN}" \
    -H "Content-Type: application/json" \
    -X POST "${CTFD_URL}/api/v1/flags" \
    -d "{\"challenge\":${challenge_id},\"type\":\"static\",\"content\":\"${flag}\"}" > /dev/null
}

# ── Helper to add a hint ──────────────────────────────────────
add_hint() {
  local challenge_id="$1" hint="$2" cost="$3"
  curl -sf \
    -H "Authorization: Token ${API_TOKEN}" \
    -H "Content-Type: application/json" \
    -X POST "${CTFD_URL}/api/v1/hints" \
    -d "{\"challenge_id\":${challenge_id},\"content\":\"${hint}\",\"cost\":${cost}}" > /dev/null
}

# ═══════════════════════════════════════════════════════════════
#                    TIER 1: NETWORK FORENSICS
#                    (Wireshark-based warm-ups)
# ═══════════════════════════════════════════════════════════════

# ── Challenge 1 — "Who's the Target?" (75 pts) ───────────────
info "Creating Challenge 1: Who's the Target?"
DESC="Open Wireshark on the \`ctf-net\` bridge interface. Someone is getting hammered with traffic. \
What is the IP address of the victim host?\\n\\n\
**Flag format:** \`CoC{x_x_x_x}\` (replace dots with underscores)"
CID=$(create_challenge "Who's the Target?" "$DESC" "Network Forensics" 75)
add_flag "$CID" "CoC{172_20_0_2}"
add_hint "$CID" "The victim is the one receiving ALL the traffic. Apply the Wireshark display filter: ip.dst == 172.20.0.2 and count." 5
success "Challenge 1 created (ID: $CID)"

# ── Challenge 2 — "The Hammer" (100 pts) ─────────────────────
info "Creating Challenge 2: The Hammer"
DESC="A machine on the internal network is sending a massive, relentless wave of packets to the victim. \
Capture the traffic on the Docker bridge using Wireshark.\\n\\n\
What type of attack is this? Look at the TCP flags carefully.\\n\\n\
**Flag format:** \`CoC{attack_type}\` (lowercase, underscore-separated)"
CID=$(create_challenge "The Hammer" "$DESC" "Network Forensics" 100)
add_flag "$CID" "CoC{syn_flood}"
add_hint "$CID" "Apply this Wireshark filter: tcp.flags.syn == 1 && tcp.flags.ack == 0. What do you see?" 10
add_hint "$CID" "The SYN flag is set, but no ACK ever comes back. This is a half-open connection attack." 20
success "Challenge 2 created (ID: $CID)"

# ── Challenge 3 — "The Spy" (150 pts) ────────────────────────
info "Creating Challenge 3: The Spy"
DESC="Besides the brute-force attacker, another machine is quietly probing the victim — \
methodically scanning each port in sequence.\\n\\n\
What reconnaissance tool is it using? Identify it from the traffic signature.\\n\\n\
**Flag format:** \`CoC{tool_name}\` (lowercase)"
CID=$(create_challenge "The Spy" "$DESC" "Network Forensics" 150)
add_flag "$CID" "CoC{nmap}"
add_hint "$CID" "Filter by the second attacker IP: ip.src == 172.20.0.3. The pattern is systematic and sequential." 10
add_hint "$CID" "The packet has a distinctive TTL and window size signature. The tool has a penguin mascot." 25
success "Challenge 3 created (ID: $CID)"

# ── Challenge 4 — "Name the Killers" (200 pts) ───────────────
info "Creating Challenge 4: Name the Killers"
DESC="Two attackers. Two missions. One victim.\\n\\n\
You have identified the victim. Now identify both attacker IPs.\\n\
Submit them sorted numerically, separated by the word 'and'.\\n\\n\
**Flag format:** \`CoC{x_x_x_x_and_y_y_y_y}\` (dots → underscores)"
CID=$(create_challenge "Name the Killers" "$DESC" "Network Forensics" 200)
add_flag "$CID" "CoC{172_20_0_3_and_172_20_0_4}"
add_hint "$CID" "Use Statistics → Conversations in Wireshark. Sort by bytes sent. The top talkers are your attackers." 15
success "Challenge 4 created (ID: $CID)"

# ── Challenge 5 — "The Fingerprint" (300 pts) ────────────────
info "Creating Challenge 5: The Fingerprint"
DESC="The DoS attacker is hammering a specific port on the victim. Which port number is it targeting?\\n\\n\
Additionally — what is the TTL value in the SYN flood packets? Combine both answers.\\n\\n\
**Flag format:** \`CoC{port_TTL}\` (e.g. CoC{80_64})"
CID=$(create_challenge "The Fingerprint" "$DESC" "Advanced Forensics" 300)
add_flag "$CID" "CoC{80_64}"
add_hint "$CID" "Filter: tcp.flags.syn == 1 && ip.src == 172.20.0.4. Expand a packet and look at the TCP destination port and IP TTL." 25
success "Challenge 5 created (ID: $CID)"

# ═══════════════════════════════════════════════════════════════
#                 TIER 2: SYSTEM INVESTIGATION
#            (Requires terminal access + docker exec)
# ═══════════════════════════════════════════════════════════════

echo ""
info "── Tier 2: System Investigation Challenges ──"
echo ""

# ── Challenge 6 — "Hidden in Plain Sight" (100 pts) ──────────
info "Creating Challenge 6: Hidden in Plain Sight"
DESC="The victim web server seems to be leaking sensitive information in its HTTP responses.\\n\\n\
Use \`curl\` or inspect the traffic in Wireshark to examine the server's response headers carefully.\\n\\n\
\`\`\`bash\\ncurl -I http://172.20.0.2\\n\`\`\`\\n\\n\
**Flag format:** \`CoC{...}\`"
CID=$(create_challenge "Hidden in Plain Sight" "$DESC" "Web Forensics" 100)
add_flag "$CID" "CoC{http_headers_are_leaky}"
add_hint "$CID" "HTTP response headers can contain more than just Content-Type. Look for anything unusual or custom." 10
add_hint "$CID" "The flag is in a custom response header. Try: curl -I http://172.20.0.2 and read every header." 20
success "Challenge 6 created (ID: $CID)"

# ── Challenge 7 — "The Crontab Conspiracy" (200 pts) ─────────
info "Creating Challenge 7: The Crontab Conspiracy"
DESC="An attacker has established persistence on the victim host. They're using a common Linux scheduling mechanism to maintain their foothold.\\n\\n\
Get a shell inside the victim container and investigate:\\n\
\`\`\`bash\\ndocker exec -it victim-host bash\\n\`\`\`\\n\\n\
Find the persistence mechanism and the secret it's writing.\\n\\n\
**Flag format:** \`CoC{...}\`"
CID=$(create_challenge "The Crontab Conspiracy" "$DESC" "System Forensics" 200)
add_flag "$CID" "CoC{persistence_via_cron}"
add_hint "$CID" "Common persistence methods in Linux: cron jobs, systemd services, bashrc modifications..." 15
add_hint "$CID" "Inside the victim container, check: cat /etc/cron.d/* or crontab -l. Also look for hidden log files." 30
add_hint "$CID" "The cron job writes to a hidden file. Try: find / -name '.*' -type f 2>/dev/null | grep log" 40
success "Challenge 7 created (ID: $CID)"

# ── Challenge 8 — "Decode the Exfil" (250 pts) ───────────────
info "Creating Challenge 8: Decode the Exfil"
DESC="The SOC team captured suspicious DNS queries from an internal host. The data appears to be encoded in the subdomain labels — a classic data exfiltration technique.\\n\\n\
Check the evidence folder on your Desktop:\\n\
\`\`\`\\n~/Desktop/evidence/suspicious_dns_capture.txt\\n\`\`\`\\n\\n\
Decode the exfiltrated data to find the flag.\\n\\n\
**Flag format:** \`CoC{...}\`"
CID=$(create_challenge "Decode the Exfil" "$DESC" "Crypto / Forensics" 250)
add_flag "$CID" "CoC{dns_tunneling_detected}"
add_hint "$CID" "The subdomain labels look like base64-encoded data. Try decoding them." 15
add_hint "$CID" "Focus on Query #3 — the first label before the first dot. Decode it with: echo '<data>' | base64 -d" 30
success "Challenge 8 created (ID: $CID)"

# ── Challenge 9 — "The Backdoor" (300 pts) ───────────────────
info "Creating Challenge 9: The Backdoor"
DESC="Intel suggests the victim server has been compromised. A backdoor has been planted somewhere deep in the filesystem.\\n\\n\
Get a shell in the victim container and hunt for it:\\n\
\`\`\`bash\\ndocker exec -it victim-host bash\\n\`\`\`\\n\\n\
Find the hidden file, read its contents, and extract the flag. There may also be a suspicious systemd service pointing to it.\\n\\n\
**Flag format:** \`CoC{...}\`"
CID=$(create_challenge "The Backdoor" "$DESC" "System Forensics" 300)
add_flag "$CID" "CoC{never_trust_hidden_files}"
add_hint "$CID" "Hidden directories start with a dot. Try: find / -name '.*' -type d 2>/dev/null" 20
add_hint "$CID" "Check /etc/systemd/system/ for suspicious services. One of them points to the backdoor script." 40
add_hint "$CID" "The backdoor is at /usr/lib/.hidden/backdoor.sh — the flag is in a comment inside." 50
success "Challenge 9 created (ID: $CID)"

# ── Challenge 10 — "Log Detective" (250 pts) ─────────────────
info "Creating Challenge 10: Log Detective"
DESC="The recon attacker isn't just scanning ports — it's also making HTTP requests to the victim web server.\\n\\n\
Examine the victim's web server access logs. One of the requests has a very suspicious User-Agent string.\\n\\n\
\`\`\`bash\\ndocker logs victim-host\\n\`\`\`\\n\\n\
**Flag format:** \`CoC{...}\`"
CID=$(create_challenge "Log Detective" "$DESC" "Log Analysis" 250)
add_flag "$CID" "CoC{user_agent_exfiltration}"
add_hint "$CID" "Web servers log every request. The access log shows IP, URL, User-Agent, etc." 15
add_hint "$CID" "Use grep to search the logs: docker logs victim-host 2>&1 | grep -i 'CoC'" 35
success "Challenge 10 created (ID: $CID)"

# ═══════════════════════════════════════════════════════════════
#                    TIER 3: ADVANCED
#                  (Requires deeper skills)
# ═══════════════════════════════════════════════════════════════

echo ""
info "── Tier 3: Advanced Challenges ──"
echo ""

# ── Challenge 11 — "Privilege Escalation" (350 pts) ──────────
info "Creating Challenge 11: Privilege Escalation"
DESC="A system administrator left a suspicious binary on this machine. It has special permissions that let it do things a normal user cannot.\\n\\n\
Your task:\\n\
1. Find binaries with SUID permissions\\n\
2. Figure out what the suspicious one does\\n\
3. Use it to read a file you normally can't access\\n\\n\
\`\`\`bash\\nfind / -perm -4000 -type f 2>/dev/null\\n\`\`\`\\n\\n\
**Flag format:** \`CoC{...}\`"
CID=$(create_challenge "Privilege Escalation" "$DESC" "System Security" 350)
add_flag "$CID" "CoC{suid_is_dangerous}"
add_hint "$CID" "SUID binaries run with the file owner's permissions (often root). Find them with: find / -perm -4000 2>/dev/null" 20
add_hint "$CID" "There's a binary called 'statuscheck' in /usr/local/bin/. Try running it and see what it outputs." 40
add_hint "$CID" "The SUID binary reads /root/flag.txt — a file you can't read as a normal user. Just run: /usr/local/bin/statuscheck" 60
success "Challenge 11 created (ID: $CID)"

# ── Challenge 12 — "Packet Surgeon" (400 pts) ────────────────
info "Creating Challenge 12: Packet Surgeon"
DESC="The recon attacker is doing more than just port scanning. Every ~45 seconds, it sends an HTTP request to the victim with a custom header containing hex-encoded data.\\n\\n\
Your mission:\\n\
1. Capture the traffic between the recon attacker (172.20.0.3) and victim (172.20.0.2)\\n\
2. Find the HTTP request with the custom \`X-Payload\` header\\n\
3. Decode the hex payload to reveal the flag\\n\\n\
**Wireshark filter hint:** \`http.request && ip.src == 172.20.0.3\`\\n\\n\
**Flag format:** \`CoC{...}\`"
CID=$(create_challenge "Packet Surgeon" "$DESC" "Advanced Forensics" 400)
add_flag "$CID" "CoC{deep_packet_inspection_ftw}"
add_hint "$CID" "In Wireshark, filter for HTTP requests from the recon attacker. Expand the HTTP headers in the packet details pane." 25
add_hint "$CID" "The X-Payload header contains a hex string. Copy it and decode: echo '<hex>' | xxd -r -p" 50
add_hint "$CID" "The hex is: 436f437b646565705f7061636b65745f696e7370656374696f6e5f6674777d. Decode it!" 75
success "Challenge 12 created (ID: $CID)"

# ═══════════════════════════════════════════════════════════════
echo "Challenges seeded successfully."
echo "Total: 12 challenges (2375 pts)"
echo "View at: ${CTFD_URL}/admin/challenges"
echo ""
