"""RoadGuard AI backend: Firebase-verified, user-isolated academic prototype.

The emergency workflow records a prepared notification only. It does not send
SMS or contact emergency services.
"""
from __future__ import annotations

import math
import os
import secrets
import sqlite3
import json
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
try:
    import firebase_admin
    from firebase_admin import auth as firebase_auth, credentials
except ImportError:
    firebase_admin = firebase_auth = credentials = None

from flask import Flask, abort, g, jsonify, request, send_from_directory, session
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename
from ml_service import predict, train

BASE_DIR = Path(__file__).resolve().parent
# Vercel Functions have a read-only application bundle. `/tmp` is the
# platform-provided writable location, but its contents are temporary.
DB_PATH = Path("/tmp/roadguard.db") if os.environ.get("VERCEL") else BASE_DIR / "roadguard.db"
SAFE_STATIC = {".css", ".js", ".html", ".svg", ".png", ".jpg", ".jpeg", ".ico"}
load_dotenv(BASE_DIR / ".env")
app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("ROADGUARD_SECRET_KEY", ""),
    MAX_CONTENT_LENGTH=20 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "false").lower() == "true",
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_: object) -> None:
    connection = g.pop("db", None)
    if connection:
        connection.close()


def one(query: str, params: tuple = ()) -> dict | None:
    row = db().execute(query, params).fetchone()
    return dict(row) if row else None


def csrf_token() -> str:
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "Authentication required."}), 401
        return view(*args, **kwargs)
    return wrapped


def csrf_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        supplied = request.headers.get("X-CSRF-Token", "")
        if not session.get("csrf_token") or not secrets.compare_digest(supplied, session["csrf_token"]):
            return jsonify({"error": "Invalid request token. Refresh and sign in again."}), 403
        return view(*args, **kwargs)
    return wrapped


def init_firebase() -> None:
    if firebase_admin is None:
        raise RuntimeError("firebase-admin is not installed. Run: pip install -r requirements.txt")
    if firebase_admin._apps:
        return
    key_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()
    if key_json:
        try:
            credential = credentials.Certificate(json.loads(key_json))
        except (ValueError, TypeError) as exc:
            raise RuntimeError("FIREBASE_SERVICE_ACCOUNT_JSON must contain valid service-account JSON.") from exc
    else:
        key_path = Path(os.environ.get("FIREBASE_SERVICE_ACCOUNT_PATH", ""))
        if not key_path.is_file():
            raise RuntimeError(
                "Set FIREBASE_SERVICE_ACCOUNT_JSON or point FIREBASE_SERVICE_ACCOUNT_PATH to a private service-account JSON file."
            )
        credential = credentials.Certificate(str(key_path))
    firebase_admin.initialize_app(credential)


def add_column(connection: sqlite3.Connection, table: str, definition: str) -> None:
    column = definition.split()[0]
    existing = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")


