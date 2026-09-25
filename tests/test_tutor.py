"""The tutor must say specific, correct things about specific circuits."""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qubuild import circuits as C     # noqa: E402
from qubuild import content as CT     # noqa: E402
from qubuild import engine as E       # noqa: E402
from qubuild import tutor as T        # noqa: E402

B = C.Circuit.build
PI = math.pi


def test_flags_gate_after_measurement():
    c = B(2, [("H", [0]), ("MEASURE", [0]), ("X", [0])])
    issues = T.analyse(c)
    assert any(i.level == "error" and "after it was measured" in i.title for i in issues)


def test_flags_idle_qubit():
    c = B(3, [("H", [0]), ("CX", [0, 1])])
    assert any("Qubit 2 is never used" in i.title for i in T.analyse(c))


def test_flags_and_removes_cancelling_pair():
    c = B(2, [("H", [0]), ("H", [0]), ("CX", [0, 1])])
    issues = [i for i in T.analyse(c) if i.fix and i.fix["type"] == "remove"]
    assert issues, "two adjacent H gates should be flagged"
    before = E.statevector(c)
    T.apply_fix(c, issues[0].fix)
    assert [o.name for o in c.ops] == ["CX"]
    assert E.fidelity(before, E.statevector(c)) > 0.999999


def test_does_not_flag_separated_pair():
    c = B(1, [("H", [0]), ("Z", [0]), ("H", [0])])
    assert not any("cancel" in i.title for i in T.analyse(c))


def test_flags_zero_angle_rotation():
    c = B(1, [("RX", [0], [0.0]), ("H", [0])])
    assert any("angle 0" in i.title for i in T.analyse(c))


def test_clean_circuit_is_clean():
    c = C.BY_ID["bell"].make()
    levels = {i.level for i in T.analyse(c)}
    assert "error" not in levels


def test_hzh_rewrite_preserves_the_unitary():
    c = B(1, [("H", [0]), ("Z", [0]), ("H", [0])])
    before = E.statevector(c)
    fix = next(s.fix for s in T.optimise(c) if s.fix and s.fix["with"]["name"] == "X")
    T.apply_fix(c, fix)
    assert [o.name for o in c.ops] == ["X"]
    assert E.fidelity(before, E.statevector(c)) > 0.999999


def test_three_cnots_rewrite_to_swap():
    c = B(2, [("X", [0]), ("CX", [0, 1]), ("CX", [1, 0]), ("CX", [0, 1])])
    before = E.statevector(c)
    fix = next(s.fix for s in T.optimise(c) if s.fix and s.fix["with"]["name"] == "SWAP")
    T.apply_fix(c, fix)
    assert E.fidelity(before, E.statevector(c)) > 0.999999


def test_walkthrough_matches_the_circuit():
    c = C.BY_ID["bell"].make()
    steps = T.explain(c)
    assert steps[0].heading == "Start"
    assert any("controlled by q0" in s.heading for s in steps)
    # the pre-measurement state is 50/50, never a collapsed 100%
    measure_steps = [s for s in steps if s.heading.startswith("Measure")]
    assert measure_steps and all("0.500" in s.body for s in measure_steps)


def test_walkthrough_reports_entanglement():
    c = C.BY_ID["ghz"].make().without_measurements()
    assert "entangled" in T.explain(c)[-1].body


def test_recommends_the_first_lesson_when_empty():
    recs = T.recommend({"lessons": {}, "quiz": {}, "challenges": {}})
    assert recs and recs[0].goto["page"] in ("Lessons", "Challenges")


def test_recommends_review_after_weak_quiz_results():
    progress = {"lessons": {l.id: 1 for l in CT.LESSONS}, "challenges": {},
                "quiz": {"a": {"correct": False, "topic": "Algorithms"},
                         "b": {"correct": False, "topic": "Algorithms"},
                         "c": {"correct": True, "topic": "Foundations"}}}
    recs = T.recommend(progress)
    assert any("Revisit" in r.title for r in recs)


