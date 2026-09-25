"""Accounts, cohorts and instructor assignments, on SQLite.

Progress used to live in a single ``progress.json`` next to the app, which is
fine for one learner on one laptop and useless for a classroom.  This module
replaces it with a real multi-user store: learners and instructors, cohorts
with rosters, work an instructor assigns, and per-learner progress rows.

**On passwords.**  They are stored as scrypt hashes with a per-user 16-byte
salt, never in plain text and never recoverable — a forgotten password is reset
by an instructor, not looked up.  scrypt is deliberately slow and
memory-hard, which is the point: it makes guessing expensive.  The parameters
below (N=2**14, r=8, p=1) are the interactive-login settings from RFC 7914.

This is honest classroom-grade authentication: it protects a roster on a
college server.  It is not a public internet identity system — that wants
e-mail verification, rate limiting, session expiry and TLS termination, none of
which belong in a Streamlit prototype.  The Deliverables page says so.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import secrets
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from . import db as DB

DB_PATH = os.environ.get(
    "QUBUILD_DB",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "qubuild.db"))

SCRYPT = dict(n=2 ** 14, r=8, p=1, dklen=64)

#: The three ways in. A *learner* is studying alone and belongs to no class.
#: A *student* joined an instructor's classroom with its code. An *instructor*
#: owns a classroom and is the only role that sees the cohort tools.
ROLES = ("learner", "student", "instructor")

#: No I, O, 0 or 1 — a classroom code gets read off a whiteboard and typed by
#: forty people, so the ambiguous glyphs are simply not in the alphabet.
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 6

_USERS_DDL = """
CREATE TABLE IF NOT EXISTS %s (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    username   TEXT UNIQUE NOT NULL,
    display    TEXT NOT NULL,
    role       TEXT NOT NULL CHECK (role IN ('learner', 'student', 'instructor')),
    cohort_id  INTEGER REFERENCES cohorts(id),
    salt       BLOB NOT NULL,
    pw_hash    BLOB NOT NULL,
    created    REAL NOT NULL,
    last_seen  REAL
);"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS cohorts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT UNIQUE NOT NULL,
    code       TEXT,
    owner_id   INTEGER,
    created    REAL NOT NULL
);
""" + (_USERS_DDL % "users") + """
CREATE TABLE IF NOT EXISTS progress (
    user_id    INTEGER PRIMARY KEY REFERENCES users(id),
    data       TEXT NOT NULL,
    updated    REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS assignments (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    cohort_id  INTEGER NOT NULL REFERENCES cohorts(id),
    kind       TEXT NOT NULL CHECK (kind IN ('lesson', 'challenge')),
    item_id    TEXT NOT NULL,
    due        TEXT,
    note       TEXT,
    created_by INTEGER REFERENCES users(id),
    created    REAL NOT NULL,
    UNIQUE (cohort_id, kind, item_id)
);
"""


#: The schema only has to be laid down once per process. It used to run on
#: every single connection, which on Windows meant four CREATE TABLE statements
#: and a PRAGMA sweep behind every click in the app.
_READY = False


def connect():
    """Open the active database, laying down the schema the first time.

    Which database that is depends on QUBUILD_DB_URL — SQLite by default, a
    shared Postgres when one is configured. Callers see no difference.
    """
    global _READY
    con = DB.connect(None if DB.is_postgres() else DB_PATH)
    if not _READY:
        con.executescript(SCHEMA)
        _migrate(con)
        _READY = True
    return con


def reset_schema_cache() -> None:
    """Forget that the schema was laid down — for tests that swap databases."""
    global _READY, _MIGRATED
    _READY = False
    _MIGRATED = False


def is_configured() -> bool:
    return os.path.exists(DB_PATH)


# --------------------------------------------------------------------------
# migration
# --------------------------------------------------------------------------
#
# Installations created before classrooms existed have a cohorts table with no
# code column and a users table whose CHECK constraint knows only two roles.
# CREATE TABLE IF NOT EXISTS leaves both alone, so the gap is closed here
# rather than by asking anyone to delete their database.

_MIGRATED = False


def _columns(con, table: str) -> set:
    if DB.is_postgres():
        rows = con.execute(
            "SELECT column_name AS name FROM information_schema.columns"
            " WHERE table_name = ?", (table,)).fetchall()
    else:
        rows = con.execute("PRAGMA table_info(%s)" % table).fetchall()
    return {r["name"] for r in rows}


def _widen_role_check(con) -> None:
    """Let the users table accept the 'student' role."""
    if DB.is_postgres():
        # The constraint is named by convention; dropping it leaves the column
        # validated in Python, which is where the three roles are defined.
        con.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check")
        return
    row = con.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'users'").fetchone()
    if row is None or "'student'" in (row["sql"] or ""):
        return
    # SQLite cannot alter a CHECK in place, so the table is rebuilt and the
    # rows copied across. Foreign keys are off on this connection, so the
    # tables that reference users(id) are undisturbed.
    cols = "id, username, display, role, cohort_id, salt, pw_hash, created, last_seen"
    con.executescript(_USERS_DDL % "users_migrated")
    con.execute("INSERT INTO users_migrated (%s) SELECT %s FROM users" % (cols, cols))
    con.execute("DROP TABLE users")
    con.execute("ALTER TABLE users_migrated RENAME TO users")


def _migrate(con) -> None:
    global _MIGRATED
    if _MIGRATED:
        return
    have = _columns(con, "cohorts")
    if "code" not in have:
        con.execute(DB.ddl_for("ALTER TABLE cohorts ADD COLUMN code TEXT"))
    if "owner_id" not in have:
        con.execute(DB.ddl_for("ALTER TABLE cohorts ADD COLUMN owner_id INTEGER"))
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS cohorts_code ON cohorts (code)")
    _widen_role_check(con)
    _MIGRATED = True


# --------------------------------------------------------------------------
# passwords
# --------------------------------------------------------------------------

def hash_password(password: str, salt: Optional[bytes] = None) -> Tuple[bytes, bytes]:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, **SCRYPT)
    return salt, digest


def verify_password(password: str, salt: bytes, expected: bytes) -> bool:
    _, digest = hash_password(password, salt)
    # constant-time compare: a timing difference here leaks the hash prefix
    return secrets.compare_digest(digest, expected)


# --------------------------------------------------------------------------
# users and cohorts
# --------------------------------------------------------------------------

@dataclass
class User:
    id: int
    username: str
    display: str
    role: str
    cohort_id: Optional[int]
    cohort_name: Optional[str] = None

    cohort_code: Optional[str] = None

    @property
    def is_instructor(self) -> bool:
        return self.role == "instructor"

    @property
    def is_student(self) -> bool:
        return self.role == "student"

    @property
    def is_learner(self) -> bool:
        return self.role == "learner"


def _field(row, name):
    """Read an optional column from either driver's row type."""
    try:
        if hasattr(row, "get"):
            return row.get(name)
        return row[name] if name in row.keys() else None
    except (KeyError, IndexError):
        return None


def _row_to_user(row) -> User:
    return User(row["id"], row["username"], row["display"], row["role"],
                row["cohort_id"], _field(row, "cohort_name"), _field(row, "cohort_code"))


# --------------------------------------------------------------------------
# classroom codes
# --------------------------------------------------------------------------

def normalise_code(code: str) -> str:
    """Codes are typed by hand, so spaces, dashes and case are all forgiven."""
    return "".join(ch for ch in (code or "").upper() if ch.isalnum())


def cohort_by_code(code: str):
    code = normalise_code(code)
    if not code:
        return None
    with connect() as con:
        return con.execute("SELECT * FROM cohorts WHERE code = ?", (code,)).fetchone()


def cohort_by_name(name: str):
    with connect() as con:
        return con.execute("SELECT * FROM cohorts WHERE name = ?",
                           ((name or "").strip(),)).fetchone()


def generate_code() -> str:
    """A fresh code that no classroom is using yet."""
    for _ in range(50):
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
        if cohort_by_code(code) is None:
            return code
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH + 2))


