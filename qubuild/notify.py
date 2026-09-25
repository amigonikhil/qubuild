"""Notifications: what happened, to whom it matters, and whether they saw it.

Two things in a classroom are worth interrupting someone for.  An instructor
sets work, and every student in that cohort should be told without having to
go looking.  A shared circuit room goes live, and the instructor should know
it is running and who is doing what inside it.

**Why there is a dedupe key.**  The second of those fires constantly: a room
with four people in it produces an edit every second or two.  One notification
per edit is not a feature, it is a denial of service against the person
reading them.  Every notification may carry a ``ref``, unique per user, and
sending again against the same ref *updates the existing row* rather than
adding another.  So thirty edits by one student collapse into a single line
that says thirty, and it moves back to unread when the count changes.

**What this is not.**  There is no push, no e-mail, no websocket.  A
notification is a row in the same database as everything else, read when the
page next renders.  That is honest for a platform whose whole argument is that
it runs on a laptop with no services behind it, and it is enough: the learner
sees the assignment the next time they look, which is when they could have
acted on it anyway.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence

from . import accounts as AC

#: Kinds, so the page can group and icon them. Anything else is allowed and
#: falls through to a plain note.
ASSIGNMENT = "assignment"
ROOM = "room"
ROSTER = "roster"
NOTE = "note"

SCHEMA = """
CREATE TABLE IF NOT EXISTS notifications (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id),
    kind       TEXT NOT NULL,
    title      TEXT NOT NULL,
    body       TEXT,
    link       TEXT,
    ref        TEXT,
    count      INTEGER NOT NULL DEFAULT 1,
    created    REAL NOT NULL,
    updated    REAL NOT NULL,
    read_at    REAL
);
CREATE INDEX IF NOT EXISTS notif_user ON notifications (user_id, id);
CREATE UNIQUE INDEX IF NOT EXISTS notif_ref ON notifications (user_id, ref);
"""

_READY = False


def _con():
    global _READY
    con = AC.connect()
    if not _READY:
        con.executescript(SCHEMA)
        _READY = True
    return con


def reset_schema_cache() -> None:
    """Forget that the table was created — for tests that swap databases."""
    global _READY
    _READY = False


@dataclass
class Notification:
    id: int
    kind: str
    title: str
    body: str
    link: str
    count: int
    created: float
    updated: float
    read_at: Optional[float]

    @property
    def unread(self) -> bool:
        return self.read_at is None


def _row(r) -> Notification:
    return Notification(int(r["id"]), r["kind"], r["title"], r["body"] or "",
                        r["link"] or "", int(r["count"] or 1),
                        float(r["created"]), float(r["updated"]), r["read_at"])


# --------------------------------------------------------------------------
# sending
# --------------------------------------------------------------------------

def send(user_ids: Iterable[int], kind: str, title: str, body: str = "",
         link: str = "", ref: str = "", bump: bool = False) -> int:
    """Deliver one notification to each user. Returns how many rows were touched.

    With a ``ref``, a second send to the same person updates the row it already
    has instead of adding another.  ``bump`` additionally increments its count
    and marks it unread again — that is what turns a stream of edits into
    "Priya made 12 changes" rather than twelve separate lines.
    """
    user_ids = [int(u) for u in dict.fromkeys(user_ids) if u]
    if not user_ids:
        return 0
    now = time.time()
    touched = 0
    with _con() as con:
        for uid in user_ids:
            if ref:
                existing = con.execute(
                    "SELECT id, count FROM notifications WHERE user_id = ? AND ref = ?",
                    (uid, ref)).fetchone()
                if existing is not None:
                    if bump:
                        # A new event on the same thread: count it and make it
                        # unread again, so a reader who already looked is told
                        # that more has happened since.
                        con.execute(
                            "UPDATE notifications SET title = ?, body = ?, link = ?,"
                            " count = count + 1, updated = ?, read_at = NULL"
                            " WHERE id = ?",
                            (title, body, link, now, existing["id"]))
                    else:
                        # Same event, restated: refresh the wording and leave
                        # read/unread exactly as the reader left it.
                        con.execute(
                            "UPDATE notifications SET title = ?, body = ?, link = ?,"
                            " updated = ? WHERE id = ?",
                            (title, body, link, now, existing["id"]))
                    touched += 1
                    continue
            con.execute(
                "INSERT INTO notifications"
                " (user_id, kind, title, body, link, ref, count, created, updated)"
                " VALUES (?,?,?,?,?,?,1,?,?)",
                (uid, kind, title, body, link, ref or None, now, now))
            touched += 1
    return touched


def notify_cohort(cohort_id: int, kind: str, title: str, body: str = "",
                  link: str = "", ref: str = "", exclude: Optional[int] = None,
                  students_only: bool = True) -> int:
    """Send to everyone in a cohort, optionally skipping the person who acted."""
    if not cohort_id:
        return 0
    people = AC.members(int(cohort_id))
    targets = [u.id for u in people
               if (not students_only or not u.is_instructor) and u.id != exclude]
    return send(targets, kind, title, body, link, ref)


def notify_instructors(cohort_id: int, kind: str, title: str, body: str = "",
                       link: str = "", ref: str = "", exclude: Optional[int] = None,
                       bump: bool = False) -> int:
    """Send to whoever teaches this cohort — its owner, and any instructor in it."""
    if not cohort_id:
        return 0
    targets = [u.id for u in AC.members(int(cohort_id))
               if u.is_instructor and u.id != exclude]
    with _con() as con:
        row = con.execute("SELECT owner_id FROM cohorts WHERE id = ?",
                          (int(cohort_id),)).fetchone()
    owner = row["owner_id"] if row is not None else None
    if owner and owner != exclude:
        targets.append(int(owner))
    return send(targets, kind, title, body, link, ref, bump=bump)


# --------------------------------------------------------------------------
# reading
# --------------------------------------------------------------------------

def announce_assignment(cohort_id: int, kind: str, item_id: str, title: str,
                        due: str = "", note: str = "", by: Optional[int] = None) -> int:
    """Tell a cohort that work has been set, and where to go and do it.

    The ref is keyed on the item, not on the due date, so moving a deadline
    edits the notice the class already has rather than sending a second one
    that contradicts the first.
    """
    what = "challenge" if kind == "challenge" else "lesson"
    body = "Due %s." % due.strip() if due and due.strip() else "No due date set."
    if note and note.strip():
        body += " " + note.strip()
    page = "Challenges" if kind == "challenge" else "Lessons"
    return notify_cohort(
        cohort_id, ASSIGNMENT,
        "New %s set: %s" % (what, title), body, page,
        ref="assign:%s:%s:%s" % (cohort_id, kind, item_id), exclude=by)


def for_user(user_id: int, limit: int = 40,
             unread_only: bool = False) -> List[Notification]:
    clause = " AND read_at IS NULL" if unread_only else ""
    with _con() as con:
        rows = con.execute(
            "SELECT * FROM notifications WHERE user_id = ?" + clause +
            " ORDER BY updated DESC, id DESC LIMIT ?", (int(user_id), int(limit))).fetchall()
    return [_row(r) for r in rows]


def unread_count(user_id: int) -> int:
    with _con() as con:
        row = con.execute(
            "SELECT COUNT(*) AS n FROM notifications"
            " WHERE user_id = ? AND read_at IS NULL", (int(user_id),)).fetchone()
    return int(row["n"]) if row else 0


def mark_read(user_id: int, notif_id: Optional[int] = None) -> None:
    """One notification, or every unread one when no id is given."""
    now = time.time()
    with _con() as con:
        if notif_id is None:
            con.execute("UPDATE notifications SET read_at = ?"
                        " WHERE user_id = ? AND read_at IS NULL", (now, int(user_id)))
        else:
            con.execute("UPDATE notifications SET read_at = ?"
                        " WHERE user_id = ? AND id = ?", (now, int(user_id), int(notif_id)))


def clear(user_id: int, read_only: bool = True) -> int:
    with _con() as con:
        clause = " AND read_at IS NOT NULL" if read_only else ""
        before = con.execute("SELECT COUNT(*) AS n FROM notifications"
                             " WHERE user_id = ?" + clause, (int(user_id),)).fetchone()
        con.execute("DELETE FROM notifications WHERE user_id = ?" + clause,
                    (int(user_id),))
    return int(before["n"]) if before else 0


def ago(then: float, now: Optional[float] = None) -> str:
    """'just now', '4 min ago', '2 h ago', '3 days ago' — short enough for a list."""
    seconds = max(0.0, (now or time.time()) - then)
    if seconds < 45:
        return "just now"
    if seconds < 3600:
        return "%d min ago" % max(1, round(seconds / 60))
    if seconds < 86400:
        return "%d h ago" % round(seconds / 3600)
    days = round(seconds / 86400)
    return "yesterday" if days == 1 else "%d days ago" % days
