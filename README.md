# QuBuild

A website for learning quantum computing that runs on your own laptop. You
open a lesson, drag gates onto wires to build a circuit, run it, and see what
comes out.

Built for Smart India Hackathon 2026 — problem statement **SIH26140**,
AI-Based Interactive Quantum Algorithm Learning Platform. Team **Innovatrix**.

---

## Running it

```
pip install -r requirements.txt
streamlit run app.py
```

That is the whole setup. No account, no key, no quantum hardware.

On Windows, `Start-QuBuild.bat` does the same thing with a double click.

---

## What is in it

**Learn.** 14 lessons across 4 tracks, from what a qubit is to Grover and
Shor. Each lesson ends with questions and the next stays locked until they are
answered — 38 checkpoints in all. Alongside them, 12 standard algorithms with
their circuits already built.

**Build.** Circuit Studio: 27 gates, drag one onto a wire to place it, drag it
again to move it, drop it in the bin to remove it. Or paste Qiskit, Cirq,
PennyLane or OpenQASM and it becomes the same circuit on screen — and converts
back out to any of the five.

**Simulate.** 8 engines: an exact one to 20 qubits, a noisy one that copies a
real machine's errors, a tensor network one that reaches 60 qubits on an
ordinary laptop, and others. You get the probability of every outcome, a Bloch
sphere per qubit, and the raw amplitudes.

**Verify.** The part nobody else does. Quantum libraries disagree about which
end the first qubit sits on — Qiskit puts it on the right, Cirq and PennyLane
on the left — so one correct circuit reads `001` in one library and `100` in
another. Beginners hit this constantly and lose days assuming they broke
something. QuBuild runs the circuit on four libraries at once and shows what
each says, then lines them all up to one answer.

**Grade.** 8 challenges marked by comparing the quantum state produced against
the correct one, not by matching code. Build it a completely different way and
it still passes if the physics is right.

**Teach.** Three roles at sign-up: Learner (alone), Student (joins with a
classroom code) and Instructor (owns a class). Instructors set work, watch
cohort progress, see which lesson a class keeps failing, and export to CSV or
SCORM. Students are notified when work is set. Instructors are notified when a
shared circuit room goes live, and can see who changed what inside it.

**Ask.** A tutor in the sidebar that reads the page you are on and the circuit
you have open. It carries 23 articles and a rule-based analyser, so it works
with no internet and no API key. Connect a language model and it also answers
open-ended questions.

---

## Why no cloud account is needed

Simulating a circuit is matrix multiplication. Twenty qubits is about 16 MB of
memory, a fraction of what a student laptop has spare. Every engine is a
Python library running inside the app on that machine, and not one makes a
network call. Progress is stored in a small local database.

IBM Quantum and qBraid connect if you want to run on real hardware, but that
is optional and nothing depends on it.

---

## Storage

SQLite by default — one file, no server, nothing to configure.

Set `QUBUILD_DB_URL` to a PostgreSQL connection string and several app servers
can share one database instead. The same code speaks both; see `qubuild/db.py`
for the three places the dialects differ.

---

## Tests

```
python -m pytest tests -q
```

140 tests, covering the physics against known states, every SDK backend
against the built-in engine, the grading, the tutor, accounts and classroom
codes, notifications, and the shared-room conflict handling. They pass on both
SQLite and PostgreSQL.

---

## Deploying

See `DEPLOY.md`. Short version: it works on Streamlit Community Cloud and
Hugging Face Spaces for free, and you should point `QUBUILD_DB_URL` at a
hosted PostgreSQL, because free hosts wipe their disk when the app sleeps and
that would erase every account.

---

## Honest limits

- Exact simulation memory doubles with every qubit. Past 20, the tensor
  network engine takes over and reports its own fidelity rather than
  pretending an approximation is exact.
- Shared rooms detect conflicts, they do not merge them. Two people editing
  the same gate in the same second: the second write is refused and that
  person is told to reload. Calling it realtime co-editing would be
  overselling it.
- Authentication is classroom-grade — scrypt hashes with a per-user salt,
  which protects a roster on a college server. It is not a public internet
  identity system; that wants e-mail verification, rate limiting and session
  expiry, none of which are here.