def set_cohort_code(cohort_id: int, code: str) -> bool:
    """Returns False if another classroom already answers to that code."""
    code = normalise_code(code)
    if not code:
        return False
    taken = cohort_by_code(code)
    if taken is not None and int(taken["id"]) != int(cohort_id):
        return False
    with connect() as con:
        con.execute("UPDATE cohorts SET code = ? WHERE id = ?", (code, cohort_id))
    return True


def create_cohort(name: str, code: Optional[str] = None,
                  owner_id: Optional[int] = None) -> int:
    name = (name or "").strip()
    code = normalise_code(code) if code else None
    with connect() as con:
        row = con.execute("SELECT * FROM cohorts WHERE name = ?", (name,)).fetchone()
        if row:
            cid = int(row["id"])
            if code and not _field(row, "code"):
                con.execute("UPDATE cohorts SET code = ? WHERE id = ?", (code, cid))
            if owner_id and not _field(row, "owner_id"):
                con.execute("UPDATE cohorts SET owner_id = ? WHERE id = ?", (owner_id, cid))
            return cid
        return int(con.insert_returning_id(
            "INSERT INTO cohorts (name, code, owner_id, created) VALUES (?, ?, ?, ?)",
            (name, code, owner_id, time.time())))


def cohorts() -> List[dict]:
    with connect() as con:
        return con.execute("SELECT * FROM cohorts ORDER BY name").fetchall()


