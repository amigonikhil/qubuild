"""Delivery table — the problem statement's objectives mapped to what is built.

Kept as data rather than prose so the same rows can drive the in-app page and
be exported into a submission document without drifting apart.
"""

import os
import re


def test_count() -> int:
    """Count `def test_*` across tests/, so the figure on the page cannot drift."""
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests")
    total = 0
    try:
        for name in sorted(os.listdir(root)):
            if name.startswith("test_") and name.endswith(".py"):
                with open(os.path.join(root, name), encoding="utf-8") as handle:
                    total += len(re.findall(r"^def test_", handle.read(), re.M))
    except OSError:
        return 0
    return total


DELIVERY = [
    dict(id="D1",
         ask="Design and develop an interactive web-based platform for learning "
             "quantum computing and quantum algorithms.",
         got="Nine-page Streamlit application — Overview, Deliverables, Lessons, "
             "Algorithm library, Circuit Studio, Challenges, Assessment, My progress, "
             "Instructor view. Runs with `streamlit run app.py`.",
         evidence="13 lessons across 4 tracks · 12-circuit algorithm library",
         status="Delivered"),
    dict(id="D2",
         ask="Provide graphical (drag-and-drop) and code-based quantum circuit "
             "design tools.",
         got="Form-driven gate builder with live inspector (change qubits, angles, "
             "delete, duplicate), plus a code panel that parses and emits four "
             "dialects. Streamlit reruns on every interaction, so results update "
             "without a Run button.",
         evidence="Qiskit · Cirq · PennyLane · OpenQASM 2.0, in and out",
         status="Delivered"),
    dict(id="D3",
         ask="Enable real-time execution and simulation using multiple backends "
             "(Qiskit Aer, PennyLane, Cirq, qBraid).",
         got="A NumPy state-vector engine plus real adapters: the circuit is "
             "converted into a genuine qiskit.QuantumCircuit, cirq.Circuit or "
             "PennyLane QNode and executed there. Installed SDKs appear "
             "automatically in the backend list.",
         evidence="7 backends including a real Aer NoiseModel",
         status="Delivered — real SDKs"),
    dict(id="D4",
         ask="Integrate AI-assisted tutoring for concept explanation, code "
             "generation, debugging and personalised recommendations.",
         got="Analysis layer computed from your circuit: gate-by-gate walkthrough "
             "with live state, error detection, one-click optimisation rewrites, "
             "recommendations from quiz history — all offline. Language layer answers "
             "from a knowledge base, or from Claude, GPT, Gemini, Groq, OpenRouter or a "
             "local Ollama model once you paste a key into qubuild/config.py.",
         evidence="7 error rules · 5 unitary-preserving rewrites · 14-article KB · 6 model providers",
         status="Delivered"),
    dict(id="D5",
         ask="Support visualisation of quantum states, Bloch spheres, measurement "
             "probabilities and circuit execution results.",
         got="3D Bloch sphere per qubit from the reduced density matrix, "
             "exact-vs-sampled histogram, amplitude table and a complex-plane "
             "phase wheel — all rendered with Matplotlib.",
         evidence="A Bell pair collapses both Bloch vectors to the origin",
         status="Delivered"),
    dict(id="D6",
         ask="Include assessment modules, coding challenges, progress tracking and "
             "instructor dashboards.",
         got="18-question bank across 5 topics with reasoning, 8 challenges graded "
             "by state fidelity with enforced constraints, XP/level/mastery "
             "persisted to disk, and an instructor dashboard with completion, score "
             "distribution, ranked misconceptions and a roster.",
         evidence="Grading compares states, not strings",
         status="Delivered"),
    dict(id="D7",
         ask="Scalable and accessible, contributing to a quantum-ready workforce.",
         got="Three required dependencies. Deploys unchanged to Streamlit Community "
             "Cloud, any container host, or a college LAN. Heavy SDKs stay optional "
             "so a low-spec lab machine can still run everything.",
         evidence="streamlit · numpy · matplotlib",
         status="Delivered"),
]

VERIFICATION = [
    ("Bell and GHZ states", "Exactly two outcomes at 50% each; both Bloch vectors collapse to the origin"),
    ("Deutsch–Jozsa (balanced oracle)", "Input register reads 11 every time, never 00"),
    ("Bernstein–Vazirani", "Recovers the hidden string s = 101 in a single query"),
    ("Grover, 2 qubits", "Marked state found with probability 1.000 after one iteration"),
    ("Grover, 3 qubits", "Marked state reaches 94.5% after two iterations"),
    ("Quantum teleportation", "The prepared state genuinely arrives on qubit 2"),
    ("QFT of a basis state", "All eight amplitudes uniform at 12.5%"),
    ("Code round-trip", "A circuit exported to each of the four dialects re-imports identically"),
    ("SDK agreement", "Every installed backend matches the reference state vector to fidelity > 1 − 10⁻⁶"),
    ("Tutor key handling", "Every provider's request shape and response shape is checked, and every "
                           "failure path (no key, wrong key, no network, timeout) falls back to the "
                           "knowledge base rather than raising"),
    ("Bit ordering", "All backends report 001 for the same circuit, despite Cirq and PennyLane "
                     "ordering wire 0 first"),
]

