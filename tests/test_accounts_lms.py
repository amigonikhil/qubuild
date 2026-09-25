"""Accounts, cohorts and the LMS exports. Runs on whichever backend is configured."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _fresh():
    from dbfixture import clean_database
    return clean_database()


def test_passwords_are_hashed_salted_and_verifiable():
    A = _fresh()
    salt, digest = A.hash_password("hunter2")
    assert b"hunter2" not in digest
    assert len(digest) == 64
    assert A.verify_password("hunter2", salt, digest)
    assert not A.verify_password("hunter3", salt, digest)
    assert A.hash_password("hunter2")[0] != salt


def test_login_and_role():
    A = _fresh()
    A.create_user("teach", "pw-one", "Teacher", "instructor", "2A")
    user = A.authenticate("teach", "pw-one")
    assert user is not None and user.is_instructor
    assert user.cohort_name == "2A"
    assert A.authenticate("teach", "wrong") is None
    assert A.authenticate("nobody", "pw-one") is None


def test_usernames_are_unique_and_case_folded():
    A = _fresh()
    assert A.create_user("Dup", "a") is not None
    assert A.create_user("dup", "b") is None
    assert A.authenticate("DUP", "a") is not None


def test_roster_import_reports_each_row():
    A = _fresh()
    report = A.import_roster("username,display\nr1,One\nr2,Two\n,\nr1,Again\n", "2B")
    assert [c["username"] for c in report["created"]] == ["r1", "r2"]
    assert report["skipped"] == ["r1"]
    assert len(report["errors"]) == 1
    assert all(len(c["password"]) >= 8 for c in report["created"])


def test_roster_import_rejects_a_bad_header():
    A = _fresh()
    report = A.import_roster("name,email\nx,y\n", "2C")
    assert report["created"] == [] and report["errors"]


def test_progress_and_cohort_rollup():
    A = _fresh()
    cid = A.create_cohort("2D")
    user = A.create_user("l1", "pw", "Learner One", "learner", "2D")
    A.save_progress(user.id, {"xp": 60, "lessons": {"l0": True, "l1": True},
                              "challenges": {},
                              "quiz": {"a": {"correct": True}, "b": {"correct": True},
                                       "c": {"correct": False}}})
    assert A.load_progress(user.id)["xp"] == 60
    row = A.cohort_progress(cid)[0]
    assert row["lessons"] == 2 and row["attempted"] == 3 and row["correct"] == 2
    assert abs(row["accuracy"] - 2 / 3) < 1e-9


def test_reassigning_updates_rather_than_duplicates():
    A = _fresh()
    cid = A.create_cohort("2E")
    A.assign(cid, "lesson", "l1", due="2026-10-01")
    A.assign(cid, "lesson", "l1", due="2026-10-08")
    A.assign(cid, "challenge", "c2")
    rows = A.assignments(cid)
    assert len(rows) == 2
    lesson = [r for r in rows if r["kind"] == "lesson"][0]
    assert lesson["due"] == "2026-10-08"


def test_csv_export_has_a_row_per_learner():
    A = _fresh()
    from qubuild import lms as L
    cid = A.create_cohort("2F")
    A.create_user("a", "p", "Ay", "learner", "2F")
    A.create_user("b", "p", "Bee", "learner", "2F")
    lines = L.to_csv(A.cohort_progress(cid), 14, 8).strip().splitlines()
    assert len(lines) == 3
    assert lines[0].startswith("Username,Name,XP")


def test_score_is_bounded_and_monotonic():
    from qubuild import lms as L
    zero = L.score_percent({"lessons": 0, "challenges": 0, "accuracy": 0.0}, 14, 8)
    full = L.score_percent({"lessons": 14, "challenges": 8, "accuracy": 1.0}, 14, 8)
    mid = L.score_percent({"lessons": 7, "challenges": 4, "accuracy": 0.5}, 14, 8)
    assert zero == 0.0 and full == 100.0 and zero < mid < full


def test_scorm_package_is_valid():
    from qubuild import lms as L
    rows = [{"username": "a", "display": "Ay", "xp": 10, "lessons": 3, "challenges": 1,
             "attempted": 5, "correct": 4, "accuracy": 0.8, "updated": None}]
    report = L.validate_package(L.scorm_package(rows, 14, 8))
    assert report["ok"], report["errors"]
    assert "imsmanifest.xml" in report["entries"]


def test_validator_actually_rejects_a_broken_package():
    """A validator that passes everything is worse than none."""
    import io, zipfile
    from qubuild import lms as L
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("imsmanifest.xml", "<manifest/>")
    report = L.validate_package(buf.getvalue())
    assert not report["ok"]
    assert any("index.html" in e for e in report["errors"])


# ---------------------------------------------------------------- classrooms

def test_instructor_signup_creates_a_class_with_its_code():
    A = _fresh()
    user, why = A.register("teach2", "pw-one-two", "Teacher", "instructor",
                           classroom="CSE-3A", code="qb 7k-2m")
    assert why == "" and user is not None
    assert user.is_instructor and not user.is_learner
    assert user.cohort_name == "CSE-3A"
    assert user.cohort_code == "QB7K2M"          # spaces, dashes and case forgiven


def test_a_student_joins_by_code_and_lands_in_that_class():
    A = _fresh()
    teacher, _ = A.register("t", "pw-one-two", "T", "instructor",
                            classroom="2B", code="ABC123")
    student, why = A.register("s", "pw-one-two", "S", "student", code="abc-123")
    assert why == "" and student is not None
    assert student.is_student
    assert student.cohort_id == teacher.cohort_id
    assert [r["username"] for r in A.cohort_progress(teacher.cohort_id)] == ["s"]


def test_a_wrong_code_is_refused_and_says_so():
    A = _fresh()
    A.register("t", "pw-one-two", "T", "instructor", classroom="2C", code="GOOD11")
    student, why = A.register("s", "pw-one-two", "S", "student", code="WRONG9")
    assert student is None
    assert "classroom code" in why.lower()


def test_a_learner_needs_no_code_and_joins_no_class():
    A = _fresh()
    user, why = A.register("solo", "pw-one-two", "Solo", "learner")
    assert why == "" and user is not None
    assert user.is_learner and user.cohort_id is None


def test_two_classes_cannot_share_one_code():
    A = _fresh()
    A.register("t1", "pw-one-two", "T1", "instructor", classroom="3A", code="SAME11")
    second, why = A.register("t2", "pw-one-two", "T2", "instructor",
                             classroom="3B", code="SAME11")
    assert second is None and "already in use" in why


def test_an_instructor_without_a_class_name_is_refused():
    A = _fresh()
    user, why = A.register("t", "pw-one-two", "T", "instructor", classroom="  ")
    assert user is None and "class a name" in why


def test_a_code_is_generated_when_the_instructor_leaves_it_blank():
    A = _fresh()
    user, why = A.register("t", "pw-one-two", "T", "instructor", classroom="3C")
    assert why == "" and user.cohort_code
    assert len(user.cohort_code) >= A.CODE_LENGTH
    assert not (set("IO01") & set(user.cohort_code))   # no ambiguous glyphs


def test_a_learner_can_be_moved_into_a_class_later():
    A = _fresh()
    teacher, _ = A.register("t", "pw-one-two", "T", "instructor",
                            classroom="3D", code="LATER1")
    learner, _ = A.register("l", "pw-one-two", "L", "learner")
    room = A.cohort_by_code("later1")
    A.set_cohort(learner.id, int(room["id"]))
    A.set_role(learner.id, "student")
    moved = A.get_user(learner.id)
    assert moved.is_student and moved.cohort_id == teacher.cohort_id


def test_an_old_database_gains_classrooms_without_losing_anyone():
    """The migration path: two roles, no code column, real rows already in it."""
    import os
    import sqlite3
    import tempfile
    import time
    from dbfixture import clean_database

    path = os.path.join(tempfile.mkdtemp(), "old.db")
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE cohorts (id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL, created REAL NOT NULL);
        CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL, display TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('learner', 'instructor')),
            cohort_id INTEGER REFERENCES cohorts(id), salt BLOB NOT NULL,
            pw_hash BLOB NOT NULL, created REAL NOT NULL, last_seen REAL);
        CREATE TABLE progress (user_id INTEGER PRIMARY KEY REFERENCES users(id),
            data TEXT NOT NULL, updated REAL NOT NULL);
    """)
    con.execute("INSERT INTO cohorts (name, created) VALUES ('Old', ?)", (time.time(),))
    con.commit()
    con.close()

    A = clean_database()
    import hashlib
    import secrets
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(b"pw-one-two", salt=salt, **A.SCRYPT)
    con = sqlite3.connect(path)
    con.execute("INSERT INTO users (username, display, role, cohort_id, salt, pw_hash,"
                " created) VALUES ('old','Old One','instructor',1,?,?,?)",
                (salt, digest, time.time()))
    con.execute("INSERT INTO progress (user_id, data, updated) VALUES (1, ?, ?)",
                ('{"xp": 42}', time.time()))
    con.commit()
    con.close()

    A.DB_PATH = path
    A.reset_schema_cache()
    os.environ["QUBUILD_DB"] = path
    assert A.authenticate("old", "pw-one-two") is not None
    assert A.load_progress(1)["xp"] == 42
    assert A.set_cohort_code(1, "OLD123")
    joined, why = A.register("new", "pw-one-two", "New", "student", code="OLD123")
    assert why == "" and joined.is_student and joined.cohort_id == 1
