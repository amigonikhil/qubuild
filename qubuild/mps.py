"""Matrix-product-state simulator: many more qubits, at a stated cost.

The exact engine in ``engine.py`` stores all 2**n amplitudes, so it stops
dead somewhere around 25-30 qubits on a laptop.  This module stores the state
as a chain of small tensors instead:

    A[0] --- A[1] --- A[2] --- ... --- A[n-1]
      |        |        |                |
     s_0      s_1      s_2             s_{n-1}

Each ``A[k]`` has shape ``(D_left, 2, D_right)``.  The bond dimensions D are
what carries entanglement between the left and right halves of the chain: a
product state needs D = 1, and a state entangled across a cut needs D equal to
the Schmidt rank there.  Memory is O(n * chi^2) rather than O(2**n), so a
circuit that keeps entanglement modest runs at 30, 50 or 100 qubits.

**This is an approximation, and the approximation is the point.**  After every
two-qubit gate the bond is truncated back to ``chi`` by discarding the smallest
Schmidt coefficients.  Keep chi large enough and the result is exact to machine
precision; too small and it is wrong.  So the simulator reports the weight it
threw away (:attr:`MPS.fidelity`) instead of quietly returning a pretty answer,
and the Studio surfaces that number next to the histogram.  A run that says
"fidelity 0.61" is telling you not to trust it.

Truncation is only meaningful when the chain is in canonical form, so an
orthogonality centre is carried along and moved to the active bond before every
two-qubit gate.  Without that, the singular values being compared are not the
Schmidt coefficients and the "error" would be fiction.

Conventions match the rest of QuBuild: qubit 0 is the least significant bit and
sits on the right of a bit string.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import engine as E
from .circuits import Circuit

# Gates with more than two qubits are rewritten into one- and two-qubit gates
# rather than handled natively: a three-site update would need its own SVD
# chain, and these standard decompositions are exact anyway.
CCX_DECOMP = [
    ("H", 2), ("CX", 1, 2), ("TDG", 2), ("CX", 0, 2), ("T", 2), ("CX", 1, 2),
    ("TDG", 2), ("CX", 0, 2), ("T", 1), ("T", 2), ("H", 2),
    ("CX", 0, 1), ("T", 0), ("TDG", 1), ("CX", 0, 1),
]


def _swap_matrix() -> np.ndarray:
    m = np.zeros((4, 4), dtype=complex)
    m[0, 0] = m[3, 3] = 1.0
    m[1, 2] = m[2, 1] = 1.0
    return m


SWAP4 = _swap_matrix()


def controlled_4x4(m: np.ndarray, control_first: bool) -> np.ndarray:
    """A controlled 2x2 as a 4x4 on the ordered site pair.

    Basis index is ``first * 2 + second``.  Which of the two sites holds the
    control depends on whether the control qubit sits left or right of the
    target in the chain, so both orderings are built explicitly.
    """
    u = np.eye(4, dtype=complex)
    if control_first:                       # control is the left site
        u[2:4, 2:4] = m
    else:                                   # control is the right site
        u[np.ix_([1, 3], [1, 3])] = m
    return u


@dataclass
class MPS:
    """A matrix-product state with a moving orthogonality centre."""

    n: int
    chi: int = 64
    cutoff: float = 1e-10
    tensors: List[np.ndarray] = field(default_factory=list)
    order: List[int] = field(default_factory=list)   # order[site] = qubit
    oc: int = 0                                      # orthogonality centre
    fidelity: float = 1.0                            # running (1 - discarded)
    max_bond: int = 1
    truncations: int = 0

    def __post_init__(self):
        if not self.tensors:
            self.tensors = []
            for _ in range(self.n):
                a = np.zeros((1, 2, 1), dtype=complex)
                a[0, 0, 0] = 1.0
                self.tensors.append(a)
        if not self.order:
            self.order = list(range(self.n))

    # ------------------------------------------------------------------
    # canonical form
    # ------------------------------------------------------------------

    def _shift_right(self, k: int) -> None:
        dl, _, dr = self.tensors[k].shape
        q, r = np.linalg.qr(self.tensors[k].reshape(dl * 2, dr))
        self.tensors[k] = q.reshape(dl, 2, -1)
        self.tensors[k + 1] = np.einsum("ab,bjc->ajc", r, self.tensors[k + 1])

    def _shift_left(self, k: int) -> None:
        dl, _, dr = self.tensors[k].shape
        q, r = np.linalg.qr(self.tensors[k].reshape(dl, 2 * dr).T)
        self.tensors[k] = q.T.reshape(-1, 2, dr)
        self.tensors[k - 1] = np.einsum("aib,cb->aic", self.tensors[k - 1], r)

    def move_center(self, target: int) -> None:
        while self.oc < target:
            self._shift_right(self.oc); self.oc += 1
        while self.oc > target:
            self._shift_left(self.oc); self.oc -= 1

    # ------------------------------------------------------------------
    # gates
    # ------------------------------------------------------------------

    def apply_1q(self, site: int, m: np.ndarray) -> None:
        self.tensors[site] = np.einsum("ij,ajb->aib", m, self.tensors[site])

    def apply_2q_adjacent(self, k: int, u: np.ndarray) -> None:
        """Apply a 4x4 to sites (k, k+1), then truncate the bond between them."""
        self.move_center(k)
        a, b = self.tensors[k], self.tensors[k + 1]
        dl, dr = a.shape[0], b.shape[2]

        theta = np.einsum("aib,bjc->aijc", a, b).reshape(dl, 4, dr)
        theta = np.einsum("xy,ayc->axc", u, theta).reshape(dl * 2, 2 * dr)

        left, s, right = np.linalg.svd(theta, full_matrices=False)

        total = float(np.sum(s ** 2))
        keep = int(np.sum(s > self.cutoff))
        keep = max(1, min(keep, self.chi))
        if keep < len(s):
            discarded = float(np.sum(s[keep:] ** 2))
            if total > 0:
                # Fidelity is multiplicative across independent truncations, so
                # the running product is the honest figure to show a learner.
                self.fidelity *= max(0.0, 1.0 - discarded / total)
            self.truncations += 1

        left, s, right = left[:, :keep], s[:keep], right[:keep, :]
        norm = np.linalg.norm(s)
        if norm > 0:
            s = s / norm

        self.tensors[k] = left.reshape(dl, 2, keep)
        self.tensors[k + 1] = (np.diag(s) @ right).reshape(keep, 2, dr)
        self.oc = k + 1
        self.max_bond = max(self.max_bond, keep)

    def _site_of(self, qubit: int) -> int:
        return self.order.index(qubit)

    def apply_2q(self, qa: int, qb: int, matrix_for_pair) -> None:
        """Apply a two-qubit gate to any pair, adjacent or not.

        Distant qubits are walked together with SWAPs.  The tensors are left
        where the walk puts them and the site->qubit map is updated instead of
        swapping back, which halves the gate count; the mapping is undone once,
        at read-out.
        """
        sa, sb = self._site_of(qa), self._site_of(qb)
        while abs(sa - sb) > 1:
            if sa < sb:
                self._swap_sites(sb - 1); sb -= 1
            else:
                self._swap_sites(sa - 1); sa -= 1
        k = min(sa, sb)
        control_first = (self.order[k] == qa)
        self.apply_2q_adjacent(k, matrix_for_pair(control_first))

    def _swap_sites(self, k: int) -> None:
        self.apply_2q_adjacent(k, SWAP4)
        self.order[k], self.order[k + 1] = self.order[k + 1], self.order[k]

    # ------------------------------------------------------------------
    # read-out
    # ------------------------------------------------------------------

    def to_statevector(self) -> np.ndarray:
        """Contract the whole chain. Only sane for small n — it is O(2**n)."""
        psi = self.tensors[0]
        for t in self.tensors[1:]:
            psi = np.tensordot(psi, t, axes=([psi.ndim - 1], [0]))
        psi = psi.reshape([2] * self.n)

        # sites are permuted, and qubit q must land on bit 2**q
        inverse = [0] * self.n
        for site, qubit in enumerate(self.order):
            inverse[qubit] = site
        psi = np.transpose(psi, [inverse[q] for q in reversed(range(self.n))])
        vec = psi.reshape(-1)
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 0 else vec

    def sample(self, shots: int, rng: np.random.Generator,
               measured: Optional[Sequence[int]] = None) -> Dict[str, int]:
        """Perfect sampling, no dense state built.

        With the chain right-canonical, the environment to the right of the
        active site is the identity, so the conditional probability of each
        outcome is read straight off the local tensor.  That makes every shot
        an exact independent draw from the represented state — no Markov chain,
        no burn-in.

        Every qubit is still sampled, because the chain has to be walked end to
        end either way; ``measured`` only decides which of those bits reach the
        label.  A circuit that measures one qubit therefore returns ``0``/``1``
        here exactly as it does on every other backend, rather than a full
        n-bit string that no caller asked for.
        """
        self.move_center(0)
        qs = list(measured) if measured else list(range(self.n))
        counts: Dict[str, int] = {}
        for _ in range(shots):
            bits = [0] * self.n
            boundary = np.ones((1, 1), dtype=complex)
            for site in range(self.n):
                t = np.einsum("ab,bjc->ajc", boundary, self.tensors[site])
                p = np.array([float(np.real(np.vdot(t[:, s, :], t[:, s, :])))
                              for s in (0, 1)])
                total = p.sum()
                p = p / total if total > 0 else np.array([1.0, 0.0])
                s = int(rng.random() >= p[0])
                bits[self.order[site]] = s
                boundary = t[:, s, :] / max(np.sqrt(p[s]), 1e-300)
            # qubit 0 rightmost, the convention every backend here reports in
            label = "".join(str(bits[q]) for q in reversed(qs))
            counts[label] = counts.get(label, 0) + 1
        return counts


# --------------------------------------------------------------------------
# running a Circuit
# --------------------------------------------------------------------------

@dataclass
class MPSResult:
    counts: Dict[str, int]
    fidelity: float
    max_bond: int
    truncations: int
    chi: int
    statevector: Optional[np.ndarray] = None


def _expand(circuit: Circuit) -> List[Tuple[str, List[int], List[float]]]:
    """Flatten to one- and two-qubit ops, decomposing CCX and CSWAP."""
    out: List[Tuple[str, List[int], List[float]]] = []
    for op in circuit.ordered_ops():
        if op.name in ("BARRIER", "MEASURE"):
            continue
        if op.name == "CSWAP":
            c, a, b = op.qubits
            out.append(("CX", [b, a], []))
            out.extend(_ccx(c, a, b))
            out.append(("CX", [b, a], []))
        elif op.name == "CCX":
            out.extend(_ccx(*op.qubits))
        else:
            out.append((op.name, list(op.qubits), list(op.params)))
    return out


def _ccx(c1: int, c2: int, t: int):
    wires = [c1, c2, t]
    return [(name, [wires[i] for i in idx], [])
            for name, *idx in CCX_DECOMP]


def run(circuit: Circuit, shots: int = 1024, chi: int = 64,
        seed: Optional[int] = None, want_statevector: bool = False) -> MPSResult:
    """Simulate a circuit as an MPS and sample it."""
    n = circuit.qubits
    state = MPS(n=n, chi=chi)
    rng = np.random.default_rng(seed)

    for name, qubits, params in _expand(circuit):
        if name == "SWAP":
            qa, qb = qubits
            state.apply_2q(qa, qb, lambda _first: SWAP4)
            continue
        spec = E.GATES.get(name)
        if spec is None:
            continue
        m = E.matrix_for(name, params)
        if spec.ctrl == 0:
            state.apply_1q(state._site_of(qubits[0]), m)
        else:
            control, target = qubits[0], qubits[1]
            state.apply_2q(control, target,
                           lambda first, m=m: controlled_4x4(m, first))

    counts = state.sample(shots, rng, circuit.measured or None) if shots else {}
    vec = state.to_statevector() if (want_statevector and n <= 20) else None
    return MPSResult(counts=counts, fidelity=state.fidelity,
                     max_bond=state.max_bond, truncations=state.truncations,
                     chi=chi, statevector=vec)


def recommended_chi(n: int) -> int:
    """A starting bond dimension that keeps memory sane as n grows."""
    if n <= 16:
        return 64
    if n <= 32:
        return 48
    if n <= 64:
        return 32
    return 24