def cohort_code(cohort_id: int) -> Optional[str]:
    with connect() as con:
        row = con.execute("SELECT code FROM cohorts WHERE id = ?", (cohort_id,)).fetchone()
    return _field(row, "code") if row is not None else None


def cohorts_owned_by(user_id: int) -> List[dict]:
    with connect() as con:
        return con.execute("SELECT * FROM cohorts WHERE owner_id = ? ORDER BY name",
                           (user_id,)).fetchall()


def set_cohort(user_id: int, cohort_id: Optional[int]) -> None:
    with connect() as con:
        con.execute("UPDATE users SET cohort_id = ? WHERE id = ?", (cohort_id, user_id))


def set_role(user_id: int, role: str) -> bool:
    role = (role or "").strip().lower()
    if role not in ROLES:
        return False
    with connect() as con:
        con.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
    return True


def create_user(username: str, password: str, display: str = "", role: str = "learner",
                cohort: Optional[str] = None) -> Optional[User]:
    """Returns None if the username is taken."""
    username = username.strip().lower()
    if not username or not password:
        return None
    cohort_id = create_cohort(cohort) if cohort else None
    salt, digest = hash_password(password)
    try:
        with connect() as con:
            uid = con.insert_returning_id(
                "INSERT INTO users (username, display, role, cohort_id, salt, pw_hash, created)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (username, display or username, role, cohort_id, salt, digest, time.time()))
    except Exception as exc:                                       # noqa: BLE001
        # a duplicate username is the expected failure; anything else is not
        if "uniq" in str(exc).lower() or "duplicate" in str(exc).lower():
            return None
        raise
    return get_user(uid)


def register(username: str, password: str, display: str = "", role: str = "learner",
             classroom: str = "", code: str = "") -> Tuple[Optional[User], str]:
    """Sign somebody up in one of the three roles.

    Returns ``(user, "")`` on success and ``(None, reason)`` otherwise, because
    "that username is taken" and "that classroom code is wrong" are different
    problems and the person filling the form deserves to be told which one.
    """
    role = (role or "learner").strip().lower()
    if role not in ROLES:
        return None, "Pick learner, student or instructor."
    if not (username or "").strip() or not password:
        return None, "Fill in a username and a password."

    if role == "student":
        room = cohort_by_code(code)
        if room is None:
            return None, ("That classroom code does not match any class. "
                          "Ask your instructor for it, or sign up as a learner.")
        user = create_user(username, password, display, "student")
        if user is None:
            return None, "That username is taken."
        set_cohort(user.id, int(room["id"]))
        return get_user(user.id), ""

    if role == "instructor":
        classroom = (classroom or "").strip()
        if not classroom:
            return None, "Give your class a name, so your students know what they are joining."
        wanted = normalise_code(code) or generate_code()
        if len(wanted) < 4:
            return None, "A classroom code needs at least 4 characters."
        existing_name = cohort_by_name(classroom)
        if existing_name is not None and _field(existing_name, "owner_id"):
            return None, "A class with that name already exists. Choose another name."
        clash = cohort_by_code(wanted)
        if clash is not None and (existing_name is None
                                  or int(clash["id"]) != int(existing_name["id"])):
            return None, "That classroom code is already in use. Choose another."
        user = create_user(username, password, display, "instructor")
        if user is None:
            return None, "That username is taken."
        cohort_id = create_cohort(classroom, wanted, user.id)
        set_cohort_code(cohort_id, wanted)
        set_cohort(user.id, cohort_id)
        return get_user(user.id), ""

    user = create_user(username, password, display, "learner")
    if user is None:
        return None, "That username is taken."
    return user, ""


def get_user(user_id: int) -> Optional[User]:
    with connect() as con:
        row = con.execute(
            "SELECT u.*, c.name AS cohort_name, c.code AS cohort_code FROM users u"
            " LEFT JOIN cohorts c ON c.id = u.cohort_id WHERE u.id = ?", (user_id,)).fetchone()
    return _row_to_user(row) if row else None


def authenticate(username: str, password: str) -> Optional[User]:
    with connect() as con:
        row = con.execute(
            "SELECT u.*, c.name AS cohort_name, c.code AS cohort_code FROM users u"
            " LEFT JOIN cohorts c ON c.id = u.cohort_id WHERE u.username = ?",
            (username.strip().lower(),)).fetchone()
        if row is None:
            # Hash anyway so a missing user and a wrong password take the same
            # time — otherwise the response time enumerates valid usernames.
            hash_password(password)
            return None
        if not verify_password(password, row["salt"], row["pw_hash"]):
            return None
        con.execute("UPDATE users SET last_seen = ? WHERE id = ?", (time.time(), row["id"]))
    return _row_to_user(row)


def set_password(user_id: int, password: str) -> None:
    salt, digest = hash_password(password)
    with connect() as con:
        con.execute("UPDATE users SET salt = ?, pw_hash = ? WHERE id = ?",
                    (salt, digest, user_id))


def members(cohort_id: int) -> List[User]:
    with connect() as con:
        rows = con.execute(
            "SELECT u.*, c.name AS cohort_name, c.code AS cohort_code FROM users u"
            " LEFT JOIN cohorts c ON c.id = u.cohort_id"
            " WHERE u.cohort_id = ? ORDER BY u.display", (cohort_id,)).fetchall()
    return [_row_to_user(r) for r in rows]


def user_count() -> int:
    with connect() as con:
        return con.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]


