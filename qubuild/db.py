"""One storage layer, two databases.

QuBuild's whole argument is that a college can run it on a machine it already
owns, so SQLite is the default and always will be: no server to install, no
credentials, one file to back up.  That is also the ceiling — one process on one
host.

Pointing ``QUBUILD_DB_URL`` at a Postgres instance lifts it.  Several app
servers behind a load balancer then share one database, which is what "scalable"
has to mean before anyone should claim it.

The two dialects differ in exactly three ways that matter here, and this module
hides those three rather than pulling in an ORM:

    placeholders   sqlite uses ?          postgres uses %s
    autoincrement  INTEGER ... AUTOINCREMENT   vs  BIGSERIAL
    upsert         both speak ON CONFLICT, so that one needs no translation

Everything above this file writes plain SQL with ``?`` and gets the right thing.
SQLite is opened in WAL mode, which lets readers continue during a write — worth
having even on a single host with thirty students in a lab.
"""

from __future__ import annotations

import os
import re
import sqlite3
from typing import Any, Iterable, Optional

DEFAULT_SQLITE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "qubuild.db")

#: SQLite files this process has already switched into WAL mode.
_WAL_SET: set = set()


def url() -> str:
    return os.environ.get("QUBUILD_DB_URL", "").strip()


def is_postgres() -> bool:
    return url().startswith(("postgres://", "postgresql://"))


def backend_name() -> str:
    return "postgresql" if is_postgres() else "sqlite"


def sqlite_path() -> str:
    """Where the SQLite file lives. Honoured only when no URL is set."""
    return os.environ.get("QUBUILD_DB", DEFAULT_SQLITE)


# --------------------------------------------------------------------------
# dialect translation
# --------------------------------------------------------------------------

_STRING = re.compile(r"'(?:[^']|'')*'")


def to_pg(sql: str) -> str:
    """Rewrite ``?`` placeholders as ``%s`` without touching quoted text."""
    out, last = [], 0
    for m in _STRING.finditer(sql):
        out.append(sql[last:m.start()].replace("?", "%s"))
        out.append(m.group(0))
        last = m.end()
    out.append(sql[last:].replace("?", "%s"))
    return "".join(out)


def ddl_for(sql: str) -> str:
    """Translate the shared schema into the active dialect."""
    if not is_postgres():
        return sql
    sql = re.sub(r"INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT", "BIGSERIAL PRIMARY KEY",
                 sql, flags=re.I)
    sql = re.sub(r"\bINTEGER\b", "BIGINT", sql)
    sql = re.sub(r"\bREAL\b", "DOUBLE PRECISION", sql)
    sql = re.sub(r"\bBLOB\b", "BYTEA", sql)
    return sql


class _Cursor:
    """Wraps a driver cursor so callers can use ``?`` and index rows by name."""

    def __init__(self, cur, pg: bool):
        self._cur, self._pg = cur, pg

    def execute(self, sql: str, params: Iterable[Any] = ()):
        self._cur.execute(to_pg(sql) if self._pg else sql, tuple(params))
        return self

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    @property
    def lastrowid(self):
        return getattr(self._cur, "lastrowid", None)


class Connection:
    """A context-managed connection that commits on a clean exit."""

    def __init__(self, raw, pg: bool):
        self._raw, self._pg = raw, pg

    def execute(self, sql: str, params: Iterable[Any] = ()):
        cur = self._raw.cursor()
        cur.execute(to_pg(sql) if self._pg else sql, tuple(params))
        return _Cursor(cur, self._pg)

    def executescript(self, script: str):
        script = ddl_for(script)
        if self._pg:
            with self._raw.cursor() as cur:
                for stmt in [s.strip() for s in script.split(";") if s.strip()]:
                    cur.execute(stmt)
        else:
            self._raw.executescript(script)

    def insert_returning_id(self, sql: str, params: Iterable[Any]) -> Optional[int]:
        """AUTOINCREMENT ids come back differently; ask for them the same way."""
        if self._pg:
            cur = self._raw.cursor()
            cur.execute(to_pg(sql.rstrip().rstrip(";")) + " RETURNING id", tuple(params))
            row = cur.fetchone()
            if not row:
                return None
            # dict_row gives a mapping, so the column comes back by name, not
            # by position — index both ways rather than assume one.
            return int(row["id"] if isinstance(row, dict) else row[0])
        cur = self._raw.cursor()
        cur.execute(sql, tuple(params))
        return cur.lastrowid

    def commit(self):
        self._raw.commit()

    def close(self):
        self._raw.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self._raw.commit()
        else:
            self._raw.rollback()
        self._raw.close()
        return False


def connect(path: Optional[str] = None) -> Connection:
    """Open the active database.

    ``path`` overrides the SQLite location for this call. It is passed
    explicitly rather than through the environment because an environment
    variable is process-global: one caller setting it would silently redirect
    every other caller, which is exactly the kind of bug that only shows up
    once two parts of the app use different databases.
    """
    if is_postgres():
        import psycopg
        from psycopg.rows import dict_row
        raw = psycopg.connect(url(), row_factory=dict_row)
        return Connection(raw, True)

    target = path or sqlite_path()
    raw = sqlite3.connect(target, timeout=15.0)
    raw.row_factory = sqlite3.Row
    try:
        # WAL is a property of the file, not of the connection, so it is set
        # once per file and never again. Asking for it on every connection
        # costs a header write, which on Windows is a visible stall behind
        # every click.
        if target not in _WAL_SET:
            raw.execute("PRAGMA journal_mode=WAL")
            _WAL_SET.add(target)
        # These two are per-connection and genuinely have to be set each time.
        raw.execute("PRAGMA busy_timeout=8000")
        raw.execute("PRAGMA synchronous=NORMAL")
    except sqlite3.Error:
        pass
    return Connection(raw, False)


def describe() -> dict:
    """For the Deliverables page — what storage is actually in use right now."""
    if is_postgres():
        host = re.sub(r"://[^@]*@", "://", url())        # never show credentials
        return {"backend": "postgresql", "target": host,
                "multi_server": True,
                "note": "Several app servers can share this database."}
    return {"backend": "sqlite", "target": sqlite_path(),
            "multi_server": False,
            "note": "Single host, WAL mode. Set QUBUILD_DB_URL to a Postgres URL "
                    "to run more than one app server."}
