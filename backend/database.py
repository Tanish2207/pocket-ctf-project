import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bluelab.db")

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row  # lets you access columns by name
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    # Users table — one row per trainee
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            namespace TEXT,         -- their K8s namespace e.g. trainee-alice
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Challenges table — the 3 CTF questions
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS challenges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            points INTEGER NOT NULL,
            flag TEXT NOT NULL      -- stored hashed ideally, plain for now
        )
    """)

    # Submissions table — who solved what and when
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            challenge_id INTEGER NOT NULL,
            solved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, challenge_id),  -- no double solving
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (challenge_id) REFERENCES challenges(id)
        )
    """)

    # Seed challenges (your 3 existing ones)
    cursor.execute("SELECT COUNT(*) FROM challenges")
    if cursor.fetchone()[0] == 0:
        challenges = [
            ("Who is Attacking?", "Check Suricata logs. Find the attacker's IP.", 100, "flag{172.20.0.11}"),
            ("What Attack?", "What type of scan was detected?", 100, "flag{PORT_SCAN}"),
            ("When Did It Start?", "Find the exact time the attack began (HH:MM:SS).", 200, "flag{HH:MM:SS}"),
        ]
        cursor.executemany(
            "INSERT INTO challenges (title, description, points, flag) VALUES (?,?,?,?)",
            challenges
        )

    conn.commit()
    conn.close()