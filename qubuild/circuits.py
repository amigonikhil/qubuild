"""Circuit model, multi-SDK source parser, code generators, algorithm library."""

from __future__ import annotations

import itertools
import math
import re
from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Sequence, Tuple

from .engine import GATES

_ids = itertools.count(1)

PI = math.pi


# --------------------------------------------------------------------------
# model
# --------------------------------------------------------------------------

MAX_QUBITS = 60                 # the widest circuit any backend here can carry


@dataclass
class Op:
    name: str
    qubits: List[int]
    params: List[float] = field(default_factory=list)
    col: float = 0.0
    id: int = field(default_factory=lambda: next(_ids))

    @property
    def span(self) -> Tuple[int, int]:
        return min(self.qubits), max(self.qubits)

    def copy(self) -> "Op":
        return Op(self.name, list(self.qubits), list(self.params), self.col, next(_ids))


@dataclass
class Circuit:
    qubits: int = 3
    ops: List[Op] = field(default_factory=list)

    # -- construction ------------------------------------------------------
    @staticmethod
    def build(qubits: int, spec: Sequence[Sequence]) -> "Circuit":
        """`spec` is a list of (name, qubits[, params]) applied in order."""
        c = Circuit(qubits, [])
        for i, item in enumerate(spec):
            name, qs = item[0], list(item[1])
            params = list(item[2]) if len(item) > 2 else []
            c.ops.append(Op(name, qs, params, float(i)))
        return c.pack()

    def copy(self) -> "Circuit":
        return Circuit(self.qubits, [o.copy() for o in self.ops])

    # -- layout ------------------------------------------------------------
    def pack(self) -> "Circuit":
        """Slide every op into the leftmost legal column, keeping order."""
        ordered = sorted(self.ops, key=lambda o: (o.col, o.qubits[0]))
        free = [0] * self.qubits
        for o in ordered:
            lo, hi = o.span
            col = max(free[lo:hi + 1]) if hi >= lo else 0
            o.col = col
            for q in range(lo, hi + 1):
                free[q] = col + 1
        self.ops = ordered
        return self

    def ordered_ops(self) -> List[Op]:
        return sorted(self.ops, key=lambda o: (o.col, o.qubits[0]))

    # -- queries -----------------------------------------------------------
    @property
    def depth(self) -> int:
        return int(max((o.col for o in self.ops), default=-1)) + 1

    @property
    def gate_count(self) -> int:
        return sum(1 for o in self.ops if o.name not in ("BARRIER", "MEASURE"))

    @property
    def two_qubit_count(self) -> int:
        return sum(1 for o in self.ops if GATES[o.name].arity >= 2)

    @property
    def measured(self) -> List[int]:
        return sorted({o.qubits[0] for o in self.ops if o.name == "MEASURE"})

    def without_measurements(self) -> "Circuit":
        c = Circuit(self.qubits, [o for o in self.ops if o.name != "MEASURE"])
        return c

    # -- editing -----------------------------------------------------------
    def add(self, name: str, qubits: Sequence[int],
            params: Sequence[float] = (), col: Optional[float] = None) -> Op:
        op = Op(name, list(qubits), list(params),
                float(self.depth if col is None else col))
        self.ops.append(op)
        self.pack()
        return op

    def remove(self, op_id: int) -> None:
        self.ops = [o for o in self.ops if o.id != op_id]
        self.pack()

    def set_qubits(self, n: int) -> None:
        # The ceiling here is the tensor-network backend's, not the dense one's.
        # Whichever cap actually applies is the caller's business: the Studio
        # passes a backend-dependent limit, because an exact statevector at 60
        # qubits does not exist and an MPS at 60 qubits is routine.
        n = max(1, min(MAX_QUBITS, n))
        self.ops = [o for o in self.ops if all(q < n for q in o.qubits)]
        self.qubits = n
        self.pack()

    def to_dict(self) -> dict:
        return {"qubits": self.qubits,
                "ops": [{"name": o.name, "qubits": o.qubits,
                         "params": o.params, "col": o.col} for o in self.ops]}

    @staticmethod
    def from_dict(d: dict) -> "Circuit":
        c = Circuit(d["qubits"], [])
        for o in d["ops"]:
            c.ops.append(Op(o["name"], list(o["qubits"]), list(o["params"]), o["col"]))
        return c.pack()