# Two lists rather than one, because "built" and "proven" are different claims
# and a jury is entitled to know which is which.
SHIPPED_SINCE = [
    ("Larger circuits",
     "MPS tensor-network backend — circuits past 50 qubits when entanglement stays modest, "
     "with a bond-dimension control and a retained-fidelity readout on every run",
     "Verified: matches the exact engine to 1e-9 on 32 circuits including non-adjacent "
     "gates, CCX and CSWAP; reported fidelity tracks true fidelity within 0.08"),
    ("Drag-and-drop circuit design",
     "A real drag surface: gates dragged from the palette onto a wire, dragged again to "
     "move, dragged to the bin to delete. A hand-written Streamlit component — no npm "
     "build step, so it works from a plain checkout",
     "Verified in a browser: place, apply, move and delete all round-trip into the Python "
     "circuit model; the browser gate table is asserted equal to the engine's"),
    ("Accounts and cohorts",
     "SQLite or Postgres store, scrypt-hashed passwords, learner and instructor roles, "
     "CSV roster import, instructor-assigned lessons and challenges",
     "Verified: 11 tests covering hashing, timing-safe login, roster errors and rollups"),
    ("Shared sessions",
     "Live rooms with a six-character code: everyone sees one circuit, presence shows who "
     "is here, and an instructor can lock the room to broadcast",
     "Verified: 10 tests, including that a stale write is REFUSED rather than silently "
     "overwriting the other person's work"),
    ("Multi-server deployment",
     "One storage layer over SQLite (WAL) or Postgres, selected by QUBUILD_DB_URL, so "
     "several app servers can share one database",
     "Verified: the entire 116-test suite passes against both backends, and three separate "
     "processes were shown sharing one room through Postgres"),
    ("LMS score export",
     "Gradebook CSV plus a SCORM 1.2 package that reports scores through the standard "
     "JavaScript API",
     "Verified: every package is re-opened and its manifest parsed before download, and "
     "the validator is itself tested against a deliberately broken package"),
    ("Real quantum hardware",
     "IBM Quantum submission, device listing, queue position and result retrieval by job "
     "id, with local credential storage",
     "PARTLY VERIFIED: tested to the network boundary against a stand-in service. No "
     "submission to IBM has been made from this codebase"),
    ("qBraid provider",
     "Hosted qBraid devices as an execution backend, circuit handed over as OpenQASM, with "
     "device listing and local credential storage",
     "PARTLY VERIFIED: 9 tests cover translation, device listing, three result shapes and "
     "every error path. No job has been submitted to qBraid"),
]

PHASE_2 = [
    ("Sub-second co-editing", "Character-level merge, cursors, operational transforms",
     "Rooms poll about once a second and refuse conflicting writes. True OT or CRDT merge "
     "needs a websocket server and a different data model; what is here is honest about "
     "being a shared session rather than Google-Docs editing"),
    ("LTI 1.3 launch", "Launch QuBuild from inside Moodle or Canvas with single sign-on",
     "Needs a client id, a deployment id and a public keyset registered by the "
     "institution's LMS administrator. SCORM export covers the grade path meanwhile"),
    ("GPU simulation", "CUDA state-vector simulation for dense circuits past 30 qubits",
     "The MPS backend covers low-entanglement width; dense width needs hardware this "
     "project does not have"),
    ("Error correction", "Surface-code encoding and syndrome decoding as a teaching track",
     "A curriculum problem more than a code one — it needs its own lesson design"),
]

DEMO_ORDER = [
    ("Open a lesson", "Show the runnable demo circuit and the live state description under it."),
    ("Load Grover from the library", "Two clicks to a depth-22 circuit — proves the library is real."),
    ("Switch the backend to Qiskit Aer", "The results panel reports which SDK actually executed it."),
    ("Turn on the noisy device model", "The clean two-peak histogram fills in. This is a real Aer NoiseModel."),
    ("Ask the tutor to check the circuit", "Add a gate after a measurement first, so it catches a real mistake."),
    ("Apply an optimisation", "One click removes a cancelling pair; the state is unchanged."),
    ("Solve a challenge", "Build a Bell pair — grading is on fidelity, so any correct construction passes."),
    ("Open the instructor view", "Cohort completion and misconception ranking — the workforce angle."),
]
