"""Curriculum, assessment bank, coding challenges and the tutor knowledge base.

Lesson bodies are Markdown with LaTeX, which Streamlit renders natively.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

import numpy as np

from . import engine as E
from .circuits import BY_ID, Circuit

PI = math.pi
B = Circuit.build


# --------------------------------------------------------------------------
# lessons
# --------------------------------------------------------------------------

@dataclass
class Track:
    id: str
    name: str
    blurb: str


TRACKS = [
    Track("found", "Foundations", "What a qubit is and what you can do to one."),
    Track("multi", "Many qubits", "Tensor products, entanglement, two-qubit gates."),
    Track("algo", "Algorithms", "Where the speedups actually come from."),
    Track("real", "Real machines", "Noise, SDKs and what runs on hardware today."),
]

TRACK_BY_ID = {t.id: t for t in TRACKS}


@dataclass
class Question:
    prompt: str
    options: List[str]
    answer: int
    why: str
    topic: str = "General"


@dataclass
class Lesson:
    id: str
    track: str
    title: str
    minutes: int
    body: str
    demo: Callable[[], Circuit]
    quiz: List[Question] = field(default_factory=list)


LESSONS: List[Lesson] = [
    Lesson("l0", "found", "Why quantum computing, and why now", 6, """
Before any of the maths, here is the honest version in one paragraph. A quantum
computer is **not** a faster laptop. It is a different kind of machine that is
very good at a small number of problems and no better than your phone at
everything else. This lesson is about which problems those are, why people are
spending serious money on it right now, and what a qubit actually is.

## A bit, and a qubit

@fig bit_vs_qubit

An ordinary computer stores a **bit** — a switch that is either 0 or 1. Every
photo, video and app on your machine is billions of those switches.

A **qubit** is different. Until you look at it, it can sit in a blend of 0 and 1
called a **superposition**. The dial in the picture is a fair mental image: it
can point anywhere, and where it points decides how likely each answer is.

The catch, and it is a big one: **when you read a qubit, you still only ever get
0 or 1.** You never see the dial. You only see where it happened to land.

@fig measurement

So a single run of a quantum computer gives you a single ordinary answer. To
learn anything you run the circuit many times and look at the pattern. Each run
is called a **shot**.

> **Everyday analogy.** A spinning coin is not heads and not tails while it is
> spinning — but slam your hand on it and it becomes one or the other. A qubit
> is roughly like that, except you also get to control *how* it spins, and two
> spinning coins can be linked so their landings always match.

## Why it is hard to fake on a normal computer

Here is the number that explains the whole field. To write down the state of
**n** qubits you need 2ⁿ numbers.

| Qubits | Numbers needed |
| --- | --- |
| 10 | about 1,000 |
| 30 | about 1 billion |
| 50 | about 1,000 trillion |
| 300 | more than the atoms in the visible universe |

@fig state_growth

Add one qubit and the bookkeeping **doubles**. Around 45–50 qubits even a large
server runs out of memory. Nature does this bookkeeping for free, which is the
original argument for building quantum computers: if you want to simulate a
quantum system, use a quantum system.

## Where it is actually expected to matter

@fig use_case

Notice what is *not* on that list: spreadsheets, websites, video games, ordinary
machine learning. Quantum computers are specialists. The realistic pitch is a
handful of problems where the speedup is real and large.

**Medicine and materials** is the most credible near-term one. Molecules *are*
quantum systems, so simulating them is the natural fit — better catalysts, better
batteries, better drug candidates.

**Security** is the most urgent. Shor's algorithm could break the RSA and
elliptic-curve encryption that protects banking and messaging today. No machine
is close to doing it yet, but data stolen now could be decrypted later, so
governments are already migrating to post-quantum cryptography.

## Why now

Three things changed at roughly the same time. Hardware crossed from a handful of
qubits to hundreds. Error correction went from theory to laboratory
demonstrations. And money arrived: India's **National Quantum Mission** was
approved in April 2023 with an outlay of **₹6,003.65 crore** through 2030–31,
targeting machines of 50 to 1,000 physical qubits and four thematic hubs.

## The honest caveat

Today's machines are **noisy**. Qubits lose their state in millionths of a
second, gates make small errors, and those errors pile up. For almost every
practical problem, a good classical algorithm still wins. Nobody has shown a
clear commercial advantage yet.

That is not a reason to ignore the field — it is the reason the field needs
people. If it were finished there would be nothing left to build.
""", lambda: B(1, [("H", [0]), ("MEASURE", [0])]), [
        Question("What do you actually get when you measure one qubit?",
                 ["A number between 0 and 1",
                  "Either 0 or 1, nothing in between",
                  "Both 0 and 1 at the same time",
                  "The two amplitudes"], 1,
                 "Measurement always gives a plain 0 or 1 — never a fraction, never both. "
                 "The superposition decides how LIKELY each answer is, but it never shows up "
                 "directly. That is why you run a circuit many times (shots) and read the "
                 "pattern instead of trusting one run.", "Foundations"),
        Question("You add one more qubit to a 20-qubit system. How much more memory does a "
                 "classical computer need to simulate it exactly?",
                 ["One more number", "Twenty more numbers", "Twice as much", "Twenty times as much"], 2,
                 "Each extra qubit DOUBLES the number of amplitudes: n qubits need 2ⁿ of them. "
                 "20 qubits need about a million; 21 need about two million. This doubling is "
                 "exactly why classical simulation dies around 45–50 qubits.", "Foundations"),
        Question("Which job is a quantum computer LEAST likely to be useful for?",
                 ["Simulating a molecule for drug discovery",
                  "Breaking RSA encryption",
                  "Running a video game at higher frame rates",
                  "Certain optimisation problems"], 2,
                 "Quantum computers are specialists, not general accelerators. Graphics is "
                 "ordinary arithmetic done very fast, which classical GPUs already do far "
                 "better. The wins are in chemistry, factoring and some optimisation — not "
                 "in everyday computing.", "Foundations"),
        Question("Why are people replacing today's encryption before a useful quantum computer exists?",
                 ["Current encryption has already been broken",
                  "Encrypted data stolen today could be decrypted years later",
                  "Quantum computers are already cheaper",
                  "Governments have banned RSA"], 1,
                 "This is called 'harvest now, decrypt later'. An attacker can copy encrypted "
                 "traffic today, store it, and decrypt it whenever a capable machine arrives. "
                 "Anything that must stay secret for a decade is already at risk, so the "
                 "migration to post-quantum cryptography starts now.", "Foundations"),
        Question("What is the main limitation of quantum computers available today?",
                 ["They are too slow at arithmetic",
                  "They are noisy — qubits lose their state and gates make errors",
                  "They cannot be programmed",
                  "There are no useful algorithms"], 1,
                 "The hardware is the bottleneck. Qubits hold their state for only millionths "
                 "of a second and every gate adds a little error, so long circuits produce "
                 "noise instead of answers. Good algorithms exist; machines reliable enough "
                 "to run them at useful size do not yet.", "Foundations")]),

    Lesson("l1", "found", "Bits, qubits and the state vector", 8, """
A classical bit is one of two things: 0 or 1. A qubit needs a richer
description — a pair of numbers, one attached to the 0 outcome and one attached
to the 1 outcome. Those numbers are called **amplitudes**.

$$|\\psi\\rangle = \\alpha|0\\rangle + \\beta|1\\rangle \\qquad |\\alpha|^2 + |\\beta|^2 = 1$$

**Every symbol in that line:**

| Symbol | Say it as | What it means |
| --- | --- | --- |
| \\|ψ⟩ | "ket psi" | The whole state of the qubit. The bar and angle bracket are just packaging that says "this is a quantum state". |
| \\|0⟩, \\|1⟩ | "ket zero", "ket one" | The two things you could end up measuring. |
| α | "alpha" | The amplitude attached to the 0 outcome. |
| β | "beta" | The amplitude attached to the 1 outcome. |
| \\|α\\|² | "mod alpha squared" | The **probability** of measuring 0. Square the size of α. |
| \\|α\\|² + \\|β\\|² = 1 | — | The probabilities must add to 1, because you always get *some* answer. |

> **Everyday analogy.** Think of α and β as two slices of a pie that must fill
> the whole pie. Make one bigger and the other gets smaller.

## Amplitudes are not probabilities

This is the single most common confusion, so be careful with it. Amplitudes are
**complex numbers**. Probabilities are what you get after squaring their size.

A complex number carries two pieces of information: a **size** and a
**direction** (the direction is called the **phase**). Squaring throws the phase
away. So α = 0.6 and α = −0.6 give exactly the same measurement odds — but they
are genuinely different states, and later, when branches recombine, that
difference decides the answer. Lesson 5 is entirely about this.

That extra piece — phase — is the whole reason a quantum computer can do
anything a classical one cannot. Take it away and you just have expensive dice.

## Many qubits

