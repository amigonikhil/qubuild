"""Execution backends.

The built-in NumPy state-vector engine is always available. Qiskit Aer, Cirq
and PennyLane are detected at import os
import time and, when present, genuinely execute
the circuit through that SDK — this module converts the platform's circuit into
each SDK's native object, runs it, and normalises the result back.

Normalised conventions (matching Qiskit):
  * state vector index i has qubit 0 as the least significant bit
  * count keys are bit strings over the measured qubits, qubit 0 rightmost

Cirq and PennyLane both order wire 0 as the *most* significant bit, so their
results are reversed on the way out. `tests/test_backends.py` checks every
adapter against the built-in engine, which is what makes that claim testable
rather than decorative.
"""

from __future__ import annotations

import importlib.util
import math
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from . import engine as E
from .circuits import Circuit

PI = math.pi


def _has(mod: str) -> bool:
    try:
        return importlib.util.find_spec(mod) is not None
    except (ImportError, ValueError):
        return False


HAS_QISKIT = _has("qiskit")
try:                                    # qBraid needs both the SDK and a key
    from . import qbraid_provider as _QBR
    HAS_QBRAID_READY = bool(_QBR.HAS_SDK and _QBR.read_key())
except Exception:                       # noqa: BLE001
    HAS_QBRAID_READY = False and _has("qiskit_aer")
HAS_CIRQ = _has("cirq")
HAS_PENNYLANE = _has("pennylane")


@dataclass(frozen=True)
class BackendInfo:
    id: str
    name: str
    sdk: str
    kind: str            # "exact" or "shots"
    available: bool
    note: str
    install: str = ""


BACKENDS: List[BackendInfo] = [
    BackendInfo("numpy_sv", "QuBuild · NumPy statevector", "builtin", "exact", True,
                "Exact amplitudes from the built-in engine. Always available, no extra "
                "dependencies, and the reference every other backend is tested against."),
    BackendInfo("numpy_shots", "QuBuild · NumPy sampler", "builtin", "shots", True,
                "Samples the exact distribution the requested number of times."),
    BackendInfo("aer_sv", "Qiskit Aer · statevector", "qiskit", "exact", HAS_QISKIT,
                "Real execution: the circuit is transpiled into a qiskit.QuantumCircuit and "
                "run on AerSimulator.", "pip install qiskit qiskit-aer"),
    BackendInfo("aer_qasm", "Qiskit Aer · qasm sampler", "qiskit", "shots", HAS_QISKIT,
                "Real shot-based execution on AerSimulator with measurement instructions.",
                "pip install qiskit qiskit-aer"),
    BackendInfo("aer_noisy", "Qiskit Aer · noisy device model", "qiskit", "shots", HAS_QISKIT,
                "Real Aer noise model: depolarising error on one- and two-qubit gates plus "
                "readout error, applied during simulation rather than to the histogram.",
                "pip install qiskit qiskit-aer"),
    BackendInfo("cirq_sim", "Cirq · Simulator", "cirq", "shots", HAS_CIRQ,
                "Real execution through cirq.Simulator. Cirq orders qubit 0 first, so "
                "results are reversed on the way back.", "pip install cirq-core"),
    BackendInfo("pennylane_default", "PennyLane · default.qubit", "pennylane", "shots",
                HAS_PENNYLANE,
                "Real execution through a PennyLane QNode on default.qubit.",
                "pip install pennylane"),
    BackendInfo("qbraid", "qBraid · hosted devices", "qbraid", "shots", HAS_QBRAID_READY,
                "Submits OpenQASM to a device on your qBraid account. Adapter written and "
                "tested to the network boundary; no job has been sent from this codebase, "
                "so treat the first real run as the first real run.",
                "pip install qbraid  +  an API key in Simulation backends"),
    BackendInfo("mps_tn", "QuBuild · MPS tensor network", "mps", "shots", True,
                "Stores the state as a chain of small tensors instead of 2**n amplitudes, "
                "so circuits that keep entanglement modest run far past the exact engine's "
                "ceiling. Approximate by design: the bond dimension caps how much "
                "entanglement is kept, and every run reports the fidelity it retained."),
]

BY_ID = {b.id: b for b in BACKENDS}


def available() -> List[BackendInfo]:
    return [b for b in BACKENDS if b.available]


def missing() -> List[BackendInfo]:
    return [b for b in BACKENDS if not b.available]


