"""Shared rooms — especially the part where two people collide."""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qubuild import accounts as AC, collab as CO


def _fresh():
    from dbfixture import clean_database
    clean_database()
    teacher = AC.create_user("t", "pw", "Teacher", "instructor", "2A")
    student = AC.create_user("s", "pw", "Student", "learner", "2A")
    return teacher, student


C0 = {"qubits": 2, "ops": [{"name": "H", "qubits": [0], "params": [], "col": 0}]}
C1 = {"qubits": 2, "ops": [{"name": "H", "qubits": [0], "params": [], "col": 0},
                           {"name": "CX", "qubits": [0, 1], "params": [], "col": 1}]}
C2 = {"qubits": 2, "ops": [{"name": "X", "qubits": [1], "params": [], "col": 0}]}


def test_room_is_created_with_a_readable_code():
    _fresh()
    room = CO.create_room("Bell pair", C0)
    assert len(room.code) == 6
    assert room.code.isupper()
    # no characters that get misheard when read out in a lab
    assert not set(room.code) & set("IO01")
    assert room.version == 1
    assert room.circuit == C0


def test_everyone_reads_the_same_room():
    _fresh()
    room = CO.create_room("Shared", C0)
    again = CO.get_room(room.code.lower())        # case-insensitive lookup
    assert again is not None and again.circuit == C0


def test_an_edit_is_visible_to_the_next_reader():
    teacher, student = _fresh()
    room = CO.create_room("Shared", C0, owner_id=teacher.id)
    ok, updated = CO.push(room.code, C1, room.version, user_id=student.id)
    assert ok and updated.version == 2
    assert CO.get_room(room.code).circuit == C1


def test_a_stale_write_is_refused_not_silently_applied():
    """The whole point. Two people editing from the same base must not clobber."""
    teacher, student = _fresh()
    room = CO.create_room("Shared", C0, owner_id=teacher.id)
    base = room.version

    ok_a, after_a = CO.push(room.code, C1, base, user_id=teacher.id)
    assert ok_a and after_a.version == base + 1

    # student still holds the old version
    ok_b, current = CO.push(room.code, C2, base, user_id=student.id)
    assert ok_b is False
    assert current.version == base + 1
    assert current.circuit == C1          # the first write survived intact


def test_after_refetching_the_second_write_succeeds():
    teacher, student = _fresh()
    room = CO.create_room("Shared", C0, owner_id=teacher.id)
    CO.push(room.code, C1, room.version, user_id=teacher.id)
    fresh = CO.get_room(room.code)
    ok, final = CO.push(room.code, C2, fresh.version, user_id=student.id)
    assert ok and final.circuit == C2


def test_locking_makes_it_a_broadcast():
    teacher, student = _fresh()
    room = CO.create_room("Demo", C0, owner_id=teacher.id)
    assert CO.set_lock(room.code, True, teacher.id) is True

    fresh = CO.get_room(room.code)
    ok, _ = CO.push(room.code, C1, fresh.version, user_id=student.id)
    assert ok is False                                    # audience cannot drive

    ok, _ = CO.push(room.code, C1, fresh.version, user_id=teacher.id)
    assert ok is True                                     # owner still can


def test_a_student_cannot_unlock_the_room():
    teacher, student = _fresh()
    room = CO.create_room("Demo", C0, owner_id=teacher.id)
    CO.set_lock(room.code, True, teacher.id)
    assert CO.set_lock(room.code, False, student.id) is False
    assert CO.get_room(room.code).locked is True


def test_presence_lists_the_living_and_forgets_the_gone():
    teacher, student = _fresh()
    room = CO.create_room("Shared", C0, owner_id=teacher.id)
    CO.heartbeat(room.code, teacher.id)
    CO.heartbeat(room.code, student.id)
    here = CO.who_is_here(room.code)
    assert {p["display"] for p in here} == {"Teacher", "Student"}

    CO.PRESENCE_WINDOW = 0.05
    time.sleep(0.12)
    CO.heartbeat(room.code, teacher.id)
    here = CO.who_is_here(room.code)
    assert [p["display"] for p in here] == ["Teacher"]
    CO.PRESENCE_WINDOW = 25.0


def test_history_records_who_changed_what():
    teacher, student = _fresh()
    room = CO.create_room("Shared", C0, owner_id=teacher.id)
    CO.push(room.code, C1, room.version, user_id=student.id)
    log = CO.history(room.code)
    assert log and log[0]["display"] == "Student" and log[0]["action"] == "edit"


def test_unknown_room_raises_rather_than_creating_one():
    _fresh()
    assert CO.get_room("ZZZZZZ") is None
    try:
        CO.push("ZZZZZZ", C0, 1)
    except KeyError:
        pass
    else:
        raise AssertionError("expected KeyError")
