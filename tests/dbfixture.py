"""Give each test a clean database, whichever backend is configured.

Without this the account tests pin themselves to a temporary SQLite file, which
means running the suite against Postgres proves nothing — every test would share
one schema and collide on usernames. With it, `pytest` run with QUBUILD_DB_URL
set genuinely certifies the Postgres path.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qubuild import accounts as AC, collab as CO, db as DB, notify as NT


def clean_database():
    """Reset storage and return the accounts module, ready to use."""
    if DB.is_postgres():
        con = DB.connect()
        con.executescript(
            "DROP TABLE IF EXISTS notifications;"
            "DROP TABLE IF EXISTS room_log; DROP TABLE IF EXISTS presence;"
            "DROP TABLE IF EXISTS rooms; DROP TABLE IF EXISTS assignments;"
            "DROP TABLE IF EXISTS progress; DROP TABLE IF EXISTS users;"
            "DROP TABLE IF EXISTS cohorts;")
        con.commit()
        con.close()
    else:
        AC.DB_PATH = os.path.join(tempfile.mkdtemp(), "t.db")
    # Each module lays its tables down once per process, so a test that swaps
    # the file underneath has to say the new one still needs them.
    AC.reset_schema_cache()
    CO.reset_schema_cache()
    NT.reset_schema_cache()
    return AC
