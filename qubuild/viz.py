"""Matplotlib renderers: circuit diagram, Bloch spheres, histogram, amplitudes.

Every figure is drawn on the same dark instrument-panel palette as the rest of
the app, and colour is only ever used to carry meaning — gate family on the
circuit, severity on the meters, complex phase on the amplitude table.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt          # noqa: E402
import numpy as np                       # noqa: E402
from matplotlib.colors import hsv_to_rgb  # noqa: E402
from matplotlib.patches import Arc, Circle, FancyBboxPatch  # noqa: E402

from . import engine as E                # noqa: E402
from .circuits import Circuit, fmt_param  # noqa: E402

INK = "#0C1017"
PANEL = "#121826"
LINE = "#283346"
TEXT = "#E3E9F3"
MUTED = "#95A3BA"
DIM = "#5F6D83"
BLUE = "#4C8DFF"
AMBER = "#FFB454"
VIOLET = "#B08CFF"
CYAN = "#39DCDC"
GOOD = "#3DD68C"
CRIT = "#FF6F6F"
NEUTRAL = "#8FA3BF"

FAMILY = {
    "X": "pauli", "Y": "pauli", "Z": "pauli", "I": "pauli",
    "H": "basis", "SX": "basis",
    "S": "phase", "SDG": "phase", "T": "phase", "TDG": "phase", "P": "phase", "RZ": "phase",
    "RX": "rot", "RY": "rot", "U": "rot",
    "CX": "entangle", "CY": "entangle", "CZ": "entangle", "CH": "entangle",
    "CRZ": "entangle", "CRY": "entangle", "CP": "entangle", "SWAP": "entangle",
    "CCX": "entangle", "CSWAP": "entangle",
    "MEASURE": "meas", "BARRIER": "meta",
}
FAM_COLOR = {"pauli": NEUTRAL, "basis": BLUE, "phase": VIOLET, "rot": CYAN,
             "entangle": AMBER, "meas": GOOD, "meta": DIM}

FAM_LEGEND = [("Pauli", NEUTRAL), ("Basis change", BLUE), ("Phase", VIOLET),
              ("Rotation", CYAN), ("Entangling", AMBER), ("Measure", GOOD)]


def family_color(name: str) -> str:
    return FAM_COLOR[FAMILY.get(name, "pauli")]


def _dark(fig, ax):
    fig.patch.set_facecolor(PANEL)
    ax.set_facecolor(PANEL)
    for spine in ax.spines.values():
        spine.set_visible(False)


# --------------------------------------------------------------------------
# circuit diagram
# --------------------------------------------------------------------------

def circuit_figure(circuit: Circuit, highlight: Optional[int] = None):
    cols = max(circuit.depth, 1)
    n = circuit.qubits
    fig, ax = plt.subplots(figsize=(max(4.2, 0.72 * cols + 1.6), 0.66 * n + 0.55), dpi=150)
    _dark(fig, ax)
    ax.set_xlim(-1.25, cols + 0.35)
    ax.set_ylim(-0.6, n - 0.4)
    ax.invert_yaxis()
    ax.axis("off")

    for q in range(n):
        ax.plot([-0.55, cols - 0.25], [q, q], color=LINE, lw=1.1, zorder=1)
        ax.text(-0.75, q, "q%d |0⟩" % q, color=DIM, fontsize=7.5, family="monospace",
                ha="right", va="center")

    half = 0.28
    for op in circuit.ordered_ops():
        x = op.col
        spec = E.GATES[op.name]
        colour = family_color(op.name)
        selected = highlight is not None and op.id == highlight

        if op.name == "BARRIER":
            ax.plot([x, x], [-0.42, n - 0.58], color=DIM, lw=1.2, ls=(0, (2, 3)), zorder=2)
            continue

        ys = op.qubits
        if len(ys) > 1:
            ax.plot([x, x], [min(ys), max(ys)], color=colour, lw=1.5, zorder=2)
        for c in ys[:spec.ctrl]:
            ax.add_patch(Circle((x, c), 0.075, color=colour, zorder=4))

        if op.name in ("SWAP", "CSWAP"):
            targets = ys if op.name == "SWAP" else ys[1:]
            for y in targets:
                ax.plot([x - 0.12, x + 0.12], [y - 0.12, y + 0.12], color=colour, lw=1.8, zorder=4)
                ax.plot([x - 0.12, x + 0.12], [y + 0.12, y - 0.12], color=colour, lw=1.8, zorder=4)
        elif op.name == "CZ":
            ax.add_patch(Circle((x, ys[1]), 0.075, color=colour, zorder=4))
        elif op.name in ("CX", "CCX"):
            y = ys[spec.ctrl]
            ax.add_patch(Circle((x, y), 0.19, facecolor=INK, edgecolor=colour, lw=1.5, zorder=4))
            ax.plot([x - 0.19, x + 0.19], [y, y], color=colour, lw=1.5, zorder=5)
            ax.plot([x, x], [y - 0.19, y + 0.19], color=colour, lw=1.5, zorder=5)
        elif op.name == "MEASURE":
            y = ys[0]
            ax.add_patch(FancyBboxPatch((x - half, y - half), 2 * half, 2 * half,
                                        boxstyle="round,pad=0,rounding_size=0.06",
                                        facecolor=INK, edgecolor=colour, lw=1.4, zorder=4))
            ax.add_patch(Arc((x, y + 0.09), 0.34, 0.30, theta1=0, theta2=180,
                             color=colour, lw=1.2, zorder=5))
            ax.plot([x, x + 0.13], [y + 0.09, y - 0.11], color=colour, lw=1.2, zorder=5)
        else:
            y = ys[spec.ctrl]
            ax.add_patch(FancyBboxPatch((x - half, y - half), 2 * half, 2 * half,
                                        boxstyle="round,pad=0,rounding_size=0.06",
                                        facecolor=INK, edgecolor=colour,
                                        lw=2.2 if selected else 1.4, zorder=4))
            label = spec.label or op.name
            sub = fmt_param(op.params[0]) if (spec.param and op.params) else None
            ax.text(x, y - (0.07 if sub else 0.0), label, color=TEXT, fontsize=8.5,
                    ha="center", va="center", family="monospace", zorder=5)
            if sub:
                ax.text(x, y + 0.15, sub, color=MUTED, fontsize=5.6, ha="center",
                        va="center", family="monospace", zorder=5)

        if selected:
            lo, hi = min(ys), max(ys)
            ax.add_patch(plt.Rectangle((x - 0.42, lo - 0.42), 0.84, hi - lo + 0.84,
                                       fill=False, edgecolor=BLUE, lw=1.2, ls=":", zorder=6))

    fig.tight_layout(pad=0.25)
    return fig


def legend_figure():
    fig, ax = plt.subplots(figsize=(6.0, 0.30), dpi=130)
    _dark(fig, ax)
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    x = 0.005
    for label, colour in FAM_LEGEND:
        ax.add_patch(plt.Rectangle((x, 0.34), 0.014, 0.32, color=colour))
        ax.text(x + 0.022, 0.5, label, color=MUTED, fontsize=7, va="center")
        x += 0.026 + 0.0115 * len(label)
    fig.tight_layout(pad=0.05)
    return fig


# --------------------------------------------------------------------------
# Bloch sphere
# --------------------------------------------------------------------------

def bloch_figure(vec: E.BlochVector, title: str = ""):
    fig = plt.figure(figsize=(2.3, 2.5), dpi=150)
    fig.patch.set_facecolor(PANEL)
    ax = fig.add_subplot(111, projection="3d")
    ax.set_facecolor(PANEL)
    ax.set_axis_off()
    ax.set_box_aspect((1, 1, 1))

    t = np.linspace(0, 2 * np.pi, 90)
    zero = np.zeros_like(t)
    for xs, ys, zs in ((np.cos(t), np.sin(t), zero),
                       (np.cos(t), zero, np.sin(t)),
                       (zero, np.cos(t), np.sin(t))):
        ax.plot(xs, ys, zs, color="#31405A", lw=0.8, alpha=0.95)

    for vector, label in (((1.25, 0, 0), "x"), ((0, 1.25, 0), "y"),
                          ((0, 0, 1.2), "|0⟩"), ((0, 0, -1.2), "|1⟩")):
        ax.plot(*[[0, c] for c in vector], color="#33435C", lw=0.8)
        ax.text(*[c * 1.16 for c in vector], label, color=MUTED, fontsize=7.5,
                ha="center", va="center")

    if vec.length > 0.005:
        ax.quiver(0, 0, 0, vec.x, vec.y, vec.z, color=BLUE, lw=2.0,
                  arrow_length_ratio=0.16)
        ax.scatter([vec.x], [vec.y], [vec.z], s=22,
                   color=BLUE if not vec.entangled else AMBER, depthshade=False)
        ax.plot([vec.x, vec.x], [vec.y, vec.y], [vec.z, 0], color="#2B3A55", lw=0.7, ls=":")
        ax.plot([0, vec.x], [0, vec.y], [0, 0], color="#2B3A55", lw=0.7, ls=":")
    else:
        ax.scatter([0], [0], [0], s=34, color=AMBER, depthshade=False)

    ax.set_xlim(-1, 1)
    ax.set_ylim(-1, 1)
    ax.set_zlim(-1, 1)
    ax.view_init(elev=18, azim=35)
    if title:
        ax.set_title(title, color=TEXT, fontsize=7.5, pad=-6, family="monospace")
    fig.tight_layout(pad=0.0)
    return fig


# --------------------------------------------------------------------------
# outcome histogram
# --------------------------------------------------------------------------

def histogram_figure(exact: Dict[str, float], counts: Optional[Dict[str, int]] = None,
                     limit: int = 16):
    keys = sorted(set(exact) | set(counts or {}),
                  key=lambda k: -(exact.get(k, 0) + (counts or {}).get(k, 0) / max(1, sum((counts or {}).values()))))
    keys = keys[:limit]
    total = sum(counts.values()) if counts else 0
    ideal = [exact.get(k, 0.0) for k in keys]
    measured = [(counts.get(k, 0) / total if total else 0.0) for k in keys] if counts else None

    height = max(1.8, 0.30 * len(keys) + 0.8)
    fig, ax = plt.subplots(figsize=(5.2, height), dpi=150)
    _dark(fig, ax)
    y = np.arange(len(keys))
    bar_h = 0.34 if measured else 0.55

    ax.barh(y - (bar_h / 2 if measured else 0), ideal, height=bar_h, color=BLUE,
            label="exact probability", zorder=3)
    if measured:
        ax.barh(y + bar_h / 2, measured, height=bar_h, color=AMBER,
                label="sampled (%d shots)" % total, zorder=3)

    ax.set_yticks(y)
    ax.set_yticklabels(["|%s⟩" % k for k in keys], color=MUTED, fontsize=7.5, family="monospace")
    ax.invert_yaxis()
    ax.set_xlim(0, max(1e-6, max(ideal + (measured or [0]))) * 1.18)
    ax.tick_params(axis="x", colors=DIM, labelsize=6.5)
    ax.xaxis.grid(True, color=LINE, lw=0.6, zorder=0)
    ax.set_axisbelow(True)
    for i, v in enumerate(ideal):
        if v < 0.005:
            continue
        ax.text(v + 0.012, i - (bar_h / 2 if measured else 0), "%.1f%%" % (v * 100),
                color=MUTED, fontsize=6.2, va="center", family="monospace")
    ax.xaxis.set_major_formatter(lambda v, _pos: "%d%%" % round(v * 100))
    leg = ax.legend(loc="upper center", bbox_to_anchor=(0.5, 1.13), ncols=2,
                    fontsize=6.5, frameon=False, labelcolor=MUTED)
    if leg:
        for text in leg.get_texts():
            text.set_color(MUTED)
    fig.tight_layout(pad=0.3)
    return fig


# --------------------------------------------------------------------------
# amplitudes
# --------------------------------------------------------------------------

def phase_hex(re: float, im: float) -> str:
    angle = math.atan2(im, re) % (2 * math.pi)
    r, g, b = hsv_to_rgb((angle / (2 * math.pi), 0.62, 0.92))
    return "#%02X%02X%02X" % (int(r * 255), int(g * 255), int(b * 255))


def amplitude_rows(state: np.ndarray, n: int, limit: int = 32) -> List[dict]:
    rows = []
    for i, amp in enumerate(state):
        p = float(abs(amp) ** 2)
        if p <= 1e-9:
            continue
        re = 0.0 if abs(amp.real) < 1e-9 else float(amp.real)
        im = 0.0 if abs(amp.imag) < 1e-9 else float(amp.imag)
        rows.append({
            "state": "|%s⟩" % E.state_label(i, n),
            "amplitude": "%.3f %s %.3fi" % (re, "−" if im < 0 else "+", abs(im)),
            "phase°": round(math.degrees(math.atan2(im, re)) % 360, 1),
            "probability": round(p, 6),
            "_color": phase_hex(re, im),
        })
    rows.sort(key=lambda r: -r["probability"])
    return rows[:limit]


def phase_wheel_figure(state: np.ndarray, n: int, limit: int = 16):
    """Amplitudes on the complex plane — magnitude is radius, phase is angle."""
    fig, ax = plt.subplots(figsize=(3.0, 3.0), dpi=150)
    _dark(fig, ax)
    ax.set_aspect("equal")
    ax.axis("off")
    for r in (0.25, 0.5, 0.75, 1.0):
        ax.add_patch(Circle((0, 0), r, fill=False, edgecolor=LINE, lw=0.6))
    ax.plot([-1.1, 1.1], [0, 0], color=LINE, lw=0.6)
    ax.plot([0, 0], [-1.1, 1.1], color=LINE, lw=0.6)

    items = sorted(((abs(a), i, a) for i, a in enumerate(state) if abs(a) > 1e-6), reverse=True)
    for mag, i, amp in items[:limit]:
        colour = phase_hex(amp.real, amp.imag)
        angle = math.atan2(amp.imag, amp.real)
        ax.plot([0, amp.real], [0, amp.imag], color=colour, lw=1.4, alpha=0.9)
        ax.scatter([amp.real], [amp.imag], s=26, color=colour, zorder=4)
        ax.text(1.16 * math.cos(angle), 1.16 * math.sin(angle), E.state_label(i, n),
                color=colour, fontsize=5.8, ha="center", va="center", family="monospace")
    ax.set_xlim(-1.42, 1.42)
    ax.set_ylim(-1.42, 1.42)
    fig.tight_layout(pad=0.1)
    return fig


# --------------------------------------------------------------------------
# dashboards
# --------------------------------------------------------------------------

def meter_bar(value: float) -> str:
    """A text meter for compact tables."""
    filled = int(round(max(0.0, min(1.0, value)) * 12))
    return "█" * filled + "░" * (12 - filled)


def completion_figure(labels: List[str], values: List[float]):
    fig, ax = plt.subplots(figsize=(8.8, max(2.0, 0.32 * len(labels) + 0.55)), dpi=120)
    _dark(fig, ax)
    y = np.arange(len(labels))
    colours = [GOOD if v >= 0.75 else AMBER if v >= 0.45 else CRIT for v in values]
    ax.barh(y, values, color=colours, height=0.55, zorder=3)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, color=MUTED, fontsize=7.5)
    ax.invert_yaxis()
    ax.set_xlim(0, 1.05)
    ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.set_xticklabels(["0%", "25%", "50%", "75%", "100%"], color=DIM, fontsize=6.5)
    ax.xaxis.grid(True, color=LINE, lw=0.6, zorder=0)
    ax.set_axisbelow(True)
    for i, v in enumerate(values):
        ax.text(v + 0.012, i, "%d%%" % round(v * 100), color=MUTED, fontsize=6.5, va="center")
    fig.tight_layout(pad=0.3)
    return fig


def distribution_figure(values: List[float]):
    fig, ax = plt.subplots(figsize=(8.8, 2.5), dpi=120)
    _dark(fig, ax)
    buckets = np.zeros(10, dtype=int)
    for v in values:
        buckets[min(9, int(v * 10))] += 1
    x = np.arange(10)
    colours = [CRIT if i < 4 else AMBER if i < 7 else GOOD for i in x]
    ax.bar(x, buckets, color=colours, width=0.72, zorder=3)
    ax.set_xticks(x)
    ax.set_xticklabels(["%d–%d" % (i * 10, i * 10 + 9) for i in x], color=DIM, fontsize=6)
    ax.set_ylabel("learners", color=DIM, fontsize=7)
    ax.tick_params(axis="y", colors=DIM, labelsize=6.5)
    ax.yaxis.grid(True, color=LINE, lw=0.6, zorder=0)
    ax.set_axisbelow(True)
    ax.set_xlabel("quiz accuracy (%)", color=DIM, fontsize=7)
    fig.tight_layout(pad=0.3)
    return fig


# --------------------------------------------------------------------------
# intro diagrams
#
# These belong to the "Why quantum computing" lesson.  They are teaching
# pictures, not data charts, so they carry almost no chrome: no spines, no
# grid, direct labels instead of legends wherever a legend would be a lookup
# step.  The one real chart here (state_growth_figure) keeps a single y axis
# and labels its two series on the curve.
# --------------------------------------------------------------------------

def bit_vs_qubit_figure():
    """A classical bit is a switch; a qubit is a dial that still reads 0 or 1."""
    fig, ax = plt.subplots(figsize=(6.4, 2.25), dpi=130)
    _dark(fig, ax)
    ax.axis("off")
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 3.4)

    ax.text(2.4, 3.15, "A classical bit", color=TEXT, fontsize=9.5,
            ha="center", fontweight="bold")
    ax.text(7.6, 3.15, "A qubit", color=TEXT, fontsize=9.5,
            ha="center", fontweight="bold")

    # left: two discrete states
    for i, (label, cx) in enumerate((("0", 1.5), ("1", 3.3))):
        ax.add_patch(FancyBboxPatch((cx - 0.52, 1.45), 1.04, 0.9,
                                    boxstyle="round,pad=0.06,rounding_size=0.14",
                                    fc=INK, ec=NEUTRAL, lw=1.4))
        ax.text(cx, 1.9, label, color=TEXT, fontsize=15, ha="center", va="center")
    ax.text(2.4, 0.95, "only ever one of these two", color=MUTED,
            fontsize=7.6, ha="center")
    ax.text(2.4, 0.5, "like a light switch: on or off", color=DIM,
            fontsize=7.2, ha="center", style="italic")

    ax.plot([5.0, 5.0], [0.35, 2.9], color=LINE, lw=1.0)

    # right: a dial anywhere on the arc
    cx, cy, r = 7.6, 1.55, 0.78
    ax.add_patch(Arc((cx, cy), 2 * r, 2 * r, theta1=0, theta2=180,
                     color=LINE, lw=1.6))
    ax.plot([cx - r, cx + r], [cy, cy], color=LINE, lw=1.0)
    ax.text(cx - r - 0.22, cy - 0.04, "1", color=MUTED, fontsize=10, ha="center")
    ax.text(cx + r + 0.22, cy - 0.04, "0", color=MUTED, fontsize=10, ha="center")
    angle = math.radians(58)
    ax.annotate("", xy=(cx + r * 0.92 * math.cos(angle), cy + r * 0.92 * math.sin(angle)),
                xytext=(cx, cy),
                arrowprops=dict(arrowstyle="-|>", color=BLUE, lw=2.0,
                                shrinkA=0, shrinkB=0))
    ax.add_patch(Circle((cx, cy), 0.055, color=BLUE, zorder=5))
    ax.text(cx, 0.95, "can point anywhere in between", color=MUTED,
            fontsize=7.6, ha="center")
    ax.text(cx, 0.5, "but reading it still gives you just 0 or 1",
            color=DIM, fontsize=7.2, ha="center", style="italic")

    fig.tight_layout(pad=0.2)
    return fig


def state_growth_figure(max_qubits: int = 50):
    """Why simulating quantum computers gets hard: memory doubles per qubit."""
    fig, ax = plt.subplots(figsize=(6.4, 2.6), dpi=130)
    _dark(fig, ax)

    n = np.arange(1, max_qubits + 1)
    quantum = 2.0 ** n              # numbers a quantum state needs
    classical = n.astype(float)     # numbers a classical register needs

    ax.plot(n, quantum, color=BLUE, lw=2.0, zorder=3)
    ax.plot(n, classical, color=NEUTRAL, lw=2.0, zorder=3)

    ax.set_yscale("log")
    ax.set_xlim(1, max_qubits)
    ax.set_ylim(1, 10 ** 16)

    # direct labels, parked in the corners the curves leave empty
    ax.text(0.04, 0.88, "one qubit added\n= twice the numbers", transform=ax.transAxes,
            color=BLUE, fontsize=7.6, ha="left", va="top", linespacing=1.35)
    ax.text(0.62, 0.10, "classical bits", transform=ax.transAxes,
            color=NEUTRAL, fontsize=7.6, ha="left", va="bottom")

    # the point where a laptop gives up
    ax.axvline(45, color=DIM, lw=0.9, ls=(0, (3, 3)), zorder=1)
    ax.text(44, 10 ** 14.4, "a big server\nstops here  ", color=MUTED, fontsize=7.2,
            ha="right", va="center", linespacing=1.35)

    ax.set_xlabel("number of qubits", color=MUTED, fontsize=8)
    ax.set_ylabel("numbers needed to describe the state", color=MUTED, fontsize=8)
    ax.tick_params(colors=DIM, labelsize=7, length=0)
    ax.yaxis.grid(True, color=LINE, lw=0.6, zorder=0)
    ax.set_axisbelow(True)
    fig.tight_layout(pad=0.3)
    return fig


USE_CASES = [
    ("Medicine", "simulating molecules\ntoo complex for\nnormal computers", CYAN),
    ("Security", "today's encryption would\nneed replacing", AMBER),
    ("Logistics", "routing, scheduling,\npacking problems", VIOLET),
    ("Materials", "better batteries,\nbetter catalysts", GOOD),
]


def use_case_figure():
    """Where quantum computing is expected to matter first."""
    fig, ax = plt.subplots(figsize=(6.4, 1.85), dpi=130)
    _dark(fig, ax)
    ax.axis("off")
    ax.set_xlim(0, 4)
    ax.set_ylim(0, 1)

    for i, (title, blurb, colour) in enumerate(USE_CASES):
        x = i + 0.5
        ax.add_patch(FancyBboxPatch((x - 0.44, 0.12), 0.88, 0.72,
                                    boxstyle="round,pad=0.02,rounding_size=0.05",
                                    fc=INK, ec=LINE, lw=1.0))
        ax.add_patch(plt.Rectangle((x - 0.44, 0.12), 0.055, 0.72, color=colour))
        ax.text(x - 0.32, 0.68, title, color=TEXT, fontsize=8.6,
                fontweight="bold", va="center", ha="left")
        ax.text(x - 0.32, 0.37, blurb, color=MUTED, fontsize=7.0,
                va="center", ha="left", linespacing=1.45)

    fig.tight_layout(pad=0.2)
    return fig


def measurement_figure():
    """One quantum state, many runs, a tally at the end."""
    fig, ax = plt.subplots(figsize=(6.4, 2.1), dpi=130)
    _dark(fig, ax)
    ax.axis("off")
    ax.set_xlim(0, 10)
    ax.set_ylim(-0.62, 3)

    ax.add_patch(FancyBboxPatch((0.35, 1.05), 2.0, 1.0,
                                boxstyle="round,pad=0.06,rounding_size=0.14",
                                fc=INK, ec=BLUE, lw=1.5))
    ax.text(1.35, 1.55, "one state\nhalf 0, half 1", color=TEXT, fontsize=8,
            ha="center", va="center", linespacing=1.4)

    ax.annotate("", xy=(4.05, 1.55), xytext=(2.5, 1.55),
                arrowprops=dict(arrowstyle="-|>", color=DIM, lw=1.4))
    ax.text(3.27, 1.78, "run it", color=MUTED, fontsize=7.2, ha="center")

    outcomes = ["0", "1", "1", "0", "1"]
    for i, bit in enumerate(outcomes):
        y = 2.55 - i * 0.48
        ax.add_patch(FancyBboxPatch((4.2, y - 0.17), 0.52, 0.34,
                                    boxstyle="round,pad=0.02,rounding_size=0.06",
                                    fc=INK, ec=LINE, lw=1.0))
        ax.text(4.46, y, bit, color=TEXT, fontsize=8.4, ha="center", va="center")
    ax.text(4.46, -0.52, "each run gives\nexactly one bit", color=DIM, fontsize=7.0,
            ha="center", va="bottom", linespacing=1.4)

    ax.annotate("", xy=(6.6, 1.55), xytext=(5.05, 1.55),
                arrowprops=dict(arrowstyle="-|>", color=DIM, lw=1.4))
    ax.text(5.82, 1.78, "tally", color=MUTED, fontsize=7.2, ha="center")

    for i, (label, frac, colour) in enumerate((("0", 0.4, NEUTRAL), ("1", 0.6, BLUE))):
        y = 1.95 - i * 0.62
        ax.text(6.75, y, label, color=MUTED, fontsize=8, va="center")
        ax.add_patch(FancyBboxPatch((7.05, y - 0.13), 2.3 * frac, 0.26,
                                    boxstyle="round,pad=0,rounding_size=0.06",
                                    fc=colour, ec="none"))
        ax.text(7.05 + 2.3 * frac + 0.12, y, "%d%%" % round(frac * 100),
                color=MUTED, fontsize=7.4, va="center")
    ax.text(7.05, 0.42, "after only 5 runs", color=MUTED, fontsize=7.2, ha="left")
    ax.text(7.05, -0.08, "run it 2,000 times and it settles near 50 / 50",
            color=DIM, fontsize=7.0, ha="left", style="italic")

    fig.tight_layout(pad=0.2)
    return fig