With **n** qubits you need 2ⁿ amplitudes, not n. Three qubits carry eight
numbers. Fifty carry more than a quadrillion. That growth is why simulating
quantum systems classically gets hard so fast — and why this platform caps the
circuit designer at 8 qubits.
""", lambda: B(3, [("H", [0]), ("H", [1]), ("H", [2])]), [
        Question("A qubit is in the state (|0⟩ + |1⟩)/√2. What is the probability of measuring 1?",
                 ["1/√2 ≈ 0.707", "0.5", "1.0", "It depends on the phase"], 1,
                 "Probability is the amplitude's size SQUARED, not the amplitude itself. "
                 "Here the amplitude is 1/√2 ≈ 0.707, so the probability is (1/√2)² = 1/2 = 0.5. "
                 "Forgetting to square is the most common slip in this topic.", "Foundations"),
        Question("How many amplitudes describe a 4-qubit state?",
                 ["4", "8", "16", "32"], 2,
                 "n qubits need 2ⁿ amplitudes — one for every possible measurement outcome. "
                 "With 4 qubits the outcomes are 0000 through 1111, which is 2⁴ = 16 of them.",
                 "Foundations"),
        Question("What is the difference between the states 0.6|0⟩ + 0.8|1⟩ and 0.6|0⟩ − 0.8|1⟩?",
                 ["No difference at all",
                  "Different measurement odds",
                  "Same measurement odds, different phase",
                  "The second one is invalid"], 2,
                 "Squaring removes the minus sign: 0.8² and (−0.8)² are both 0.64, so both "
                 "states give 64% chance of 1. But the minus sign is a real, physical "
                 "difference in PHASE. Send both through a Hadamard and they come out as "
                 "different states — that is interference, and it is where speedups come from.",
                 "Foundations"),
        Question("Why must |α|² + |β|² equal 1?",
                 ["To make the maths easier",
                  "Because probabilities of all outcomes must add to 1",
                  "Because α and β are always positive",
                  "It does not have to"], 1,
                 "|α|² and |β|² ARE the probabilities of measuring 0 and 1. A measurement "
                 "always returns one of them, so the two chances must cover every "
                 "possibility — they add to 1, exactly like any other probability distribution.",
                 "Foundations"),
        Question("What does the ket notation |0⟩ actually tell you?",
                 ["The qubit is switched off",
                  "The value is zero volts",
                  "It marks 0 as a quantum state rather than an ordinary number",
                  "The amplitude is zero"], 2,
                 "The bar and angle bracket are just notation — a label saying 'this is a "
                 "state vector, not a plain number'. |0⟩ is the state that always measures 0. "
                 "Note it is NOT the same as the number 0, and not the same as an amplitude "
                 "of zero.", "Foundations")]),

    Lesson("l2", "found", "Superposition and the Bloch sphere", 10, """
Any single-qubit state can be drawn as a point on the surface of a ball. The
north pole is $|0\\rangle$, the south pole is $|1\\rangle$, and every other point
is a superposition. This picture is called the **Bloch sphere**, and it turns
quantum gates into something you can actually see: rotations.

$$|\\psi\\rangle = \\cos(\\theta/2)\\,|0\\rangle + e^{i\\varphi}\\sin(\\theta/2)\\,|1\\rangle$$

**Every symbol in that line:**

| Symbol | Say it as | What it means |
| --- | --- | --- |
| θ | "theta" | Latitude — how far you have tipped away from the north pole. Controls the measurement odds. θ = 0 is certainly 0; θ = 180° is certainly 1; θ = 90° is a 50/50 split. |
| φ | "phi" | Longitude — where you are around the equator. This is the **phase**. |
| cos(θ/2) | — | The amplitude of \\|0⟩. Notice the **half**: going all the way around the sphere is θ = 360°, which is only 180° in the formula. |
| sin(θ/2) | — | The size of the amplitude of \\|1⟩. |
| e^(iφ) | "e to the i phi" | A dial that sets the phase without changing any probability. Its size is always exactly 1. |

> **Everyday analogy.** Latitude and longitude on Earth. Latitude tells you how
> far north or south you are — that is the part you can measure. Longitude tells
> you which way round you have gone — invisible to a single measurement, but it
> decides who you meet when two travellers arrive at the same place.

## Why φ does not change the odds

The probability of measuring 1 is sin²(θ/2). Look carefully: **φ is not in that
expression at all.** Spinning a qubit around the equator changes nothing you can
detect by measuring it right now.

So why carry it? Because phase decides how two branches **interfere** when you
bring them back together. It is stored information that becomes visible later.
A gate like Hadamard converts phase differences into probability differences,
which is how every quantum algorithm gets its advantage.

## Hadamard, the workhorse

The **Hadamard gate** (H) takes $|0\\rangle$ from the north pole down to the
equator, to the point called $|+\\rangle$. Half the time you measure 0, half the
time 1 — but the state itself is completely definite, not random. The randomness
appears only at measurement.

Run the demo and watch the Bloch vector swing from the pole to the equator.

## A vector shorter than the sphere

If the arrow is shorter than the radius, the qubit has no state of its own — it
is **entangled** with another qubit. You will meet that in the Many qubits track.
""", lambda: B(1, [("H", [0])]), [
        Question("Which of these changes the Bloch vector's latitude (θ) rather than its longitude (φ)?",
                 ["Rz", "S", "Ry", "T"], 2,
                 "Rz, S and T are all rotations about the z-axis (the pole-to-pole axis), so "
                 "they spin the arrow around without tipping it — longitude only, odds "
                 "unchanged. Ry tips the arrow toward or away from the pole, changing "
                 "latitude and therefore the measurement probabilities.", "Foundations"),
        Question("On the Bloch sphere, what does the north pole represent?",
                 ["|+⟩", "|0⟩", "|1⟩", "A measurement"], 1,
                 "By convention the north pole is |0⟩ and the south pole is |1⟩. Points on "
                 "the equator, such as |+⟩, are the even 50/50 superpositions.",
                 "Foundations"),
        Question("A qubit sits exactly on the equator. What are the odds of measuring 0?",
                 ["0%", "25%", "50%", "100%"], 2,
                 "The equator is θ = 90°, so the amplitude of |0⟩ is cos(45°) ≈ 0.707 and the "
                 "probability is 0.707² = 0.5. Every point on the equator is an even split — "
                 "what changes around the equator is the phase, not the odds.", "Foundations"),
        Question("Two qubits sit at different points on the equator. What differs between them?",
                 ["Their measurement probabilities", "Their phase", "Their energy", "Nothing"], 1,
                 "Moving along the equator changes longitude φ — the phase — while latitude "
                 "stays at 90°, so both are 50/50 on measurement. You cannot tell them apart "
                 "with one measurement, but a Hadamard turns that hidden difference into "
                 "visibly different outcomes.", "Foundations"),
        Question("What does a Bloch arrow SHORTER than the sphere's radius indicate?",
                 ["The qubit has lost energy",
                  "The qubit is entangled with another qubit",
                  "A measurement error",
                  "The state is invalid"], 1,
                 "A full-length arrow means the qubit has a definite state of its own. When "
                 "it is entangled with another qubit, the pair has a joint state but neither "
                 "one has an individual state — and that shows up as a shortened arrow. For a "
                 "Bell pair the arrow has length zero.", "Foundations")]),

    Lesson("l3", "found", "Measurement collapses the state", 7, """
Measurement is not a passive read. Looking at a qubit **changes** it. In the
computational basis it forces the qubit onto $|0\\rangle$ or $|1\\rangle$ with
probabilities $|\\alpha|^2$ and $|\\beta|^2$, and whatever superposition was
there is destroyed for good.

@fig measurement

> **Everyday analogy.** A spinning coin has no answer while it spins. Slam your
> hand down and it becomes heads or tails — and there is no way to get the spin
> back. Worse, you cannot even tell afterwards how fast it was spinning. One
> slam, one bit of information, and the rest is gone.

## What this costs you

**A single run tells you almost nothing.** One shot gives one bit. To see the
distribution you need many shots — typically 1,000 or more.

**Gates after a measurement act on a collapsed state.** The qubit is now an
ordinary classical 0 or 1, so anything you do next is classical. In this
platform that is almost always a bug rather than a design choice.

**You cannot copy a qubit to look at it twice.** This is the **no-cloning
theorem**. There is no "peek" operation, no debugger breakpoint that inspects a
live quantum state. It is the single biggest practical difference from ordinary
programming.

## How algorithms cope

Because you only get one sample, quantum algorithms are designed so the answer is
*already* concentrated on one outcome before you measure. The work happens before
the measurement, not during it.