# --------------------------------------------------------------------------
# roster import
# --------------------------------------------------------------------------

def import_roster(csv_text: str, cohort: str) -> Dict[str, object]:
    """Bulk-create learners from CSV with columns username, display (optional).

    Returns a report rather than raising, because a roster with one bad row
    should still import the other thirty-nine.  Temporary passwords are
    generated here and returned once — they are not recoverable afterwards.
    """
    created, skipped, errors = [], [], []
    reader = csv.DictReader(io.StringIO(csv_text.strip()))
    if not reader.fieldnames or "username" not in [f.strip().lower() for f in reader.fieldnames]:
        return {"created": [], "skipped": [], "errors": ["CSV needs a 'username' column"]}

    for i, row in enumerate(reader, 2):
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        username = row.get("username", "")
        if not username:
            errors.append("row %d: blank username" % i)
            continue
        temporary = secrets.token_urlsafe(9)
        # A name on an imported roster is by definition somebody's student.
        user = create_user(username, temporary, row.get("display", ""), "student", cohort)
        if user is None:
            skipped.append(username)
        else:
            created.append({"username": username, "password": temporary})
    return {"created": created, "skipped": skipped, "errors": errors}


# --------------------------------------------------------------------------
# progress
# --------------------------------------------------------------------------

def load_progress(user_id: int) -> Optional[dict]:
    with connect() as con:
        row = con.execute("SELECT data FROM progress WHERE user_id = ?", (user_id,)).fetchone()
    if row is None:
        return None
    try:
        return json.loads(row["data"])
    except ValueError:
        return None


