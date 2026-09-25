"""Physics and parser regression tests.

Run with `python -m pytest tests -q` or plain `python tests/test_physics.py`.
Every claim the platform makes in a lesson is checked here.
"""

import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qubuild import circuits as C          # noqa: E402
from qubuild import engine as E            # noqa: E402

B = C.Circuit.build
PI = math.pi


def dist(circuit, tol=1e-9):
    st = E.statevector(circuit)
    p = E.probabilities(st)
    return {E.state_label(i, circuit.qubits): float(round(v, 9))
            for i, v in enumerate(p) if v > tol}


def near(a, b, tol=1e-6):
    return abs(a - b) < tol


# ---- single qubit ---------------------------------------------------------

def test_hadamard_is_even():
    d = dist(B(1, [("H", [0])]))
    assert near(d["0"], 0.5) and near(d["1"], 0.5)


def test_x_flips():
    assert near(dist(B(1, [("X", [0])]))["1"], 1.0)


def test_h_squared_is_identity():
    assert near(dist(B(1, [("H", [0]), ("H", [0])]))["0"], 1.0)


def test_hzh_is_x():
    assert near(dist(B(1, [("H", [0]), ("Z", [0]), ("H", [0])]))["1"], 1.0)


def test_phase_kickback():
    d = dist(B(1, [("H", [0]), ("P", [0], [PI]), ("H", [0])]))
    assert near(d["1"], 1.0)


def test_t_squared_is_s():
    a = E.statevector(B(1, [("H", [0]), ("T", [0]), ("T", [0])]))
    b = E.statevector(B(1, [("H", [0]), ("S", [0])]))
    assert near(E.fidelity(a, b), 1.0)


# ---- Bloch vectors --------------------------------------------------------

def test_bloch_plus():
    v = E.bloch(E.statevector(B(1, [("H", [0])])), 1, 0)
    assert near(v.x, 1.0) and near(v.y, 0.0) and near(v.z, 0.0)


def test_bloch_plus_i():
    v = E.bloch(E.statevector(B(1, [("H", [0]), ("S", [0])])), 1, 0)
    assert near(v.y, 1.0)


def test_bloch_zero():
    v = E.bloch(E.statevector(B(1, [])), 1, 0)
    assert near(v.z, 1.0)


# ---- entanglement ---------------------------------------------------------

def test_bell_distribution():
    d = dist(B(2, [("H", [0]), ("CX", [0, 1])]))
    assert set(d) == {"00", "11"} and near(d["00"], 0.5)


def test_bell_qubits_are_maximally_mixed():
    st = E.statevector(B(2, [("H", [0]), ("CX", [0, 1])]))
    assert near(E.bloch(st, 2, 0).length, 0.0)
    assert near(E.bloch(st, 2, 1).length, 0.0)
    assert E.bloch(st, 2, 0).entangled


def test_ghz():
    d = dist(B(3, [("H", [0]), ("CX", [0, 1]), ("CX", [1, 2])]))
    assert set(d) == {"000", "111"} and near(d["111"], 0.5)


def test_separable_state_has_pure_qubits():
    st = E.statevector(B(2, [("H", [0]), ("H", [1])]))
    assert near(E.bloch(st, 2, 0).length, 1.0)


# ---- controlled gates -----------------------------------------------------

def test_cnot_direction():
    assert dist(B(2, [("X", [0]), ("CX", [0, 1])]))["11"] == 1.0
    assert dist(B(2, [("X", [1]), ("CX", [0, 1])]))["10"] == 1.0


def test_swap():
    assert dist(B(3, [("X", [0]), ("SWAP", [0, 2])]))["100"] == 1.0


def test_toffoli():
    assert dist(B(3, [("X", [0]), ("X", [1]), ("CCX", [0, 1, 2])]))["111"] == 1.0
    assert dist(B(3, [("X", [0]), ("CCX", [0, 1, 2])]))["001"] == 1.0


def test_fredkin():
    assert dist(B(3, [("X", [0]), ("X", [1]), ("CSWAP", [0, 1, 2])]))["101"] == 1.0


def test_cz_equals_h_cx_h():
    a = E.statevector(B(2, [("H", [0]), ("H", [1]), ("CZ", [0, 1])]))
    b = E.statevector(B(2, [("H", [0]), ("H", [1]), ("H", [1]), ("CX", [0, 1]), ("H", [1])]))
    assert near(E.fidelity(a, b), 1.0)


# ---- library circuits -----------------------------------------------------

def lib(name):
    return C.BY_ID[name].make()


def test_library_bell():
    d = dist(lib("bell"))
    assert near(d["00"], 0.5) and near(d["11"], 0.5)


def test_library_ghz():
    d = dist(lib("ghz"))
    assert near(d["000"], 0.5) and near(d["111"], 0.5)


def test_w_state():
    d = dist(lib("wstate"))
    assert near(d["001"], 1 / 3) and near(d["010"], 1 / 3) and near(d["100"], 1 / 3)


def test_deutsch_jozsa_reports_balanced():
    d = dist(lib("dj"))
    top = {}
    for k, v in d.items():
        top[k[1:]] = top.get(k[1:], 0) + v
    assert near(top["11"], 1.0)


def test_bernstein_vazirani_finds_101():
    d = dist(lib("bv"))
    top = {}
    for k, v in d.items():
        top[k[1:]] = top.get(k[1:], 0) + v
    assert near(top["101"], 1.0)


def test_grover_two_qubits_is_certain():
    assert near(dist(lib("grover2"))["11"], 1.0)


def test_grover_three_qubits_peaks():
    d = dist(lib("grover3"))
    assert d["111"] > 0.94