def init_db() -> None:
    """Create tables and migrate old shared rows without deleting them.

    Old shared rows remain unassigned (user_id NULL) rather than being exposed
    to the next person who logs in.
    """
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript("""
        CREATE TABLE IF NOT EXISTS users (
          id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
          email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
          created_at TEXT NOT NULL, email_verified INTEGER NOT NULL DEFAULT 0,
          firebase_uid TEXT UNIQUE
        );
        CREATE TABLE IF NOT EXISTS driver_profiles (
          user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
          age INTEGER NOT NULL, experience_years INTEGER NOT NULL,
          vehicle_type TEXT NOT NULL, emergency_notes TEXT, completed_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS user_preferences (
          user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
          safe_speed INTEGER NOT NULL DEFAULT 65, voice_enabled INTEGER NOT NULL DEFAULT 1,
          updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS contacts (
          id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
          name TEXT NOT NULL, phone TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS trips (
          id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
          started_at TEXT NOT NULL, ended_at TEXT NOT NULL, duration_seconds INTEGER NOT NULL,
          distance_km REAL NOT NULL, safety_score INTEGER NOT NULL,
          high_risk_events INTEGER NOT NULL DEFAULT 0, max_risk INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS telemetry (
          id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
          received_at TEXT NOT NULL, speed_kmh REAL NOT NULL, acceleration REAL NOT NULL,
          risk_score INTEGER NOT NULL, latitude REAL, longitude REAL
        );
        CREATE TABLE IF NOT EXISTS incidents (
          id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
          created_at TEXT NOT NULL, status TEXT NOT NULL, latitude REAL, longitude REAL, note TEXT
        );
    """)
    for table in ("contacts", "trips", "telemetry", "incidents"):
        add_column(con, table, "user_id INTEGER")
    for definition in ("email_verified INTEGER NOT NULL DEFAULT 0", "verification_code TEXT", "code_expires_at TEXT", "firebase_uid TEXT"):
        add_column(con, "users", definition)
    con.executescript("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_users_firebase_uid ON users(firebase_uid) WHERE firebase_uid IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_contacts_user ON contacts(user_id);
        CREATE INDEX IF NOT EXISTS idx_trips_user ON trips(user_id);
        CREATE INDEX IF NOT EXISTS idx_telemetry_user ON telemetry(user_id);
        CREATE INDEX IF NOT EXISTS idx_incidents_user ON incidents(user_id);
    """)
    con.commit()
    con.close()


def preferences(user_id: int) -> dict:
    saved = one("SELECT safe_speed AS safeSpeed, voice_enabled AS voice FROM user_preferences WHERE user_id=?", (user_id,))
    if saved:
        saved["voice"] = bool(saved["voice"])
        return saved
    db().execute("INSERT INTO user_preferences(user_id,safe_speed,voice_enabled,updated_at) VALUES (?,?,?,?)", (user_id, 65, 1, now()))
    db().commit()
    return {"safeSpeed": 65, "voice": True}


def number(value, field: str, minimum: float, maximum: float) -> float:
    try:
        value = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be a number.") from None
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError(f"{field} must be between {minimum} and {maximum}.")
    return value


def request_location(payload: dict) -> tuple[float | None, float | None]:
    location = payload.get("location") or {}
    if location.get("latitude") is None:
        return None, None
    return number(location.get("latitude"), "latitude", -90, 90), number(location.get("longitude"), "longitude", -180, 180)


@app.get("/")
def homepage():
    return send_from_directory(BASE_DIR, "index.html")


@app.get("/<path:path>")
def static_files(path: str):
    candidate = (BASE_DIR / path).resolve()
    if BASE_DIR not in candidate.parents or not candidate.is_file() or candidate.suffix.lower() not in SAFE_STATIC:
        abort(404)
    return send_from_directory(BASE_DIR, path)


@app.get("/api/auth/me")
def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"authenticated": False})
    user = one("SELECT id,name,email FROM users WHERE id=? AND email_verified=1", (user_id,))
    if not user:
        session.clear()
        return jsonify({"authenticated": False})
    profile = one("SELECT age,experience_years AS experienceYears,vehicle_type AS vehicleType FROM driver_profiles WHERE user_id=?", (user_id,))
    return jsonify({"authenticated": True, "user": user, "driverProfile": profile, "csrfToken": csrf_token()})


@app.post("/api/auth/firebase-sync")
def firebase_sync():
    """Trust only a server-verified Firebase ID token, never browser UID/email."""
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return jsonify({"error": "Firebase ID token required."}), 401
    try:
        init_firebase()
        decoded = firebase_auth.verify_id_token(header.split(" ", 1)[1].strip(), check_revoked=True)
    except Exception:
        return jsonify({"error": "Invalid or expired Firebase ID token."}), 401
    uid = str(decoded.get("uid", "")).strip()
    email = str(decoded.get("email", "")).strip().lower()
    if not uid or not email or not decoded.get("email_verified", False):
        return jsonify({"error": "Verify your Firebase email before using RoadGuard."}), 403
    name = str(decoded.get("name") or email.split("@", 1)[0]).strip()[:100]
    user = one("SELECT id FROM users WHERE firebase_uid=?", (uid,))
    if user:
        user_id = user["id"]
        db().execute("UPDATE users SET name=?,email=?,email_verified=1 WHERE id=?", (name, email, user_id))
    else:
        same_email = one("SELECT id,firebase_uid FROM users WHERE email=?", (email,))
        if same_email and same_email["firebase_uid"] not in (None, uid):
            return jsonify({"error": "This email is already linked to another account."}), 409
        if same_email:
            user_id = same_email["id"]
            db().execute("UPDATE users SET name=?,firebase_uid=?,email_verified=1 WHERE id=?", (name, uid, user_id))
        else:
            cursor = db().execute(
                "INSERT INTO users(name,email,password_hash,created_at,email_verified,firebase_uid) VALUES (?,?,?,?,?,?)",
                (name, email, generate_password_hash(secrets.token_urlsafe(32)), now(), 1, uid),
            )
            user_id = cursor.lastrowid
    db().commit()
    session.clear()
    session["user_id"], session["firebase_uid"], session.permanent = user_id, uid, True
    return jsonify({"authenticated": True, "user": {"id": user_id, "name": name, "email": email}, "csrfToken": csrf_token()})


@app.post("/api/auth/logout")
@login_required
@csrf_required
def logout():
    session.clear()
    return "", 204


@app.route("/api/driver-profile", methods=["GET", "PUT"])
@login_required
def driver_profile():
    user_id = session["user_id"]
    if request.method == "GET":
        return jsonify(one("SELECT age,experience_years AS experienceYears,vehicle_type AS vehicleType,emergency_notes AS emergencyNotes FROM driver_profiles WHERE user_id=?", (user_id,)) or {})
    if not secrets.compare_digest(request.headers.get("X-CSRF-Token", ""), session.get("csrf_token", "")):
        return jsonify({"error": "Invalid request token. Refresh and sign in again."}), 403
    payload = request.get_json(silent=True) or {}
    try:
        age, experience = int(payload.get("age", 0)), int(payload.get("experienceYears", -1))
    except (TypeError, ValueError):
        return jsonify({"error": "Age and experience must be whole numbers."}), 400
    vehicle = str(payload.get("vehicleType", "")).strip()[:80]
    if not 16 <= age <= 100 or not 0 <= experience <= 80 or not vehicle:
        return jsonify({"error": "Complete age, driving experience, and vehicle type."}), 400
    db().execute(
        "INSERT INTO driver_profiles(user_id,age,experience_years,vehicle_type,emergency_notes,completed_at) VALUES (?,?,?,?,?,?) "
        "ON CONFLICT(user_id) DO UPDATE SET age=excluded.age,experience_years=excluded.experience_years,vehicle_type=excluded.vehicle_type,emergency_notes=excluded.emergency_notes,completed_at=excluded.completed_at",
        (user_id, age, experience, vehicle, str(payload.get("emergencyNotes", "")).strip()[:500], now()),
    )
    db().commit()
    return jsonify({"saved": True})


@app.get("/api/status")
@login_required
def status():
    user_id = session["user_id"]
    latest = one("SELECT * FROM telemetry WHERE user_id=? ORDER BY id DESC LIMIT 1", (user_id,))
    weekly = db().execute("SELECT COALESCE(SUM(distance_km),0) AS distance,COUNT(*) AS trips,COALESCE(AVG(safety_score),0) AS score,COALESCE(SUM(high_risk_events),0) AS events FROM trips WHERE user_id=? AND ended_at >= datetime('now','-7 days')", (user_id,)).fetchone()
    return jsonify({"latestTelemetry": latest, "profile": preferences(user_id), "weekly": dict(weekly), "serverTime": now()})


@app.route("/api/profile", methods=["GET", "PUT"])
@login_required
def profile():
    user_id = session["user_id"]
    if request.method == "GET":
        return jsonify(preferences(user_id))
    if not secrets.compare_digest(request.headers.get("X-CSRF-Token", ""), session.get("csrf_token", "")):
        return jsonify({"error": "Invalid request token. Refresh and sign in again."}), 403
    payload = request.get_json(silent=True) or {}
    try:
        safe_speed = int(payload.get("safeSpeed", 65))
    except (TypeError, ValueError):
        return jsonify({"error": "safeSpeed must be a whole number."}), 400
    if not 25 <= safe_speed <= 140:
        return jsonify({"error": "safeSpeed must be between 25 and 140."}), 400
    voice = int(bool(payload.get("voice", True)))
    db().execute("INSERT INTO user_preferences(user_id,safe_speed,voice_enabled,updated_at) VALUES (?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET safe_speed=excluded.safe_speed,voice_enabled=excluded.voice_enabled,updated_at=excluded.updated_at", (user_id, safe_speed, voice, now()))
    db().commit()
    return jsonify({"safeSpeed": safe_speed, "voice": bool(voice)})


@app.route("/api/contacts", methods=["GET", "POST"])
@login_required
def contacts():
    user_id = session["user_id"]
    if request.method == "GET":
        rows = db().execute("SELECT id,name,phone FROM contacts WHERE user_id=? ORDER BY id DESC", (user_id,)).fetchall()
        return jsonify([dict(row) for row in rows])
    if not secrets.compare_digest(request.headers.get("X-CSRF-Token", ""), session.get("csrf_token", "")):
        return jsonify({"error": "Invalid request token. Refresh and sign in again."}), 403
    payload = request.get_json(silent=True) or {}
    name, phone = str(payload.get("name", "")).strip()[:100], str(payload.get("phone", "")).strip()[:30]
    if not name or not phone:
        return jsonify({"error": "name and phone are required."}), 400
    cursor = db().execute("INSERT INTO contacts(user_id,name,phone,created_at) VALUES (?,?,?,?)", (user_id, name, phone, now()))
    db().commit()
    return jsonify({"id": cursor.lastrowid, "name": name, "phone": phone}), 201


@app.delete("/api/contacts/<int:contact_id>")
@login_required
@csrf_required
def delete_contact(contact_id: int):
    cursor = db().execute("DELETE FROM contacts WHERE id=? AND user_id=?", (contact_id, session["user_id"]))
    db().commit()
    return ("", 204) if cursor.rowcount else (jsonify({"error": "Contact not found."}), 404)


@app.post("/api/telemetry")
@login_required
@csrf_required
def receive_telemetry():
    payload = request.get_json(silent=True) or {}
    try:
        speed, acceleration = number(payload.get("speedKmh"), "speedKmh", 0, 300), number(payload.get("acceleration"), "acceleration", 0, 100)
        risk = int(number(payload.get("riskScore"), "riskScore", 0, 100))
        latitude, longitude = request_location(payload)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    db().execute("INSERT INTO telemetry(user_id,received_at,speed_kmh,acceleration,risk_score,latitude,longitude) VALUES (?,?,?,?,?,?,?)", (session["user_id"], now(), speed, acceleration, risk, latitude, longitude))
    db().commit()
    return jsonify({"accepted": True, "riskScore": risk})


@app.route("/api/trips", methods=["GET", "POST", "DELETE"])
@login_required
def trips():
    user_id = session["user_id"]
    if request.method == "GET":
        rows = db().execute("SELECT id,started_at AS startedAt,ended_at AS endedAt,duration_seconds AS durationSeconds,distance_km AS distanceKm,safety_score AS safetyScore,high_risk_events AS highRiskEvents,max_risk AS maxRisk FROM trips WHERE user_id=? ORDER BY id DESC LIMIT 100", (user_id,)).fetchall()
        return jsonify([dict(row) for row in rows])
    if not secrets.compare_digest(request.headers.get("X-CSRF-Token", ""), session.get("csrf_token", "")):
        return jsonify({"error": "Invalid request token. Refresh and sign in again."}), 403
    if request.method == "DELETE":
        db().execute("DELETE FROM trips WHERE user_id=?", (user_id,))
        db().commit()
        return "", 204
    payload = request.get_json(silent=True) or {}
    needed = ("startedAt", "durationSeconds", "distanceKm", "safetyScore", "highRiskEvents", "maxRisk")
    if any(key not in payload for key in needed):
        return jsonify({"error": "Incomplete trip data."}), 400
    try:
        duration = int(number(payload["durationSeconds"], "durationSeconds", 0, 172800))
        distance = number(payload["distanceKm"], "distanceKm", 0, 5000)
        safety = int(number(payload["safetyScore"], "safetyScore", 0, 100))
        events = int(number(payload["highRiskEvents"], "highRiskEvents", 0, 10000))
        max_risk = int(number(payload["maxRisk"], "maxRisk", 0, 100))
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    cursor = db().execute("INSERT INTO trips(user_id,started_at,ended_at,duration_seconds,distance_km,safety_score,high_risk_events,max_risk) VALUES (?,?,?,?,?,?,?,?)", (user_id, str(payload["startedAt"])[:50], now(), duration, distance, safety, events, max_risk))
    db().commit()
    return jsonify({"id": cursor.lastrowid}), 201


@app.post("/api/incidents")
@login_required
@csrf_required
def incident():
    payload = request.get_json(silent=True) or {}
    try:
        latitude, longitude = request_location(payload)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    user_id = session["user_id"]
    cursor = db().execute("INSERT INTO incidents(user_id,created_at,status,latitude,longitude,note) VALUES (?,?,?,?,?,?)", (user_id, now(), "notification-prepared", latitude, longitude, "Prototype emergency workflow"))
    contacts_for_user = db().execute("SELECT name,phone FROM contacts WHERE user_id=?", (user_id,)).fetchall()
    db().commit()
    return jsonify({"incidentId": cursor.lastrowid, "status": "notification-prepared", "recipients": [dict(row) for row in contacts_for_user], "message": "Demo only: no SMS or emergency service was contacted."}), 201


@app.post("/api/ml/train-demo")
@login_required
@csrf_required
def train_demo_model():
    return jsonify(train())


@app.post("/api/ml/upload-train")
@login_required
@csrf_required
def train_uploaded_model():
    uploaded = request.files.get("dataset")
    if not uploaded or not uploaded.filename:
        return jsonify({"error": "Choose a CSV dataset first."}), 400
    if not uploaded.filename.lower().endswith(".csv"):
        return jsonify({"error": "Only CSV files are supported."}), 400
    try:
        frame = pd.read_csv(uploaded, sep=None, engine="python")
        return jsonify(train(frame, source_name=secure_filename(uploaded.filename)))
    except Exception as error:
        return jsonify({"error": f"Dataset training failed: {error}"}), 400


@app.post("/api/ml/predict")
@login_required
@csrf_required
def model_prediction():
    try:
        return jsonify(predict(request.get_json(silent=True) or {}))
    except (TypeError, ValueError) as error:
        return jsonify({"error": str(error)}), 400


def validate_startup() -> None:
    if not app.config["SECRET_KEY"]:
        raise RuntimeError("Set ROADGUARD_SECRET_KEY before starting. See .env.example and README.md.")
    if not os.environ.get("FIREBASE_SERVICE_ACCOUNT_PATH"):
        raise RuntimeError("Set FIREBASE_SERVICE_ACCOUNT_PATH before starting. See .env.example and README.md.")


# These run for both local execution and a production WSGI server such as Gunicorn.
# Render provides the PORT environment variable and Gunicorn imports this module.
validate_startup()
init_db()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False)