# --------------------------------------------------------------------------
# angle formatting
# --------------------------------------------------------------------------

_SPECIAL = [(1, "π"), (-1, "−π"), (0.5, "π/2"), (-0.5, "−π/2"), (0.25, "π/4"),
            (-0.25, "−π/4"), (0.75, "3π/4"), (-0.75, "−3π/4"), (2, "2π"),
            (0.125, "π/8"), (-0.125, "−π/8"), (0, "0")]


def fmt_param(v: float) -> str:
    r = v / PI
    for k, s in _SPECIAL:
        if abs(r - k) < 1e-9:
            return s
    return str(round(v, 3))


_PY_SPECIAL = [(0, "0"), (1, "pi"), (-1, "-pi"), (0.5, "pi/2"), (-0.5, "-pi/2"),
               (0.25, "pi/4"), (-0.25, "-pi/4"), (0.125, "pi/8"), (-0.125, "-pi/8")]


def py_param(v: float) -> str:
    r = v / PI
    for k, s in _PY_SPECIAL:
        if abs(r - k) < 1e-9:
            return s
    return str(round(v, 6))


# --------------------------------------------------------------------------
# expression evaluation (for parsed angles like `pi/2`, `np.pi/4`)
# --------------------------------------------------------------------------

_SAFE = re.compile(r"^[\d\s+\-*/().]*$")


def eval_expr(src: str) -> Optional[float]:
    s = (src or "").strip()
    if not s:
        return None
    s = re.sub(r"\b(?:np|numpy|math|cmath|sympy)\.", "", s)
    s = re.sub(r"\btau\b", "(2*PI)", s, flags=re.I)
    s = re.sub(r"\bpi\b", "PI", s, flags=re.I)
    probe = s.replace("PI", "").replace("sqrt", "")
    if not _SAFE.match(probe):
        return None
    try:
        value = eval(s, {"__builtins__": {}}, {"PI": PI, "sqrt": math.sqrt})  # noqa: S307
        return float(value)
    except Exception:
        return None


# --------------------------------------------------------------------------
# parser — accepts Qiskit, Cirq, PennyLane, OpenQASM and a bare DSL
# --------------------------------------------------------------------------

ALIAS = {
    "h": "H", "hadamard": "H", "x": "X", "paulix": "X", "not": "X",
    "y": "Y", "pauliy": "Y", "z": "Z", "pauliz": "Z",
    "s": "S", "sdg": "SDG", "sdag": "SDG", "phase": "S",
    "t": "T", "tdg": "TDG", "tdag": "TDG",
    "sx": "SX", "sqrtx": "SX", "id": "I", "i": "I", "iden": "I", "identity": "I",
    "rx": "RX", "ry": "RY", "rz": "RZ", "p": "P", "u": "U", "u3": "U",
    "phaseshift": "P", "phasegate": "P",
    "cx": "CX", "cnot": "CX", "ccx": "CCX", "ccnot": "CCX", "toffoli": "CCX",
    "cy": "CY", "cz": "CZ", "ch": "CH", "crz": "CRZ", "cry": "CRY",
    "cp": "CP", "cphase": "CP", "cu1": "CP", "controlledphaseshift": "CP",
    "swap": "SWAP", "cswap": "CSWAP", "fredkin": "CSWAP",
    "measure": "MEASURE", "m": "MEASURE", "measurez": "MEASURE",
    "barrier": "BARRIER",
}

_SKIP = re.compile(
    r"^(from|import|include|openqasm|creg|print|return|for|if|else|while|def|class|@|\}|\{|\))",
    re.I)
