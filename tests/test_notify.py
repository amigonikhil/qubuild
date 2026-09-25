"""Notifications: the fan-out, the collapsing, and what a live room reports."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _fresh():
    from dbfixture import clean_database
    clean_database()
    from qubuild import accounts as A, collab as CO, notify as N
    return A, N, CO


def _classroom():
    A, N, CO = _fresh()
    teacher, _ = A.register("miss", "pw-one-two", "Miss Rao", "instructor",
                            classroom="CSE-3A", code="ABC123")
    priya, _ = A.register("priya", "pw-one-two", "Priya", "student", code="ABC123")
    arun, _ = A.register("arun", "pw-one-two", "Arun", "student", code="ABC123")
    return A, N, CO, teacher, priya, arun


# ---------------------------------------------------------------- assignments

def test_setting_work_reaches_every_student_and_not_the_instructor():
    A, N, CO, teacher, priya, arun = _classroom()
    sent = N.announce_assignment(teacher.cohort_id, "challenge", "c6",
                                 "Grover's search", "2026-10-01", by=teacher.id)
    assert sent == 2
    assert N.unread_count(priya.id) == 1
    assert N.unread_count(arun.id) == 1
    assert N.unread_count(teacher.id) == 0

    note = N.for_user(priya.id)[0]
    assert "Grover" in note.title and "2026-10-01" in note.body
    assert note.link == "Challenges"          # the button has somewhere to go


def test_moving_a_deadline_edits_the_notice_instead_of_sending_a_second():
    A, N, CO, teacher, priya, _ = _classroom()
    N.announce_assignment(teacher.cohort_id, "lesson", "l3", "Phase kickback", "2026-10-01")
    N.announce_assignment(teacher.cohort_id, "lesson", "l3", "Phase kickback", "2026-10-08")
    notes = N.for_user(priya.id)
    assert len(notes) == 1, "a changed due date must not contradict itself in the list"
    assert "2026-10-08" in notes[0].body


def test_a_learner_outside_the_class_is_not_told():
    A, N, CO, teacher, priya, _ = _classroom()
    solo, _ = A.register("solo", "pw-one-two", "Solo", "learner")
    N.announce_assignment(teacher.cohort_id, "lesson", "l1", "Why quantum")
    assert N.unread_count(solo.id) == 0


# ---------------------------------------------------------------- collapsing

def test_a_burst_of_activity_becomes_one_line_with_a_count():
    A, N, CO, teacher, priya, _ = _classroom()
    for i in range(20):
        N.send([teacher.id], N.ROOM, "Priya is editing Bell demo", "change %d" % i,
               ref="room:XY12:priya", bump=True)
    notes = N.for_user(teacher.id)
    assert len(notes) == 1, "twenty edits must not be twenty notifications"
    assert notes[0].count == 20
    assert notes[0].body == "change 19"        # the newest wording wins


def test_reading_it_sticks_until_something_new_happens():
    A, N, CO, teacher, priya, _ = _classroom()
    N.send([teacher.id], N.ROOM, "Priya is editing", "one", ref="r1", bump=True)
    N.mark_read(teacher.id)
    assert N.unread_count(teacher.id) == 0

    # restating the same fact must not nag
    N.send([teacher.id], N.ROOM, "Priya is editing", "one", ref="r1")
    assert N.unread_count(teacher.id) == 0

    # genuinely new activity must
    N.send([teacher.id], N.ROOM, "Priya is editing", "two", ref="r1", bump=True)
    assert N.unread_count(teacher.id) == 1


def test_clearing_keeps_what_has_not_been_read():
    A, N, CO, teacher, priya, _ = _classroom()
    N.send([priya.id], N.NOTE, "read me", ref="a")
    N.send([priya.id], N.NOTE, "unread", ref="b")
    N.mark_read(priya.id, N.for_user(priya.id)[-1].id)
    N.clear(priya.id, read_only=True)
    left = N.for_user(priya.id)
    assert len(left) == 1 and left[0].unread


# ---------------------------------------------------------------- live rooms

def test_opening_a_room_tells_the_instructor_who_and_where():
    A, N, CO, teacher, priya, _ = _classroom()
    from qubuild import circuits as C
    room = CO.create_room("Bell demo", C.BY_ID["bell"].make().to_dict(),
                          owner_id=priya.id, cohort_id=teacher.cohort_id)
    note = N.for_user(teacher.id)[0]
    assert "Bell demo" in note.title
    assert "Priya" in note.body and room.code in note.body
    assert N.unread_count(priya.id) == 0, "the person who opened it needs no telling"


def test_the_log_says_what_changed_not_merely_that_something_did():
    A, N, CO, teacher, priya, _ = _classroom()
    from qubuild import circuits as C
    base = C.BY_ID["bell"].make()
    room = CO.create_room("Bell demo", base.to_dict(),
                          owner_id=priya.id, cohort_id=teacher.cohort_id)

    added = C.Circuit.from_dict(base.to_dict())
    added.add("X", [1])
    ok, room = CO.push(room.code, added.to_dict(), room.version, user_id=priya.id)
    assert ok
    assert "added X q1" in CO.history(room.code)[0]["detail"]

    ok, room = CO.push(room.code, base.to_dict(), room.version, user_id=priya.id)
    assert "removed X q1" in CO.history(room.code)[0]["detail"]

    wider = C.Circuit.from_dict(base.to_dict())
    wider.set_qubits(3)
    ok, room = CO.push(room.code, wider.to_dict(), room.version, user_id=priya.id)
    assert "3 qubits" in CO.history(room.code)[0]["detail"]


def test_edits_reach_the_instructor_as_a_single_running_line():
    A, N, CO, teacher, priya, _ = _classroom()
    from qubuild import circuits as C
    base = C.BY_ID["bell"].make()
    room = CO.create_room("Bell demo", base.to_dict(),
                          owner_id=priya.id, cohort_id=teacher.cohort_id)
    for i in range(1, 6):
        edited = C.Circuit.from_dict(base.to_dict())
        edited.set_qubits(i + 1)
        ok, room = CO.push(room.code, edited.to_dict(), room.version, user_id=priya.id)
        assert ok

    room_notes = [n for n in N.for_user(teacher.id) if n.kind == N.ROOM]
    editing = [n for n in room_notes if "is editing" in n.title]
    assert len(editing) == 1, "one line per person per room, however many edits"
    assert editing[0].count == 5
    assert "Priya" in editing[0].title


def test_live_rooms_reports_who_is_present_and_the_recent_changes():
    A, N, CO, teacher, priya, _ = _classroom()
    from qubuild import circuits as C
    base = C.BY_ID["bell"].make()
    room = CO.create_room("Bell demo", base.to_dict(),
                          owner_id=priya.id, cohort_id=teacher.cohort_id)
    wider = C.Circuit.from_dict(base.to_dict())
    wider.set_qubits(4)
    CO.push(room.code, wider.to_dict(), room.version, user_id=priya.id)
    CO.heartbeat(room.code, priya.id)

    live = CO.live_rooms(teacher.cohort_id)
    assert len(live) == 1
    assert live[0]["present"] == ["Priya"]
    assert "4 qubits" in live[0]["last"]["detail"]


def test_a_quiet_room_drops_off_the_live_list():
    A, N, CO, teacher, priya, _ = _classroom()
    from qubuild import circuits as C
    CO.create_room("Old demo", C.BY_ID["bell"].make().to_dict(),
                   owner_id=priya.id, cohort_id=teacher.cohort_id)
    assert CO.live_rooms(teacher.cohort_id, window=900) != []
    assert CO.live_rooms(teacher.cohort_id, window=0.0) == []


def test_a_failure_to_notify_never_costs_an_edit():
    """The shared circuit is the product; the notice about it is not."""
    A, N, CO, teacher, priya, _ = _classroom()
    from qubuild import circuits as C
    base = C.BY_ID["bell"].make()
    room = CO.create_room("Bell demo", base.to_dict(),
                          owner_id=priya.id, cohort_id=teacher.cohort_id)

    def explode(*args, **kwargs):
        raise RuntimeError("notification backend is down")

    original = N.notify_instructors
    N.notify_instructors = explode
    try:
        wider = C.Circuit.from_dict(base.to_dict())
        wider.set_qubits(3)
        ok, room = CO.push(room.code, wider.to_dict(), room.version, user_id=priya.id)
        assert ok, "the edit must still land"
        assert room.circuit["qubits"] == 3
    finally:
        N.notify_instructors = original


def test_ago_reads_like_a_person_wrote_it():
    A, N, CO = _fresh()
    import time
    now = time.time()
    assert N.ago(now - 5, now) == "just now"
    assert N.ago(now - 300, now) == "5 min ago"
    assert N.ago(now - 7200, now) == "2 h ago"
    assert N.ago(now - 86400, now) == "yesterday"
    assert N.ago(now - 3 * 86400, now) == "3 days ago"
