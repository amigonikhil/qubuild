"""The tutor.

Two layers, and the split is deliberate:

* The **analysis layer** — circuit walkthrough, error detection, optimisation
  rewrites, personalised recommendations — is computed from the actual circuit
  and the learner's actual history. It needs no network and no model, and it is
  what makes the tutor say something specific rather than generic.
* The **language layer** answers free-form questions from a curated knowledge
  base, and routes to a chat model when one is configured. Configuration is a
  provider name and an API key in ``qubuild/config.py``; the HTTP work is in
  ``qubuild/llm.py``. With no key the knowledge base answers alone, so the
  platform is fully usable offline.
"""

from __future__ import annotations

import json
import math
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

from . import content as CT
from . import engine as E
from . import llm
from .circuits import Circuit, Op, fmt_param

# A URL typed into the sidebar at runtime. It overrides config.py for this
# session only, so someone can try an endpoint without editing a file.
_SESSION_ENDPOINT: Optional[str] = None
_SESSION_KEY: Optional[str] = None


def set_model_endpoint(url: Optional[str], api_key: Optional[str] = None) -> None:
    """Temporary override, for trying an endpoint without editing config.py."""
    global _SESSION_ENDPOINT, _SESSION_KEY
    _SESSION_ENDPOINT = url or None
    _SESSION_KEY = api_key or None


def has_model() -> bool:
    """True when a free-form question can reach a language model."""
    return _SESSION_ENDPOINT is not None or llm.is_configured()


def model_status() -> dict:
    """What the sidebar shows. The session endpoint wins when both are set."""
    state = llm.status()
    if _SESSION_ENDPOINT:
        state = dict(state, ready=True, provider="session",
                     label="Endpoint set in the sidebar", model=_SESSION_ENDPOINT)
    return state


# ==========================================================================
# error detection
# ==========================================================================

@dataclass
class Issue:
    level: str          # error | warn | info | good
    title: str
    body: str
    fix: Optional[dict] = None


def analyse(circuit: Circuit) -> List[Issue]:
    issues: List[Issue] = []
    ops = circuit.ordered_ops()
    if not ops:
        return [Issue("info", "Empty circuit",
                      "Add a gate, or load something from the algorithm library to see how it "
                      "is put together.")]

    used = {q for o in ops for q in o.qubits}
    for q in range(circuit.qubits):
        if q not in used:
            issues.append(Issue("warn", "Qubit %d is never used" % q,
                                "It stays in |0> and doubles the size of the state vector for "
                                "nothing. Remove the wire unless you need it as an ancilla."))

    meas_col = {o.qubits[0]: o.col for o in ops if o.name == "MEASURE"}
    for o in ops:
        if o.name in ("MEASURE", "BARRIER"):
            continue
        for q in o.qubits:
            if q in meas_col and o.col > meas_col[q]:
                issues.append(Issue(
                    "error",
                    "%s acts on qubit %d after it was measured" % (E.GATES[o.name].label or o.name, q),
                    "Qubit %d collapsed at column %d, so this gate operates on a classical bit. "
                    "Move the measurement to the end, or drop it."
                    % (q, int(meas_col[q]) + 1)))
                break
    if not meas_col:
        issues.append(Issue("info", "No measurements",
                            "The statevector view still works, but the shot histogram has "
                            "nothing to sample. Add M gates to the qubits you care about."))

    by_qubit: Dict[int, List[Op]] = {}
    for o in ops:
        if o.name == "BARRIER":
            continue
        for q in o.qubits:
            by_qubit.setdefault(q, []).append(o)

    seen = set()
    for q, lst in by_qubit.items():
        for a, b in zip(lst, lst[1:]):
            if a.name != b.name or a.name not in E.SELF_INVERSE:
                continue
            if a.qubits != b.qubits:
                continue
            blocked = [o for o in ops if o is not a and o is not b
                       and a.col < o.col < b.col and set(o.qubits) & set(a.qubits)]
            if blocked or (a.id, b.id) in seen:
                continue
            seen.add((a.id, b.id))
            issues.append(Issue(
                "warn", "Two %s gates cancel" % a.name,
                "%s is its own inverse, so this pair is an identity. Removing both leaves the "
                "circuit unchanged and shortens it." % a.name,
                {"type": "remove", "ids": [a.id, b.id]}))

    for o in ops:
        spec = E.GATES[o.name]
        if spec.param and o.params and abs(o.params[0]) < 1e-9:
            issues.append(Issue(
                "warn", "%s on qubit %d has angle 0" % (o.name, o.qubits[-1]),
                "A zero-angle rotation does nothing. It still costs depth on hardware.",
                {"type": "remove", "ids": [o.id]}))

    for q, lst in by_qubit.items():
        rots = [o for o in lst if o.name in ("RZ", "RX", "RY", "P") and len(o.qubits) == 1]
        for a, b in zip(rots, rots[1:]):
            if a.name != b.name:
                continue
            blocked = [o for o in ops if o is not a and o is not b
                       and a.col < o.col < b.col and q in o.qubits]
            if blocked:
                continue
            total = (a.params[0] if a.params else 0) + (b.params[0] if b.params else 0)
            issues.append(Issue(
                "info", "Two %s rotations can merge" % a.name,
                "Consecutive %s gates on qubit %d compose into a single %s(%s). One gate "
                "instead of two." % (a.name, q, a.name, fmt_param(total))))

    tq = circuit.two_qubit_count
    if tq > 12:
        issues.append(Issue("warn", "%d two-qubit gates" % tq,
                            "Two-qubit gates carry most of the error on real hardware. At this "
                            "count a run on a NISQ device would be heavily degraded — worth "
                            "looking for a shallower construction."))

    if not issues:
        issues.append(Issue("good", "Nothing to flag",
                            "No idle qubits, no cancelling pairs, no gates after measurement. "
                            "Depth %d, %d gates, %d of them two-qubit."
                            % (circuit.depth, circuit.gate_count, tq)))
    return issues