_ASSIGN = re.compile(r"^[A-Za-z_]\w*\s*=(?!=)")
_PREFIX = re.compile(r"\b(qc|circ|circuit|program|qml|cirq|qiskit|ops|moment)\s*\.")
_QREF = re.compile(r"^[A-Za-z_]*q\w*\[\s*(\d+)\s*\]$", re.I)
_QNAME = re.compile(r"^q(?:ubit)?_?(\d+)$", re.I)
_WIRES = re.compile(r"wires\s*=\s*\[?([-0-9,\s]+)\]?", re.I)
_INTLIST = re.compile(r"^\[[-0-9,\s]+\]$")


@dataclass
class ParseError:
    line: int
    message: str


def _split_args(text: str) -> List[str]:
    out, depth, cur = [], 0, ""
    for ch in text:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur)
            cur = ""
            continue
        cur += ch
    out.append(cur)
    return [a for a in out if a.strip()]


def parse(text: str) -> Tuple[Circuit, List[ParseError]]:
    errors: List[ParseError] = []
    parsed: List[dict] = []
    declared, max_q = 0, -1

    for ln, raw in enumerate(str(text).split("\n"), start=1):
        line = re.sub(r"#.*$", "", raw)
        line = re.sub(r"//.*$", "", line).strip().rstrip(";")
        if not line or _SKIP.match(line):
            continue

        m = re.search(r"QuantumCircuit\s*\(\s*(\d+)", line, re.I)
        if m:
            declared = max(declared, int(m.group(1)))
            continue
        m = re.search(r"qreg\s+\w+\s*\[\s*(\d+)\s*\]", line, re.I)
        if m:
            declared = max(declared, int(m.group(1)))
            continue
        m = re.match(r"^qubits?\s+(\d+)$", line, re.I)
        if m:
            declared = max(declared, int(m.group(1)))
            continue
        m = re.search(r"LineQubit\.range\s*\(\s*(\d+)", line, re.I)
        if m:
            declared = max(declared, int(m.group(1)))
            continue
        m = re.search(r"device\s*\([^)]*wires\s*=\s*(\d+)", line, re.I)
        if m:
            declared = max(declared, int(m.group(1)))
            continue
        if re.search(r"measure_all|measure\s*\(\s*\)|measure\s+all", line, re.I):
            parsed.append({"name": "MEASURE_ALL"})
            continue
        if _ASSIGN.match(line):
            continue

        body = _PREFIX.sub("", line)
        body = re.sub(r"^append\s*\(", "", body)
        body = re.sub(r"->\s*\w+\s*\[\s*\d+\s*\]", "", body)

        gm = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)", body)
        if not gm:
            continue
        key = re.sub(r"[^a-z0-9]", "", gm.group(1).lower())
        name = ALIAS.get(key)
        if name is None:
            errors.append(ParseError(ln, 'Unknown gate "%s"' % gm.group(1)))
            continue

        rest = body[len(gm.group(1)):]
        groups, outside, depth, cur = [], "", 0, ""
        for ch in rest:
            if ch == "(":
                depth += 1
                if depth == 1:
                    cur = ""
                    continue
            if ch == ")":
                if depth == 1:
                    groups.append(cur)
                    depth = 0
                    continue
                if depth > 0:
                    depth -= 1
                    continue
                continue
            if depth > 0:
                cur += ch
            else:
                outside += ch

        args: List[str] = []
        for grp in groups:
            args += _split_args(grp)
        args += _split_args(re.sub(r"\s+", ",", outside.strip()))

        qubits: List[int] = []
        numbers: List[float] = []
        for arg in args:
            a = arg.strip()
            if not a or a[0] in "'\"":
                continue
            if re.match(r"^[A-Za-z_]\w*\s*=", a) and not a.lower().startswith("wires"):
                continue
            wm = _WIRES.search(a)
            if wm:
                qubits += [int(v) for v in wm.group(1).split(",") if v.strip().lstrip("-").isdigit()]
                continue
            qm = _QREF.match(a) or _QNAME.match(a)
            if qm:
                qubits.append(int(qm.group(1)))
                continue
            if _INTLIST.match(a):
                qubits += [int(v) for v in a.strip("[]").split(",") if v.strip()]
                continue
            val = eval_expr(a)
            if val is None:
                errors.append(ParseError(ln, 'Could not read argument "%s"' % a))
            else:
                numbers.append(val)

        spec = GATES[name]
        qs = list(qubits)
        if len(qs) < spec.arity and numbers:
            need = spec.arity - len(qs)
            take = numbers[-need:]
            numbers = numbers[:-need]
            qs += [int(round(v)) for v in take]
        if name == "MEASURE" and len(qs) > 1:
            qs = qs[:1]
        if len(qs) < spec.arity:
            errors.append(ParseError(
                ln, "%s needs %d qubit%s" % (name, spec.arity, "s" if spec.arity > 1 else "")))
            continue
        qs = qs[:spec.arity]
        if len(set(qs)) != len(qs):
            errors.append(ParseError(ln, "%s was given the same qubit twice" % name))
            continue
        max_q = max([max_q] + qs)
        parsed.append({"name": name, "qubits": qs, "params": numbers[:spec.nparams]})

    n = max(1, declared, max_q + 1)
    circuit = Circuit(n, [])
    seq = 0
    for item in parsed:
        if item["name"] == "MEASURE_ALL":
            for q in range(n):
                circuit.ops.append(Op("MEASURE", [q], [], float(seq)))
                seq += 1
            continue
        if any(q >= n for q in item["qubits"]):
            continue
        circuit.ops.append(Op(item["name"], item["qubits"], item["params"], float(seq)))
        seq += 1
    return circuit.pack(), errors


