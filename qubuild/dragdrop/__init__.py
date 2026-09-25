"""A real drag-and-drop circuit canvas, as a Streamlit custom component.

Streamlit renders server-side and has no drag surface of its own, so the
graphical builder used to place gates through select boxes.  This module adds
the missing half: a browser-side canvas where a gate is dragged from a palette
onto a wire, dragged again to move it, and dragged off the grid to delete it.

**How it talks back to Python without a build step.**  The usual way to write a
Streamlit component is a React app compiled with npm.  That is a whole toolchain
for what is, underneath, two postMessage calls:

    streamlit:setFrameHeight     — tell the host how tall the iframe is
    streamlit:setComponentValue  — hand a value back to Python

``declare_component(path=...)`` will serve any directory containing an
``index.html``, so the frontend here is one hand-written file speaking that
protocol directly.  No node_modules, nothing to build, and the component works
from a plain checkout — which matters for a platform whose whole argument is
that a college can run it offline.

The value posted back is the same circuit dictionary ``Circuit.to_dict()``
produces, so the canvas is interchangeable with every other way of building a
circuit in the app.
"""

from __future__ import annotations

import os
from typing import Optional

import streamlit.components.v1 as components

_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")

_component = components.declare_component("qubuild_canvas", path=_DIR)


# Gates the palette offers, grouped the way the lessons introduce them.
PALETTE = [
    ("Basics", [("H", "H"), ("X", "X"), ("Y", "Y"), ("Z", "Z"), ("I", "I")]),
    ("Phase", [("S", "S"), ("SDG", "S†"), ("T", "T"), ("TDG", "T†"), ("P", "P(θ)")]),
    ("Rotation", [("RX", "Rx"), ("RY", "Ry"), ("RZ", "Rz"), ("SX", "√X")]),
    ("Two-qubit", [("CX", "CX"), ("CY", "CY"), ("CZ", "CZ"), ("CH", "CH"),
                   ("SWAP", "SWAP"), ("CP", "CP(θ)"), ("CRZ", "CRz"), ("CRY", "CRy")]),
    ("Three-qubit", [("CCX", "CCX"), ("CSWAP", "CSWAP")]),
    ("Meta", [("MEASURE", "M"), ("BARRIER", "|")]),
]

# arity, number of controls and parameter count, mirrored from engine.GATES so
# the browser can validate a drop without a server round-trip.
SPECS = {
    "I": (1, 0, 0), "X": (1, 0, 0), "Y": (1, 0, 0), "Z": (1, 0, 0), "H": (1, 0, 0),
    "S": (1, 0, 0), "SDG": (1, 0, 0), "T": (1, 0, 0), "TDG": (1, 0, 0), "SX": (1, 0, 0),
    "RX": (1, 0, 1), "RY": (1, 0, 1), "RZ": (1, 0, 1), "P": (1, 0, 1), "U": (1, 0, 3),
    "CX": (2, 1, 0), "CY": (2, 1, 0), "CZ": (2, 1, 0), "CH": (2, 1, 0),
    "CRZ": (2, 1, 1), "CRY": (2, 1, 1), "CP": (2, 1, 1),
    "SWAP": (2, 0, 0), "CCX": (3, 2, 0), "CSWAP": (3, 1, 0),
    "MEASURE": (1, 0, 0), "BARRIER": (1, 0, 0),
}


def canvas(circuit: dict, key: str = "qf_canvas",
           height: Optional[int] = None) -> Optional[dict]:
    """Render the canvas and return an edited circuit, or None if untouched.

    ``circuit`` is a ``Circuit.to_dict()`` payload.  The return value is the
    same shape once the learner drags something; Streamlit reruns the script on
    every interaction, so the caller writes it straight back into session state.
    """
    rows = max(1, int(circuit.get("qubits", 1)))
    cols = max(8, max([int(o.get("col", 0)) for o in circuit.get("ops", [])] or [0]) + 3)
    guess = 150 + rows * 54 + 120
    return _component(circuit=circuit, palette=PALETTE, specs=SPECS,
                      cols=cols, key=key, default=None,
                      height=height or min(720, guess))