# ==========================================================================
# narrated walkthrough
# ==========================================================================

@dataclass
class Step:
    heading: str
    body: str


def describe_state(state: np.ndarray, n: int) -> str:
    probs = E.probabilities(state)
    terms = sorted(((float(p), i) for i, p in enumerate(probs) if p > 1e-6), reverse=True)
    if len(terms) == 1:
        return "The state is now |%s>." % E.state_label(terms[0][1], n)
    top = ", ".join("%.1f%% |%s>" % (p * 100, E.state_label(i, n)) for p, i in terms[:4])
    mixed = sum(1 for q in range(n) if E.bloch(state, n, q).entangled)
    tail = ""
    if mixed:
        tail = (" %d qubit%s now entangled with the rest, so no single qubit has a state of "
                "its own." % (mixed, " is" if mixed == 1 else "s are"))
    return "%d outcomes carry amplitude — %s%s.%s" % (
        len(terms), top, ", ..." if len(terms) > 4 else "", tail)


def explain(circuit: Circuit) -> List[Step]:
    ops = [o for o in circuit.ordered_ops() if o.name != "BARRIER"]
    if not ops:
        return [Step("Nothing to explain yet",
                     "Build a circuit and I will walk through it gate by gate, with the state "
                     "after each step.")]

    steps = [Step("Start", "All %d qubits begin in |0>, so the state is |%s> with amplitude 1."
                  % (circuit.qubits, "0" * circuit.qubits))]
    running: List[Op] = []
    for o in ops:
        spec = E.GATES[o.name]
        if o.name == "MEASURE":
            partial = Circuit(circuit.qubits, [x for x in running if x.name != "MEASURE"])
            v = E.bloch(E.statevector(partial), circuit.qubits, o.qubits[0])
            steps.append(Step(
                "Measure qubit %d" % o.qubits[0],
                "Reads 0 with probability %.3f and 1 with probability %.3f, then collapses. "
                "The walkthrough keeps describing the pre-measurement state so you can see "
                "what the shot histogram is sampling from." % (v.p0, v.p1)))
            running.append(o)
            continue
        running.append(o)
        partial = Circuit(circuit.qubits, [x for x in running if x.name != "MEASURE"])
        state = E.statevector(partial)
        if len(o.qubits) == 1:
            where = "qubit %d" % o.qubits[0]
        elif spec.ctrl:
            where = "qubit %d, controlled by %s" % (
                o.qubits[spec.ctrl],
                " and ".join("q%d" % q for q in o.qubits[:spec.ctrl]))
        else:
            where = "qubits " + " and ".join(str(q) for q in o.qubits)
        param = "(%s)" % fmt_param(o.params[0]) if spec.param and o.params else ""
        steps.append(Step("%s%s on %s" % (spec.label or o.name, param, where),
                          "%s %s" % (spec.desc, describe_state(state, circuit.qubits))))
    return steps


# ==========================================================================
# optimisation
# ==========================================================================

@dataclass
class Suggestion:
    title: str
    body: str
    fix: Optional[dict] = None