Grover's search is the clearest example: it spends its entire runtime pushing
amplitude onto the correct answer, so the final measurement is nearly certain to
return it. An algorithm that ended with a flat 50/50 spread would be useless —
you would learn nothing.
""", lambda: B(1, [("H", [0]), ("MEASURE", [0])]), [
        Question("You run a Bell-state circuit once and read 11. What have you learned about the state?",
                 ["The state was |11⟩ all along",
                  "Almost nothing — a single shot cannot distinguish distributions",
                  "The circuit is wrong",
                  "The qubits were not entangled"], 1,
                 "One sample is one sample. A Bell state gives 00 and 11 with 50% each, so "
                 "reading 11 once is exactly what you would expect — and also exactly what "
                 "you would see from a circuit that always outputs 11. Only the pattern over "
                 "many shots tells them apart.", "Foundations"),
        Question("What happens to a superposition when you measure it?",
                 ["It is unchanged",
                  "It collapses to a single definite outcome",
                  "It splits into two states",
                  "It reverses"], 1,
                 "Measurement projects the state onto one basis state and discards the rest. "
                 "After measuring you have an ordinary 0 or 1 — the superposition is gone and "
                 "cannot be recovered. This is why measurement usually belongs at the END of "
                 "a circuit.", "Foundations"),
        Question("Why do you run a quantum circuit thousands of times?",
                 ["To make it more accurate each run",
                  "Because each run returns only one outcome, and you need the distribution",
                  "To warm up the hardware",
                  "Because the first runs are always wrong"], 1,
                 "Each shot returns a single outcome drawn from the state's probabilities. "
                 "One shot is one draw. Repeating builds up the histogram that actually "
                 "carries the answer — much like flipping a coin many times to estimate "
                 "whether it is fair.", "Foundations"),
        Question("The no-cloning theorem says you cannot…",
                 ["Measure a qubit twice",
                  "Make an identical copy of an unknown quantum state",
                  "Entangle three qubits",
                  "Reverse a gate"], 1,
                 "No operation can duplicate an arbitrary unknown state. You CAN copy a state "
                 "you already know how to build, by just building it again. What is forbidden "
                 "is copying something unknown — which is why there is no way to peek at a "
                 "live quantum state while keeping it intact.", "Foundations"),
        Question("You place an X gate AFTER a measurement on the same qubit. What does it do?",
                 ["Restores the superposition",
                  "Flips an ordinary classical bit",
                  "Causes an error",
                  "Nothing at all"], 1,
                 "Once measured, the qubit holds a definite 0 or 1, so X simply flips that "
                 "classical value — no quantum behaviour is left to exploit. It is legal, but "
                 "if you expected quantum behaviour after this point, it is a bug.",
                 "Foundations")]),

    Lesson("l4", "found", "Single-qubit gates", 10, """
Every operation on a qubit, apart from measurement, is a **rotation** of the
Bloch arrow. Nothing is created or destroyed; the arrow is only turned. That has
one important consequence straight away: **every gate is reversible.** Apply the
right rotation afterwards and you are exactly back where you started.

> **Everyday analogy.** Think of a globe on a stand. A gate spins it about some
> axis by some angle. Spin it back by the same amount and the globe is where it
> began — no information was lost. Measurement is the one operation that is not
> like this: it is a photograph, and you cannot un-photograph.

## The gates you will use most

| Gate | What it does | In plain words |
| --- | --- | --- |
| X | 180° about the x-axis | The NOT gate. Swaps \\|0⟩ and \\|1⟩. |
| Y | 180° about the y-axis | A flip plus a phase change. |
| Z | 180° about the z-axis | Leaves \\|0⟩ alone, flips the sign of \\|1⟩. Odds unchanged. |
| H | The basis changer | Turns pole states into equator states and back. Makes superpositions. |
| S, T | Quarter and eighth turns about z | Pure phase. Nothing visible until interference. |
| Rx, Ry, Rz | The same rotations, any angle | Rx and Ry change the odds; Rz only changes phase. |

## Two facts worth memorising

$$H\\cdot H = I \\qquad H\\cdot Z\\cdot H = X$$

**Reading them:**

| Piece | Meaning |
| --- | --- |
| H · H | Apply H, then H again. |
| I | The identity — do nothing. So H undoes itself. |
| H · Z · H | Apply H, then Z, then H. |
| = X | The result is exactly a NOT gate. |

The second one is worth sitting with. On its own, Z does nothing you can measure —
it only flips a sign. But sandwich it between two Hadamards and it becomes a
visible bit flip. **A phase change in one basis is a value change in another.**

That sentence is the seed of phase kickback, which is the engine inside almost
every quantum algorithm you will meet later.
""", lambda: B(1, [("H", [0]), ("Z", [0]), ("H", [0])]), [
        Question("What does H·Z·H do to a qubit?",
                 ["Nothing", "Acts as X", "Acts as Y", "Acts as S"], 1,
                 "Sandwiching Z between Hadamards swaps the roles of the z and x axes, which "
                 "turns a phase flip into a bit flip — the result is exactly the X (NOT) gate. "
                 "This is the clearest demonstration that phase and value are the same thing "
                 "viewed from different angles.", "Gates"),
        Question("Which gate is its own inverse?",
                 ["S", "T", "H", "Rz(π/3)"], 2,
                 "H·H = I, so applying Hadamard twice returns the original state. S and T are "
                 "quarter and eighth turns — you need four and eight of them respectively to "
                 "get back. A rotation by π/3 needs six.", "Gates"),
        Question("Applying Z to |+⟩ gives…",
                 ["|+⟩", "|−⟩", "|0⟩", "|1⟩"], 1,
                 "|+⟩ is (|0⟩+|1⟩)/√2. Z leaves |0⟩ alone and flips the sign of |1⟩, giving "
                 "(|0⟩−|1⟩)/√2, which is |−⟩. The measurement odds are still 50/50 — only the "
                 "phase changed — but it is now a genuinely different state.", "Gates"),
        Question("Why is every quantum gate (except measurement) reversible?",
                 ["Because they are all self-inverse",
                  "Because they are rotations, and any rotation can be undone",
                  "Because they are slow",
                  "They are not reversible"], 1,
                 "A gate rotates the Bloch arrow without shortening it, so no information is "
                 "lost and the rotation can always be undone by turning back. Measurement is "
                 "the exception precisely because it DOES destroy information. Note "
                 "reversible is not the same as self-inverse: T is reversible but you need "
                 "T† to undo it.", "Gates"),
        Question("Which gate changes the probability of measuring 1?",
                 ["Z", "S", "T", "Ry"], 3,
                 "Z, S and T all rotate about the z-axis, which moves the arrow around the "
                 "equator — phase only, odds untouched. Ry tips the arrow toward or away from "
                 "the poles, which is exactly what changes the measurement probabilities.",
                 "Gates")]),

    Lesson("l5", "found", "Phase and interference", 9, """
Phase is invisible to a measurement — until you make it visible. This lesson is
about the trick that turns hidden phase into a readable answer, and it is the
single most important idea in the whole platform.

> **Everyday analogy.** Two speakers playing the same note. Push them slightly
> out of step and the sound can double in volume — or cancel to silence. Nothing
> changed about either speaker on its own. What changed is how the two waves
> line up when they meet. Quantum amplitudes add up exactly like this.

## The demonstration

Put a qubit in superposition, then change the relative phase between the two
branches, then fold the branches back together with a Hadamard:

$$H\\frac{|0\\rangle+|1\\rangle}{\\sqrt2} = |0\\rangle \\qquad
H\\frac{|0\\rangle-|1\\rangle}{\\sqrt2} = |1\\rangle$$

**Reading it:**

| Piece | Meaning |
| --- | --- |
| (\\|0⟩+\\|1⟩)/√2 | The even superposition, both branches in step. Written \\|+⟩. |
| (\\|0⟩−\\|1⟩)/√2 | The same odds, but the \\|1⟩ branch has its sign flipped. Written \\|−⟩. |
| √2 | Divides by about 1.414 so the probabilities still add to 1. |
| H … = \\|0⟩ | Feed the in-step version into a Hadamard and you get a **guaranteed** 0. |
| H … = \\|1⟩ | Feed the out-of-step version in and you get a **guaranteed** 1. |

Look at what just happened. Before the final H, both states were an identical
50/50 gamble — no measurement could tell them apart. After the final H, one is
certainly 0 and the other is certainly 1. **A completely invisible difference
became a completely certain answer.**

## Why this is the whole game

Every quantum algorithm is built on this move: arrange the computation so that
wrong answers pick up phases that **cancel** each other, and the right answer's
amplitudes **add**. The speedup comes from destructive interference — not from
"trying all answers at once".

That phrase, "tries every answer in parallel", is the most common misleading
description of quantum computing. The superposition genuinely exists, but you
only get one sample out of it. The real work is making that sample almost
certainly correct.

