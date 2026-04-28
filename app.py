import logging
import re
import socket
import sqlite3

import docker
from flask import Flask, g, jsonify, render_template, request

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("pocketctf")
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("docker").setLevel(logging.WARNING)

app = Flask(__name__)
DATABASE  = "ctf.db"
ATTACKER_IMAGE = "ctf-attacker"
VICTIM_IMAGE   = "ctf-victim"
BASE_PORT = 7681   # port pairs allocated upward from here

log.info("Connecting to Docker daemon...")
try:
    docker_client = docker.from_env()
    log.info("Docker daemon connected: v%s", docker_client.version()["Version"])
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
        db.close()


def init_db():
    log.info("Initialising database at: %s", DATABASE)
    with app.app_context():
        db = get_db()
        # Drop sessions table if it has the old single-session schema
        try:
            db.execute("SELECT attacker_slug FROM sessions LIMIT 1")
            log.info("Sessions table schema is current")
        except sqlite3.OperationalError:
            log.warning("Old sessions schema detected — dropping and recreating")
            db.execute("DROP TABLE IF EXISTS sessions")

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
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                player_name  TEXT    NOT NULL,
                player_role  TEXT    NOT NULL,
                flag_id      INTEGER NOT NULL,
                submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(player_name, flag_id),
                FOREIGN KEY (flag_id) REFERENCES flags(id)
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                attacker_name      TEXT,
                victim_name        TEXT,
                attacker_slug      TEXT,
                victim_slug        TEXT,
                attacker_container TEXT,
                victim_container   TEXT,
                attacker_port      INTEGER,
                victim_port        INTEGER,
                network_name       TEXT,
                status             TEXT DEFAULT 'stopped',
                created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        db.commit()
    log.info("Database ready — tables: flags, submissions, sessions")


# ── Docker helpers ────────────────────────────────────────────────────────────

def get_host_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def get_container(name):
    if not name:
        return None
    try:
        c = docker_client.containers.get(name)
        log.debug("Container '%s' found — status: %s", name, c.status)
        return c
    except docker.errors.NotFound:
        log.debug("Container '%s' does not exist", name)
        return None


def container_status(name):
    c = get_container(name)
    return c.status if c else "stopped"


def ensure_network(name):
    try:
        docker_client.networks.get(name)
        log.debug("Network '%s' already exists", name)
    except docker.errors.NotFound:
        log.info("Creating Docker network '%s'", name)
        docker_client.networks.create(name, driver="bridge")
        log.info("Network '%s' created", name)


def sanitize_slug(name: str) -> str:
    """Convert student name to a Docker/URL-safe lowercase slug."""
    slug = name.lower().replace(" ", "-")
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug[:20] or "player"


def allocate_ports():
    """Find the next free consecutive attacker+victim port pair."""
    db = get_db()
    rows = db.execute(
        "SELECT attacker_port, victim_port FROM sessions WHERE status='running'"
    ).fetchall()
    used = set()
    for r in rows:
        if r["attacker_port"]: used.add(r["attacker_port"])
        if r["victim_port"]:   used.add(r["victim_port"])
    port = BASE_PORT
    while port in used or (port + 1) in used:
        port += 2
    log.debug("Allocated ports: attacker=%d victim=%d", port, port + 1)
    return port, port + 1


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def dashboard():
    log.info("GET / — rendering teacher dashboard")
    db = get_db()
    flags = db.execute("SELECT * FROM flags ORDER BY for_role, points").fetchall()
    leaderboard = db.execute("""
        SELECT s.player_name, s.player_role,
               SUM(f.points) AS total_points,
               COUNT(*)      AS flags_captured
        FROM   submissions s
        JOIN   flags f ON s.flag_id = f.id
        GROUP  BY s.player_name
        ORDER  BY total_points DESC
    """).fetchall()
    return render_template(
        "dashboard.html",
        flags=flags,
        leaderboard=leaderboard,
        host_ip=get_host_ip(),
    )


