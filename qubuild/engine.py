"""State-vector simulation engine.

Pure NumPy. Qubit 0 is the least significant bit, matching Qiskit, so the
basis-state label ``011`` means q2=0, q1=1, q0=1.

The whole engine is deliberately small and dependency-free: it is the one
backend that is guaranteed to be available, and every other backend in
``backends.py`` is checked against it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence

import numpy as np

SQRT1_2 = 1.0 / np.sqrt(2.0)

# --------------------------------------------------------------------------
# gate matrices
# --------------------------------------------------------------------------

MAT: Dict[str, np.ndarray] = {
    "I": np.array([[1, 0], [0, 1]], dtype=complex),
    "X": np.array([[0, 1], [1, 0]], dtype=complex),
    "Y": np.array([[0, -1j], [1j, 0]], dtype=complex),
    "Z": np.array([[1, 0], [0, -1]], dtype=complex),
    "H": np.array([[SQRT1_2, SQRT1_2], [SQRT1_2, -SQRT1_2]], dtype=complex),
    "S": np.array([[1, 0], [0, 1j]], dtype=complex),
    "SDG": np.array([[1, 0], [0, -1j]], dtype=complex),
    "T": np.array([[1, 0], [0, SQRT1_2 + 1j * SQRT1_2]], dtype=complex),
    "TDG": np.array([[1, 0], [0, SQRT1_2 - 1j * SQRT1_2]], dtype=complex),
    "SX": 0.5 * np.array([[1 + 1j, 1 - 1j], [1 - 1j, 1 + 1j]], dtype=complex),
}


def rx(t: float) -> np.ndarray:
    c, s = np.cos(t / 2), np.sin(t / 2)
    return np.array([[c, -1j * s], [-1j * s, c]], dtype=complex)


def ry(t: float) -> np.ndarray:
    c, s = np.cos(t / 2), np.sin(t / 2)
    return np.array([[c, -s], [s, c]], dtype=complex)


def rz(t: float) -> np.ndarray:
    return np.array([[np.exp(-0.5j * t), 0], [0, np.exp(0.5j * t)]], dtype=complex)


def phase(t: float) -> np.ndarray:
    return np.array([[1, 0], [0, np.exp(1j * t)]], dtype=complex)


def u3(theta: float, phi: float, lam: float) -> np.ndarray:
    c, s = np.cos(theta / 2), np.sin(theta / 2)
    return np.array(
        [[c, -np.exp(1j * lam) * s],
         [np.exp(1j * phi) * s, np.exp(1j * (phi + lam)) * c]], dtype=complex)


@dataclass(frozen=True)
class GateSpec:
    name: str
    arity: int          # how many wires the op occupies
    ctrl: int           # how many leading wires are controls
    label: str          # what is drawn in the box
    kind: str           # box | ctrl | swap | cswap | meas | barrier
    desc: str
    param: Optional[str] = None
    nparams: int = 0


def _g(name, arity, ctrl, label, kind, desc, param=None, nparams=0):
    return GateSpec(name, arity, ctrl, label, kind, desc, param,
                    nparams or (1 if param else 0))


GATES: Dict[str, GateSpec] = {g.name: g for g in [
    _g("I", 1, 0, "I", "box", "Identity — leaves the qubit untouched."),
    _g("X", 1, 0, "X", "box", "Pauli-X — the quantum NOT. Flips |0> and |1>; a pi rotation about the x-axis."),
    _g("Y", 1, 0, "Y", "box", "Pauli-Y — bit flip plus phase flip; a pi rotation about the y-axis."),
    _g("Z", 1, 0, "Z", "box", "Pauli-Z — leaves |0> alone and sends |1> to -|1>. Invisible to a z-measurement on its own."),
    _g("H", 1, 0, "H", "box", "Hadamard — maps |0> to |+> and |1> to |->. The workhorse for creating superposition."),
    _g("S", 1, 0, "S", "box", "Phase gate — a quarter turn about z (adds i to the |1> amplitude)."),
    _g("SDG", 1, 0, "S†", "box", "Inverse phase gate — a quarter turn about z, the other way."),
    _g("T", 1, 0, "T", "box", "pi/8 gate — an eighth turn about z. With H it generates universal single-qubit rotations."),
    _g("TDG", 1, 0, "T†", "box", "Inverse T gate."),
    _g("SX", 1, 0, "√X", "box", "Square root of X — a half turn about x. Native on much IBM hardware."),
    _g("RX", 1, 0, "Rx", "box", "Rotation about x by theta. Continuous control over how far the qubit tips.", "theta"),
    _g("RY", 1, 0, "Ry", "box", "Rotation about y by theta. Moves between |0> and |1> with real amplitudes.", "theta"),
    _g("RZ", 1, 0, "Rz", "box", "Rotation about z by theta. Changes relative phase, not measurement odds in the z basis.", "theta"),
    _g("P", 1, 0, "P", "box", "Phase shift — multiplies the |1> amplitude by e^{i*phi}.", "phi"),
    _g("U", 1, 0, "U", "box", "General single-qubit unitary U(theta, phi, lambda). Any one-qubit gate is a U.", "theta", 3),
    _g("CX", 2, 1, "X", "ctrl", "CNOT — flips the target when the control is |1>. The standard entangler."),
    _g("CY", 2, 1, "Y", "ctrl", "Controlled-Y."),
    _g("CZ", 2, 1, "Z", "ctrl", "Controlled-Z — flips the sign of |11>. Symmetric in its two qubits."),
    _g("CH", 2, 1, "H", "ctrl", "Controlled-Hadamard."),
    _g("CRZ", 2, 1, "Rz", "ctrl", "Controlled z-rotation — the phase workhorse inside the QFT.", "theta"),
    _g("CRY", 2, 1, "Ry", "ctrl", "Controlled y-rotation — tips the target by theta only when the control is |1>.", "theta"),
    _g("CP", 2, 1, "P", "ctrl", "Controlled phase — adds phi only to the |11> component.", "phi"),
    _g("SWAP", 2, 0, "x", "swap", "SWAP — exchanges the states of two qubits."),
    _g("CCX", 3, 2, "X", "ctrl", "Toffoli — flips the target only when both controls are |1>. Classical AND, reversibly."),
    _g("CSWAP", 3, 1, "x", "cswap", "Fredkin — swaps two qubits when the control is |1>."),
    _g("MEASURE", 1, 0, "M", "meas", "Measurement in the computational basis — collapses the qubit and records a classical bit."),
    _g("BARRIER", 1, 0, "", "barrier", "Barrier — a visual and compiler fence. No physical effect."),
]}

SELF_INVERSE = {"I", "X", "Y", "Z", "H", "CX", "CY", "CZ", "SWAP", "CCX", "CSWAP"}


def matrix_for(name: str, params: Sequence[float]) -> np.ndarray:
    p = list(params) + [0.0, 0.0, 0.0]
    if name == "RX":
        return rx(p[0])
    if name in ("RY", "CRY"):
        return ry(p[0])
    if name in ("RZ", "CRZ"):
        return rz(p[0])
    if name in ("P", "CP"):
        return phase(p[0])
    if name == "U":
        return u3(p[0], p[1], p[2])
    if name in ("CX", "CCX"):
        return MAT["X"]
    if name == "CY":
        return MAT["Y"]
    if name == "CZ":
        return MAT["Z"]
    if name == "CH":
        return MAT["H"]
    return MAT.get(name, MAT["I"])


# --------------------------------------------------------------------------
# state manipulation
# --------------------------------------------------------------------------

def zero_state(n: int) -> np.ndarray:
    st = np.zeros(1 << n, dtype=complex)
    st[0] = 1.0
    return st


def apply_1q(state: np.ndarray, n: int, target: int, m: np.ndarray,
             controls: Sequence[int] = ()) -> np.ndarray:
    """Apply a 2x2 matrix to `target`, gated on all `controls` being 1.

    Reshapes the state so the target axis is isolated, which lets NumPy do
    the whole sweep in two vectorised expressions.
    """
    size = 1 << n
    idx = np.arange(size)
    bit = 1 << target
    lo = idx[(idx & bit) == 0]
    if controls:
        mask = 0
        for c in controls:
            mask |= 1 << c
        lo = lo[(lo & mask) == mask]
    hi = lo | bit
    a, b = state[lo].copy(), state[hi].copy()
    state[lo] = m[0, 0] * a + m[0, 1] * b
    state[hi] = m[1, 0] * a + m[1, 1] * b
    return state


def apply_swap(state: np.ndarray, n: int, a: int, b: int,
               controls: Sequence[int] = ()) -> np.ndarray:
    if a == b:
        return state
    size = 1 << n
    idx = np.arange(size)
    ba, bb = 1 << a, 1 << b
    sel = idx[((idx & ba) != 0) & ((idx & bb) == 0)]
    if controls:
        mask = 0
        for c in controls:
            mask |= 1 << c
        sel = sel[(sel & mask) == mask]
    other = (sel & ~ba) | bb
    state[sel], state[other] = state[other].copy(), state[sel].copy()
    return state


def collapse(state: np.ndarray, n: int, q: int, rng: np.random.Generator) -> int:
    idx = np.arange(1 << n)
    bit = 1 << q
    is_one = (idx & bit) != 0
    p1 = float(np.sum(np.abs(state[is_one]) ** 2))
    outcome = 1 if rng.random() < p1 else 0
    keep = is_one if outcome else ~is_one
    norm = np.sqrt(p1 if outcome else 1.0 - p1)
    state[~keep] = 0.0
    if norm > 1e-15:
        state[keep] /= norm
    return outcome


def probabilities(state: np.ndarray) -> np.ndarray:
    return np.abs(state) ** 2


def state_label(i: int, n: int) -> str:
    return format(i, "0{}b".format(n))


@dataclass
class BlochVector:
    x: float
    y: float
    z: float
    p0: float
    p1: float

    @property
    def length(self) -> float:
        return float(np.sqrt(self.x ** 2 + self.y ** 2 + self.z ** 2))

    @property
    def purity(self) -> float:
        return 0.5 * (1.0 + self.length ** 2)

    @property
    def entangled(self) -> bool:
        return self.length < 0.999


def bloch(state: np.ndarray, n: int, q: int) -> BlochVector:
    """Bloch vector of the single-qubit reduced density matrix."""
    idx = np.arange(1 << n)
    bit = 1 << q
    lo = idx[(idx & bit) == 0]
    hi = lo | bit
    a, b = state[lo], state[hi]
    r00 = float(np.sum(np.abs(a) ** 2))
    r11 = float(np.sum(np.abs(b) ** 2))
    r01 = complex(np.sum(a * np.conj(b)))
    return BlochVector(2.0 * r01.real, -2.0 * r01.imag, r00 - r11, r00, r11)


def sample(state: np.ndarray, n: int, shots: int,
           measured: Optional[Sequence[int]] = None,
           noise: Optional[dict] = None,
           seed: Optional[int] = None) -> Dict[str, int]:
    """Sample bit strings. `noise` may carry `depol` and `readout` rates."""
    rng = np.random.default_rng(seed)
    probs = probabilities(state)
    total = probs.sum()
    probs = probs / total if total > 0 else probs
    qs = list(measured) if measured else list(range(n))

    depol = float(noise.get("depol", 0.0)) if noise else 0.0
    readout = float(noise.get("readout", 0.0)) if noise else 0.0

    if depol > 0:
        probs = (1.0 - depol) * probs + depol / len(probs)
        probs = probs / probs.sum()

    draws = rng.choice(len(probs), size=shots, p=probs)
    bits = np.zeros((shots, len(qs)), dtype=np.int8)
    for k, q in enumerate(qs):
        bits[:, k] = (draws >> q) & 1
    if readout > 0:
        flips = rng.random(bits.shape) < readout
        bits = bits ^ flips.astype(np.int8)

    counts: Dict[str, int] = {}
    for row in bits:
        key = "".join(str(int(v)) for v in row[::-1])   # q0 rightmost
        counts[key] = counts.get(key, 0) + 1
    return counts


def fidelity(a: np.ndarray, b: np.ndarray) -> float:
    """|<a|b>|^2 — insensitive to global phase."""
    return float(abs(np.vdot(a, b)) ** 2)


# --------------------------------------------------------------------------
# execution
# --------------------------------------------------------------------------

@dataclass
class RunResult:
    state: np.ndarray
    bits: Dict[int, int] = field(default_factory=dict)


def run(circuit, initial: Optional[np.ndarray] = None,
        seed: Optional[int] = None) -> RunResult:
    """Execute a Circuit. MEASURE ops collapse the state in place."""
    n = circuit.qubits
    rng = np.random.default_rng(seed)
    state = zero_state(n) if initial is None else np.array(initial, dtype=complex)
    bits: Dict[int, int] = {}
    for op in circuit.ordered_ops():
        if op.name == "BARRIER":
            continue
        if op.name == "MEASURE":
            bits[op.qubits[0]] = collapse(state, n, op.qubits[0], rng)
            continue
        if op.name == "SWAP":
            apply_swap(state, n, op.qubits[0], op.qubits[1])
            continue
        if op.name == "CSWAP":
            apply_swap(state, n, op.qubits[1], op.qubits[2], [op.qubits[0]])
            continue
        spec = GATES.get(op.name)
        if spec is None:
            continue
        controls = op.qubits[:spec.ctrl]
        target = op.qubits[spec.ctrl]
        apply_1q(state, n, target, matrix_for(op.name, op.params), controls)
    return RunResult(state, bits)


def statevector(circuit) -> np.ndarray:
    """The state just before measurement — measurements are stripped."""
    return run(circuit.without_measurements()).state