def optimise(circuit: Circuit) -> List[Suggestion]:
    out: List[Suggestion] = []
    for issue in analyse(circuit):
        if issue.fix or "merge" in issue.title or "cancel" in issue.title:
            out.append(Suggestion(issue.title, issue.body, issue.fix))

    ops = circuit.ordered_ops()
    for a, b, c in zip(ops, ops[1:], ops[2:]):
        same_wire = (len(a.qubits) == len(b.qubits) == len(c.qubits) == 1
                     and a.qubits[0] == b.qubits[0] == c.qubits[0])
        if not same_wire:
            continue
        names = (a.name, b.name, c.name)
        if names == ("H", "Z", "H"):
            out.append(Suggestion(
                "H · Z · H can become a single X",
                "Three gates on qubit %d collapse to one. Same unitary, a third of the depth."
                % a.qubits[0],
                {"type": "replace", "ids": [a.id, b.id, c.id],
                 "with": {"name": "X", "qubits": [a.qubits[0]], "params": []}}))
        if names == ("H", "X", "H"):
            out.append(Suggestion(
                "H · X · H can become a single Z",
                "Conjugating X by Hadamards gives Z. Three gates become one.",
                {"type": "replace", "ids": [a.id, b.id, c.id],
                 "with": {"name": "Z", "qubits": [a.qubits[0]], "params": []}}))

    for a, b, c in zip(ops, ops[1:], ops[2:]):
        if a.name == b.name == c.name == "CX":
            x, y = a.qubits
            if b.qubits == [y, x] and c.qubits == [x, y]:
                out.append(Suggestion(
                    "Three alternating CNOTs are a SWAP",
                    "On hardware a compiler often prefers the explicit SWAP so it can route "
                    "around connectivity limits. Same operation, clearer intent.",
                    {"type": "replace", "ids": [a.id, b.id, c.id],
                     "with": {"name": "SWAP", "qubits": [x, y], "params": []}}))

    if not out:
        out.append(Suggestion(
            "No local rewrites found",
            "Depth %d with %d two-qubit gates. Nothing in the peephole rules applies — the next "
            "win would come from a different construction rather than a local edit."
            % (circuit.depth, circuit.two_qubit_count)))
    return out


def apply_fix(circuit: Circuit, fix: dict) -> Circuit:
    if not fix:
        return circuit
    ids = set(fix.get("ids", []))
    if fix["type"] == "remove":
        circuit.ops = [o for o in circuit.ops if o.id not in ids]
    elif fix["type"] == "replace":
        anchor = next((o.col for o in circuit.ops if o.id in ids), 0.0)
        circuit.ops = [o for o in circuit.ops if o.id not in ids]
        w = fix["with"]
        circuit.ops.append(Op(w["name"], list(w["qubits"]), list(w["params"]), anchor - 0.5))
    return circuit.pack()


# ==========================================================================
# recommendations
# ==========================================================================

@dataclass
class Recommendation:
    title: str
    why: str
    goto: Optional[dict] = None


def recommend(progress: dict) -> List[Recommendation]:
    recs: List[Recommendation] = []
    lessons = progress.get("lessons", {})
    quiz = progress.get("quiz", {})
    challenges = progress.get("challenges", {})

    by_topic: Dict[str, List[int]] = {}
    for record in quiz.values():
        by_topic.setdefault(record.get("topic", "General"), []).append(1 if record["correct"] else 0)
    weak = sorted(((sum(v) / len(v), t) for t, v in by_topic.items() if len(v) >= 2),
                  key=lambda x: x[0])
    if weak and weak[0][0] < 0.7:
        rate, topic = weak[0]
        lesson = next((l for l in CT.LESSONS if l.quiz and l.quiz[0].topic == topic), None)
        recs.append(Recommendation(
            "Revisit \"%s\"" % (lesson.title if lesson else topic),
            "%d%% on %s questions" % (round(rate * 100), topic),
            {"page": "Lessons", "lesson": lesson.id} if lesson else {"page": "Lessons"}))

    nxt = next((l for l in CT.LESSONS if l.id not in lessons), None)
    if nxt:
        recs.append(Recommendation(
            nxt.title, "Next in the %s track" % CT.TRACK_BY_ID[nxt.track].name,
            {"page": "Lessons", "lesson": nxt.id}))

    nxt_c = next((c for c in CT.CHALLENGES if c.id not in challenges), None)
    if nxt_c:
        recs.append(Recommendation(
            "Challenge: " + nxt_c.title, "%s · %d XP" % (nxt_c.level, nxt_c.xp),
            {"page": "Challenges", "challenge": nxt_c.id}))

    if len(lessons) >= 4 and not challenges:
        recs.insert(0, Recommendation(
            'Start with "Make a superposition"',
            "You have read four lessons but built nothing yet",
            {"page": "Challenges", "challenge": "c1"}))

    if not recs:
        recs.append(Recommendation("Open the Studio and build something of your own",
                                   "Everything on the syllabus is done", {"page": "Circuit Studio"}))
    return recs[:3]