def save_progress(user_id: int, data: dict) -> None:
    with connect() as con:
        con.execute(
            "INSERT INTO progress (user_id, data, updated) VALUES (?, ?, ?)"
            " ON CONFLICT(user_id) DO UPDATE SET data = excluded.data, updated = excluded.updated",
            (user_id, json.dumps(data), time.time()))


def cohort_progress(cohort_id: int) -> List[dict]:
    """Every learner in a cohort with their stored progress, for the instructor view."""
    out = []
    with connect() as con:
        rows = con.execute(
            "SELECT u.id, u.username, u.display, p.data, p.updated FROM users u"
            " LEFT JOIN progress p ON p.user_id = u.id"
            " WHERE u.cohort_id = ? AND u.role IN ('learner', 'student')"
            " ORDER BY u.display",
            (cohort_id,)).fetchall()
    for r in rows:
        try:
            data = json.loads(r["data"]) if r["data"] else {}
        except ValueError:
            data = {}
        quiz = list(data.get("quiz", {}).values())
        right = sum(1 for q in quiz if q.get("correct"))
        out.append({
            "user_id": r["id"], "username": r["username"], "display": r["display"],
            "xp": int(data.get("xp", 0)),
            "lessons": len(data.get("lessons", {})),
            "challenges": len(data.get("challenges", {})),
            "attempted": len(quiz),
            "correct": right,
            "accuracy": (right / len(quiz)) if quiz else 0.0,
            "updated": r["updated"],
        })
    return out


# --------------------------------------------------------------------------
# assignments
# --------------------------------------------------------------------------

def assign(cohort_id: int, kind: str, item_id: str, due: str = "",
           note: str = "", by: Optional[int] = None) -> None:
    with connect() as con:
        # ON CONFLICT rather than INSERT OR REPLACE: the latter is SQLite-only,
        # and re-assigning an item should update the due date, not renumber the row.
        con.execute(
            "INSERT INTO assignments"
            " (cohort_id, kind, item_id, due, note, created_by, created)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT (cohort_id, kind, item_id) DO UPDATE SET"
            " due = excluded.due, note = excluded.note,"
            " created_by = excluded.created_by, created = excluded.created",
            (cohort_id, kind, item_id, due, note, by, time.time()))


def unassign(assignment_id: int) -> None:
    with connect() as con:
        con.execute("DELETE FROM assignments WHERE id = ?", (assignment_id,))


def assignments(cohort_id: int) -> List[dict]:
    with connect() as con:
        return con.execute(
            "SELECT * FROM assignments WHERE cohort_id = ? ORDER BY kind, item_id",
            (cohort_id,)).fetchall()


def bootstrap_demo() -> Optional[str]:
    """Create a first instructor if the database is empty.

    Returns the generated password once, so it can be shown to whoever set the
    platform up.  Does nothing if any user already exists.
    """
    if user_count() > 0:
        return None
    password = secrets.token_urlsafe(9)
    user = create_user("instructor", password, "Instructor", "instructor", "Demo cohort")
    if user is not None and user.cohort_id:
        set_cohort_code(int(user.cohort_id), generate_code())
    return password