# --------------------------------------------------------------------------
# code generators
# --------------------------------------------------------------------------

QISKIT_M = {"I": "id", "X": "x", "Y": "y", "Z": "z", "H": "h", "S": "s", "SDG": "sdg",
            "T": "t", "TDG": "tdg", "SX": "sx", "RX": "rx", "RY": "ry", "RZ": "rz",
            "P": "p", "U": "u", "CX": "cx", "CY": "cy", "CZ": "cz", "CH": "ch",
            "CRZ": "crz", "CRY": "cry", "CP": "cp", "SWAP": "swap", "CCX": "ccx",
            "CSWAP": "cswap", "BARRIER": "barrier"}

QASM_M = dict(QISKIT_M, U="u3")
QASM_M.pop("BARRIER", None)

PENNY_M = {"I": "Identity", "X": "PauliX", "Y": "PauliY", "Z": "PauliZ",
           "H": "Hadamard", "S": "S", "T": "T", "SX": "SX", "RX": "RX", "RY": "RY",
           "RZ": "RZ", "P": "PhaseShift", "U": "U3", "CX": "CNOT", "CY": "CY",
           "CZ": "CZ", "CH": "CH", "CRZ": "CRZ", "CRY": "CRY",
           "CP": "ControlledPhaseShift", "SWAP": "SWAP", "CCX": "Toffoli",
           "CSWAP": "CSWAP", "SDG": "adjoint(qml.S)", "TDG": "adjoint(qml.T)"}

CIRQ_M = {"I": "I", "X": "X", "Y": "Y", "Z": "Z", "H": "H", "S": "S", "T": "T",
          "CX": "CNOT", "CZ": "CZ", "SWAP": "SWAP", "CCX": "TOFFOLI", "CSWAP": "CSWAP",
          "SX": "X**0.5", "SDG": "S**-1", "TDG": "T**-1", "CY": "Y.controlled()",
          "CH": "H.controlled()"}


