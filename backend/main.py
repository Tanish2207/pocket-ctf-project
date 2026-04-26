import logging

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from passlib.context import CryptContext
from database import init_db, get_db
from provisioner import provision_trainee, deprovision_trainee

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI()

# Allow frontend to talk to backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

pwd_context = CryptContext(schemes=["bcrypt"])

# ── Startup ──────────────────────────────────────────────
@app.on_event("startup")
def startup():
    init_db()

# ── Models ───────────────────────────────────────────────
class RegisterRequest(BaseModel):
    username: str
    password: str

class LoginRequest(BaseModel):
    username: str
    password: str

class FlagSubmission(BaseModel):
    username: str
    challenge_id: int
    flag: str

# ── Routes ───────────────────────────────────────────────

@app.post("/register")
def register(req: RegisterRequest):
    """
    1. Hash password
    2. Insert user into DB
    3. Trigger K8s provisioning (spin up victim + attacker pods)
    """
    logger.info("[REGISTER] Step 1 — Request received for username='%s'", req.username)

    # Step 2: Hash password
    db = get_db()
    # hashed = pwd_context.hash(req.password)
    namespace = f"trainee-{req.username.lower()}"
    logger.info("[REGISTER] Step 2 — Password hashed, namespace='%s'", namespace)

    # Step 3: Insert into DB
    try:
        db.execute(
            "INSERT INTO users (username, password, namespace) VALUES (?,?,?)",
            (req.username, req.password, namespace)
        )
        db.commit()
        logger.info("[REGISTER] Step 3 — User '%s' inserted into DB successfully", req.username)
    except Exception as e:
        logger.error("[REGISTER] Step 3 FAILED — DB insert error for '%s': %s", req.username, e)
        raise HTTPException(status_code=400, detail="Username already taken")
    finally:
        db.close()

    # Step 4: Provision K8s pods
    logger.info("[REGISTER] Step 4 — Starting K8s provisioning for '%s'", req.username)
    try:
        provision_trainee(req.username)
        logger.info("[REGISTER] Step 4 — Provisioning completed successfully for '%s'", req.username)
    except Exception as e:
        logger.error("[REGISTER] Step 4 FAILED — Provisioning error for '%s': %s", req.username, e)
        raise HTTPException(status_code=500, detail=f"Provisioning failed: {e}")

    logger.info("[REGISTER] Done — '%s' registered and environment queued", req.username)
    return {"message": f"Welcome {req.username}! Your environment is being set up."}


@app.post("/login")
def login(req: LoginRequest):
    db = get_db()
    try:
        user = db.execute(
            "SELECT * FROM users WHERE username = ?", (req.username,)
        ).fetchone()

        if not user or not (req.password == user["password"]):
            raise HTTPException(status_code=401, detail="Invalid credentials")

        return {"message": "Login successful", "username": req.username}
    finally:
        db.close()


@app.get("/challenges")
def get_challenges():
    """Return all challenges (without flags)"""
    db = get_db()
    try:
        rows = db.execute(
            "SELECT id, title, description, points FROM challenges"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close()


@app.post("/submit")
def submit_flag(req: FlagSubmission):
    """
    1. Find user
    2. Check flag against DB
    3. Record submission if correct
    4. Return result
    """
    db = get_db()
    try:
        user = db.execute(
            "SELECT * FROM users WHERE username = ?", (req.username,)
        ).fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        challenge = db.execute(
            "SELECT * FROM challenges WHERE id = ?", (req.challenge_id,)
        ).fetchone()
        if not challenge:
            raise HTTPException(status_code=404, detail="Challenge not found")

        # Check if already solved
        already = db.execute(
            "SELECT * FROM submissions WHERE user_id=? AND challenge_id=?",
            (user["id"], req.challenge_id)
        ).fetchone()
        if already:
            return {"result": "already_solved", "message": "You already solved this!"}

        # Validate flag
        if req.flag.strip() != challenge["flag"]:
            return {"result": "wrong", "message": "Wrong flag. Keep digging!"}

        # Record correct submission
        db.execute(
            "INSERT INTO submissions (user_id, challenge_id) VALUES (?,?)",
            (user["id"], req.challenge_id)
        )
        db.commit()

        return {"result": "correct", "message": f"+{challenge['points']} points!"}
    finally:
        db.close()


@app.get("/leaderboard")
def leaderboard():
    """Aggregate total points per user, sorted descending"""
    db = get_db()
    try:
        rows = db.execute("""
            SELECT u.username,
                   COALESCE(SUM(c.points), 0) as total_points,
                   COUNT(s.id) as solved_count
            FROM users u
            LEFT JOIN submissions s ON u.id = s.user_id
            LEFT JOIN challenges c ON s.challenge_id = c.id
            GROUP BY u.id
            ORDER BY total_points DESC
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close()


# --- at the very bottom of main.py ---
app.mount("/", StaticFiles(directory="static", html=True), name="static")