# ==========================================================================
# question answering
# ==========================================================================

@dataclass
class Answer:
    text: str
    title: str = ""
    action: str = ""
    goto: Optional[dict] = None
    source: str = "knowledge base"


_ACTIONS = [
    (r"(explain|walk|what does).*(circuit|this)", "explain"),
    (r"(check|debug|wrong|error|bug|mistake)", "analyse"),
    (r"(optimi[sz]e|shorten|shallower|fewer gates|simplif)", "optimise"),
    (r"(what next|what should i|recommend|where do i start|study plan|learning path)", "recommend"),
    (r"(generate|give me|write|show).*(code|qiskit|export)", "code"),
]


def answer_locally(question: str) -> Answer:
    q = (question or "").lower().strip()
    if not q:
        return Answer("Ask me anything about the material, or about the circuit you have open.")

    best, best_score = None, 0
    for article in CT.KB:
        score = sum(len(k) for k in article.keys if k in q)
        if score > best_score:
            best, best_score = article, score

    # A bare action keyword must not hijack a concept question.  "Why is the
    # gloves analogy wrong?" and "what is error correction?" both contain an
    # analyse trigger, but neither is about the circuit on screen.  A strong
    # topic match wins unless the learner actually pointed at their circuit.
    about_circuit = re.search(r"\b(my|this|the) (circuit|code)\b|\bit\b", q) is not None
    for pattern, action in _ACTIONS:
        if re.search(pattern, q):
            if best_score >= 5 and not about_circuit:
                break
            return Answer("", action=action)

    if best:
        return Answer(best.text, best.title, goto=best.goto)

    for name, spec in E.GATES.items():
        if re.search(r"\b%s\b" % name.lower(), q):
            return Answer(spec.desc, "%s gate" % name)

    # Last resort before giving up: a bare verb with a vague object — "explain
    # all these", "walk me through it" — still clearly means the open circuit.
    for verb, action in ((r"\b(explain|walk|describe|what.s happening)\b", "explain"),
                         (r"\b(check|debug|verify)\b", "analyse"),
                         (r"\b(optimi[sz]e|simplify|shorten)\b", "optimise")):
        if re.search(verb, q):
            return Answer("", action=action)

    # No prepared answer and no model to fall through to.  What this says is
    # read by whoever is standing at the machine — a learner, or a room full of
    # people at a demo — so it offers what *is* available instead of printing
    # setup instructions at them.  The sidebar is where a model gets connected,
    # and it says so there.
    return Answer(
        "That one is outside my built-in notes. What I can do right now, with no "
        "internet and no account: explain any gate by name, walk through the circuit "
        "you have open, check it for mistakes, suggest a shorter version, write the "
        "code for it, or tell you what to learn next — the buttons above do each of "
        "those. Ask me about a gate, or about your circuit, and I will answer.",
        source="knowledge base")


def ask(question: str, context: Optional[dict] = None) -> Answer:
    """Answer a free-form question, using the configured model when there is one.

    Order of preference:
      1. an action the analysis layer can perform (explain, check, optimise) —
         always local, always specific to the circuit, never sent anywhere;
      2. a sidebar endpoint, if one was typed this session;
      3. the provider configured in ``config.py``;
      4. the knowledge base.

    Every model failure falls through to (4), so a wrong key costs an answer,
    not the app.
    """
    local = answer_locally(question)
    if local.action:
        return local

    if _SESSION_ENDPOINT:
        text = _post_session_endpoint(question, context)
        if text:
            return Answer(text, "Model answer", source="sidebar endpoint")

    text = llm.complete(question, context)
    if text:
        return Answer(text, "Model answer", source=llm.status()["label"])
    return local


def _post_session_endpoint(question: str, context: Optional[dict]) -> str:
    payload = {"question": question, "context": context or {}}
    request = urllib.request.Request(
        _SESSION_ENDPOINT, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json",
                 **({"Authorization": "Bearer " + _SESSION_KEY} if _SESSION_KEY else {})})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = json.loads(response.read().decode())
        return body.get("text") or body.get("answer") or ""
    except (urllib.error.URLError, ValueError, TimeoutError, OSError):
        return ""
