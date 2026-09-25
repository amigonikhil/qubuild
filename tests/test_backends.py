"""Every installed SDK backend must agree with the built-in engine.

Skipped adapters are reported, not silently passed — if Qiskit is installed and
its numbers disagree with ours, this fails.
"""

import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qubuild import backends as BK       # noqa: E402
from qubuild import circuits as C        # noqa: E402
from qubuild import engine as E          # noqa: E402

PI = math.pi

CASES = [
    ("bell", C.BY_ID["bell"].make()),
    ("ghz", C.BY_ID["ghz"].make()),
    ("wstate", C.BY_ID["wstate"].make()),
    ("grover3", C.BY_ID["grover3"].make()),
    ("qft3", C.BY_ID["qft3"].make()),
    ("teleport", C.BY_ID["teleport"].make()),
    ("rotations", C.Circuit.build(3, [
        ("RX", [0], [0.7]), ("RY", [1], [1.3]), ("RZ", [2], [-0.4]),
        ("CRY", [0, 1], [PI / 3]), ("CP", [1, 2], [PI / 5]), ("SWAP", [0, 2]),
        ("T", [0]), ("SDG", [1]), ("SX", [2]), ("P", [0], [PI / 7]),
        ("CCX", [0, 1, 2]), ("CH", [2, 0]), ("CY", [1, 0]), ("CSWAP", [0, 1, 2]),
        ("MEASURE", [0]), ("MEASURE", [1]), ("MEASURE", [2])])),
]


def _report(name, ok, note=""):
    print(("  ok  " if ok else "FAIL  ") + name + ("  " + note if note else ""))
    return 0 if ok else 1


def main():
    fails = 0
    print("available backends:")
    for b in BK.BACKENDS:
        print("   %-22s %-11s %s" % (b.id, b.sdk, "available" if b.available else "not installed"))
    print()

    for backend in BK.available():
        if backend.sdk == "builtin":
            continue
        if backend.id == "aer_noisy":
            continue   # deliberately deviates; checked separately below
        for case_name, circuit in CASES:
            label = "%s / %s" % (backend.id, case_name)
            reference = E.statevector(circuit)
            res = BK.execute(circuit, backend.id, shots=4000, seed=11)

            if res.executed_by != backend.sdk:
                fails += _report(label + " [statevector]", False,
                                 "did not execute on the SDK: " + res.detail)
                continue

            fid = E.fidelity(reference, res.state)
            fails += _report(label + " [statevector]", fid > 0.999999,
                             "fidelity=%.9f" % fid)

            if res.counts is not None and backend.id != "aer_noisy":
                exact = BK.exact_marginal(reference, circuit.qubits, circuit.measured or None)
                total = sum(res.counts.values())
                bad_keys = [k for k in res.counts if k not in exact and res.counts[k] / total > 0.01]
                worst = 0.0
                for key, p in exact.items():
                    got = res.counts.get(key, 0) / total
                    worst = max(worst, abs(got - p))
                ok = not bad_keys and worst < 0.05
                fails += _report(label + " [counts]", ok,
                                 "max deviation %.4f%s" % (worst, (" unexpected " + str(bad_keys)) if bad_keys else ""))

    # noise must broaden the distribution but keep the peak in the right place
    if BK.BY_ID["aer_noisy"].available:
        ghz = C.BY_ID["ghz"].make()
        clean = BK.execute(ghz, "aer_qasm", shots=4000, seed=3)
        noisy = BK.execute(ghz, "aer_noisy", shots=4000, seed=3)
        fails += _report("aer_noisy broadens the histogram",
                         len(noisy.counts) > len(clean.counts),
                         "%d outcomes vs %d" % (len(noisy.counts), len(clean.counts)))
        peak = max(noisy.counts, key=noisy.counts.get)
        fails += _report("aer_noisy keeps the peak on 000/111", peak in ("000", "111"), peak)

    # count-key convention: qubit 0 must be the rightmost character
    asym = C.Circuit.build(3, [("X", [0]), ("MEASURE", [0]), ("MEASURE", [1]), ("MEASURE", [2])])
    for backend in BK.available():
        res = BK.execute(asym, backend.id, shots=200, seed=1)
        if res.counts is None:
            continue
        key = max(res.counts, key=res.counts.get)
        fails += _report("%s bit order (expect 001)" % backend.id, key == "001", key)

    print("\n%s" % ("all backend checks passed" if not fails else "%d check(s) failed" % fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