def to_qiskit(c: Circuit) -> str:
    lines = ["from qiskit import QuantumCircuit",
             "from qiskit_aer import AerSimulator",
             "from numpy import pi", "",
             "qc = QuantumCircuit(%d, %d)" % (c.qubits, c.qubits)]
    for o in c.ordered_ops():
        if o.name == "MEASURE":
            lines.append("qc.measure(%d, %d)" % (o.qubits[0], o.qubits[0]))
            continue
        m = QISKIT_M.get(o.name)
        if not m:
            continue
        args = [py_param(p) for p in o.params] + [str(q) for q in o.qubits]
        lines.append("qc.%s(%s)" % (m, ", ".join(args)))
    lines += ["", "result = AerSimulator().run(qc, shots=1024).result()",
              "print(result.get_counts())"]
    return "\n".join(lines)


def to_qasm(c: Circuit) -> str:
    lines = ['OPENQASM 2.0;', 'include "qelib1.inc";', "",
             "qreg q[%d];" % c.qubits, "creg m[%d];" % c.qubits, ""]
    for o in c.ordered_ops():
        if o.name == "BARRIER":
            lines.append("barrier q[%d];" % o.qubits[0])
            continue
        if o.name == "MEASURE":
            lines.append("measure q[%d] -> m[%d];" % (o.qubits[0], o.qubits[0]))
            continue
        m = QASM_M.get(o.name)
        if not m:
            continue
        ps = "(%s)" % ",".join(py_param(p) for p in o.params) if o.params else ""
        lines.append("%s%s %s;" % (m, ps, ",".join("q[%d]" % q for q in o.qubits)))
    return "\n".join(lines)


def to_pennylane(c: Circuit) -> str:
    lines = ["import pennylane as qml", "from numpy import pi", "",
             'dev = qml.device("default.qubit", wires=%d, shots=1024)' % c.qubits,
             "", "@qml.qnode(dev)", "def circuit():"]
    body = False
    for o in c.ordered_ops():
        if o.name in ("MEASURE", "BARRIER"):
            continue
        m = PENNY_M.get(o.name)
        if not m:
            continue
        body = True
        wires = ("wires=%d" % o.qubits[0] if len(o.qubits) == 1
                 else "wires=[%s]" % ", ".join(str(q) for q in o.qubits))
        args = [py_param(p) for p in o.params] + [wires]
        lines.append("    qml.%s(%s)" % (m, ", ".join(args)))
    if not body:
        lines.append("    pass")
    meas = c.measured or list(range(c.qubits))
    lines.append("    return qml.counts(wires=[%s])" % ", ".join(str(q) for q in meas))
    lines += ["", "print(circuit())"]
    return "\n".join(lines)


def to_cirq(c: Circuit) -> str:
    lines = ["import cirq", "from numpy import pi", "",
             "q = cirq.LineQubit.range(%d)" % c.qubits, "circuit = cirq.Circuit()"]
    for o in c.ordered_ops():
        if o.name == "BARRIER":
            continue
        qs = ", ".join("q[%d]" % q for q in o.qubits)
        if o.name == "MEASURE":
            lines.append("circuit.append(cirq.measure(q[%d], key='m%d'))"
                         % (o.qubits[0], o.qubits[0]))
            continue
        if o.name in ("RX", "RY", "RZ"):
            gate = "cirq.%s(%s)" % (o.name.lower(), py_param(o.params[0] if o.params else 0))
        elif o.name == "P":
            gate = "cirq.ZPowGate(exponent=%s)" % round((o.params[0] if o.params else 0) / PI, 5)
        elif o.name == "CP":
            gate = "cirq.CZPowGate(exponent=%s)" % round((o.params[0] if o.params else 0) / PI, 5)
        elif o.name == "CRZ":
            gate = "cirq.rz(%s).controlled()" % py_param(o.params[0] if o.params else 0)
        elif o.name == "CRY":
            gate = "cirq.ry(%s).controlled()" % py_param(o.params[0] if o.params else 0)
        else:
            base = CIRQ_M.get(o.name)
            if not base:
                continue
            gate = "cirq." + base
        lines.append("circuit.append(%s(%s))" % (gate, qs))
    lines += ["", "print(cirq.Simulator().run(circuit, repetitions=1024).histogram(key='m0'))"]
    return "\n".join(lines)


