"""The dialect layer — the translation, not the database."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qubuild import db as DB


def _sqlite_mode():
    os.environ.pop("QUBUILD_DB_URL", None)


def test_defaults_to_sqlite():
    _sqlite_mode()
    assert DB.backend_name() == "sqlite"
    assert DB.is_postgres() is False
    assert DB.describe()["multi_server"] is False


def test_a_url_switches_backend():
    os.environ["QUBUILD_DB_URL"] = "postgresql://u:p@db.example.org:5432/qubuild"
    try:
        assert DB.is_postgres() is True
        assert DB.backend_name() == "postgresql"
        assert DB.describe()["multi_server"] is True
    finally:
        _sqlite_mode()


def test_describe_never_prints_the_password():
    os.environ["QUBUILD_DB_URL"] = "postgresql://admin:hunter2@db.example.org/qubuild"
    try:
        target = DB.describe()["target"]
        assert "hunter2" not in target
        assert "admin" not in target
        assert "db.example.org" in target
    finally:
        _sqlite_mode()


def test_placeholders_are_rewritten():
    assert (DB.to_pg("SELECT * FROM t WHERE a = ? AND b = ?")
            == "SELECT * FROM t WHERE a = %s AND b = %s")


def test_question_marks_inside_strings_are_left_alone():
    """A literal '?' in SQL text must not become a placeholder."""
    sql = "SELECT * FROM t WHERE note = 'why? because' AND id = ?"
    out = DB.to_pg(sql)
    assert "'why? because'" in out
    assert out.endswith("id = %s")
    assert out.count("%s") == 1


def test_ddl_translation_only_happens_for_postgres():
    ddl = "CREATE TABLE x (id INTEGER PRIMARY KEY AUTOINCREMENT, t REAL, b BLOB)"
    _sqlite_mode()
    assert DB.ddl_for(ddl) == ddl

    os.environ["QUBUILD_DB_URL"] = "postgresql://x/y"
    try:
        out = DB.ddl_for(ddl)
        assert "BIGSERIAL PRIMARY KEY" in out
        assert "DOUBLE PRECISION" in out
        assert "BYTEA" in out
        assert "AUTOINCREMENT" not in out
    finally:
        _sqlite_mode()


def test_sqlite_connection_uses_wal():
    _sqlite_mode()
    import tempfile
    path = os.path.join(tempfile.mkdtemp(), "w.db")
    con = DB.connect(path)
    mode = con.execute("PRAGMA journal_mode").fetchone()[0]
    con.close()
    assert str(mode).lower() == "wal"


def test_explicit_path_beats_the_environment():
    """Threading the path avoids one caller redirecting every other caller."""
    _sqlite_mode()
    import tempfile
    a = os.path.join(tempfile.mkdtemp(), "a.db")
    b = os.path.join(tempfile.mkdtemp(), "b.db")
    os.environ["QUBUILD_DB"] = a
    try:
        con = DB.connect(b)
        con.executescript("CREATE TABLE IF NOT EXISTS marker (x INTEGER)")
        con.commit(); con.close()
        assert os.path.exists(b)
        assert not os.path.exists(a)
    finally:
        os.environ.pop("QUBUILD_DB", None)
