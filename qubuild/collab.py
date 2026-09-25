"""Shared circuits: several people editing the same thing at once.

**What this is, precisely.**  A shared room holds one circuit in the database.
Everyone in the room reads it, anyone may write to it, and each client polls for
changes on a short interval.  Edits land in about a second.

**What it is not.**  It is not operational transforms or CRDTs, so two people
typing into the same gate in the same second do not merge — the second write is
rejected, not silently dropped, and that person is told to reload.  Calling this
"realtime co-editing" would be overselling it; it is a shared session with
conflict detection, which is what a classroom actually needs: an instructor
broadcasting a circuit, a pair working on one problem, a demonstrator driving
while thirty people watch.

Conflict handling is the honest part.  Every write carries the version it was
based on.  If the room has moved on, the write is refused and the caller gets
the current state back, rather than one person's work quietly overwriting
another's — the failure mode that makes naive shared editing worse than none.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from . import accounts as AC
from . import db as DB
from . import notify as NT

SCHEMA = """
CREATE TABLE IF NOT EXISTS rooms (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    code       TEXT UNIQUE NOT NULL,
    title      TEXT NOT NULL,
    cohort_id  INTEGER REFERENCES cohorts(id),
    owner_id   INTEGER REFERENCES users(id),
    circuit    TEXT NOT NULL,
    version    INTEGER NOT NULL DEFAULT 1,
    locked     INTEGER NOT NULL DEFAULT 0,
    updated_by INTEGER,
    updated    REAL NOT NULL,
    created    REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS presence (
    room_id    INTEGER NOT NULL REFERENCES rooms(id),
    user_id    INTEGER NOT NULL REFERENCES users(id),
    seen       REAL NOT NULL,
    PRIMARY KEY (room_id, user_id)
);
CREATE TABLE IF NOT EXISTS room_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id    INTEGER NOT NULL REFERENCES rooms(id),
    user_id    INTEGER REFERENCES users(id),
    action     TEXT NOT NULL,
    detail     TEXT,
    at         REAL NOT NULL
);
"""

PRESENCE_WINDOW = 25.0          # seconds before someone counts as gone


_READY = False


def _con():
    global _READY
    con = AC.connect()          # same database, same dialect translation
    if not _READY:
        con.executescript(SCHEMA)
        _migrate(con)
        _READY = True
    return con


def reset_schema_cache() -> None:
    """Forget that the tables exist — for tests that swap databases."""
    global _READY
    _READY = False


def _migrate(con) -> None:
    """Rooms created before the log said *what* changed have no detail column."""
    try:
        if DB.is_postgres():
            rows = con.execute(
                "SELECT column_name AS name FROM information_schema.columns"
                " WHERE table_name = 'room_log'").fetchall()
        else:
            rows = con.execute("PRAGMA table_info(room_log)").fetchall()
        if "detail" not in {r["name"] for r in rows}:
            con.execute(DB.ddl_for("ALTER TABLE room_log ADD COLUMN detail TEXT"))
    except Exception:                                              # noqa: BLE001
        pass                 # an older log without detail still reads fine


# --------------------------------------------------------------------------
# what actually changed
# --------------------------------------------------------------------------

def _signature(circuit: dict) -> List[str]:
    """One printable line per gate, so two circuits can be compared as text."""
    out = []
    for op in (circuit or {}).get("ops", []):
        qubits = op.get("qubits") or []
        params = op.get("params") or []
        label = "%s q%s" % (op.get("name", "?"),
                            "→q".join(str(q) for q in qubits) if qubits else "?")
        if params:
            label += "(%s)" % ", ".join("%.2f" % float(p) for p in params)
        out.append(label)
    return out


def describe_change(before: dict, after: dict) -> str:
    """A sentence a person can read: what this edit did to the circuit.

    The room log used to record the word "edit", which tells an instructor that
    something happened and nothing about what.  Both versions of the circuit
    are already in hand at the moment of the write, so the difference costs
    nothing to compute and is the whole value of watching a room.
    """
    old_n = int((before or {}).get("qubits", 0) or 0)
    new_n = int((after or {}).get("qubits", 0) or 0)
    notes = []
    if old_n != new_n:
        notes.append("set the circuit to %d qubit%s" % (new_n, "" if new_n == 1 else "s"))

    old_ops, new_ops = _signature(before), _signature(after)
    removed, added = list(old_ops), list(new_ops)
    for item in list(removed):
        if item in added:                 # unchanged gates cancel out
            removed.remove(item)
            added.remove(item)

    if added and removed and len(added) == 1 and len(removed) == 1:
        notes.append("replaced %s with %s" % (removed[0], added[0]))
    else:
        if added:
            notes.append("added " + ", ".join(added[:3])
                         + (" and %d more" % (len(added) - 3) if len(added) > 3 else ""))
        if removed:
            notes.append("removed " + ", ".join(removed[:3])
                         + (" and %d more" % (len(removed) - 3) if len(removed) > 3 else ""))

    if not notes:
        return "reordered the circuit" if old_ops != new_ops else "saved with no change"
    return "; ".join(notes)


@dataclass
class Room:
    id: int
    code: str
    title: str
    version: int
    locked: bool
    circuit: dict
    updated: float
    updated_by: Optional[int]
    owner_id: Optional[int]


def _row_to_room(row) -> Room:
    try:
        circuit = json.loads(row["circuit"])
    except ValueError:
        circuit = {"qubits": 1, "ops": []}
    return Room(row["id"], row["code"], row["title"], row["version"],
                bool(row["locked"]), circuit, row["updated"], row["updated_by"],
                row["owner_id"])


def _code() -> str:
    """Six characters a person can read out loud without ambiguity."""
    import secrets
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"        # no I/O/0/1
    return "".join(secrets.choice(alphabet) for _ in range(6))


def create_room(title: str, circuit: dict, owner_id: Optional[int] = None,
                cohort_id: Optional[int] = None) -> Room:
    now = time.time()
    with _con() as con:
        for _ in range(8):                               # retry on code collision
            code = _code()
            try:
                new_id = con.insert_returning_id(
                    "INSERT INTO rooms (code, title, cohort_id, owner_id, circuit,"
                    " version, locked, updated_by, updated, created)"
                    " VALUES (?,?,?,?,?,1,0,?,?,?)",
                    (code, title.strip() or "Shared circuit", cohort_id, owner_id,
                     json.dumps(circuit), owner_id, now, now))
                break
            except Exception:                            # noqa: BLE001
                continue
        else:
            raise RuntimeError("Could not allocate a room code.")
        row = con.execute("SELECT * FROM rooms WHERE id = ?", (new_id,)).fetchone()
        con.execute("INSERT INTO room_log (room_id, user_id, action, detail, at)"
                    " VALUES (?,?,?,?,?)",
                    (new_id, owner_id, "opened", "opened the room", now))

    if cohort_id:
        try:
            who = AC.get_user(int(owner_id)) if owner_id else None
            NT.notify_instructors(
                int(cohort_id), NT.ROOM,
                "Live room open: %s" % row["title"],
                "%s started it. Code %s." % (who.display if who else "Someone",
                                             row["code"]),
                "Instructor view", ref="room:%s:open" % row["code"],
                exclude=int(owner_id) if owner_id else None)
        except Exception:                                          # noqa: BLE001
            pass
    return _row_to_room(row)


def get_room(code: str) -> Optional[Room]:
    with _con() as con:
        row = con.execute("SELECT * FROM rooms WHERE code = ?",
                          (code.strip().upper(),)).fetchone()
    return _row_to_room(row) if row else None


def rooms_for(cohort_id: Optional[int] = None) -> List[Room]:
    with _con() as con:
        if cohort_id is None:
            rows = con.execute("SELECT * FROM rooms ORDER BY updated DESC LIMIT 25").fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM rooms WHERE cohort_id = ? ORDER BY updated DESC LIMIT 25",
                (cohort_id,)).fetchall()
    return [_row_to_room(r) for r in rows]


def push(code: str, circuit: dict, base_version: int,
         user_id: Optional[int] = None) -> Tuple[bool, Room]:
    """Write a circuit to the room, but only if nobody else got there first.

    Returns (accepted, room).  On rejection the returned room carries the
    current state so the caller can show what actually happened instead of
    losing the edit silently.
    """
    now = time.time()
    with _con() as con:
        row = con.execute("SELECT * FROM rooms WHERE code = ?",
                          (code.strip().upper(),)).fetchone()
        if row is None:
            raise KeyError("No such room: %s" % code)
        if row["locked"] and user_id != row["owner_id"]:
            return False, _row_to_room(row)
        if row["version"] != base_version:
            return False, _row_to_room(row)
        try:
            before = json.loads(row["circuit"])
        except ValueError:
            before = {}
        detail = describe_change(before, circuit)
        con.execute(
            "UPDATE rooms SET circuit = ?, version = version + 1, updated_by = ?,"
            " updated = ? WHERE id = ?",
            (json.dumps(circuit), user_id, now, row["id"]))
        con.execute("INSERT INTO room_log (room_id, user_id, action, detail, at)"
                    " VALUES (?,?,?,?,?)",
                    (row["id"], user_id, "edit", detail, now))
        fresh = con.execute("SELECT * FROM rooms WHERE id = ?", (row["id"],)).fetchone()

    _tell_the_instructor(fresh, user_id, detail)
    return True, _row_to_room(fresh)


def _tell_the_instructor(room_row, user_id: Optional[int], detail: str) -> None:
    """One running line per person per room, not one per keystroke.

    The notification carries a ref keyed on the room and the editor, so the
    twentieth edit updates the same row the first one created instead of
    adding a twentieth entry.  Failures here are swallowed: a shared circuit
    must keep working even if nobody can be told about it.
    """
    cohort_id = room_row["cohort_id"] if room_row is not None else None
    if not cohort_id or not user_id:
        return
    try:
        who = AC.get_user(int(user_id))
        name = who.display if who else "Someone"
        NT.notify_instructors(
            int(cohort_id), NT.ROOM,
            "%s is editing %s" % (name, room_row["title"]),
            detail, "Instructor view",
            ref="room:%s:%s" % (room_row["code"], user_id),
            exclude=int(user_id), bump=True)
    except Exception:                                              # noqa: BLE001
        pass


def set_lock(code: str, locked: bool, user_id: Optional[int]) -> bool:
    """Owner-only. A locked room is broadcast: everyone watches, only the owner drives."""
    with _con() as con:
        row = con.execute("SELECT * FROM rooms WHERE code = ?",
                          (code.strip().upper(),)).fetchone()
        if row is None or (row["owner_id"] is not None and row["owner_id"] != user_id):
            return False
        con.execute("UPDATE rooms SET locked = ? WHERE id = ?", (1 if locked else 0, row["id"]))
    return True


def heartbeat(code: str, user_id: int) -> None:
    now = time.time()
    with _con() as con:
        row = con.execute("SELECT id FROM rooms WHERE code = ?",
                          (code.strip().upper(),)).fetchone()
        if row is None:
            return
        con.execute(
            "INSERT INTO presence (room_id, user_id, seen) VALUES (?,?,?)"
            " ON CONFLICT(room_id, user_id) DO UPDATE SET seen = excluded.seen",
            (row["id"], user_id, now))


def who_is_here(code: str) -> List[dict]:
    cutoff = time.time() - PRESENCE_WINDOW
    with _con() as con:
        row = con.execute("SELECT id FROM rooms WHERE code = ?",
                          (code.strip().upper(),)).fetchone()
        if row is None:
            return []
        rows = con.execute(
            "SELECT u.display, u.username, p.seen FROM presence p"
            " JOIN users u ON u.id = p.user_id"
            " WHERE p.room_id = ? AND p.seen > ? ORDER BY u.display",
            (row["id"], cutoff)).fetchall()
    return [{"display": r["display"], "username": r["username"], "seen": r["seen"]}
            for r in rows]


def history(code: str, limit: int = 12) -> List[dict]:
    with _con() as con:
        row = con.execute("SELECT id FROM rooms WHERE code = ?",
                          (code.strip().upper(),)).fetchone()
        if row is None:
            return []
        rows = con.execute(
            "SELECT l.action, l.detail, l.at, u.display FROM room_log l"
            " LEFT JOIN users u ON u.id = l.user_id"
            " WHERE l.room_id = ? ORDER BY l.id DESC LIMIT ?",
            (row["id"], limit)).fetchall()
    return [{"action": r["action"], "detail": r["detail"] or "",
             "at": r["at"], "display": r["display"] or "someone"} for r in rows]


def live_rooms(cohort_id: Optional[int] = None, window: float = 900.0) -> List[dict]:
    """Rooms touched recently, with who is in them and the last thing done.

    This is what an instructor wants on a dashboard: not every room ever made,
    but the ones running right now, and what is happening inside them.
    """
    cutoff = time.time() - window
    out = []
    for room in rooms_for(cohort_id):
        if room.updated < cutoff:
            continue
        here = who_is_here(room.code)
        log = history(room.code, limit=6)
        out.append({
            "code": room.code, "title": room.title, "locked": room.locked,
            "version": room.version, "updated": room.updated,
            "present": [p["display"] for p in here],
            "recent": log,
            "last": (log[0] if log else None),
        })
    return out