The demo puts a qubit in superposition, adds a phase of π, and folds it back.
The output is completely deterministic even though the middle of the circuit was
maximally uncertain.
""", lambda: B(1, [("H", [0]), ("P", [0], [PI]), ("H", [0]), ("MEASURE", [0])]), [
        Question('Why is "a quantum computer tries every answer in parallel" misleading?',
                 ["It is exactly right",
                  "Measurement returns one outcome, so the algorithm must interfere the wrong answers away first",
                  "Qubits cannot hold superpositions",
                  "Parallelism requires entanglement"], 1,
                 "The superposition is real, but you only get ONE sample out of it, chosen at "
                 "random by the probabilities. If every answer were equally likely you would "
                 "learn nothing. The actual work of an algorithm is cancelling the wrong "
                 "answers so the sample you get is almost certainly right.", "Foundations"),
        Question("What does a Hadamard do to the state (|0⟩ − |1⟩)/√2?",
                 ["Returns |0⟩", "Returns |1⟩", "Leaves it unchanged", "Returns |+⟩"], 1,
                 "H|−⟩ = |1⟩. The minus sign means the two branches are out of step, so when "
                 "the Hadamard recombines them they cancel on the 0 outcome and reinforce on "
                 "the 1 outcome. The in-step version, |+⟩, gives |0⟩ instead.", "Foundations"),
        Question("Before the final Hadamard, can a measurement tell |+⟩ from |−⟩?",
                 ["Yes, easily",
                  "No — both give 50/50 in the computational basis",
                  "Only with many shots",
                  "Only on real hardware"], 1,
                 "Both states have amplitudes of size 1/√2 on each outcome, so both measure "
                 "0 half the time and 1 half the time — no number of shots separates them. "
                 "You must first convert the phase difference into a probability difference, "
                 "which is exactly what the Hadamard does.", "Foundations"),
        Question("Where does a quantum speedup actually come from?",
                 ["Running many CPUs at once",
                  "Wrong answers cancelling through destructive interference",
                  "Faster clock speeds",
                  "Storing more data per qubit"], 1,
                 "Amplitudes are like waves: they can add or cancel. A good algorithm arranges "
                 "for the wrong answers' amplitudes to cancel out and the right answer's to "
                 "reinforce, so the final measurement lands on the answer. Clock speed and "
                 "storage have nothing to do with it — quantum gates are actually SLOWER than "
                 "classical ones.", "Foundations"),
        Question("What does the P(π) gate do in the demo circuit?",
                 ["Measures the qubit",
                  "Flips the sign of the |1⟩ branch, turning |+⟩ into |−⟩",
                  "Resets the qubit to |0⟩",
                  "Creates entanglement"], 1,
                 "P(π) multiplies the |1⟩ branch by e^(iπ) = −1, leaving |0⟩ untouched. That "
                 "converts |+⟩ into |−⟩. Nothing measurable has changed yet — the odds are "
                 "still 50/50 — but the following Hadamard turns that hidden sign flip into a "
                 "guaranteed 1.", "Foundations")]),

    Lesson("l6", "multi", "Two qubits and the tensor product", 8, """
Two qubits have four amplitudes, one for each of $|00\\rangle$, $|01\\rangle$,
$|10\\rangle$, $|11\\rangle$. If the qubits are independent, that four-vector
factorises into a pair of two-vectors. If it does not factorise, the qubits are
entangled.

$$|\\psi\\rangle = a|00\\rangle + b|01\\rangle + c|10\\rangle + d|11\\rangle
\\quad\\text{separable}\\iff ad = bc$$

> **Bit ordering.** This platform, like Qiskit, puts qubit 0 on the *right* of
> the label. The string `011` means q2=0, q1=1, q0=1.
""", lambda: B(2, [("H", [0]), ("H", [1])]), [
        Question("The state (|00⟩ + |01⟩ + |10⟩ + |11⟩)/2 is…",
                 ["Entangled", "Separable — it is |+⟩ on both qubits", "Not a valid state", "Mixed"],
                 1, "ad = bc holds (¼ = ¼), and the state factorises as |+⟩⊗|+⟩.", "Entanglement")]),

    Lesson("l7", "multi", "Entanglement and Bell states", 11, """
Hadamard on one qubit, then CNOT onto a second, and you have the Bell state
$(|00\\rangle + |11\\rangle)/\\sqrt2$. Measure either qubit and you get 0 or 1
with even odds — but the two results always agree.

Here is the sharp diagnostic: look at each qubit's Bloch vector. For a maximally
entangled pair, both vectors have **length zero**. Each qubit on its own is
completely undetermined; all the information lives in the correlation. The
Studio shows this directly — build a Bell state and watch both spheres collapse
to their centre.

There are four Bell states, differing by an X or a Z on one side. They form a
basis, which is exactly what superdense coding and teleportation exploit.
""", lambda: BY_ID["bell"].make(), [
        Question("In a Bell state, what is the length of each individual qubit's Bloch vector?",
                 ["1 — both are pure", "0 — each qubit alone is maximally mixed", "0.5",
                  "It depends which Bell state"], 1,
                 "Maximal entanglement means maximal local ignorance. The reduced state of each "
                 "qubit is the completely mixed state at the centre of the sphere.", "Entanglement")]),

    Lesson("l8", "multi", "Controlled gates and universality", 9, """
A controlled gate applies its operation only to the branches where the control
qubit is $|1\\rangle$. Because it acts on the superposition rather than on a
definite bit, it entangles rather than merely branching.

CNOT plus arbitrary single-qubit rotations is a **universal** gate set: any
unitary on any number of qubits can be decomposed into them. That is why
hardware vendors work so hard on two-qubit gate fidelity — everything reduces to
it.

CZ is worth a second look. It is symmetric: it does not matter which qubit you
call the control. And $CX = (I\\otimes H)\\cdot CZ\\cdot(I\\otimes H)$, so the two
are the same gate wearing different clothes.
""", lambda: B(2, [("H", [0]), ("H", [1]), ("CZ", [0, 1]), ("H", [1])]), [
        Question("Which set is universal for quantum computation?",
                 ["H and X alone", "CNOT plus arbitrary single-qubit gates", "CNOT alone",
                  "Only the Pauli gates"], 1,
                 "One entangling two-qubit gate plus full single-qubit control generates the "
                 "whole unitary group.", "Gates")]),

    Lesson("l9", "algo", "Phase kickback and Deutsch–Jozsa", 12, """
Put the target qubit of a controlled gate into $|-\\rangle$ and something odd
happens: the target does not change, but the **control** picks up a phase. This
is phase kickback, and it is the engine of almost every early quantum algorithm.

Deutsch–Jozsa uses it to decide, in a single oracle query, whether a function is
constant (same output everywhere) or balanced (0 on half the inputs, 1 on the
other half). Classically you may need to check $2^{n-1}+1$ inputs. Here: put
every input qubit in superposition, query once, undo the superposition, measure.
All zeros means constant; anything else means balanced.

The demo's oracle is two CNOTs, which implements a balanced function — so the
top register reads `11` every time, never `00`.
""", lambda: BY_ID["dj"].make(), [
        Question("In Deutsch–Jozsa, what does an all-zeros measurement of the input register tell you?",
                 ["The function is balanced", "The function is constant", "The circuit failed",
                  "Nothing without more shots"], 1,
                 "Constant functions produce total constructive interference on the all-zeros "
                 "outcome; balanced ones produce exactly zero amplitude there.", "Algorithms")]),

    Lesson("l10", "algo", "Grover's search", 13, """
Grover finds a marked item among $N$ in about $\\sqrt N$ steps instead of $N/2$.
It alternates two moves:

- **Oracle** — flip the sign of the marked state's amplitude.
- **Diffuser** — reflect every amplitude about the average.

Together these rotate the state vector a small angle toward the answer each
round. On two qubits one iteration lands exactly on the target: the demo finds
$|11\\rangle$ with probability 1. On three qubits, two iterations reach about
94.5%.

> **More iterations is not better.** Overshoot the optimal
> $\\lfloor\\frac{\\pi}{4}\\sqrt N\\rfloor$ rounds and the amplitude rotates back
> off the target. Add a third iteration in the Studio and watch the success
> probability fall.
""", lambda: BY_ID["grover2"].make(), [
        Question("Roughly how many Grover iterations are optimal for N items?",
                 ["log N", "√N", "N/2", "N log N"], 1,
                 "About (π/4)√N. Each iteration rotates the state by a fixed small angle "
                 "toward the marked item.", "Algorithms")]),

    Lesson("l11", "algo", "The quantum Fourier transform", 12, """
The QFT maps amplitudes into the frequency domain, using Hadamards and
controlled phase rotations. On $n$ qubits it takes $O(n^2)$ gates, against
$O(n\\,2^n)$ for the classical FFT on the same vector length.

You cannot read the Fourier coefficients out directly — measurement gives you
one sample. What the QFT is *for* is turning a periodicity hidden in a phase
into a peak you can measure. That is the step that makes Shor's factoring
algorithm work, via quantum phase estimation.

Note the SWAP at the end of the demo: the standard construction leaves the
output qubits in reverse order.
""", lambda: BY_ID["qft3"].make(), [
        Question("What is the QFT actually used for inside Shor's algorithm?",
                 ["Compressing the input", "Turning a hidden period into a measurable peak",
                  "Reading out all Fourier coefficients", "Error correction"], 1,
                 "Phase estimation uses the inverse QFT to convert an eigenphase — which "
                 "encodes the period — into a basis state you can sample.", "Algorithms")]),

    Lesson("l12", "real", "Noise, shots and real hardware", 10, """
Today's devices are noisy. Two-qubit gates on good superconducting hardware sit
around 99–99.9% fidelity; a few hundred of them in sequence and the signal is
gone. Readout adds its own error, typically 1–3% per qubit.

Select the **Qiskit Aer · noisy device model** backend in the Studio and watch a
GHZ state's clean two-peak histogram fill in with the other six outcomes. That
is a real Aer `NoiseModel` with depolarising and readout error, not a cosmetic
smear on the chart.

Practical habits this rewards: keep circuits shallow, minimise two-qubit gates,
and treat every result as a distribution with error bars rather than an answer.
""", lambda: BY_ID["ghz"].make(), [
        Question("Which circuit property most strongly predicts how badly noise will hurt you?",
                 ["Number of qubits", "Number of two-qubit gates and circuit depth",
                  "Number of Hadamards", "Number of shots"], 1,
                 "Two-qubit gates are the noisiest operation and depth sets how long the state "
                 "must survive decoherence.", "Hardware")]),

    Lesson("l13", "real", "Working across SDKs", 8, """