def test_question_routing():
    assert T.answer_locally("explain my circuit").action == "explain"
    assert T.answer_locally("is there a bug in this?").action == "analyse"
    assert T.answer_locally("can you optimise it").action == "optimise"
    assert T.answer_locally("what should i study next").action == "recommend"


def test_knowledge_base_lookup():
    a = T.answer_locally("what is entanglement")
    assert a.title == "Entanglement" and "Bloch" in a.text


def test_gate_lookup_fallback():
    a = T.answer_locally("what does the toffoli gate do")
    assert "Toffoli" in a.text or "CCX" in a.title


def test_unknown_question_is_honest():
    a = T.answer_locally("what is the airspeed velocity of a swallow")
    assert a.source == "knowledge base"
    assert not a.action and not a.title


def test_the_honest_answer_offers_help_rather_than_homework():
    """It is read by a learner, and at a demo by a room — not by a developer.

    The old wording ended with "open app.py, set API_PROVIDER and API_KEY",
    which is a maintenance instruction printed at whoever is watching.
    """
    text = T.answer_locally("what is the airspeed velocity of a swallow").text.lower()
    assert "app.py" not in text and "api_key" not in text and "restart" not in text
    for offer in ("gate", "circuit", "mistakes", "learn next"):
        assert offer in text, offer


def test_all_challenges_are_solvable_by_their_reference_solution():
    """Every challenge must be passable, and its constraints must not block the answer."""
    solutions = {
        "c1": (1, [("H", [0])]),
        "c2": (1, [("H", [0]), ("Z", [0]), ("H", [0])]),
        "c3": (1, [("H", [0]), ("SDG", [0])]),
        "c4": (2, [("H", [0]), ("CX", [0, 1])]),
        "c5": (2, [("X", [0]), ("H", [0]), ("X", [1]), ("CX", [0, 1])]),
        "c6": (3, [("H", [0]), ("CX", [0, 1]), ("CX", [1, 2])]),
        "c7": (2, [("X", [0]), ("CX", [0, 1]), ("CX", [1, 0]), ("CX", [0, 1])]),
        "c8": (2, [("H", [0]), ("H", [1]), ("X", [0]), ("CZ", [0, 1]), ("X", [0]),
                   ("H", [0]), ("H", [1]), ("X", [0]), ("X", [1]), ("CZ", [0, 1]),
                   ("X", [0]), ("X", [1]), ("H", [0]), ("H", [1])]),
    }
    for challenge in CT.CHALLENGES:
        n, spec = solutions[challenge.id]
        circuit = B(n, spec)
        assert n == challenge.qubits, challenge.id
        assert not [o for o in circuit.ops if o.name in challenge.banned], challenge.id
        if challenge.max_two_qubit is not None:
            assert circuit.two_qubit_count <= challenge.max_two_qubit, challenge.id
        score = challenge.score(E.statevector(circuit))
        assert score > 0.999, "%s scored %.4f" % (challenge.id, score)


def test_quiz_bank_is_well_formed():
    for q in CT.QUIZ_BANK + [q for l in CT.LESSONS for q in l.quiz]:
        assert 2 <= len(q.options) <= 5
        assert 0 <= q.answer < len(q.options)
        assert len(q.why) > 20


def test_every_lesson_demo_runs():
    for lesson in CT.LESSONS:
        circuit = lesson.demo()
        state = E.statevector(circuit)
        assert abs(float((abs(state) ** 2).sum()) - 1.0) < 1e-9, lesson.id


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    for name, fn in tests:
        try:
            fn()
            print("  ok  " + name)
        except Exception as exc:                                   # noqa: BLE001
            fails += 1
            print("FAIL  %s: %s" % (name, exc))
    print("\n%d passed, %d failed" % (len(tests) - fails, fails))
    sys.exit(1 if fails else 0)