DEFAULT_NOISE = {"depol_1q": 0.002, "depol_2q": 0.02, "readout": 0.02}


@dataclass
class ExecutionResult:
    state: np.ndarray
    counts: Optional[Dict[str, int]]
    backend: BackendInfo
    shots: int
    noise: Optional[dict]
    ms: int
    executed_by: str
    detail: str = ""
    blochs: List[E.BlochVector] = field(default_factory=list)

    @property
    def qubits(self) -> int:
        return int(round(math.log2(len(self.state))))


# ==========================================================================
# conversions
# ==========================================================================

def to_qiskit_circuit(circuit: Circuit, with_measurements: bool):
    """Build a real qiskit.QuantumCircuit. Classical bits cover measured qubits only."""
    from qiskit import QuantumCircuit

    measured = circuit.measured
    qc = QuantumCircuit(circuit.qubits, len(measured) if with_measurements and measured else 0)
    slot = {q: i for i, q in enumerate(measured)}
    for op in circuit.ordered_ops():
        n, qs, p = op.name, op.qubits, op.params
        if n == "MEASURE":
            if with_measurements and measured:
                qc.measure(qs[0], slot[qs[0]])
            continue
        if n == "BARRIER":
            qc.barrier(qs[0])
        elif n == "I":
            pass
        elif n in ("X", "Y", "Z", "H", "S", "T", "SX"):
            getattr(qc, n.lower())(qs[0])
        elif n == "SDG":
            qc.sdg(qs[0])
        elif n == "TDG":
            qc.tdg(qs[0])
        elif n in ("RX", "RY", "RZ", "P"):
            getattr(qc, n.lower())(p[0] if p else 0.0, qs[0])
        elif n == "U":
            vals = list(p) + [0.0, 0.0, 0.0]
            qc.u(vals[0], vals[1], vals[2], qs[0])
        elif n in ("CX", "CY", "CZ", "CH", "SWAP", "CCX", "CSWAP"):
            getattr(qc, n.lower())(*qs)
        elif n in ("CRZ", "CRY", "CP"):
            getattr(qc, n.lower())(p[0] if p else 0.0, *qs)
    return qc


def to_cirq_circuit(circuit: Circuit, with_measurements: bool):
    import cirq

    q = cirq.LineQubit.range(circuit.qubits)
    cc = cirq.Circuit()
    measured = circuit.measured
    for op in circuit.ordered_ops():
        n, qs, p = op.name, op.qubits, op.params
        t = p[0] if p else 0.0
        if n in ("BARRIER", "MEASURE"):
            continue
        if n == "I":
            continue
        gate = {
            "X": cirq.X, "Y": cirq.Y, "Z": cirq.Z, "H": cirq.H, "S": cirq.S, "T": cirq.T,
            "SX": cirq.X ** 0.5, "SDG": cirq.S ** -1, "TDG": cirq.T ** -1,
            "CX": cirq.CNOT, "CZ": cirq.CZ, "SWAP": cirq.SWAP,
            "CCX": cirq.TOFFOLI, "CSWAP": cirq.CSWAP,
            "CY": cirq.Y.controlled(), "CH": cirq.H.controlled(),
        }.get(n)
        if gate is None:
            if n == "RX":
                gate = cirq.rx(t)
            elif n == "RY":
                gate = cirq.ry(t)
            elif n == "RZ":
                gate = cirq.rz(t)
            elif n == "P":
                gate = cirq.ZPowGate(exponent=t / PI)
            elif n == "CP":
                gate = cirq.CZPowGate(exponent=t / PI)
            elif n == "CRZ":
                gate = cirq.rz(t).controlled()
            elif n == "CRY":
                gate = cirq.ry(t).controlled()
            elif n == "U":
                gate = cirq.MatrixGate(E.matrix_for("U", p))
            else:
                continue
        cc.append(gate.on(*[q[i] for i in qs]))
    if with_measurements and measured:
        cc.append(cirq.measure(*[q[i] for i in measured], key="m"))
    return cc, q


def _cirq_to_little_endian(vec: np.ndarray, n: int) -> np.ndarray:
    """Cirq puts qubit 0 in the most significant position; reverse the axes."""
    if n == 0:
        return vec
    return np.transpose(np.reshape(vec, [2] * n)).ravel()


