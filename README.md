# PocketCTF — MVP Setup Guide

## Architecture

```
TEACHER'S MACHINE (runs everything)
├── Flask app          :5000   ← teacher dashboard
├── ctf-attacker       :7681   ← attacker web terminal (Student A)
├── ctf-victim         :7682   ← victim web terminal   (Student B)
└── Docker bridge: ctf-net     ← both containers share this; nmap works!

STUDENT A's BROWSER  →  http://<teacher-ip>:5000/student/attacker
                     →  http://<teacher-ip>:7681  (terminal)

STUDENT B's BROWSER  →  http://<teacher-ip>:5000/student/victim
                     →  http://<teacher-ip>:7682  (terminal)
```

**All containers run on the teacher's machine.** Students connect via browser over LAN.
nmap works because both containers share the `ctf-net` Docker bridge — they can reach each other via hostname (`victim`, `attacker`).

**Database:** SQLite (`ctf.db`) — zero setup, file-based, perfect for MVP.

---

## Step 1 — Modify your Dockerfiles

Add these lines **at the end** of your existing `Dockerfile.attacker`:

```dockerfile
# Install ttyd (web terminal)
RUN apt-get update && apt-get install -y wget && \
    wget -q -O /usr/local/bin/ttyd \
      https://github.com/tsl0922/ttyd/releases/download/1.7.7/ttyd.x86_64 && \
    chmod +x /usr/local/bin/ttyd

COPY attacker-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
EXPOSE 7681
CMD ["/entrypoint.sh"]
```

Add these lines **at the end** of your existing `Dockerfile.victim`:

```dockerfile
RUN apt-get update && apt-get install -y wget && \
    wget -q -O /usr/local/bin/ttyd \
      https://github.com/tsl0922/ttyd/releases/download/1.7.7/ttyd.x86_64 && \
    chmod +x /usr/local/bin/ttyd

COPY victim-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
EXPOSE 7682
CMD ["/entrypoint.sh"]
```

> **Apple Silicon (M1/M2/M3)?** Replace `ttyd.x86_64` with `ttyd.aarch64` in both blocks.

---

## Step 2 — Build images

```bash
# From your project directory (where Dockerfiles live)
docker build -f Dockerfile.attacker -t ctf-attacker .
docker build -f Dockerfile.victim   -t ctf-victim   .
```

---

## Step 3 — Set up Flask app

```bash
# Copy pocketctf/ files next to your Dockerfiles, then:
pip install -r requirements.txt
python app.py
```

The app starts on `http://0.0.0.0:5000`.

---

## Step 4 — Run a session

1. **Teacher** opens `http://localhost:5000` (or use the LAN IP shown in terminal)
2. Enter student names → click **▶ Start Session**
3. Wait ~5 seconds for containers to start (status indicators go green)
4. Share URLs with students:
   - Student A (Attacker): `http://<teacher-ip>:5000/student/attacker`
   - Student B (Victim/Defender): `http://<teacher-ip>:5000/student/victim`
5. Students click **OPEN TERMINAL** to get their shell

---

## Step 5 — Add CTF challenges

On the teacher dashboard, use the **Flag Management** panel:

| Field | Example |
|---|---|
| Flag String | `FLAG{nmap_found_port_22}` |
| Title | `Port Scan Discovery` |
| Description | `Used nmap to find the open SSH port` |
| Points | `100` |
| Visible To | `Attacker` |

Students submit flags via the Student Portal. Scores update on the leaderboard (auto-refresh every 15s, or hit ↺).

---

## Networking Notes

- The containers are named `attacker` and `victim` within Docker's `ctf-net` bridge
- From the attacker container: `nmap -sV victim` resolves correctly
- From the victim container: `ping attacker` works too
- Students **cannot** reach each other's machines directly — all traffic goes container-to-container inside Docker on the teacher's machine

---

## File Layout

```
your-project/
├── Dockerfile.attacker          ← your existing file + ttyd lines added
├── Dockerfile.victim            ← your existing file + ttyd lines added
├── attacker.sh                  ← your existing script (called by entrypoint)
├── attacker-entrypoint.sh       ← new: starts ttyd after setup
├── victim-entrypoint.sh         ← new: starts ttyd
└── pocketctf/
    ├── app.py                   ← Flask backend
    ├── requirements.txt
    ├── ctf.db                   ← auto-created on first run
    └── templates/
        ├── dashboard.html       ← teacher UI
        └── student.html         ← student UI
```

---

## Stopping

Click **■ Stop Session** in the dashboard — this stops and removes both containers.
The SQLite DB persists between sessions, so scores are kept.

To wipe scores: `rm pocketctf/ctf.db` and restart Flask.
