import logging
import os
import socket
import sqlite3

import docker
from flask import Flask, g, jsonify, redirect, render_template, request, url_for

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("pocketctf")

app = Flask(__name__)
DATABASE = "ctf.db"
NETWORK_NAME = "ctf-net"
ATTACKER_IMAGE = "ctf-attacker"
VICTIM_IMAGE = "ctf-victim"
ATTACKER_CONTAINER = "ctf-attacker"
VICTIM_CONTAINER = "ctf-victim"
ATTACKER_TTYD_PORT = 7681
VICTIM_TTYD_PORT = 7682

log.info("Connecting to Docker daemon...")
try:
    docker_client = docker.from_env()
    log.info("Docker daemon connected successfully: %s", docker_client.version()["Version"])
except Exception as e:
    log.critical("Failed to connect to Docker daemon: %s", e)
    raise


# ── DB helpers ────────────────────────────────────────────────────────────────

def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        log.debug("Opening new DB connection to %s", DATABASE)
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
    return db


@app.teardown_appcontext
def close_db(exc):
    db = getattr(g, "_database", None)
    if db:
        log.debug("Closing DB connection")
        db.close()


def init_db():
    log.info("Initialising database at: %s", DATABASE)
    with app.app_context():
        db = get_db()
        db.executescript("""
            CREATE TABLE IF NOT EXISTS flags (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                flag        TEXT    UNIQUE NOT NULL,
                title       TEXT    NOT NULL,
                description TEXT    NOT NULL,
                points      INTEGER NOT NULL DEFAULT 100,
                for_role    TEXT    NOT NULL DEFAULT 'attacker'
            );

            CREATE TABLE IF NOT EXISTS submissions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                player_name TEXT    NOT NULL,
                player_role TEXT    NOT NULL,
                flag_id     INTEGER NOT NULL,
                submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(player_name, flag_id),
                FOREIGN KEY (flag_id) REFERENCES flags(id)
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                attacker_name TEXT,
                victim_name   TEXT,
                status        TEXT DEFAULT 'stopped',
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        db.commit()
    log.info("Database initialised — tables: flags, submissions, sessions")


# ── Docker helpers ────────────────────────────────────────────────────────────

def get_host_ip():
    """Best-effort LAN IP detection."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        log.debug("Detected host LAN IP: %s", ip)
        return ip
    except Exception as e:
        log.warning("Could not detect host IP (%s) — falling back to 127.0.0.1", e)
        return "127.0.0.1"


def get_container(name):
    try:
        c = docker_client.containers.get(name)
        log.debug("Container '%s' found — status: %s", name, c.status)
        return c
    except docker.errors.NotFound:
        log.debug("Container '%s' does not exist", name)
        return None


def ensure_network():
    try:
        docker_client.networks.get(NETWORK_NAME)
        log.debug("Docker network '%s' already exists", NETWORK_NAME)
    except docker.errors.NotFound:
        log.info("Docker network '%s' not found — creating bridge network", NETWORK_NAME)
        docker_client.networks.create(NETWORK_NAME, driver="bridge")
        log.info("Docker network '%s' created", NETWORK_NAME)


def container_status(name):
    c = get_container(name)
    return c.status if c else "stopped"


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def dashboard():
    log.info("GET / — rendering teacher dashboard")
    db = get_db()
    flags = db.execute("SELECT * FROM flags ORDER BY for_role, points").fetchall()
    log.debug("Loaded %d flag(s) from DB", len(flags))
    leaderboard = db.execute("""
        SELECT s.player_name, s.player_role,
               SUM(f.points) AS total_points,
               COUNT(*)      AS flags_captured
        FROM   submissions s
        JOIN   flags f ON s.flag_id = f.id
        GROUP  BY s.player_name
        ORDER  BY total_points DESC
    """).fetchall()
    log.debug("Leaderboard has %d player(s)", len(leaderboard))
    session = db.execute(
        "SELECT * FROM sessions ORDER BY id DESC LIMIT 1"
    ).fetchone()
    log.debug("Latest session status: %s", session["status"] if session else "none")

    a_status = container_status(ATTACKER_CONTAINER)
    v_status = container_status(VICTIM_CONTAINER)
    log.info("Container status — attacker: %s | victim: %s", a_status, v_status)

    return render_template(
        "dashboard.html",
        flags=flags,
        leaderboard=leaderboard,
        session=session,
        host_ip=get_host_ip(),
        attacker_port=ATTACKER_TTYD_PORT,
        victim_port=VICTIM_TTYD_PORT,
        attacker_status=a_status,
        victim_status=v_status,
    )


@app.route("/start", methods=["POST"])
def start_session():
    attacker_name = request.form.get("attacker_name", "Student A").strip()
    victim_name   = request.form.get("victim_name",   "Student B").strip()
    log.info("POST /start — attacker: '%s', victim: '%s'", attacker_name, victim_name)

    try:
        ensure_network()

        # --- Victim ---
        v = get_container(VICTIM_CONTAINER)
        if not v:
            log.info("Victim container '%s' not found — creating from image '%s'", VICTIM_CONTAINER, VICTIM_IMAGE)
            docker_client.containers.run(
                VICTIM_IMAGE,
                name=VICTIM_CONTAINER,
                network=NETWORK_NAME,
                hostname="victim",
                ports={f"{VICTIM_TTYD_PORT}/tcp": VICTIM_TTYD_PORT},
                detach=True,
                tty=True,
                cap_add=["NET_ADMIN", "NET_RAW"],
            )
            log.info("Victim container started — web terminal at port %d", VICTIM_TTYD_PORT)
        elif v.status != "running":
            log.info("Victim container exists but is '%s' — restarting", v.status)
            v.start()
            log.info("Victim container restarted")
        else:
            log.info("Victim container already running — skipping")

        # --- Attacker ---
        a = get_container(ATTACKER_CONTAINER)
        if not a:
            log.info("Attacker container '%s' not found — creating from image '%s'", ATTACKER_CONTAINER, ATTACKER_IMAGE)
            docker_client.containers.run(
                ATTACKER_IMAGE,
                name=ATTACKER_CONTAINER,
                network=NETWORK_NAME,
                hostname="attacker",
                ports={f"{ATTACKER_TTYD_PORT}/tcp": ATTACKER_TTYD_PORT},
                detach=True,
                tty=True,
                cap_add=["NET_ADMIN", "NET_RAW"],
            )
            log.info("Attacker container started — web terminal at port %d", ATTACKER_TTYD_PORT)
        elif a.status != "running":
            log.info("Attacker container exists but is '%s' — restarting", a.status)
            a.start()
            log.info("Attacker container restarted")
        else:
            log.info("Attacker container already running — skipping")

        db = get_db()
        db.execute(
            "INSERT INTO sessions (attacker_name, victim_name, status) VALUES (?,?,?)",
            (attacker_name, victim_name, "running"),
        )
        db.commit()
        log.info("Session recorded in DB — attacker: '%s', victim: '%s'", attacker_name, victim_name)
        return jsonify({"status": "started"})

    except Exception as e:
        log.error("Failed to start session: %s", e, exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/stop", methods=["POST"])
def stop_session():
    log.info("POST /stop — stopping all containers")
    errors = []
    for name in [ATTACKER_CONTAINER, VICTIM_CONTAINER]:
        c = get_container(name)
        if c:
            try:
                log.info("Stopping container '%s' (timeout=5s)...", name)
                c.stop(timeout=5)
                log.info("Container '%s' stopped — removing...", name)
                c.remove()
                log.info("Container '%s' removed", name)
            except Exception as e:
                log.error("Error stopping/removing '%s': %s", name, e)
                errors.append(str(e))
        else:
            log.debug("Container '%s' not found — nothing to stop", name)
    if errors:
        log.warning("Stop completed with errors: %s", errors)
        return jsonify({"status": "partial", "errors": errors})
    log.info("All containers stopped and removed successfully")
    return jsonify({"status": "stopped"})


@app.route("/status")
def status():
    return jsonify(
        {
            "attacker": container_status(ATTACKER_CONTAINER),
            "victim":   container_status(VICTIM_CONTAINER),
        }
    )


@app.route("/logs/<role>")
def logs(role):
    name = ATTACKER_CONTAINER if role == "attacker" else VICTIM_CONTAINER
    c = get_container(name)
    if not c:
        return jsonify({"logs": "Container not running."})
    return jsonify({"logs": c.logs(tail=60).decode("utf-8", errors="replace")})


# ── Flags ─────────────────────────────────────────────────────────────────────

@app.route("/flags/add", methods=["POST"])
def add_flag():
    d = request.form
    log.info("POST /flags/add — title: '%s', points: %s, role: %s", d.get("title"), d.get("points"), d.get("for_role"))
    db = get_db()
    try:
        db.execute(
            "INSERT INTO flags (flag, title, description, points, for_role) VALUES (?,?,?,?,?)",
            (d["flag"], d["title"], d["description"], int(d["points"]), d["for_role"]),
        )
        db.commit()
        log.info("Flag '%s' added successfully", d.get("title"))
        return jsonify({"status": "added"})
    except sqlite3.IntegrityError:
        log.warning("Duplicate flag rejected: '%s'", d.get("flag"))
        return jsonify({"error": "Flag already exists"}), 400


@app.route("/flags/delete/<int:flag_id>", methods=["DELETE"])
def delete_flag(flag_id):
    log.info("DELETE /flags/delete/%d", flag_id)
    db = get_db()
    db.execute("DELETE FROM flags WHERE id = ?", (flag_id,))
    db.commit()
    log.info("Flag id=%d deleted", flag_id)
    return jsonify({"status": "deleted"})


# ── Student portal ────────────────────────────────────────────────────────────

@app.route("/student/<role>")
def student_portal(role):
    if role not in ("attacker", "victim"):
        return "Invalid role", 404
    host_ip = get_host_ip()
    port = ATTACKER_TTYD_PORT if role == "attacker" else VICTIM_TTYD_PORT
    db = get_db()
    flags = db.execute(
        "SELECT id, title, description, points FROM flags WHERE for_role = ? OR for_role = 'both'",
        (role,),
    ).fetchall()
    return render_template(
        "student.html",
        role=role,
        host_ip=host_ip,
        terminal_port=port,
        flags=flags,
    )


@app.route("/submit-flag", methods=["POST"])
def submit_flag():
    data = request.json or {}
    player_name = data.get("player_name", "").strip()
    player_role = data.get("player_role", "").strip()
    flag        = data.get("flag", "").strip()
    log.info("POST /submit-flag — player: '%s' (%s), flag: '%s'", player_name, player_role, flag)

    if not all([player_name, player_role, flag]):
        log.warning("Flag submission rejected — missing fields")
        return jsonify({"error": "Missing fields"}), 400

    db = get_db()
    row = db.execute("SELECT * FROM flags WHERE flag = ?", (flag,)).fetchone()
    if not row:
        log.warning("Wrong flag submitted by '%s': '%s'", player_name, flag)
        return jsonify({"error": "Wrong flag. Keep trying!"}), 400

    try:
        db.execute(
            "INSERT INTO submissions (player_name, player_role, flag_id) VALUES (?,?,?)",
            (player_name, player_role, row["id"]),
        )
        db.commit()
        log.info("Flag captured! player='%s', challenge='%s', points=%d", player_name, row["title"], row["points"])
        return jsonify({
            "success": True,
            "points": row["points"],
            "title":  row["title"],
            "message": row["description"],
        })
    except sqlite3.IntegrityError:
        log.warning("Duplicate submission by '%s' for flag id=%d", player_name, row["id"])
        return jsonify({"error": "Already submitted this flag!"}), 400


@app.route("/leaderboard")
def leaderboard_api():
    db = get_db()
    rows = db.execute("""
        SELECT s.player_name, s.player_role,
               SUM(f.points) AS total_points,
               COUNT(*)      AS flags_captured
        FROM   submissions s
        JOIN   flags f ON s.flag_id = f.id
        GROUP  BY s.player_name
        ORDER  BY total_points DESC
    """).fetchall()
    return jsonify([dict(r) for r in rows])


if __name__ == "__main__":
    init_db()
    host_ip = get_host_ip()
    log.info("=" * 55)
    log.info("PocketCTF starting up")
    log.info("Teacher dashboard : http://%s:5000", host_ip)
    log.info("Attacker terminal : http://%s:%d", host_ip, ATTACKER_TTYD_PORT)
    log.info("Victim terminal   : http://%s:%d", host_ip, VICTIM_TTYD_PORT)
    log.info("=" * 55)
    app.run(host="0.0.0.0", port=5000, debug=False)