def pennylane_program(circuit: Circuit):
    """Return a function that applies the ops on a PennyLane device."""
    import pennylane as qml

    def apply():
        for op in circuit.ordered_ops():
            n, qs, p = op.name, op.qubits, op.params
            t = p[0] if p else 0.0
            if n in ("BARRIER", "MEASURE"):
                continue
            w = qs[0] if len(qs) == 1 else list(qs)
            if n == "I":
                qml.Identity(wires=w)
            elif n == "X":
                qml.PauliX(wires=w)
            elif n == "Y":
                qml.PauliY(wires=w)
            elif n == "Z":
                qml.PauliZ(wires=w)
            elif n == "H":
                qml.Hadamard(wires=w)
            elif n == "S":
                qml.S(wires=w)
            elif n == "SDG":
                qml.adjoint(qml.S(wires=w))
            elif n == "T":
                qml.T(wires=w)
            elif n == "TDG":
                qml.adjoint(qml.T(wires=w))
            elif n == "SX":
                qml.SX(wires=w)
            elif n == "RX":
                qml.RX(t, wires=w)
            elif n == "RY":
                qml.RY(t, wires=w)
            elif n == "RZ":
                qml.RZ(t, wires=w)
            elif n == "P":
                qml.PhaseShift(t, wires=w)
            elif n == "U":
                vals = list(p) + [0.0, 0.0, 0.0]
                qml.U3(vals[0], vals[1], vals[2], wires=w)
            elif n == "CX":
                qml.CNOT(wires=w)
            elif n == "CY":
                qml.CY(wires=w)
            elif n == "CZ":
                qml.CZ(wires=w)
            elif n == "CH":
                qml.CH(wires=w)
            elif n == "CRZ":
                qml.CRZ(t, wires=w)
            elif n == "CRY":
                qml.CRY(t, wires=w)
            elif n == "CP":
                qml.ControlledPhaseShift(t, wires=w)
            elif n == "SWAP":
                qml.SWAP(wires=w)
            elif n == "CCX":
                qml.Toffoli(wires=w)
            elif n == "CSWAP":
                qml.CSWAP(wires=w)
    return apply


# ==========================================================================
# execution
# ==========================================================================

def _counts_from_bit_rows(rows: np.ndarray) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for row in rows:
        key = "".join(str(int(b)) for b in row[::-1])
        counts[key] = counts.get(key, 0) + 1
    return counts


def _run_numpy(circuit, shots, noise, exact, seed):
    state = E.statevector(circuit)
    counts = None
    if not exact or noise:
        ns = None
        if noise:
            ns = {"depol": noise.get("depol_2q", 0.02), "readout": noise.get("readout", 0.02)}
        counts = E.sample(state, circuit.qubits, shots, circuit.measured or None, ns, seed)
    return state, counts, "built-in NumPy engine"


def _run_qiskit(circuit, shots, noise, exact, seed):
    from qiskit import transpile
    from qiskit.quantum_info import Statevector
    from qiskit_aer import AerSimulator

    ideal = to_qiskit_circuit(circuit.without_measurements(), False)
    state = np.asarray(Statevector.from_instruction(ideal).data, dtype=complex)

    counts = None
    detail = "qiskit-aer, statevector from qiskit.quantum_info.Statevector"
    if not exact or noise:
        noise_model = None
        if noise:
            from qiskit_aer.noise import NoiseModel, ReadoutError, depolarizing_error
            noise_model = NoiseModel()
            noise_model.add_all_qubit_quantum_error(
                depolarizing_error(noise.get("depol_1q", 0.002), 1),
                ["id", "u1", "u2", "u3", "u", "x", "y", "z", "h", "s", "sdg", "t",
                 "tdg", "sx", "rx", "ry", "rz", "p"])
            noise_model.add_all_qubit_quantum_error(
                depolarizing_error(noise.get("depol_2q", 0.02), 2),
                ["cx", "cy", "cz", "ch", "crz", "cry", "cp", "swap"])
            r = noise.get("readout", 0.02)
            noise_model.add_all_qubit_readout_error(ReadoutError([[1 - r, r], [r, 1 - r]]))
            detail = "qiskit-aer with a NoiseModel (depolarising + readout error)"
        meas = to_qiskit_circuit(circuit, True)
        if meas.num_clbits == 0:
            meas.measure_all()
        sim = AerSimulator(noise_model=noise_model)
        job = sim.run(transpile(meas, sim), shots=shots, seed_simulator=seed)
        counts = {k.replace(" ", ""): int(v) for k, v in job.result().get_counts().items()}
    return state, counts, detail