def to_dsl(c: Circuit) -> str:
    lines = ["qubits %d" % c.qubits]
    for o in c.ordered_ops():
        if o.name == "BARRIER":
            lines.append("barrier q[%d]" % o.qubits[0])
            continue
        if o.name == "MEASURE":
            lines.append("measure q[%d]" % o.qubits[0])
            continue
        ps = "(%s)" % ", ".join(py_param(p) for p in o.params) if o.params else ""
        lines.append("%s%s %s" % (o.name.lower(), ps,
                                  ", ".join("q[%d]" % q for q in o.qubits)))
    return "\n".join(lines)


GENERATORS = {"Qiskit": to_qiskit, "Cirq": to_cirq, "PennyLane": to_pennylane,
              "OpenQASM": to_qasm, "QuBuild": to_dsl}


# --------------------------------------------------------------------------
# algorithm library
# --------------------------------------------------------------------------

@dataclass
class Algorithm:
    id: str
    name: str
    tag: str
    level: str
    blurb: str
    factory: callable

    def make(self) -> Circuit:
        return self.factory()


def _bell():
    return Circuit.build(2, [("H", [0]), ("CX", [0, 1]),
                             ("MEASURE", [0]), ("MEASURE", [1])])


def _ghz():
    return Circuit.build(3, [("H", [0]), ("CX", [0, 1]), ("CX", [1, 2]),
                             ("MEASURE", [0]), ("MEASURE", [1]), ("MEASURE", [2])])


def _wstate():
    return Circuit.build(3, [
        ("RY", [0], [2 * math.asin(1 / math.sqrt(3))]),
        ("X", [0]), ("CRY", [0, 1], [PI / 2]),
        ("X", [1]), ("CCX", [0, 1, 2]), ("X", [1]), ("X", [0]),
        ("MEASURE", [0]), ("MEASURE", [1]), ("MEASURE", [2])])


def _kickback():
    return Circuit.build(1, [("H", [0]), ("P", [0], [PI]), ("H", [0]), ("MEASURE", [0])])


def _dj():
    return Circuit.build(3, [
        ("X", [2]), ("H", [0]), ("H", [1]), ("H", [2]), ("BARRIER", [0]),
        ("CX", [0, 2]), ("CX", [1, 2]), ("BARRIER", [0]),
        ("H", [0]), ("H", [1]), ("MEASURE", [0]), ("MEASURE", [1])])


def _bv():
    return Circuit.build(4, [
        ("X", [3]), ("H", [0]), ("H", [1]), ("H", [2]), ("H", [3]), ("BARRIER", [0]),
        ("CX", [0, 3]), ("CX", [2, 3]), ("BARRIER", [0]),
        ("H", [0]), ("H", [1]), ("H", [2]),
        ("MEASURE", [0]), ("MEASURE", [1]), ("MEASURE", [2])])


def _grover2():
    return Circuit.build(2, [
        ("H", [0]), ("H", [1]), ("BARRIER", [0]), ("CZ", [0, 1]), ("BARRIER", [0]),
        ("H", [0]), ("H", [1]), ("X", [0]), ("X", [1]), ("CZ", [0, 1]),
        ("X", [0]), ("X", [1]), ("H", [0]), ("H", [1]),
        ("MEASURE", [0]), ("MEASURE", [1])])


def _grover3():
    ccz = [("H", [2]), ("CCX", [0, 1, 2]), ("H", [2])]
    diffuser = ([("H", [0]), ("H", [1]), ("H", [2]), ("X", [0]), ("X", [1]), ("X", [2])]
                + ccz
                + [("X", [0]), ("X", [1]), ("X", [2]), ("H", [0]), ("H", [1]), ("H", [2])])
    it = ccz + [("BARRIER", [0])] + diffuser
    spec = ([("H", [0]), ("H", [1]), ("H", [2]), ("BARRIER", [0])] + it
            + [("BARRIER", [0])] + it
            + [("MEASURE", [0]), ("MEASURE", [1]), ("MEASURE", [2])])
    return Circuit.build(3, spec)