@app.route("/start", methods=["POST"])
def start_session():
    attacker_name = request.form.get("attacker_name", "").strip()
    victim_name   = request.form.get("victim_name",   "").strip()
    if not attacker_name or not victim_name:
        return jsonify({"error": "Both attacker and victim names are required"}), 400

    attacker_slug = sanitize_slug(attacker_name)
    victim_slug   = sanitize_slug(victim_name)
    attacker_container = f"{attacker_slug}-ctf-attacker"
    victim_container   = f"{victim_slug}-ctf-victim"
    network_name       = f"{attacker_slug}-{victim_slug}-net"

    log.info("POST /start — %s (%s) vs %s (%s)",
             attacker_name, attacker_slug, victim_name, victim_slug)

    db = get_db()
    conflict = db.execute(
        """SELECT id FROM sessions WHERE status='running'
           AND (attacker_slug=? OR victim_slug=? OR attacker_slug=? OR victim_slug=?)""",
        (attacker_slug, attacker_slug, victim_slug, victim_slug),
    ).fetchone()
    if conflict:
        log.warning("Name conflict — slug already used in a running session")
        return jsonify({"error": "A running session already uses one of these names"}), 400

    try:
        attacker_port, victim_port = allocate_ports()
        ensure_network(network_name)

        v = get_container(victim_container)
        if not v:
            log.info("Creating victim '%s' on port %d", victim_container, victim_port)
            docker_client.containers.run(
                VICTIM_IMAGE, name=victim_container,
                network=network_name, hostname="victim",
                ports={"7682/tcp": victim_port},
                detach=True, tty=True, cap_add=["NET_ADMIN", "NET_RAW"],
            )
        elif v.status != "running":
            log.info("Victim exists (%s) — restarting", v.status)
            v.start()

        a = get_container(attacker_container)
        if not a:
            log.info("Creating attacker '%s' on port %d", attacker_container, attacker_port)
            docker_client.containers.run(
                ATTACKER_IMAGE, name=attacker_container,
                network=network_name, hostname="attacker",
                ports={"7681/tcp": attacker_port},
                detach=True, tty=True, cap_add=["NET_ADMIN", "NET_RAW"],
            )
        elif a.status != "running":
            log.info("Attacker exists (%s) — restarting", a.status)
            a.start()

        db.execute(
            """INSERT INTO sessions
               (attacker_name, victim_name, attacker_slug, victim_slug,
                attacker_container, victim_container,
                attacker_port, victim_port, network_name, status)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (attacker_name, victim_name, attacker_slug, victim_slug,
             attacker_container, victim_container,
             attacker_port, victim_port, network_name, "running"),
        )
        db.commit()
        host_ip = get_host_ip()
        log.info("Session started — /student/%s/attacker | /student/%s/victim",
                 attacker_slug, victim_slug)
        return jsonify({
            "status":        "started",
            "attacker_name": attacker_name,
            "victim_name":   victim_name,
            "attacker_port": attacker_port,
            "victim_port":   victim_port,
            "attacker_url":  f"http://{host_ip}:5000/student/{attacker_slug}/attacker",
            "victim_url":    f"http://{host_ip}:5000/student/{victim_slug}/victim",
        })
    except Exception as e:
        log.error("Failed to start session: %s", e, exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/stop/<int:session_id>", methods=["POST"])
def stop_session(session_id):
    log.info("POST /stop/%d", session_id)
    db = get_db()
    session = db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
    if not session:
        return jsonify({"error": "Session not found"}), 404

    errors = []
    for cname in [session["attacker_container"], session["victim_container"]]:
        c = get_container(cname)
        if c:
            try:
                log.info("Stopping '%s'...", cname)
                c.stop(timeout=5)
                c.remove()
                log.info("'%s' removed", cname)
            except Exception as e:
                log.error("Error stopping '%s': %s", cname, e)
                errors.append(str(e))

    if session["network_name"]:
        try:
            docker_client.networks.get(session["network_name"]).remove()
            log.info("Network '%s' removed", session["network_name"])
        except Exception as e:
            log.warning("Could not remove network '%s': %s", session["network_name"], e)

    db.execute("UPDATE sessions SET status='stopped' WHERE id=?", (session_id,))
    db.commit()
    log.info("Session %d marked as stopped", session_id)
    if errors:
        return jsonify({"status": "partial", "errors": errors})
    return jsonify({"status": "stopped"})


@app.route("/status")
def status():
    db = get_db()
    sessions = db.execute("SELECT * FROM sessions ORDER BY id DESC").fetchall()
    result = []
    for s in sessions:
        a_st = container_status(s["attacker_container"])
        v_st = container_status(s["victim_container"])
        result.append({
            "id":               s["id"],
            "attacker_name":    s["attacker_name"],
            "victim_name":      s["victim_name"],
            "attacker_slug":    s["attacker_slug"],
            "victim_slug":      s["victim_slug"],
            "attacker_status":  a_st,
            "victim_status":    v_st,
            "attacker_port":    s["attacker_port"],
            "victim_port":      s["victim_port"],
            "status":           s["status"],
            "created_at":       s["created_at"],
        })
    return jsonify(result)


@app.route("/logs/<int:session_id>/<role>")
def logs(session_id, role):
    db = get_db()
    session = db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
    if not session:
        return jsonify({"logs": "Session not found."}), 404
    name = session["attacker_container"] if role == "attacker" else session["victim_container"]
    c = get_container(name)
    if not c:
        return jsonify({"logs": "Container not running."})
    return jsonify({"logs": c.logs(tail=80).decode("utf-8", errors="replace")})


# ── Flags ─────────────────────────────────────────────────────────────────────

@app.route("/flags/add", methods=["POST"])
def add_flag():
    d = request.form
    log.info("POST /flags/add — title: '%s', points: %s, role: %s",
             d.get("title"), d.get("points"), d.get("for_role"))
    db = get_db()
    try:
        db.execute(
            "INSERT INTO flags (flag, title, description, points, for_role) VALUES (?,?,?,?,?)",
            (d["flag"], d["title"], d["description"], int(d["points"]), d["for_role"]),
        )
        db.commit()
        log.info("Flag '%s' added", d.get("title"))
        return jsonify({"status": "added"})
    except sqlite3.IntegrityError:
        log.warning("Duplicate flag: '%s'", d.get("flag"))
        return jsonify({"error": "Flag already exists"}), 400


@app.route("/flags/delete/<int:flag_id>", methods=["DELETE"])
def delete_flag(flag_id):
    log.info("DELETE /flags/delete/%d", flag_id)
    db = get_db()
    db.execute("DELETE FROM flags WHERE id = ?", (flag_id,))
    db.commit()
    return jsonify({"status": "deleted"})


# ── Student portal ────────────────────────────────────────────────────────────

@app.route("/student/<slug>/<role>")
def student_portal(slug, role):
    if role not in ("attacker", "victim"):
        return "Invalid role", 404
    db = get_db()
    col = "attacker_slug" if role == "attacker" else "victim_slug"
    session = db.execute(
        f"SELECT * FROM sessions WHERE {col}=? AND status='running'", (slug,)
    ).fetchone()
    if not session:
        return (
            f"<h2 style='font-family:monospace;color:red;padding:40px'>"
            f"No active session found for '{slug}' as {role}.</h2>",
            404,
        )
    port = session["attacker_port"] if role == "attacker" else session["victim_port"]
    flags = db.execute(
        "SELECT id, title, description, points FROM flags WHERE for_role=? OR for_role='both'",
        (role,),
    ).fetchall()
    return render_template(
        "student.html",
        role=role,
        host_ip=get_host_ip(),
        terminal_port=port,
        flags=flags,
    )


@app.route("/submit-flag", methods=["POST"])
def submit_flag():
    data = request.json or {}
    player_name = data.get("player_name", "").strip()
    player_role = data.get("player_role", "").strip()
    flag        = data.get("flag", "").strip()
    log.info("POST /submit-flag — player: '%s' (%s), flag: '%s'",
             player_name, player_role, flag)
    if not all([player_name, player_role, flag]):
        return jsonify({"error": "Missing fields"}), 400
    db = get_db()
    row = db.execute("SELECT * FROM flags WHERE flag = ?", (flag,)).fetchone()
    if not row:
        log.warning("Wrong flag by '%s': '%s'", player_name, flag)
        return jsonify({"error": "Wrong flag. Keep trying!"}), 400
    try:
        db.execute(
            "INSERT INTO submissions (player_name, player_role, flag_id) VALUES (?,?,?)",
            (player_name, player_role, row["id"]),
        )
        db.commit()
        log.info("Flag captured! player='%s', challenge='%s', points=%d",
                 player_name, row["title"], row["points"])
        return jsonify({
            "success": True,
            "points":  row["points"],
            "title":   row["title"],
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
    log.info("Student URL format: http://%s:5000/student/<name>/attacker|victim", host_ip)
    log.info("=" * 55)
    app.run(host="0.0.0.0", port=5000, debug=False)