def test_superdense_decodes_11():
    assert near(dist(lib("superdense"))["11"], 1.0)


def test_teleportation_moves_the_state():
    c = lib("teleport").without_measurements()
    v = E.bloch(E.statevector(c), 3, 2)
    theta = PI / 3
    assert near(v.z, math.cos(theta)) and near(v.x, math.sin(theta))


def test_qft_of_basis_state_is_uniform():
    c = lib("qft3")
    c.ops.insert(0, C.Op("X", [0], [], -1.0))
    c.pack()
    p = E.probabilities(E.statevector(c))
    assert all(near(v, 1 / 8) for v in p)


# ---- parser ---------------------------------------------------------------

def parsed_dist(src):
    circuit, errors = C.parse(src)
    return dist(circuit), errors


def test_parse_qiskit():
    d, e = parsed_dist("from qiskit import QuantumCircuit\n"
                       "qc = QuantumCircuit(2)\nqc.h(0)\nqc.cx(0, 1)\nqc.measure_all()")
    assert not e and near(d["00"], 0.5) and near(d["11"], 0.5)


def test_parse_qasm():
    d, e = parsed_dist('OPENQASM 2.0;\ninclude "qelib1.inc";\n'
                       "qreg q[2];\nh q[0];\ncx q[0],q[1];")
    assert not e and near(d["11"], 0.5)


def test_parse_pennylane():
    d, e = parsed_dist("import pennylane as qml\n"
                       "qml.Hadamard(wires=0)\nqml.CNOT(wires=[0, 1])")
    assert not e and near(d["11"], 0.5)


def test_parse_cirq():
    d, e = parsed_dist("import cirq\nq = cirq.LineQubit.range(2)\n"
                       "circuit.append(cirq.H(q[0]))\ncircuit.append(cirq.CNOT(q[0], q[1]))")
    assert not e and near(d["11"], 0.5)


def test_parse_angle_expressions():
    d, e = parsed_dist("qubits 1\nrx(pi/2) q[0]")
    assert not e and near(d["0"], 0.5)
    d, e = parsed_dist("qc = QuantumCircuit(1)\nqc.rx(np.pi, 0)")
    assert not e and near(d["1"], 1.0)


def test_parser_reports_unknown_gate():
    _, errors = C.parse("qc.foo(0)")
    assert len(errors) == 1 and "Unknown gate" in errors[0].message


def test_round_trip_through_every_generator():
    source = lib("ghz")
    reference = dist(source)
    for name, gen in C.GENERATORS.items():
        back, errors = C.parse(gen(source))
        assert not errors, (name, errors)
        assert dist(back) == reference, name


# ---- sampling and measurement --------------------------------------------

def test_sampling_matches_distribution():
    st = E.statevector(B(2, [("H", [0]), ("CX", [0, 1])]))
    counts = E.sample(st, 2, 4000, [0, 1], seed=7)
    assert set(counts) <= {"00", "11"}
    assert abs(counts["00"] - 2000) < 250


def test_noise_spreads_the_distribution():
    st = E.statevector(B(2, [("H", [0]), ("CX", [0, 1])]))
    counts = E.sample(st, 2, 4000, [0, 1], {"depol": 0.3, "readout": 0.05}, seed=7)
    assert set(counts) == {"00", "01", "10", "11"}


def test_every_backend_reports_only_the_measured_qubits():
    """A count key is a bit string over the measured qubits, not every qubit.

    The MPS sampler walks the whole chain, so it once returned all three bits
    for a teleport circuit that measures one — the physics was right and the
    label was wrong, which reads as a wrong answer to the learner.
    """
    from qubuild import backends as BK
    circuit = C.BY_ID["teleport"].make()
    assert circuit.measured == [2]
    exact = BK.exact_marginal(E.statevector(circuit), circuit.qubits, circuit.measured)

    for backend in BK.available():
        if backend.id == "aer_noisy":
            continue                      # deliberately smeared; checked elsewhere
        result = BK.execute(circuit, backend.id, shots=2000, seed=11)
        if result.counts is None:
            continue
        assert all(len(k) == 1 for k in result.counts), (backend.id, list(result.counts))
        total = sum(result.counts.values())
        for key, p in exact.items():
            assert abs(result.counts.get(key, 0) / total - p) < 0.05, (backend.id, key)


def test_mid_circuit_measurement_collapses():
    ones = 0
    for seed in range(300):
        res = E.run(B(2, [("H", [0]), ("MEASURE", [0]), ("CX", [0, 1])]), seed=seed)
        p = E.probabilities(res.state)
        idx = int(np.argmax(p))
        assert near(p[idx], 1.0), "collapse must leave a basis state"
        assert idx in (0, 3), "measure-then-CNOT can only give 00 or 11"
        ones += idx == 3
    assert 100 < ones < 200


def test_fidelity_ignores_global_phase():
    a = E.statevector(B(1, [("X", [0])]))
    b = E.statevector(B(1, [("X", [0]), ("Z", [0])]))
    assert near(E.fidelity(a, b), 1.0)
    c = E.statevector(B(1, [("I", [0])]))
    assert E.fidelity(a, c) < 1e-12


# ---- circuit model --------------------------------------------------------

def test_packing_preserves_order_and_parallelism():
    c = B(2, [("H", [0]), ("X", [1]), ("CX", [0, 1])])
    cols = {o.name: o.col for o in c.ops}
    assert cols["H"] == 0 and cols["X"] == 0 and cols["CX"] == 1
    assert c.depth == 2


def test_set_qubits_drops_out_of_range_ops():
    c = B(3, [("H", [0]), ("CX", [1, 2])])
    c.set_qubits(2)
    assert [o.name for o in c.ops] == ["H"]


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