def _qft3():
    return Circuit.build(3, [
        ("H", [2]), ("CP", [1, 2], [PI / 2]), ("CP", [0, 2], [PI / 4]),
        ("H", [1]), ("CP", [0, 1], [PI / 2]), ("H", [0]), ("SWAP", [0, 2])])


def _teleport():
    return Circuit.build(3, [
        ("RY", [0], [PI / 3]), ("BARRIER", [0]),
        ("H", [1]), ("CX", [1, 2]), ("BARRIER", [0]),
        ("CX", [0, 1]), ("H", [0]), ("BARRIER", [0]),
        ("CX", [1, 2]), ("CZ", [0, 2]), ("MEASURE", [2])])


def _superdense():
    return Circuit.build(2, [
        ("H", [0]), ("CX", [0, 1]), ("BARRIER", [0]),
        ("Z", [0]), ("X", [0]), ("BARRIER", [0]),
        ("CX", [0, 1]), ("H", [0]), ("MEASURE", [0]), ("MEASURE", [1])])


def _coin():
    return Circuit.build(1, [("H", [0]), ("MEASURE", [0])])


LIBRARY: List[Algorithm] = [
    Algorithm("bell", "Bell state Φ+", "Entanglement", "Core",
              "Two qubits, perfectly correlated. Measure one and you instantly know the "
              "other — the smallest entangled state there is.", _bell),
    Algorithm("ghz", "GHZ state", "Entanglement", "Core",
              "Three-way entanglement: all zeros or all ones, nothing in between. The test "
              "case for multi-qubit correlation.", _ghz),
    Algorithm("wstate", "W state", "Entanglement", "Advanced",
              "Exactly one excitation shared across three qubits. Unlike GHZ, it survives "
              "losing a qubit.", _wstate),
    Algorithm("kickback", "Phase kickback", "Interference", "Core",
              "H, then a phase, then H again. The phase you cannot measure directly turns "
              "into an outcome you can.", _kickback),
    Algorithm("dj", "Deutsch–Jozsa", "Algorithm", "Core",
              "Decides whether a hidden function is constant or balanced in a single query. "
              "Classically you might need half the inputs.", _dj),
    Algorithm("bv", "Bernstein–Vazirani", "Algorithm", "Core",
              "Recovers a hidden bit string s = 101 in one query instead of three. Here the "
              "oracle is the pair of CNOTs.", _bv),
    Algorithm("grover2", "Grover search (marks |11⟩)", "Algorithm", "Core",
              "One Grover iteration on two qubits finds the marked item with certainty. "
              "Amplitude amplification at its cleanest.", _grover2),
    Algorithm("grover3", "Grover search, 3 qubits", "Algorithm", "Advanced",
              "Two iterations over eight items push the marked state |111⟩ to about 95% "
              "probability.", _grover3),
    Algorithm("qft3", "Quantum Fourier transform", "Algorithm", "Advanced",
              "The engine inside Shor and phase estimation. Rewrites amplitudes in the "
              "frequency basis using controlled phases.", _qft3),
    Algorithm("teleport", "Quantum teleportation", "Protocol", "Advanced",
              "Moves an unknown state from qubit 0 to qubit 2 using entanglement and two "
              "classical bits.", _teleport),
    Algorithm("superdense", "Superdense coding", "Protocol", "Advanced",
              "Sends two classical bits by touching one qubit. Encodes \"11\" here — change "
              "the Z and X to change the message.", _superdense),
    Algorithm("coin", "Certified coin flip", "Basics", "Intro",
              "One Hadamard, one measurement. The simplest true random-number generator in "
              "the world.", _coin),
]

BY_ID = {a.id: a for a in LIBRARY}