def _run_cirq(circuit, shots, noise, exact, seed):
    import cirq

    ideal, _ = to_cirq_circuit(circuit.without_measurements(), False)
    sim = cirq.Simulator(seed=seed)
    raw = sim.simulate(ideal, qubit_order=cirq.LineQubit.range(circuit.qubits))
    state = _cirq_to_little_endian(np.asarray(raw.final_state_vector, dtype=complex),
                                   circuit.qubits)
    counts = None
    if not exact:
        cc, _ = to_cirq_circuit(circuit, True)
        if not circuit.measured:
            q = cirq.LineQubit.range(circuit.qubits)
            cc.append(cirq.measure(*q, key="m"))
        res = sim.run(cc, repetitions=shots)
        counts = _counts_from_bit_rows(res.measurements["m"])
    detail = "cirq.Simulator, qubit order reversed to little-endian"
    return state, counts, detail


def _run_pennylane(circuit, shots, noise, exact, seed):
    import pennylane as qml

    apply = pennylane_program(circuit)
    n = circuit.qubits

    dev = qml.device("default.qubit", wires=n)

    @qml.qnode(dev)
    def state_node():
        apply()
        return qml.state()

    state = _cirq_to_little_endian(np.asarray(state_node(), dtype=complex), n)

    counts = None
    if not exact:
        wires = circuit.measured or list(range(n))

        @qml.qnode(qml.device("default.qubit", wires=n, seed=seed))
        def counts_node():
            apply()
            return qml.counts(wires=wires)

        if hasattr(qml, "set_shots"):
            raw = qml.set_shots(counts_node, shots=shots)()
        else:                                     # PennyLane < 0.42
            counts_node.device._shots = qml.measurements.Shots(shots)
            raw = counts_node()
        counts = {str(k)[::-1]: int(v) for k, v in raw.items()}
    return state, counts, "PennyLane QNode on default.qubit, wire order reversed"


# Above this width a dense statevector is no longer something a laptop should
# be asked for (2**22 complex amplitudes is already 64 MB), so the MPS backend
# stops producing one and the panels that need amplitudes are skipped.
DENSE_LIMIT = 20

# How far the tensor-network backend is allowed to go.  Past DENSE_LIMIT there is
# no 2**n statevector at all — that is the point of it — so the panels that need
# one are switched off rather than fed a fake array.
MPS_LIMIT = 60


def _run_mps(circuit, shots, noise, exact, seed, chi=None):
    from . import mps as MPS
    n = circuit.qubits
    chi = chi or MPS.recommended_chi(n)
    res = MPS.run(circuit, shots=shots, chi=chi, seed=seed,
                  want_statevector=n <= DENSE_LIMIT)
    state = res.statevector
    if state is None:
        state = E.zero_state(min(n, 1))
    detail = ("MPS, bond dimension %d (max reached %d), fidelity %.4f after %d "
              "truncations" % (res.chi, res.max_bond, res.fidelity, res.truncations))
    return state, res.counts, detail


def _run_qbraid(circuit, shots, noise, exact, seed):
    from . import qbraid_provider as QBR
    device = os.environ.get("QUBUILD_QBRAID_DEVICE", "qbraid_qir_simulator")
    counts = QBR.run(circuit, device, shots=shots)
    # No statevector comes back from a hosted device — the exact engine supplies
    # one so the Bloch and amplitude panels still have something to show, and
    # the detail line says plainly that the counts are the real measurement.
    state, _, _ = _run_numpy(circuit, 0, None, True, seed)
    return state, counts, ("qBraid device %s — counts are real; the state shown is the "
                           "exact simulation for reference" % device)


_RUNNERS = {
    "builtin": _run_numpy,
    "qiskit": _run_qiskit,
    "cirq": _run_cirq,
    "pennylane": _run_pennylane,
    "mps": _run_mps,
    "qbraid": _run_qbraid,
}