Qiskit, Cirq and PennyLane describe the same circuits with different words. Once
you can read one, the others are mostly vocabulary:

```python
qc.h(0);              qc.cx(0, 1)                 # Qiskit
cirq.H(q[0]);         cirq.CNOT(q[0], q[1])       # Cirq
qml.Hadamard(wires=0); qml.CNOT(wires=[0, 1])     # PennyLane
h q[0];               cx q[0],q[1];               # OpenQASM
```

The Studio's code panel reads all four and writes all four, so you can paste a
circuit from a paper in one dialect and export it in another.

Watch out for one real difference: **Qiskit puts qubit 0 on the right of a bit
string; Cirq and PennyLane put wire 0 on the left.** This platform normalises
everything to the Qiskit convention, and the backend adapters reverse Cirq and
PennyLane results on the way back — which is exactly the bug that bites people
comparing results across SDKs.
""", lambda: B(2, [("H", [0]), ("CX", [0, 1])]), [
        Question("A paper prints its result as |01⟩ using Cirq conventions. In Qiskit's convention that same state is…",
                 ["|01⟩", "|10⟩", "|11⟩", "Undefined"], 1,
                 "Cirq orders qubits left to right (q0 first); Qiskit puts q0 on the right. "
                 "The bit string reverses.", "Hardware")]),
]

LESSON_BY_ID = {l.id: l for l in LESSONS}


# --------------------------------------------------------------------------
# coding challenges
# --------------------------------------------------------------------------

def _target(n, spec):
    return E.statevector(B(n, spec))


@dataclass
class Challenge:
    id: str
    title: str
    level: str
    xp: int
    qubits: int
    brief: str
    hint: str
    score: Callable[[np.ndarray], float]
    banned: List[str] = field(default_factory=list)
    max_two_qubit: Optional[int] = None


CHALLENGES: List[Challenge] = [
    Challenge("c1", "Make a superposition", "Intro", 40, 1,
              "Put qubit 0 into an equal superposition of |0⟩ and |1⟩ with real, positive amplitudes.",
              "One gate does this.",
              lambda s: E.fidelity(s, _target(1, [("H", [0])]))),
    Challenge("c2", "Flip to |1⟩ without using X", "Intro", 50, 1,
              "End in state |1⟩ using only H, Z, S or T gates — no X, Y, Rx or Ry.",
              "H·Z·H = X. Sandwich a phase flip between two basis changes.",
              lambda s: E.fidelity(s, _target(1, [("X", [0])])),
              banned=["X", "Y", "RX", "RY", "U", "SX"]),
    Challenge("c3", "Reach the |−i⟩ state", "Intro", 60, 1,
              "Steer qubit 0 to the −y point of the Bloch sphere: (|0⟩ − i|1⟩)/√2.",
              "Get to the equator first, then rotate around z the other way.",
              lambda s: E.fidelity(s, _target(1, [("H", [0]), ("SDG", [0])]))),
    Challenge("c4", "Build a Bell pair", "Core", 70, 2,
              "Create (|00⟩ + |11⟩)/√2 on qubits 0 and 1.",
              "Superposition on one qubit, then copy the correlation across with a CNOT.",
              lambda s: E.fidelity(s, _target(2, [("H", [0]), ("CX", [0, 1])]))),
    Challenge("c5", "The odd Bell state", "Core", 80, 2,
              "Create Ψ− = (|01⟩ − |10⟩)/√2, the singlet. It is the only Bell state that "
              "looks the same in every basis.",
              "Flip qubit 0 before the Hadamard to get the minus sign, and flip qubit 1 to "
              "get the anti-correlation.",
              lambda s: E.fidelity(s, _target(2, [("X", [0]), ("H", [0]), ("X", [1]),
                                                  ("CX", [0, 1])]))),
    Challenge("c6", "Three-qubit GHZ", "Core", 90, 3,
              "Create (|000⟩ + |111⟩)/√2 using at most two two-qubit gates.",
              "Chain the correlation: 0 to 1, then 1 to 2.",
              lambda s: E.fidelity(s, _target(3, [("H", [0]), ("CX", [0, 1]), ("CX", [1, 2])])),
              max_two_qubit=2),
    Challenge("c7", "Swap without SWAP", "Advanced", 100, 2,
              "Put qubit 0 into |1⟩, then exchange the two qubits so the state is |10⟩ — "
              "using CNOTs only, no SWAP gate.",
              "Three CNOTs, alternating direction, make a SWAP.",
              lambda s: E.fidelity(s, _target(2, [("X", [1])])),
              banned=["SWAP", "CSWAP"]),
    Challenge("c8", "Amplify the answer", "Advanced", 120, 2,
              "Build one full Grover iteration on two qubits so that |10⟩ is measured with certainty.",
              "Uniform superposition, an oracle that flips the sign of |10⟩, then the standard diffuser.",
              lambda s: float(E.probabilities(s)[2])),
]

CHALLENGE_BY_ID = {c.id: c for c in CHALLENGES}


# --------------------------------------------------------------------------
# assessment bank
# --------------------------------------------------------------------------

QUIZ_BANK: List[Question] = [
    Question("How many complex amplitudes describe an n-qubit pure state?",
             ["2n", "n²", "2ⁿ", "n!"], 2,
             "One amplitude per computational basis state, and there are 2ⁿ of them.", "Foundations"),
    Question("Which operation is NOT reversible?",
             ["Hadamard", "CNOT", "Measurement", "Rz(θ)"], 2,
             "Every gate is unitary and therefore invertible. Measurement destroys information.",
             "Foundations"),
    Question("Applying Z to |+⟩ gives…", ["|+⟩", "|−⟩", "|0⟩", "|1⟩"], 1,
             "Z flips the sign of the |1⟩ component, turning (|0⟩+|1⟩)/√2 into (|0⟩−|1⟩)/√2.",
             "Foundations"),
    Question("A global phase e^{iγ} on the whole state…",
             ["Changes the measurement statistics", "Is physically unobservable",
              "Breaks normalisation", "Only matters for one qubit"], 1,
             "Global phase cancels in every probability. Only relative phases between branches "
             "are observable.", "Foundations"),
    Question("What is T·T equal to?", ["I", "S", "Z", "H"], 1,
             "T is a π/4 phase; two of them make the π/2 phase gate S.", "Gates"),
    Question("Which gate is its own inverse?", ["S", "T", "H", "Rz(π/3)"], 2,
             "H·H = I. S and T are quarter and eighth turns, so they are not self-inverse.", "Gates"),
    Question("CZ differs from CNOT by…",
             ["Nothing, they are identical", "A Hadamard on the target either side", "A SWAP",
              "A global phase"], 1,
             "CX = (I⊗H)·CZ·(I⊗H). Conjugating the target by H swaps the phase flip for a bit flip.",
             "Gates"),
    Question("Which state is entangled?",
             ["(|00⟩+|01⟩)/√2", "(|00⟩+|11⟩)/√2", "|+⟩⊗|+⟩", "|10⟩"], 1,
             "Only the second fails to factorise into a state for each qubit.", "Entanglement"),
    Question("Entanglement lets you…",
             ["Send information faster than light", "Copy an unknown quantum state",
              "Create correlations no classical strategy can reproduce", "Measure without disturbance"],
             2, "The correlations violate Bell inequalities, but the marginal statistics on each "
                "side are uniform, so no signal is sent.", "Entanglement"),
    Question("The no-cloning theorem says…",
             ["You cannot measure a qubit twice",
              "There is no unitary that copies an arbitrary unknown state",
              "Entangled states cannot be separated", "Quantum memory is impossible"], 1,
             "Linearity of quantum mechanics forbids a universal copier. You can copy basis "
             "states, just not superpositions.", "Entanglement"),
    Question("Grover's algorithm gives which kind of speedup?",
             ["Exponential", "Quadratic", "Linear", "None"], 1,
             "√N versus N — quadratic, and provably optimal for unstructured search.", "Algorithms"),
    Question("Shor's algorithm factors integers by…",
             ["Searching all factors in parallel",
              "Finding the period of a modular exponential with phase estimation",
              "Using entanglement to guess", "Running Grover on the factors"], 1,
             "Factoring reduces to period finding, and the QFT extracts the period efficiently.",
             "Algorithms"),
    Question("Deutsch–Jozsa needs how many oracle queries?", ["1", "n", "2ⁿ⁻¹+1", "log n"], 0,
             "One query, against 2ⁿ⁻¹+1 in the classical worst case.", "Algorithms"),
    Question("Running twice the optimal number of Grover iterations…",
             ["Doubles the success probability", "Rotates past the target and lowers it",
              "Has no effect", "Causes an error"], 1,
             "Grover is a rotation. Past the optimum it keeps rotating away from the marked state.",
             "Algorithms"),
    Question("On current superconducting hardware, which error dominates a deep circuit?",
             ["Single-qubit gate error", "Two-qubit gate error", "Compilation error", "Shot noise"],
             1, "Two-qubit gates are typically an order of magnitude noisier than single-qubit gates.",
             "Hardware"),
    Question("What does increasing the shot count improve?",
             ["Gate fidelity", "Statistical resolution of the output distribution",
              "Circuit depth limits", "Decoherence time"], 1,
             "Shots only reduce sampling noise. They do nothing about hardware error.", "Hardware"),
    Question('A "transpiled" circuit is one that has been…',
             ["Compiled to the device's native gates and connectivity", "Translated to another SDK",
              "Error corrected", "Optimised for shots"], 0,
             "Transpilation maps logical gates onto what the chip physically supports, inserting "
             "SWAPs where qubits are not adjacent.", "Hardware"),
    Question("Why does exact simulation stop being possible at a few dozen qubits?",
             ["Browser security", "The state vector doubles in size with each qubit",
              "Hardware limits", "Licensing"], 1,
             "Exact simulation stores 2ⁿ amplitudes. Beyond a few dozen qubits no classical "
             "machine can hold the vector.", "Hardware"),
]


# --------------------------------------------------------------------------
# tutor knowledge base
# --------------------------------------------------------------------------

@dataclass
class Article:
    keys: List[str]
    title: str
    text: str
    goto: Optional[Dict[str, str]] = None


KB: List[Article] = [
    Article(["superposition", "superpose"], "Superposition",
            "A qubit in superposition carries a number for the 0 outcome and a number for "
            "the 1 outcome at the same time: a|0> + b|1>. Those numbers are called amplitudes, "
            "and squaring their size gives you the chance of each answer.\n\n"
            "Careful with the phrase '0 and 1 at the same time' — it is the usual "
            "description and it is misleading. The qubit is in one definite state; what is "
            "split is how likely each ANSWER is. And when you measure, you still get a plain "
            "0 or 1, never both.\n\n"
            "Think of a spinning coin: while it spins it is neither heads nor tails, but it "
            "is doing something perfectly definite. The Hadamard gate is how you set a qubit "
            "spinning: H|0> = (|0>+|1>)/sqrt(2), an even 50/50 split.",
            {"page": "Lessons", "lesson": "l2"}),
    Article(["entangle", "bell", "epr", "glove", "correlat"], "Entanglement",
            "Two qubits are entangled when their joint state cannot be written as one state for "
            "each qubit. The tell-tale sign in this platform: each qubit's Bloch vector shrinks. "
            "For a Bell state both vectors have length zero — every qubit is individually random, "
            "yet the pair is perfectly correlated. Build one with H on qubit 0 then CNOT(0->1). "
            "Beware the glove analogy — a left glove posted to one city and a right glove to "
            "another are merely correlated, and they were left and right all along. Entangled "
            "qubits have no such pre-set values, and the difference is measurable: entangled "
            "pairs violate Bell's inequality and correlated gloves never can.",
            {"page": "Lessons", "lesson": "l7"}),
    Article(["bloch", "sphere"], "The Bloch sphere",
            "A single qubit's state is a point on a unit sphere: cos(t/2)|0> + e^{i p} sin(t/2)|1>. "
            "Theta is latitude (measurement odds), phi is longitude (phase). Gates are rotations. "
            "A vector shorter than 1 means the qubit is entangled with something else, so it has "
            "no pure state of its own.", {"page": "Lessons", "lesson": "l2"}),
    Article(["measur", "measurement", "collapse", "shots"], "Measurement",
            "Measuring forces the qubit to pick: it comes out 0 or 1, with chances |a|^2 "
            "and |b|^2, and the superposition is destroyed. You cannot get it back, and you "
            "cannot peek without breaking it.\n\n"
            "So one run gives you exactly one bit. To see the pattern you run the circuit "
            "many times — each run is called a shot, and 1,000 or more is normal.\n\n"
            "Practical warning: gates placed AFTER a measurement act on an ordinary "
            "classical 0 or 1, because the quantum behaviour is already gone. That is "
            "almost always a bug rather than something you meant.", {"page": "Lessons", "lesson": "l3"}),
    Article(["phase", "interference", "kickback"], "Phase and interference",
            "Relative phase does not change z-basis odds, but it decides how branches interfere "
            "when you recombine them. H(|0>-|1>)/sqrt(2) = |1> while H(|0>+|1>)/sqrt(2) = |0> — "
            "same probabilities before, opposite outcomes after. Phase kickback is the trick of "
            "hiding an answer in a phase and then folding it out with Hadamards.",
            {"page": "Lessons", "lesson": "l5"}),
    Article(["grover", "search", "amplitude amplification"], "Grover's algorithm",
            "Grover searches N unstructured items in about (pi/4)sqrt(N) queries. Each iteration "
            "is an oracle (flip the sign of the marked state) followed by a diffuser (reflect "
            "about the mean), which rotates the state a fixed angle toward the answer. Two qubits "
            "need exactly one iteration; three need two. Overshooting makes it worse.",
            {"page": "Algorithm library", "algo": "grover2"}),
    Article(["shor", "factor", "qft", "fourier"], "QFT and Shor",
            "The quantum Fourier transform costs O(n^2) gates and converts a phase-encoded "
            "periodicity into a measurable peak. Shor reduces factoring to finding the period of "
            "a^x mod N, then uses phase estimation — which ends with an inverse QFT — to read "
            "that period off. You cannot extract all the coefficients.",
            {"page": "Algorithm library", "algo": "qft3"}),
    Article(["teleport", "teleportation"], "Quantum teleportation",
            "Teleportation moves an unknown state from one qubit to another using a shared Bell "
            "pair and two classical bits. Nothing travels faster than light — the classical bits "
            "are required, and without them the receiver holds a maximally mixed qubit. It also "
            "does not clone: the source state is destroyed by the Bell measurement.",
            {"page": "Algorithm library", "algo": "teleport"}),
    Article(["cnot", "cx", "controlled", "cz", "toffoli"], "Controlled gates",
            "A controlled gate acts on the target only in the branches where the control is |1>. "
            "CNOT plus arbitrary single-qubit rotations is universal. CZ is CNOT with Hadamards "
            "on the target either side, and unlike CNOT it is symmetric between its two qubits. "
            "Toffoli (CCX) is a reversible AND.", {"page": "Lessons", "lesson": "l8"}),
    Article(["noise", "decoherence", "error", "nisq", "hardware"], "Noise on real hardware",
            "Two-qubit gates dominate the error budget on today's machines, with readout error "
            "close behind. That makes depth and two-qubit gate count the numbers to watch. Pick "
            "the Aer noisy backend in the Studio to see a clean GHZ histogram fill in with "
            "spurious outcomes.", {"page": "Lessons", "lesson": "l12"}),
    Article(["qubit", "what is a qubit"], "What a qubit is",
            "A qubit is a two-level quantum system described by two complex amplitudes with "
            "|a|^2+|b|^2=1. The physical carrier varies — a superconducting circuit, a trapped "
            "ion, a photon's polarisation — but the mathematics is identical, which is why you "
            "can learn it all here.", {"page": "Lessons", "lesson": "l1"}),
    Article(["qiskit", "cirq", "pennylane", "sdk", "qasm", "qbraid",
             "qubit ordering", "bit ordering", "endian", "reversed"], "Working across SDKs",
            "The code panel in the Studio reads Qiskit, Cirq, PennyLane and OpenQASM and can "
            "export any of them. The main gotcha is bit ordering: Qiskit puts qubit 0 on the "
            "right of a bit string, Cirq and PennyLane put wire 0 on the left, so printed "
            "results look reversed between them. This platform normalises to the Qiskit order.",
            {"page": "Lessons", "lesson": "l13"}),
    Article(["no-cloning", "clone", "copy"], "No-cloning",
            "There is no unitary that copies an arbitrary unknown state — linearity forbids it. "
            "You can copy computational basis states with a CNOT, but apply the same CNOT to a "
            "superposition and you get entanglement, not a copy. This is what makes quantum key "
            "distribution secure."),
    Article(["universal", "gate set"], "Universal gate sets",
            "Any unitary can be built from CNOT plus arbitrary single-qubit gates. For "
            "fault-tolerant hardware the practical set is usually Clifford+T (H, S, CNOT, T), "
            "where T is the expensive one to implement."),

    # ---- concepts the lesson rail asks about -----------------------------
    Article(["amplitude", "squared magnitude", "2^n amplitudes", "why 2"], "Amplitudes",
            "An amplitude is one of the complex numbers in front of a basis state: in "
            "a|0> + b|1>, a and b are the amplitudes. They are not probabilities — you get a "
            "probability by squaring the magnitude, |a|^2. That extra structure is the whole "
            "story: probabilities are never negative, but amplitudes can be negative or "
            "complex, so two of them can cancel. That cancellation is interference, and "
            "interference is where every quantum speedup comes from. With n qubits you carry "
            "2^n amplitudes, not n, which is why classical simulation gets expensive fast.",
            {"page": "Lessons", "lesson": "l1"}),
    Article(["normalis", "normaliz", "add up to 1", "sum to one"], "Normalisation",
            "The squared magnitudes of all amplitudes must add to exactly 1, because the "
            "qubit has to be found in *some* state when you measure it. |a|^2+|b|^2=1 is that "
            "rule for one qubit. Every quantum gate is unitary precisely so that it preserves "
            "this — apply any sequence of gates and the total is still 1.",
            {"page": "Lessons", "lesson": "l1"}),
    Article(["born rule", "probability of measuring", "how likely"], "The Born rule",
            "The Born rule is the bridge from the maths to what you actually see: the "
            "probability of measuring outcome k is the squared magnitude of k's amplitude. "
            "It is also why you cannot read a quantum state out — measurement hands you one "
            "outcome, not the amplitudes that produced it. Run many shots and the histogram "
            "approaches those probabilities, which is exactly what the Studio shows you.",
            {"page": "Lessons", "lesson": "l3"}),
    Article(["tensor product", "kron", "|01", "basis state", "combine qubits"],
            "The tensor product",
            "Two qubits are not two separate states side by side — they are combined with a "
            "tensor product, giving four basis states |00>, |01>, |10>, |11> and four "
            "amplitudes. Read |01> right to left in this platform (Qiskit order): qubit 0 is "
            "1 and qubit 1 is 0. n qubits give 2^n basis states, which is the exponential that "
            "makes quantum systems hard to simulate and useful to compute with.",
            {"page": "Lessons", "lesson": "l6"}),
    Article(["unitary", "reversib", "irreversib", "quantum and", "and gate"],
            "Unitary and reversible",
            "Every quantum gate is unitary, which means it preserves total probability and can "
            "always be undone — run the inverse and you are back where you started. Classical "
            "AND throws information away (output 0 tells you nothing about which input was 0), "
            "so there is no direct quantum AND. Irreversible classical logic has to be embedded "
            "reversibly instead, usually with a Toffoli gate and an extra ancilla qubit. "
            "Measurement is the one irreversible step in the whole model.",
            {"page": "Lessons", "lesson": "l4"}),
    Article(["global phase", "relative phase", "overall phase"], "Global vs relative phase",
            "Multiplying an entire state by a phase factor changes nothing you can ever "
            "observe — |psi> and e^(i*t)|psi> are the same physical state. Relative phase, the "
            "difference between amplitudes, is completely different: it decides how they "
            "interfere and it is measurable. This is why this platform grades challenges on "
            "fidelity, |<a|b>|^2, rather than comparing state vectors number by number — two "
            "correct answers can differ by a global phase.",
            {"page": "Lessons", "lesson": "l5"}),
    Article(["deutsch", "jozsa", "oracle", "one query"], "Oracles and Deutsch-Jozsa",
            "An oracle is a black-box function wired in as a reversible circuit — you are "
            "allowed to call it, not to look inside. Deutsch-Jozsa was the first proof that a "
            "quantum computer can beat a classical one: decide whether the oracle is constant "
            "or balanced in a single query, where a classical worst case needs exponentially "
            "many. The trick is phase kickback — the answer is written into the phase of the "
            "control register, then interference turns it into a bit you can read.",
            {"page": "Lessons", "lesson": "l9"}),
    Article(["t1", "t2", "coherence time", "dephasing", "relaxation"], "T1 and T2",
            "T1 is relaxation — a qubit in |1> decaying to |0> by losing energy to its "
            "surroundings. T2 is dephasing — the relative phase between amplitudes randomising. "
            "T2 is usually the tighter limit, and it is the damaging one, because phase is "
            "exactly what interference depends on. Both set a hard budget: your circuit has to "
            "finish before they run out, which is why circuit depth matters more than qubit "
            "count on real machines.",
            {"page": "Lessons", "lesson": "l12"}),
    Article(["fidelity", "how is grading", "marked correct", "graded"], "Fidelity grading",
            "Fidelity, |<a|b>|^2, measures how close two quantum states are: 1 is identical, 0 "
            "is perfectly distinguishable. Challenges here are graded on fidelity against the "
            "target state rather than on matching output text, for two reasons. A correct "
            "circuit built a different way still counts as correct, because global phase is "
            "unobservable. And an answer that merely produced the right-looking numbers by "
            "accident does not pass, because the underlying state is wrong."),
]


# --------------------------------------------------------------------------
# algorithm library — the long explanations
#
# C.LIBRARY holds each algorithm's circuit and a one-line blurb.  The deep dive
# lives here instead, next to the rest of the teaching copy, so the circuit
# definitions stay free of prose.  Keys are the Algorithm ids.
#
# Every entry follows the same shape, because learners get more out of a fixed
# structure than a well-turned essay: what it does, how it works, a worked
# example with real numbers, and why it matters.
# --------------------------------------------------------------------------

@dataclass
class AlgoDetail:
    what: str
    how: List[str]
    example: str
    why: str


ALGO_DETAIL: Dict[str, AlgoDetail] = {

    "bell": AlgoDetail(
        what="Makes the simplest entangled pair. Two qubits that are each completely "
             "random on their own, yet always agree when you measure them.",
        how=["Start with both qubits at |00⟩ — both definitely 0.",
             "Hadamard on qubit 0 puts it in an even superposition, so the pair is now "
             "half |00⟩ and half |10⟩.",
             "CNOT flips qubit 1 only in the branch where qubit 0 is 1. The |10⟩ branch "
             "becomes |11⟩; the |00⟩ branch is untouched.",
             "You are left with half |00⟩ and half |11⟩ — and crucially, no |01⟩ or |10⟩."],
        example="Run it 1,000 times and you get roughly 500 readings of 00 and 500 of 11 — "
                "never 01, never 10. Look at qubit 0 alone and it is a fair coin. Look at "
                "qubit 1 alone and it is a fair coin. But the two coins always land the "
                "same way up.\n\n"
                "The tempting explanation is that they were secretly set to 0 or 1 all "
                "along. They were not, and that is testable: entangled pairs break a "
                "limit called Bell's inequality, and pre-set values never can.",
        why="This is the building block for teleportation, superdense coding and "
            "quantum key distribution. If you understand this circuit you understand "
            "the core of most two-qubit protocols."),

    "ghz": AlgoDetail(
        what="The three-qubit version of a Bell state: all three qubits agree, every time.",
        how=["Hadamard on qubit 0 creates the superposition.",
             "CNOT from qubit 0 to qubit 1 links the second qubit to the first.",
             "CNOT from qubit 1 to qubit 2 extends the chain to the third.",
             "The result is half |000⟩ and half |111⟩ — nothing else."],
        example="1,000 shots gives about 500 readings of 000 and 500 of 111. None of the "
                "other six combinations ever appear.\n\n"
                "GHZ states are brittle in a specific way: measuring ANY single qubit "
                "collapses all three at once. Lose one qubit to noise and the whole "
                "state is gone — which is exactly why it is the standard stress test "
                "for real hardware. Run it on the noisy backend and watch the other six "
                "outcomes creep in.",
        why="The usual benchmark for how good a real machine is. The height of the "
            "unwanted bars tells you how much your hardware is lying to you."),

    "wstate": AlgoDetail(
        what="Entangles three qubits so that exactly one of them is 1 — but which one "
             "is undecided until you measure.",
        how=["Rotate qubit 0 by a carefully chosen angle so it is 1 with probability 1/3.",
             "Use controlled rotations to spread the remaining 2/3 across the other two "
             "qubits.",
             "The state ends up an even mix of |100⟩, |010⟩ and |001⟩."],
        example="1,000 shots gives roughly 333 each of 100, 010 and 001. You never see "
                "000, and you never see two qubits high at once.\n\n"
                "The contrast with GHZ is the point. Measure one qubit of a GHZ state "
                "and the entanglement is destroyed entirely. Measure one qubit of a W "
                "state and — if you read 0 — the other two are STILL entangled. W states "
                "survive losing a qubit; GHZ states do not.",
        why="Where you need entanglement that degrades gracefully rather than "
            "collapsing. Comes up in quantum networking and leader-election protocols."),

    "kickback": AlgoDetail(
        what="The trick at the heart of almost every quantum algorithm: make a "
             "controlled operation write its answer into the CONTROL qubit's phase "
             "instead of into the target.",
        how=["Put the control qubit in superposition with a Hadamard.",
             "Put the target qubit into the state |−⟩ = (|0⟩−|1⟩)/√2, using X then H.",
             "Apply CNOT. Flipping |−⟩ turns it into −|−⟩ — the same state with a minus "
             "sign out front.",
             "That minus sign has nowhere to live except on the control branch that "
             "triggered it. The target comes out unchanged; the control has been marked.",
             "A final Hadamard on the control turns that invisible mark into a "
             "guaranteed measurement outcome."],
        example="Before the CNOT the control is |+⟩ — a 50/50 coin. Afterwards it is "
                "|−⟩ — still a 50/50 coin if you measure it directly. Nothing looks "
                "different.\n\n"
                "But apply H to each: |+⟩ becomes a certain 0, |−⟩ becomes a certain 1. "
                "The target qubit never changed, yet the control now reports what the "
                "operation did. That is kickback.",
        why="Deutsch–Jozsa, Bernstein–Vazirani, Grover and Shor are all kickback plus "
            "bookkeeping. Learn this one circuit properly and the famous algorithms "
            "stop looking like magic."),

    "dj": AlgoDetail(
        what="Decides whether a hidden function is constant (always the same answer) or "
             "balanced (0 half the time, 1 the other half) — using exactly one query.",
        how=["Put every input qubit into superposition with Hadamards.",
             "Put the output qubit in |−⟩ so the function's answer comes back as a phase.",
             "Run the hidden function once. Every input is queried in the same breath, "
             "and each one stamps a phase onto its own branch.",
             "Hadamard the input qubits again. This folds all those phases together.",
             "Measure. All zeros means constant; anything else means balanced."],
        example="Take a 3-bit function, so 8 possible inputs.\n\n"
                "**Classically:** in the worst case you must test 5 inputs. Four matching "
                "answers still leaves both options open — the fifth is what settles it. "
                "In general that is 2ⁿ⁻¹ + 1 queries.\n\n"
                "**Quantum:** 1 query, always. Not 'on average' — always.\n\n"
                "If the function is constant, every branch picks up the same phase, so "
                "they all add up on the all-zeros outcome and cancel everywhere else. If "
                "it is balanced, the phases split evenly and cancel ON the all-zeros "
                "outcome. So reading 000 means constant, and any other reading means "
                "balanced.",
        why="The first clean proof that quantum beats classical for a defined task. The "
            "problem itself is useless — nobody needs this function — but the proof "
            "mattered, and the technique is reused everywhere."),

    "bv": AlgoDetail(
        what="Finds a hidden binary string in one query, where a classical computer needs "
             "one query per bit.",
        how=["A hidden string s is buried inside a function that returns the bitwise dot "
             "product of your input with s.",
             "Hadamard every input qubit; put the output qubit in |−⟩.",
             "One call to the function stamps a phase pattern that encodes s.",
             "Hadamard the inputs again — the pattern unfolds directly into the bits of s.",
             "Measure. The bit string you read IS s."],
        example="Suppose the hidden string is **1011** (4 bits).\n\n"
                "**Classically:** query with 1000 to learn bit 1, then 0100, then 0010, "
                "then 0001. Four queries for four bits. n bits, n queries.\n\n"
                "**Quantum:** one query returns 1011 directly.\n\n"
                "With a 100-bit secret that is 100 queries versus 1.",
        why="The cleanest demonstration of the speedup mechanism, because the answer "
            "appears literally as the measured bits. Good for a demo — an audience can "
            "see the hidden string appear."),

    "grover2": AlgoDetail(
        what="Searches an unsorted list far faster than checking items one by one. This "
             "version searches 4 items and finds the one marked |11⟩.",
        how=["Hadamards put all 4 possibilities at equal amplitude — each 25% likely.",
             "The **oracle** flips the sign of the marked item only. Probabilities are "
             "unchanged so far; the marking is invisible to a measurement.",
             "The **diffuser** reflects every amplitude about their average. The marked "
             "item, sitting below the average after its sign flip, is thrown far above it.",
             "Repeat oracle + diffuser the right number of times, then measure."],
        example="Start: all four items at amplitude 0.5, so 25% each.\n\n"
                "The oracle flips |11⟩ to −0.5. The average of (0.5, 0.5, 0.5, −0.5) is "
                "0.25. Reflecting each value about 0.25 sends the three unmarked items to "
                "0 and the marked one to 1.0.\n\n"
                "Result: **|11⟩ with 100% probability after a single iteration.** With "
                "4 items one iteration is exactly right.\n\n"
                "Classically you would check items one at a time: 2.5 looks on average, "
                "4 in the worst case.",
        why="The most broadly useful quantum algorithm, because 'search an unstructured "
            "space' describes a huge class of real problems. The speedup is quadratic — "
            "√N instead of N — which is real but far more modest than Shor's."),

    "grover3": AlgoDetail(
        what="The same search over 8 items instead of 4, which is where the √N pattern "
             "becomes visible.",
        how=["Three Hadamards spread amplitude over all 8 possibilities, 12.5% each.",
             "The oracle marks the target by flipping its sign.",
             "The diffuser reflects about the average, pushing amplitude onto the target.",
             "**Two** iterations are needed here, not one — roughly (π/4)√8 ≈ 2.2."],
        example="After 1 iteration the target sits at about 78%. After 2 it reaches about "
                "94.5%. After 3 it FALLS back to roughly 33%.\n\n"
                "That last number is the lesson. Grover rotates the state by a fixed "
                "angle each round, so overshooting rotates you straight past the answer "
                "and back out again. More iterations is not better — there is a correct "
                "number, about (π/4)√N, and you must stop there.\n\n"
                "Classically, 8 items means 4 checks on average.",
        why="Shows both the speedup and its sharpest gotcha. If someone asks you at a "
            "demo what happens when you run Grover too long, this is the circuit to "
            "open."),

    "qft3": AlgoDetail(
        what="The quantum version of the Fourier transform: it converts a repeating "
             "pattern hidden in phases into a measurable peak.",
        how=["Hadamard the top qubit to expose its contribution.",
             "Apply controlled phase rotations of decreasing size, each one folding a "
             "lower qubit's information into the higher ones.",
             "Repeat down the register.",
             "Swap the qubit order at the end, because the construction leaves the bits "
             "reversed."],
        example="A classical Fast Fourier Transform on 2ⁿ samples costs about n·2ⁿ steps. "
                "The QFT does the same transform in about n² gates — for n = 20 that is "
                "roughly 400 gates versus about 20 million steps.\n\n"
                "The catch, and it is severe: you **cannot read out all the "
                "coefficients**. The transform happens across amplitudes you can never "
                "fully see. It is only useful when you need ONE thing from the "
                "spectrum — such as a period.",
        why="The engine inside Shor's factoring algorithm and inside phase estimation. "
            "Shor works by turning factoring into a period-finding problem and then "
            "using an inverse QFT to read that period off."),

    "teleport": AlgoDetail(
        what="Moves an unknown quantum state from one qubit to another without the qubit "
             "itself travelling. Nothing goes faster than light.",
        how=["Alice and Bob share an entangled Bell pair, prepared in advance.",
             "Alice has a third qubit holding the unknown state she wants to send.",
             "She performs a joint measurement on her two qubits, which destroys the "
             "original state and yields two ordinary classical bits.",
             "She sends those two bits to Bob — by phone, internet, anything normal.",
             "Depending on which of the four results arrived, Bob applies I, X, Z or ZX "
             "to his half of the pair. It is now in the original state."],
        example="Alice wants to send a state she cannot measure and cannot copy — she "
                "does not even know what it is.\n\n"
                "Her measurement gives 00, 01, 10 or 11, each a quarter of the time. "
                "Those two bits look completely random and carry no information about "
                "the state on their own.\n\n"
                "**Without them Bob has nothing** — his qubit is entirely random until "
                "he learns which correction to apply. That is the reason this cannot "
                "beat light speed: the classical message is mandatory and travels "
                "normally.\n\n"
                "Note also that Alice's original is destroyed. This moves a state; it "
                "never copies one, which is exactly what no-cloning demands.",
        why="The foundation of quantum networking and quantum repeaters. It is also the "
            "clearest counter to the 'spooky faster-than-light signalling' "
            "misunderstanding, which makes it a useful thing to be able to explain."),

    "superdense": AlgoDetail(
        what="Sends two classical bits by physically transmitting only one qubit — the "
             "mirror image of teleportation.",
        how=["Alice and Bob share a Bell pair in advance.",
             "Alice encodes the two bits she wants to send by applying one of four "
             "operations to her half alone: I for 00, X for 01, Z for 10, ZX for 11.",
             "She sends that single qubit to Bob.",
             "Bob undoes the Bell circuit on both qubits and measures, recovering both "
             "bits exactly."],
        example="Alice wants to send **10**. She applies Z to her qubit and posts it. "
                "Bob applies CNOT then H across the pair, measures, and reads 10 with "
                "certainty.\n\n"
                "One qubit in transit, two bits delivered. The accounting is honest "
                "though: the entangled pair had to be distributed beforehand, which "
                "means a qubit already travelled. What superdense coding buys you is "
                "the ability to do that expensive step in advance, when bandwidth is "
                "cheap, and then send at double rate when it matters.",
        why="Proves entanglement is a genuine resource you can spend, not just a "
            "curiosity. Pairs naturally with teleportation — they are the same "
            "machinery run in opposite directions."),

    "coin": AlgoDetail(
        what="The smallest useful quantum circuit: one Hadamard and one measurement, "
             "giving a genuinely unpredictable bit.",
        how=["Start at |0⟩.",
             "Apply H to reach an even superposition of |0⟩ and |1⟩.",
             "Measure. You get 0 or 1 with exactly equal probability."],
        example="Run it 1,000 times and you get close to 500 each way, drifting a little "
                "run to run exactly as a fair coin does.\n\n"
                "The difference from software randomness is worth being precise about. "
                "A normal random number generator runs a formula from a seed — anyone "
                "who learns the seed can reproduce every number it will ever produce. "
                "This bit is not computed from anything. There is no seed, and no "
                "shorter description of the output than the output itself.\n\n"
                "Try it on the noisy backend too: a biased split, say 508/492, shows you "
                "readout error on real hardware.",
        why="The first circuit worth running, and a real product — certified quantum "
            "random number generators are sold today for cryptographic key "
            "generation. Also the simplest honest answer to 'what can this actually "
            "do right now?'"),
}
