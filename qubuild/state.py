"""Learner progress: XP, lesson and challenge completion, quiz history.

Stored as a JSON file next to the app. In a deployed installation this is the
seam where you would swap in a learner-record service — everything else in the
platform only touches the dictionary this module hands back.
"""

from __future__ import annotations

import json
import math
import os
import time
from typing import Dict, List

from . import content as CT

PROGRESS_PATH = os.environ.get(
    "QUBUILD_PROGRESS",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "progress.json"))


def blank() -> dict:
    return {"xp": 0, "lessons": {}, "quiz": {}, "mastered": {}, "challenges": {},
            "runs": 0, "days": []}


def load() -> dict:
    data = blank()
    try:
        with open(PROGRESS_PATH, "r", encoding="utf-8") as fh:
            data.update(json.load(fh))
    except (OSError, ValueError):
        pass
    today = time.strftime("%Y-%m-%d")
    if today not in data["days"]:
        data["days"].append(today)
    return data


def save(data: dict) -> bool:
    try:
        with open(PROGRESS_PATH, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=1)
        return True
    except OSError:
        return False


def reset() -> dict:
    try:
        os.remove(PROGRESS_PATH)
    except OSError:
        pass
    return load()


def add_xp(data: dict, amount: int) -> None:
    data["xp"] = int(data.get("xp", 0)) + int(amount)
    save(data)


def level(xp: int) -> int:
    return int(math.sqrt(max(0, xp) / 60)) + 1


def level_floor(lvl: int) -> int:
    return int(round(60 * (lvl - 1) ** 2))


def mastery(data: dict) -> List[dict]:
    rows = []
    for track in CT.TRACKS:
        lessons = [l for l in CT.LESSONS if l.track == track.id]
        done = sum(1 for l in lessons if l.id in data["lessons"])
        rows.append({"name": track.name, "value": done / len(lessons) if lessons else 0.0,
                     "detail": "%d/%d lessons" % (done, len(lessons))})
    quiz = list(data["quiz"].values())
    right = sum(1 for q in quiz if q["correct"])
    rows.append({"name": "Assessment",
                 "value": right / len(quiz) if quiz else 0.0,
                 "detail": ("%d/%d correct" % (right, len(quiz))) if quiz else "no attempts yet"})
    solved = len(data["challenges"])
    rows.append({"name": "Circuit building", "value": solved / len(CT.CHALLENGES),
                 "detail": "%d/%d challenges" % (solved, len(CT.CHALLENGES))})
    return rows


def record_quiz(data: dict, key: str, correct: bool, topic: str, xp: int = 12) -> bool:
    """Returns True if this was the first attempt (and therefore scored)."""
    if key in data["quiz"]:
        return False
    data["quiz"][key] = {"correct": bool(correct), "topic": topic, "ts": time.time()}
    if correct:
        data["xp"] = int(data.get("xp", 0)) + xp
    save(data)
    return True


def record_mastery(data: dict, key: str) -> bool:
    """Mark a lesson question as eventually answered correctly.

    Kept apart from record_quiz on purpose.  record_quiz stores the FIRST
    attempt and feeds the accuracy figures on Assessment and My progress; if
    retries wrote into it, a learner could grind those numbers up to 100%.
    Mastery is what gates progress through a lesson, and retries are welcome
    there.  Returns True the first time a key is mastered.
    """
    book = data.setdefault("mastered", {})
    if book.get(key):
        return False
    book[key] = True
    save(data)
    return True


def lesson_mastered(data: dict, lesson_id: str, total: int) -> bool:
    """True when every question in a lesson has been answered correctly."""
    if total <= 0:
        return True
    book = data.get("mastered", {})
    return all(book.get("lesson:%s:%d" % (lesson_id, i)) for i in range(total))


# --------------------------------------------------------------------------
# demonstration cohort for the instructor view
# --------------------------------------------------------------------------

NAMES = ["A. Menon", "R. Iyer", "S. Kaur", "D. Bose", "M. Fernandes", "K. Rao",
         "T. Nakamura", "L. Okafor", "P. Sharma", "J. Alvarez", "H. Chen", "N. Gupta",
         "F. Haddad", "V. Reddy", "E. Novak", "B. Adeyemi", "C. Mwangi",
         "O. Lindqvist", "Y. Tanaka", "Z. Ahmed", "G. Rossi", "I. Petrov",
         "W. Dube", "Q. Lin"]


def _seeded(seed: int):
    state = {"s": seed}

    def rnd() -> float:
        state["s"] = (state["s"] * 1103515245 + 12345) & 0x7FFFFFFF
        return state["s"] / 0x7FFFFFFF
    return rnd


def cohort() -> List[dict]:
    """Synthetic but deterministic — clearly labelled as such in the UI."""
    rnd = _seeded(20260829)
    rows = []
    for name in NAMES:
        engagement = 0.25 + rnd() * 0.75
        lessons = int(round(engagement * len(CT.LESSONS)))
        accuracy = max(0.25, min(0.98, engagement * 0.7 + rnd() * 0.35))
        solved = min(len(CT.CHALLENGES),
                     int(round(engagement * len(CT.CHALLENGES) * (0.5 + rnd() * 0.6))))
        rows.append({"name": name, "lessons": lessons, "accuracy": accuracy,
                     "challenges": solved, "days_since_active": int(rnd() * 11),
                     "xp": int(lessons * 30 + accuracy * 180 + solved * 70)})
    rows.sort(key=lambda r: -r["xp"])
    return rows


def miss_rates() -> List[dict]:
    rnd = _seeded(77)
    rows = [{"question": q.prompt, "topic": q.topic, "miss_rate": 0.12 + rnd() * 0.55}
            for q in CT.QUIZ_BANK]
    rows.sort(key=lambda r: -r["miss_rate"])
    return rows