def execute(circuit: Circuit, backend_id: str = "numpy_sv", shots: int = 1024,
            noise: Optional[dict] = None, seed: Optional[int] = None,
            chi: Optional[int] = None) -> ExecutionResult:
    """Run a circuit and return a normalised result.

    Falls back to the built-in engine (and says so) if the selected SDK raises.
    """
    info = BY_ID.get(backend_id, BACKENDS[0])
    if not info.available:
        info = BACKENDS[0]
    if info.id == "aer_noisy" and noise is None:
        noise = dict(DEFAULT_NOISE)

    exact = info.kind == "exact"
    started = time.perf_counter()
    runner = _RUNNERS[info.sdk]
    try:
        if info.sdk == "mps":
            state, counts, detail = runner(circuit, shots, noise, exact, seed, chi)
        else:
            state, counts, detail = runner(circuit, shots, noise, exact, seed)
        executed_by = info.sdk
    except Exception as exc:                                       # noqa: BLE001
        state, counts, _ = _run_numpy(circuit, shots, noise, exact, seed)
        executed_by = "builtin"
        detail = "%s failed (%s) — fell back to the built-in engine" % (info.sdk, exc)

    ms = max(1, int((time.perf_counter() - started) * 1000))
    # A Bloch vector is read out of the full statevector, which a tensor-network
    # run past DENSE_LIMIT deliberately never builds.  Return no vectors rather
    # than indexing an array that is 2**60 entries short.
    dense = state is not None and state.size == (1 << circuit.qubits)
    blochs = ([E.bloch(state, circuit.qubits, q) for q in range(circuit.qubits)]
              if dense else [])
    return ExecutionResult(state, counts, info, shots, noise, ms, executed_by, detail, blochs)


def exact_marginal(state: np.ndarray, n: int, measured: Optional[List[int]]) -> Dict[str, float]:
    """Exact probability over the measured qubits only."""
    probs = E.probabilities(state)
    qs = measured if measured else list(range(n))
    out: Dict[str, float] = {}
    for i, p in enumerate(probs):
        if p < 1e-12:
            continue
        key = "".join(str((i >> q) & 1) for q in reversed(qs))
        out[key] = out.get(key, 0.0) + float(p)
    return out


# --------------------------------------------------------------------------
# cross-SDK check
# --------------------------------------------------------------------------
#
# Every runner above already normalises its SDK's output to one convention, so
# the Studio shows one answer whichever backend is selected.  That is correct,
# and it also hides the single most useful thing a learner can be shown: the
# SDKs do not agree on how to write a bit string down, and a student who only
# ever sees one of them cannot tell which half of what she knows is physics.
#
# So this function asks each SDK the same question and reports the answer in
# that SDK's OWN words, next to the normalised one.  It runs them itself rather
# than reusing _run_cirq / _run_pennylane, because those return the corrected
# state and the whole point here is to see the state before the correction.
# Nothing above this line is touched.

CROSS_LIMIT = 12          # four SDKs on one keystroke; past this it is not free


@dataclass
class SDKReading:
    """How one SDK writes down the most likely outcome of a circuit."""
    sdk: str
    native: str           # the bit string as that SDK prints it
    normalised: str       # the same physical state in QuBuild's convention
    flipped: bool         # does this SDK read the wires the other way round?
    agrees: bool          # after normalising, does it match the reference?
    fidelity: float       # |<reference|this>|^2, 1.0 when they are the same state
    available: bool
    note: str = ""


def _bits_low_first(index: int, n: int) -> str:
    """Qiskit's convention: qubit 0 is the RIGHTMOST character."""
    return format(index, "0%db" % n) if n else ""


def _bits_high_first(index: int, n: int) -> str:
    """Cirq and PennyLane: wire 0 is the LEFTMOST character."""
    return format(index, "0%db" % n) if n else ""


def _peak(vec: np.ndarray) -> int:
    return int(np.argmax(np.abs(np.asarray(vec, dtype=complex)) ** 2))


def _fidelity(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=complex).ravel()
    b = np.asarray(b, dtype=complex).ravel()
    if a.shape != b.shape:
        return 0.0
    return float(min(1.0, abs(np.vdot(a, b)) ** 2))


def _raw_cirq(circuit: Circuit) -> np.ndarray:
    """Cirq's statevector exactly as Cirq hands it over — qubit 0 most significant."""
    import cirq
    ideal, _ = to_cirq_circuit(circuit.without_measurements(), False)
    sim = cirq.Simulator(seed=0)
    out = sim.simulate(ideal, qubit_order=cirq.LineQubit.range(circuit.qubits))
    return np.asarray(out.final_state_vector, dtype=complex)


