# PocketCTF — Operator Runbook

**A portable, one-click cyber range for network security workshops.**

> Deploy isolated attack environments for each student in under 60 seconds.
> No cloud required — runs entirely on your laptop.

---

## Prerequisites

**None!** Run `setup_host.sh` on a clean Ubuntu system and it handles everything.

| Requirement | Installed by `setup_host.sh` |
|---|---|
| LXD (snap) | Yes |
| ZFS storage pool | Yes |
| `pocket-base` container (Docker, XFCE4, xRDP, Wireshark) | Yes |
| `scoreboard` container (Docker, CTFd) | Yes |

---

## Quick Start (Clean System → Live Event)

```bash
# Step 0: Bootstrap the host (ONCE, needs internet, ~15 min)
sudo bash setup_host.sh

# Step 1: Finalize image (ONCE, needs internet, ~10 min)
bash 00_finalize_image.sh

# Step 2: First-time CTFd setup
lxc start scoreboard
# Browser → http://localhost:8000 → complete setup wizard
# Settings → Access Tokens → Generate a token → copy it
lxc stop scoreboard

# Step 3: Seed challenges
lxc start scoreboard
sleep 15
bash 03_seed_ctfd.sh http://localhost:8000 YOUR_API_TOKEN
lxc stop scoreboard

# Step 4: Deploy event (event day!)
bash 01_deploy_ctf.sh 3    # for 3 players

# Step 5: Cleanup
bash 02_teardown_ctf.sh
```

---

## Configuration (Environment Variables)

All scripts are fully configurable via environment variables — **nothing is hardcoded**.

| Variable | Default | Used by |
|---|---|---|
| `TEMPLATE` | `pocket-base` | All scripts |
| `SCOREBOARD` | `scoreboard` | 01, 02 |
| `LXD_POOL_NAME` | `pocketctf-pool` | setup_host |
| `LXD_POOL_SIZE` | `30GB` | setup_host |
| `CONTAINER_USER` | `ubuntu` | setup_host |
| `CONTAINER_PASS` | `ubuntu` | setup_host |
| `UBUNTU_IMAGE` | `ubuntu:22.04` | setup_host |
| `BASE_RDP_PORT` | `3388` | 01 (player-1→3389, etc.) |
| `CTFD_HOST_PORT` | `8000` | 01 |
| `OVERRIDE_HOST_IP` | *(auto-detected)* | 01 |

Example: `TEMPLATE=my-custom-base bash 00_finalize_image.sh`

---

## Script Reference

| Script | Purpose | When to run |
|---|---|---|
| `setup_host.sh` | Install LXD, ZFS, create base containers | Once on a fresh host |
| `00_finalize_image.sh` | Build attack Docker images, plant CTF challenges | Once before first event |
| `01_deploy_ctf.sh <N>` | Clone N player containers, wire RDP, start CTFd | Event morning |
| `02_teardown_ctf.sh` | Delete all player containers, stop scoreboard | After event |
| `03_seed_ctfd.sh <url> <token>` | Create all 12 challenges in CTFd | Once after CTFd setup |

---

## Challenge Overview (12 Challenges, 2375 pts)

### Tier 1 — Network Forensics (825 pts)
Network Forensics challenges involve analyzing live attack traffic.

| # | Challenge | Points | Category |
|---|---|---|---|
| 1 | Who's the Target? | 75 | Network Forensics |
| 2 | The Hammer | 100 | Network Forensics |
| 3 | The Spy | 150 | Network Forensics |
| 4 | Name the Killers | 200 | Network Forensics |
| 5 | The Fingerprint | 300 | Advanced Forensics |

### Tier 2 — System Investigation (1100 pts)
System Investigation challenges require terminal access, log analysis, and investigation.

| # | Challenge | Points | Category |
|---|---|---|---|
| 6 | Hidden in Plain Sight | 100 | Web Forensics |
| 7 | The Crontab Conspiracy | 200 | System Forensics |
| 8 | Decode the Exfil | 250 | Crypto / Forensics |
| 9 | The Backdoor | 300 | System Forensics |
| 10 | Log Detective | 250 | Log Analysis |

### Tier 3 — Advanced (750 pts)
Advanced challenges require deeper security knowledge.

| # | Challenge | Points | Category |
|---|---|---|---|
| 11 | Privilege Escalation | 350 | System Security |
| 12 | Packet Surgeon | 400 | Advanced Forensics |

---

## During the Event

### Monitor container status
```bash
lxc list
```

### Check Docker inside a specific player
```bash
lxc exec player-1 -- docker ps
lxc exec player-1 -- docker logs attacker-dos --tail 20
```

### Restart a crashed attacker inside player's container
```bash
lxc exec player-1 -- docker restart attacker-dos
```

### View CTFd scoreboard from any device
```
http://<your-laptop-ip>:8000
```

---

## Student Instructions (hand out this section)

1. Open **Remmina** (or any RDP client)
2. Create a new connection:
   - **Protocol:** RDP
   - **Server:** `<IP given by instructor>:<PORT given to you>`
   - **Username:** `ubuntu`
   - **Password:** `ubuntu`
3. You are now inside your private cyber range.
4. Open **Wireshark**, select the `br-ctf-net` or `docker0` interface
5. Start capturing — you'll see live attack traffic
6. Answer the challenges at `http://<instructor-ip>:8000`
7. For system challenges, open a **Terminal** and use `docker exec` to investigate containers

---

## Quick Reference

| Item | Value |
|---|---|
| Template | `pocket-base` (configurable) |
| CTFd container | `scoreboard` (configurable) |
| CTFd web port | `8000` (configurable) |
| Player RDP ports | `3389`+N (configurable base) |
| Victim IP (inside player) | `172.20.0.2` |
| Recon attacker IP | `172.20.0.3` |
| DoS attacker IP | `172.20.0.4` |
| Container credentials | `ubuntu` / `ubuntu` |
| Flag format | `CoC{...}` |

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Docker not starting inside player | `lxc exec player-N -- systemctl restart docker` |
| Wireshark shows no interfaces | Run as root inside container: `sudo wireshark` |
| RDP can't connect from phone | Check that Wi-Fi is on same subnet |
| CTFd not reachable | `lxc exec scoreboard -- docker compose ps` |
| ZFS pool full | `lxc storage info <pool-name>` |
| Host IP not detected | Use `OVERRIDE_HOST_IP=x.x.x.x bash 01_deploy_ctf.sh 3` |
| LXD not found after install | `export PATH=/snap/bin:$PATH` |