def _raw_pennylane(circuit: Circuit) -> np.ndarray:
    """PennyLane's statevector before the wire order is reversed."""
    import pennylane as qml
    apply = pennylane_program(circuit)
    dev = qml.device("default.qubit", wires=circuit.qubits)

    @qml.qnode(dev)
    def state_node():
        apply()
        return qml.state()

    return np.asarray(state_node(), dtype=complex)


def cross_check(circuit: Circuit) -> List[SDKReading]:
    """Ask every installed SDK for the same circuit and compare how each writes it.

    The reference is the built-in engine.  For each SDK the most likely basis
    state is rendered twice: once in that SDK's own reading order, and once
    after QuBuild's normalisation.  ``agrees`` is the real check — it compares
    the whole normalised state vector, not just the peak.
    """
    n = circuit.qubits
    clean = circuit.without_measurements()
    reference = E.statevector(clean)
    ref_index = _peak(reference)
    ref_bits = _bits_low_first(ref_index, n)

    rows: List[SDKReading] = [SDKReading(
        sdk="QuBuild (NumPy)", native=ref_bits, normalised=ref_bits, flipped=False,
        agrees=True, fidelity=1.0, available=True,
        note="the reference every other row is checked against")]

    # --- Qiskit Aer: same convention as ours, so native == normalised -------
    if HAS_QISKIT:
        try:
            from qiskit_aer import AerSimulator                       # noqa: F401
            state, _, _ = _run_qiskit(clean, 0, None, True, 0)
            idx = _peak(state)
            rows.append(SDKReading(
                sdk="Qiskit Aer", native=_bits_low_first(idx, n),
                normalised=_bits_low_first(idx, n), flipped=False,
                agrees=idx == ref_index, fidelity=_fidelity(reference, state),
                available=True, note="qubit 0 on the right — the convention we follow"))
        except Exception as exc:                                       # noqa: BLE001
            rows.append(SDKReading("Qiskit Aer", "", "", False, False, 0.0, False,
                                   str(exc)[:60]))
    else:
        rows.append(SDKReading("Qiskit Aer", "", "", False, False, 0.0, False,
                               "not installed"))

    # --- Cirq and PennyLane: wire 0 on the left ----------------------------
    for label, flag, raw_fn, hint in (
            ("Cirq", HAS_CIRQ, _raw_cirq, "wire 0 on the left — reads backwards"),
            ("PennyLane", HAS_PENNYLANE, _raw_pennylane,
             "wire 0 on the left — reads backwards")):
        if not flag:
            rows.append(SDKReading(label, "", "", False, False, 0.0, False,
                                   "not installed"))
            continue
        try:
            raw = raw_fn(clean)
            fixed = _cirq_to_little_endian(raw, n)
            idx_raw, idx_fixed = _peak(raw), _peak(fixed)
            rows.append(SDKReading(
                sdk=label,
                native=_bits_high_first(idx_raw, n),
                normalised=_bits_low_first(idx_fixed, n),
                flipped=True,
                agrees=idx_fixed == ref_index,
                fidelity=_fidelity(reference, fixed),
                available=True, note=hint))
        except Exception as exc:                                       # noqa: BLE001
            rows.append(SDKReading(label, "", "", False, False, 0.0, False,
                                   str(exc)[:60]))
    return rows


def cross_check_is_useful(circuit: Circuit) -> Tuple[bool, str]:
    """Would a cross-SDK comparison actually show anything on this circuit?

    A bit string that reads the same backwards — 00, 11, 0110 — hides the
    difference completely, which is why a Bell state is the worst possible
    demonstration of it despite being the best demonstration of everything else.
    """
    n = circuit.qubits
    if n < 2:
        return False, "Add a second qubit — one wire has no order to disagree about."
    if n > CROSS_LIMIT:
        return False, ("Shown up to %d qubits; running four SDKs on every keystroke "
                       "past that is not free." % CROSS_LIMIT)
    if not circuit.without_measurements().ops:
        return False, "Drop a gate on a wire and the three SDKs will answer."
    bits = _bits_low_first(_peak(E.statevector(circuit.without_measurements())), n)
    if bits == bits[::-1]:
        return False, ("This outcome reads the same both ways (%s), so the SDKs cannot "
                       "disagree about it. Put a gate on one wire only." % bits)
    return True, ""
