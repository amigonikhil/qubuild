"""QuBuild — an AI-assisted platform for learning quantum computing.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import inspect
import io
import html
import json
import math
import os
import random
import re
import sys

import importlib
import numpy as np
import streamlit as st

from qubuild import accounts as AC
from qubuild import circuits as C
from qubuild import hardware as HW
from qubuild import lms as LMS
from qubuild import config as CFG
from qubuild import collab as CO
from qubuild import content as CT
from qubuild import db as DBX
from qubuild import deliverables as DL
from qubuild import qbraid_provider as QBR
from qubuild import dragdrop as DND
from qubuild import engine as E
from qubuild import state as ST
from qubuild import notify as NT
from qubuild import tutor as T


class _Deferred:
    """A module that is not imported until something actually asks for it.

    Matplotlib and the SDK probe together account for most of the time between
    pressing run and seeing the sign-in screen, and the sign-in screen draws no
    charts and executes no circuits.  Loading them at the moment of first use
    moves that cost off the opening of the app, where it is waited on, and into
    the first page that needs it, where something is already rendering.
    """

    def __init__(self, name: str):
        object.__setattr__(self, "_name", name)
        object.__setattr__(self, "_module", None)

    def _load(self):
        module = object.__getattribute__(self, "_module")
        if module is None:
            module = importlib.import_module(object.__getattribute__(self, "_name"))
            object.__setattr__(self, "_module", module)
        return module

    def __getattr__(self, item):
        return getattr(self._load(), item)

    def __setattr__(self, item, value):
        setattr(self._load(), item, value)


viz = _Deferred("qubuild.viz")
BK = _Deferred("qubuild.backends")


def _silence_proactor_reset():
    """Stop Windows logging a traceback every time a browser tab goes away.

    On Windows asyncio uses the proactor event loop.  When a Streamlit tab is
    closed or reloaded the socket is reset, and _call_connection_lost re-raises
    the ConnectionResetError after the transport is already gone, so it surfaces
    as an unhandled-callback traceback.  Nothing in the app has failed, but a red
    traceback in the terminal during a demo reads like something did.
    """
    if sys.platform != "win32":
        return
    try:
        from asyncio.proactor_events import _ProactorBasePipeTransport
    except ImportError:
        return

    original = _ProactorBasePipeTransport._call_connection_lost
    if getattr(original, "_qubuild_quiet", False):
        return

    def quiet(self, exc):
        try:
            original(self, exc)
        except (ConnectionResetError, ConnectionAbortedError):
            pass

    quiet._qubuild_quiet = True
    _ProactorBasePipeTransport._call_connection_lost = quiet


_silence_proactor_reset()

# ==========================================================================
#  ####################################################################
#  ##                                                                ##
#  ##                  PASTE YOUR API KEY HERE                       ##
#  ##                                                                ##
#  ####################################################################
#
#  Fill in the two lines below, save this file, and restart the app.
#  That is the whole setup.  Example:
#
#       API_PROVIDER = "anthropic"
#       API_KEY      = "sk-ant-api03-xxxxxxxxxxxxxxxxxxxx"
#
#  API_PROVIDER can be:
#
#     "none"        no key, no internet — the built-in tutor answers  (default)
#     "anthropic"   Claude          key from  console.anthropic.com
#     "openai"      ChatGPT         key from  platform.openai.com
#     "gemini"      Google Gemini   key from  aistudio.google.com     (free tier)
#     "groq"        fast Llama      key from  console.groq.com        (free tier)
#     "openrouter"  many models     key from  openrouter.ai
#     "ollama"      a model on your own PC — no key needed
#
#  Leave API_MODEL as "" and a sensible default is chosen for you.
#
#  WARNING: a key typed here is plain text in this file.  On a deployed
#  copy leave it empty and set QUBUILD_PROVIDER and QUBUILD_API_KEY as
#  secrets instead — the block below picks them up automatically.
# ==========================================================================

API_PROVIDER = "none"

API_KEY = ""

API_MODEL = ""

# ==========================================================================
#  Nothing below this line needs editing.
# ==========================================================================

# --------------------------------------------------------------------------
# secrets, for a deployed copy
#
# A key belongs in source on a laptop and nowhere near it on a public host.
# Streamlit hands hosted secrets to the app as st.secrets; copying the ones we
# recognise into the environment lets qubuild/config.py pick them up through
# the path it already has, so a deployed copy and a local one read the same
# code.  Nothing here fails if there are no secrets — that is the normal case.
for _name in ("QUBUILD_PROVIDER", "QUBUILD_API_KEY", "QUBUILD_MODEL",
              "QUBUILD_DB_URL", "QUBUILD_DB"):
    try:
        if _name in st.secrets and not os.environ.get(_name):
            os.environ[_name] = str(st.secrets[_name])
    except Exception:                                              # noqa: BLE001
        break          # no secrets file at all, which is the usual local case

# Hand the three settings above to the tutor.  They override qubuild/config.py,
# which is still there if you would rather keep the key out of this file.
if API_PROVIDER and API_PROVIDER != "none":
    CFG.PROVIDER, CFG.API_KEY, CFG.MODEL = API_PROVIDER, API_KEY, API_MODEL
else:
    # Nothing set here — fall back to whatever was saved from the sidebar, so a
    # key never has to be pasted into source to get the tutor working.
    CFG.apply_saved()

PI = math.pi

PAGES = ["Overview", "Lessons", "Algorithm library", "Circuit Studio",
         "Challenges", "Assessment", "My progress", "Notifications",
         "Instructor view", "Deliverables"]

#: Pages only an instructor is offered. A learner or a student never sees the
#: entry in the sidebar, never sees the card on the Overview, and is turned
#: away if the page is reached some other way.
INSTRUCTOR_ONLY = {"Instructor view"}


#: What the sign-up screen offers, and the caption under each choice.
ROLE_CHOICES = {
    "Learner": ("learner", "on my own"),
    "Student": ("student", "I have a classroom code"),
    "Instructor": ("instructor", "I teach a class"),
}


def teaching() -> bool:
    user = SS.get("user")
    return user is not None and getattr(user, "is_instructor", False)


def visible_pages() -> list:
    return [p for p in PAGES if p not in INSTRUCTOR_ONLY or teaching()]

SUBTITLE = {
    "Overview": "Learn, build, simulate and visualise quantum circuits",
    "Deliverables": "Every objective in the problem statement, and where it is met",
    "Lessons": "Structured tracks from a single qubit to Shor",
    "Algorithm library": "Load a canonical circuit and take it apart",
    "Circuit Studio": "Build a circuit, or paste code from any of four SDKs",
    "Challenges": "Auto-graded circuit-building problems",
    "Assessment": "Question bank with instant explanations",
    "My progress": "Mastery, history and what to do next",
    "Instructor view": "Cohort analytics and misconception tracking",
    "Notifications": "What changed since you were last here",
}

st.set_page_config(page_title="QuBuild", page_icon="⚛", layout="wide",
                   initial_sidebar_state="expanded")

CSS = """
<style>
  :root { --qf-line:#28334680; }
  .stApp { background:#070910; }
  section[data-testid="stSidebar"] { background:#0C1017; border-right:1px solid #1C2434; }
  h1,h2,h3,h4 { letter-spacing:-.01em; }
  .qf-title { font-size:1.55rem; font-weight:700; margin:0; }
  .qf-sub { color:#5F6D83; font-size:.86rem; margin:.1rem 0 1.1rem; }
  .qf-eyebrow { font-family:ui-monospace,monospace; font-size:.66rem; letter-spacing:.14em;
                text-transform:uppercase; color:#5F6D83; }
  .qf-card { background:#0C1017; border:1px solid #1C2434; border-radius:7px;
             padding:.85rem 1rem; margin-bottom:.55rem; }
  .qf-card h4 { margin:.1rem 0 .25rem; font-size:1rem; }
  .qf-card p { margin:0; color:#95A3BA; font-size:.82rem; line-height:1.5; }
  .qf-chip { display:inline-block; font-family:ui-monospace,monospace; font-size:.68rem;
             padding:2px 9px; border-radius:20px; border:1px solid #334158; color:#95A3BA;
             margin-right:.3rem; white-space:nowrap; }
  .qf-chip.on   { border-color:#4C8DFF; color:#4C8DFF; background:#0F1B33; }
  .qf-chip.good { border-color:#2A5E45; color:#3DD68C; background:#0F2119; }
  .qf-chip.warn { border-color:#5C4A22; color:#F2C14E; background:#211B0F; }
  .qf-chip.crit { border-color:#5E2A2A; color:#FF6F6F; background:#210F0F; }
  .qf-issue { border-left:2px solid #5F6D83; padding:.15rem 0 .15rem .7rem; margin:.5rem 0; }
  .qf-issue.error{border-color:#FF6F6F} .qf-issue.warn{border-color:#F2C14E}
  .qf-issue.good{border-color:#3DD68C} .qf-issue.info{border-color:#4C8DFF}
  .qf-issue b { font-size:.85rem; } .qf-issue p { margin:.15rem 0 0; color:#95A3BA; font-size:.8rem; }

  .qf-hero { background:radial-gradient(120% 140% at 85% 15%, rgba(76,141,255,.12), transparent 62%), #0C1017;
             border:1px solid #1C2434; border-radius:9px; padding:1.4rem 1.5rem; margin-bottom:1.2rem; }
  .qf-hero h2 { font-size:1.9rem; line-height:1.15; margin:.3rem 0 .5rem; }
  .qf-hero p { color:#95A3BA; max-width:62ch; margin:0; }
  .qf-formula { font-family:ui-monospace,monospace; }
  div[data-testid="stMetricValue"] { font-size:1.5rem; }
  .stButton>button { border-radius:6px; border:1px solid #334158; background:#121826; }
  .stButton>button:hover { border-color:#4C8DFF; color:#4C8DFF; }
  code { color:#39DCDC !important; }
  .qf-table { width:100%; border-collapse:collapse; margin:.2rem 0 .4rem;
              font-size:.82rem; table-layout:fixed; }
  .qf-table th { text-align:left; font-family:ui-monospace,monospace; font-size:.66rem;
                 letter-spacing:.12em; text-transform:uppercase; color:#5F6D83;
                 border-bottom:1px solid #1C2434; padding:.45rem .7rem .35rem 0; }
  .qf-table td { color:#95A3BA; line-height:1.5; vertical-align:top;
                 border-bottom:1px solid #131A26; padding:.5rem .7rem .5rem 0; }
  .qf-table td:first-child { color:#D6DEEA; }
  hr { border-color:#1C2434 !important; }

  /* ---- docked AI tutor rail ------------------------------------------- */
  .qf-rail-head { display:flex; align-items:center; gap:.5rem; margin:0 0 .1rem; }
  .qf-rail-head .dot { width:7px; height:7px; border-radius:50%; background:#3DD68C; flex:none; }
  .qf-rail-head .dot.off { background:#5F6D83; }
  .qf-rail-head b { font-size:.95rem; }
  .qf-seeing { font-size:.72rem; color:#5F6D83; line-height:1.45; margin:.25rem 0 .1rem;
               border-left:2px solid #1C2434; padding-left:.55rem; }
  .st-key-qf_rail [data-testid="stChatMessage"] { background:transparent; padding:.35rem 0; }
  .st-key-qf_rail .stButton>button { font-size:.76rem; padding:.22rem .55rem; text-align:left; }
  .st-key-qf_rail p, .st-key-qf_rail li { font-size:.83rem; line-height:1.55; }
  .st-key-qf_rail h1, .st-key-qf_rail h2, .st-key-qf_rail h3 { font-size:1rem; }
  .st-key-qf_rail code { font-size:.76rem; }
  .st-key-qf_rail [data-testid="stVerticalBlock"] { gap:.35rem; }

  /* ====================================================================
     INSTRUMENT THEME
     The look is a bench instrument in a dark lab: IBM Plex (the typeface
     IBM Quantum itself uses), a cyan signal accent against deep navy, a
     faint wire grid behind everything, and a soft glow on anything the
     learner is meant to act on.  Loaded from Google Fonts with a system
     stack behind it, so an offline demo degrades to plain text rather
     than to something broken.
     ================================================================= */
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

  :root {
    --qf-bg:#05070D; --qf-panel:#0A0F1A; --qf-panel-2:#0D1422;
    --qf-edge:#17203200; --qf-border:#1B2537;
    --qf-ink:#E6ECF7; --qf-dim:#8A99B4; --qf-faint:#55627A;
    --qf-cyan:#39DCDC; --qf-blue:#4C8DFF; --qf-violet:#B08CFF;
  }

  /* =================================================================
     TYPE SCALE.  Every size in this stylesheet is in rem, so this one
     number sets the size of the whole app — text, widgets, tables and
     buttons together, with the proportions of the design untouched.
     16px is the browser default; raise it for a projector, lower it to
     fit more on screen.
     ================================================================= */
  html { font-size:17px; }

  html, body, .stApp, [class*="css"] {
    font-family:'IBM Plex Sans',ui-sans-serif,system-ui,-apple-system,sans-serif;
  }
  body, .stApp, .block-container { font-size:1rem; }
  code, pre, .qf-eyebrow, .qf-chip, .qf-readout,
  [data-testid="stMetricValue"] {
    font-family:'IBM Plex Mono',ui-monospace,SFMono-Regular,Menlo,monospace;
  }

  .stApp { background:var(--qf-bg); color:var(--qf-ink); }

  /* the wire grid + a cold light source top-right */
  .stApp::before {
    content:""; position:fixed; inset:0; pointer-events:none; z-index:0;
    background:
      linear-gradient(var(--qf-border) 1px, transparent 1px) 0 0 / 100% 72px,
      linear-gradient(90deg, var(--qf-border) 1px, transparent 1px) 0 0 / 72px 100%,
      radial-gradient(900px 480px at 88% -10%, #39DCDC12, transparent 70%),
      radial-gradient(760px 520px at 8% 4%, #4C8DFF0E, transparent 68%);
    opacity:.28;
    mask-image:linear-gradient(180deg,#000 0%,#0008 45%,#0000 95%);
    -webkit-mask-image:linear-gradient(180deg,#000 0%,#0008 45%,#0000 95%);
  }
  .block-container { position:relative; z-index:1; }

  /* ---- headings ---- */
  h1,h2,h3,h4 { font-weight:600; letter-spacing:-.018em; color:var(--qf-ink); }
  .qf-title { font-size:1.45rem; font-weight:600; margin:0; letter-spacing:-.02em; }
  .qf-sub   { color:var(--qf-faint); font-size:.85rem; margin:.35rem 0 1.3rem; }
  .qf-eyebrow { font-size:.64rem; letter-spacing:.2em; text-transform:uppercase;
                color:var(--qf-cyan); font-weight:500; }
  .qf-trace { height:2px; margin:.5rem 0 0; border-radius:2px;
              background:linear-gradient(90deg,var(--qf-cyan) 0,var(--qf-blue) 60px,
                        var(--qf-border) 60px,var(--qf-border) 100%); }

  /* ---- sidebar ---- */
  section[data-testid="stSidebar"] {
    background:linear-gradient(180deg,#080C15 0%,#060910 100%);
    border-right:1px solid var(--qf-border);
  }
  section[data-testid="stSidebar"] [role="radiogroup"] label {
    border-radius:6px; padding:.24rem .5rem; margin:1px 0;
    border-left:2px solid transparent; transition:background .12s,border-color .12s;
  }
  section[data-testid="stSidebar"] [role="radiogroup"] label:hover {
    background:#0F1727; border-left-color:var(--qf-border);
  }
  section[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {
    background:linear-gradient(90deg,#0D2430,#0A1119 70%);
    border-left-color:var(--qf-cyan);
  }

  /* ---- panels ---- */
  .qf-card, [data-testid="stExpander"], div[data-testid="stForm"] {
    background:linear-gradient(180deg,var(--qf-panel-2),var(--qf-panel));
    border:1px solid var(--qf-border); border-radius:10px;
  }
  .qf-card { padding:.9rem 1.05rem; margin-bottom:.6rem; transition:border-color .15s; }
  .qf-card:hover { border-color:#26344C; }
  .qf-card h4 { margin:.1rem 0 .3rem; font-size:.98rem; }
  .qf-card p  { margin:0; color:var(--qf-dim); font-size:.82rem; line-height:1.55; }

  .qf-hero {
    background:
      radial-gradient(760px 300px at 82% -30%, #39DCDC1A, transparent 66%),
      linear-gradient(180deg,#0C1524,#080D17);
    border:1px solid var(--qf-border); border-radius:14px; padding:1.9rem 2rem;
  }
  .qf-hero h2 { font-size:1.72rem; line-height:1.3; margin:.7rem 0 .55rem;
                letter-spacing:-.022em; }
  .qf-hero-line { padding:1.5rem 1.8rem; }
  .qf-hero-line h2 { font-size:1.5rem; margin:.5rem 0 0; letter-spacing:-.018em; }
  .qf-hero p  { color:var(--qf-dim); font-size:.92rem; line-height:1.65; margin:0; max-width:62ch; }

  /* ---- controls ---- */
  .stButton>button, .stDownloadButton>button {
    border-radius:8px; border:1px solid var(--qf-border);
    background:linear-gradient(180deg,#111A2B,#0C1320); color:var(--qf-ink);
    font-weight:500; transition:border-color .14s, box-shadow .14s, transform .08s;
  }
  .stButton>button:hover, .stDownloadButton>button:hover {
    border-color:var(--qf-cyan); box-shadow:0 0 0 1px #39DCDC22, 0 6px 18px #39DCDC14;
  }
  .stButton>button:active { transform:translateY(1px); }
  .stButton>button[kind="primary"] {
    background:linear-gradient(180deg,#12707A,#0C4E57); border-color:#1E8D98; color:#EAFDFD;
  }
  [data-testid="stMetricValue"] { font-variant-numeric:tabular-nums; letter-spacing:-.01em; }
  [data-testid="stMetricLabel"] { color:var(--qf-faint); text-transform:uppercase;
                                  font-size:.66rem; letter-spacing:.14em; }
  .stProgress > div > div > div > div {
    background:linear-gradient(90deg,var(--qf-cyan),var(--qf-blue)); }

  .qf-chip { border-radius:5px; border-color:#27324A; }
  .qf-chip.on { border-color:var(--qf-cyan); color:var(--qf-cyan); background:#0B2229; }

  /* ---- lesson reading view ---- */
  .qf-read { max-width:74ch; }
  .qf-read p, .qf-read li { font-size:1rem; line-height:1.78; color:#CBD6E8; }
  .qf-read h2 { font-size:1.28rem; margin:2.1rem 0 .7rem;
                padding-left:.7rem; border-left:3px solid var(--qf-cyan); }
  .qf-read blockquote { border-left:3px solid var(--qf-violet); background:#120F1F;
                        border-radius:0 8px 8px 0; padding:.8rem 1rem; margin:1.3rem 0; }
  .qf-read table { border-collapse:collapse; font-size:.88rem; }
  .qf-read th { color:var(--qf-cyan); text-transform:uppercase; font-size:.66rem;
                letter-spacing:.12em; }

  .qf-crumb { display:flex; align-items:center; gap:.6rem; color:var(--qf-faint);
              font-size:.72rem; letter-spacing:.16em; text-transform:uppercase;
              margin-bottom:.2rem; }

  .qf-tile { display:block; background:linear-gradient(180deg,var(--qf-panel-2),var(--qf-panel));
             border:1px solid var(--qf-border); border-left:3px solid #27324A;
             border-radius:9px; padding:.75rem .9rem; }
  .qf-tile.done { border-left-color:#3DD68C; }
  .qf-tile.now  { border-left-color:var(--qf-cyan); }
  .qf-tile b { font-size:.9rem; font-weight:500; }
  .qf-tile span { display:block; color:var(--qf-faint); font-size:.72rem; margin-top:.15rem; }

  /* ---- readouts ---- */
  .qf-readout { font-variant-numeric:tabular-nums; letter-spacing:.02em; }
  .qf-gauge { display:flex; align-items:center; gap:.55rem; margin:.2rem 0 .4rem; }
  .qf-gauge .bar { flex:1; height:5px; border-radius:3px; background:#131C2C; overflow:hidden; }
  .qf-gauge .bar i { display:block; height:100%; border-radius:3px; }
  .qf-gauge .val { font-family:'IBM Plex Mono',monospace; font-size:.72rem;
                   font-variant-numeric:tabular-nums; color:var(--qf-dim);
                   min-width:3.8rem; text-align:right; }
  .qf-live { display:inline-block; width:6px; height:6px; border-radius:50%;
             background:var(--qf-cyan); margin-right:.45rem; vertical-align:middle;
             box-shadow:0 0 0 0 #39DCDC99; animation:qf-pulse 2.4s ease-out infinite; }
  @keyframes qf-pulse { 70%{box-shadow:0 0 0 8px #39DCDC00} 100%{box-shadow:0 0 0 0 #39DCDC00} }
  @media (prefers-reduced-motion: reduce) { .qf-live { animation:none; } }

  /* ---- sign-in ---- */
  /* the sidebar is narrow; a clipped install command is a useless one */
  section[data-testid="stSidebar"] pre,
  section[data-testid="stSidebar"] code {
    white-space:pre-wrap !important; word-break:break-all; font-size:.72rem; }
  section[data-testid="stSidebar"] [data-testid="stCode"] { overflow-x:hidden; }

  /* The expand control on a diagram was a trap.
     Streamlit's "Fullscreen" button does not use the browser Fullscreen API
     here — it swaps the image into an in-page overlay, and the app header
     (Deploy, the menu) sits on top of exactly where the exit control appears,
     so the picture opened and could not be closed. The diagrams are already
     rendered at 2.4x and sized to fit their column, so expanding them gains
     nothing; the button is removed rather than repositioned, because there is
     no reliable place to put it inside an overlay Streamlit owns.
     Scoped to frames containing an image: code blocks keep their copy button,
     which lives outside stFullScreenFrame entirely. */
  [data-testid="stFullScreenFrame"]:has(img) [data-testid="stElementToolbar"],
  [data-testid="stFullScreenFrame"]:has(img) button[aria-label="Fullscreen"],
  [data-testid="stImageContainer"] ~ [data-testid="stElementToolbar"],
  [data-testid="StyledFullScreenButton"] {
    display:none !important; }

  /* anything else that keeps a toolbar (code copy, dataframe tools) stays, and
     is just restyled to match */
  [data-testid="stBaseButton-elementToolbar"] {
    background:#0A0F1ACC !important; border:1px solid var(--qf-border) !important;
    color:var(--qf-ink) !important; border-radius:7px !important; }
  [data-testid="stBaseButton-elementToolbar"]:hover {
    border-color:var(--qf-cyan) !important; }

  .qf-gate { margin:6vh 0 1.4rem; }
  .qf-gate .mark { font-size:2.6rem; letter-spacing:-.035em; font-weight:600;
                   margin:.35rem 0 0; line-height:1; }
  .qf-gate .tag  { color:var(--qf-dim); font-size:.9rem; margin:.9rem 0 0;
                   line-height:1.65; }

  /* inputs: Streamlit's defaults are light, which fights everything else */
  [data-testid="stTextInputRootElement"],
  div[data-baseweb="select"] > div, div[data-baseweb="input"] {
    background:#0B1220 !important; border-color:var(--qf-border) !important; }
  [data-testid="stTextInputRootElement"]:focus-within {
    border-color:var(--qf-cyan) !important; box-shadow:0 0 0 1px #39DCDC33; }
  input, textarea { color:var(--qf-ink) !important; }

  /* Controls hold their own scale.  Reading text got bigger; the labels inside
     buttons and dropdowns did not, because those sit in fixed columns and a
     bigger label there just breaks mid-word or clips a number. */
  .stButton > button, .stDownloadButton > button,
  [data-testid="stFormSubmitButton"] button,
  .stButton > button *, .stDownloadButton > button *,
  [data-testid="stFormSubmitButton"] button * {
    font-size:.88rem !important; line-height:1.3 !important;
    word-break:keep-all !important; overflow-wrap:normal !important;
    hyphens:none !important; }
  div[data-baseweb="select"] *, [data-testid="stNumberInputContainer"] input,
  [data-baseweb="input"] input { font-size:.85rem !important; }
  section[data-testid="stSidebar"] { font-size:.95rem; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


@st.cache_resource(show_spinner=False)
def _warm_up():
    """Load the heavy modules in the background while the page is drawing.

    Deferring matplotlib and the SDK probe takes them off the path to the
    sign-in screen, but it would only move that wait to the first chart.  A
    daemon thread started here imports them during the seconds the person
    spends reading the sign-in screen and typing a password, so by the time a
    figure is wanted the module is already in memory.  Python's per-module
    import lock does the synchronising: if the main thread gets there first it
    simply waits, exactly as it would have anyway.
    """
    import threading

    def load():
        try:
            importlib.import_module("qubuild.viz")
            importlib.import_module("qubuild.backends")
        except Exception:                                          # noqa: BLE001
            pass          # a warm-up that fails must never break the app

    thread = threading.Thread(target=load, name="qubuild-warmup", daemon=True)
    thread.start()
    return thread


_warm_up()

RAIL_WIDTH = 23.0          # rem — the docked tutor column

RAIL_CSS = """
<style>
  @media (min-width:1250px) {
    [data-testid="stMainBlockContainer"], section.main > div.block-container {
        padding-right:%(pad)srem !important; max-width:none !important; }
    .st-key-qf_rail {
        position:fixed; top:3.1rem; right:0; bottom:0; width:%(w)srem;
        background:#0A0E16; border-left:1px solid #1C2434;
        padding:.85rem 1rem 2.5rem; overflow-y:auto; overflow-x:hidden; z-index:80; }
    .st-key-qf_railtab {
        position:fixed; top:5.2rem; right:.6rem; z-index:81; width:2.6rem; }
  }
  /* Narrow screens: the rail stops floating and simply sits under the page. */
  @media (max-width:1249px) {
    .st-key-qf_rail { border-top:1px solid #1C2434; padding-top:1rem; margin-top:1.5rem; }
  }
</style>
"""


# ==========================================================================
# session state
# ==========================================================================

def init_state():
    ss = st.session_state
    ss.setdefault("page", "Overview")
    ss.setdefault("progress", ST.load())
    ss.setdefault("circuit", C.BY_ID["bell"].make())
    ss.setdefault("undo", [])
    ss.setdefault("selected", None)
    ss.setdefault("backend", "numpy_sv")
    ss.setdefault("shots", 1024)
    ss.setdefault("seed", 7)
    ss.setdefault("lesson", CT.LESSONS[0].id)
    ss.setdefault("reading", False)
    ss.setdefault("wrong_answers", {})
    ss.setdefault("challenge", None)
    ss.setdefault("tutor_log", [])
    ss.setdefault("tutor_open", True)
    ss.setdefault("tutor_pending", None)
    ss.setdefault("code_buffer", None)
    ss.setdefault("quiz", None)
    ss.setdefault("grade", None)

    # Navigation requested on the previous run, applied here.  It cannot be
    # applied at the moment of the click: `page` is the sidebar radio's key, and
    # Streamlit forbids writing to a widget's key once that widget exists on the
    # current run.  init_state() runs before sidebar(), so this assignment is
    # always legal — see goto().
    if ss.get("pending_nav"):
        for key, value in ss.pop("pending_nav").items():
            ss[key] = value


init_state()
SS = st.session_state
PROGRESS = SS.progress


def goto(page: str, **kwargs):
    """Move to another page.

    The destination is parked in ``pending_nav`` rather than written straight to
    ``SS.page``.  ``page`` is the key of the sidebar's navigation radio, and
    Streamlit raises StreamlitAPIException if you assign to a widget's key after
    that widget has been created this run — which is always the case here, since
    the sidebar is drawn before any page body.  init_state() applies the parked
    values on the next run, before the radio exists."""
    if kwargs.get("lesson"):
        kwargs["reading"] = True
    SS.pending_nav = dict(kwargs, page=page)
    st.rerun()


def push_undo():
    SS.undo.append(json.dumps(SS.circuit.to_dict()))
    del SS.undo[:-30]


def set_circuit(circuit: C.Circuit, remember: bool = True):
    if remember:
        push_undo()
    SS.circuit = circuit
    SS.selected = None
    SS.code_buffer = None
    SS.grade = None


@st.cache_data(show_spinner=False, max_entries=64)
def execute(circuit_json: str, backend_id: str, shots: int, seed: int, chi: int = 0):
    circuit = C.Circuit.from_dict(json.loads(circuit_json))
    return BK.execute(circuit, backend_id, shots, seed=seed, chi=chi or None)


def current_result():
    return execute(json.dumps(SS.circuit.to_dict()), SS.backend, SS.shots, SS.seed,
                   SS.get("chi", 0))


def chips(items):
    st.markdown(" ".join('<span class="qf-chip %s">%s</span>' % (cls, text)
                         for text, cls in items), unsafe_allow_html=True)


def header(page: str):
    st.markdown('<p class="qf-title">%s</p><div class="qf-trace"></div>'
                '<p class="qf-sub">%s</p>'
                % (page, SUBTITLE[page]), unsafe_allow_html=True)


def gauge(label: str, value: float, colour: str = "#3DD68C", suffix: str = "") -> None:
    """A thin bench-meter bar. Used for anything the learner should watch drift."""
    pct = max(0.0, min(1.0, value)) * 100
    st.markdown(
        '<div class="qf-gauge"><span class="qf-eyebrow">%s</span>'
        '<span class="bar"><i style="width:%.1f%%;background:%s"></i></span>'
        '<span class="val">%s</span></div>'
        % (label, pct, colour, suffix or ("%.3f" % value)), unsafe_allow_html=True)


# The exact engine holds 2**n amplitudes, so the designer used to stop at 8.
# The MPS backend has no such wall, but the dense panels (amplitudes, phase
# wheel, Bloch spheres) still do — 20 qubits is a million amplitudes, which is
# the last width where those stay honest and responsive.
MAX_QUBITS = 20

# Streamlit renamed `use_container_width` to `width`; support both.
_HAS_WIDTH = "width" in inspect.signature(st.button).parameters
WIDE = {"width": "stretch"} if _HAS_WIDTH else {"use_container_width": True}


# Render at 2x and display at the 1x size: the browser then has enough pixels
# for a high-density screen and for the fullscreen view, instead of upscaling a
# 130-dpi bitmap into a blurry one.  It was 2.4x, which is 44% more pixels to
# rasterise for a difference no screen can show.
OVERSAMPLE = 2.0


def _to_png(fig):
    import matplotlib.pyplot as plt     # already loaded by the time a figure exists

    natural = int(fig.get_size_inches()[0] * fig.dpi)
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", facecolor=fig.get_facecolor(),
                dpi=fig.dpi * OVERSAMPLE, bbox_inches="tight", pad_inches=0.08)
    plt.close(fig)
    return buffer.getvalue(), natural


def _place(png: bytes, natural: int, stretch: bool, width: int | None = None):
    if stretch:
        st.image(png, **({"width": "stretch"} if _HAS_WIDTH
                         else {"use_container_width": True}))
    else:
        st.image(png, width=width or natural)


# --------------------------------------------------------------------------
# cached figures
# --------------------------------------------------------------------------
#
# Streamlit re-runs the whole script on every interaction, so a page used to
# redraw all of its matplotlib figures each time somebody clicked a tab or
# typed in the tutor box.  A circuit diagram alone costs about a third of a
# second to rasterise, which is most of what "it lags" means.
#
# These figures are pure functions of their inputs, so the PNG is cached
# against those inputs and the redraw only happens when the picture would
# actually be different.

_MAKERS = {
    "circuit": lambda d, hl: viz.circuit_figure(C.Circuit.from_dict(d), hl),
    "legend": lambda: viz.legend_figure(),
    "bloch": lambda vec, title: viz.bloch_figure(E.BlochVector(*vec), title),
    "histogram": lambda exact, counts: viz.histogram_figure(exact, counts),
    "phase_wheel": lambda re, im, n: viz.phase_wheel_figure(
        np.asarray(re) + 1j * np.asarray(im), n),
    "completion": lambda labels, values: viz.completion_figure(labels, values),
    "distribution": lambda values: viz.distribution_figure(values),
    "bit_vs_qubit": lambda: viz.bit_vs_qubit_figure(),
    "state_growth": lambda: viz.state_growth_figure(),
    "use_case": lambda: viz.use_case_figure(),
    "measurement": lambda: viz.measurement_figure(),
}


@st.cache_data(show_spinner=False, max_entries=192)
def _render(name: str, payload: str):
    return _to_png(_MAKERS[name](*json.loads(payload)))


def draw(name: str, *args, stretch: bool = True, width: int | None = None):
    """Show a figure, drawing it only if this exact one has not been drawn."""
    png, natural = _render(name, json.dumps(args, default=float))
    _place(png, natural, stretch, width)


# ==========================================================================
# sidebar
# ==========================================================================

def hardware_panel():
    """Token, device list, submission and retrieval for IBM Quantum.

    Submission and retrieval are separate on purpose: free-tier queues run to
    hours, so the useful workflow is to submit in advance and fetch by job id
    later — possibly in a session started days afterwards.
    """
    st.caption("Everything else in QuBuild is a simulator. This sends the circuit to a "
               "physical processor and waits in the public queue.")
    info = HW.status()

    if not info["sdk_installed"]:
        st.warning("Client library not installed")
        st.caption("Install it into **the same Python that is running this app** — the "
                   "usual reason this fails twice is a second interpreter on the machine "
                   "(Anaconda alongside python.org, say). This app is running:")
        st.code(sys.executable, language=None)
        st.caption("So the command that is certain to hit the right one is:")
        st.code('"%s" -m pip install qiskit qiskit-ibm-runtime' % sys.executable,
                language="bash")
        st.caption("Then stop Streamlit (Ctrl+C) and start it again — a running app will "
                   "not pick up a newly installed package.")
    if not info["token_present"]:
        st.caption("An API token from your IBM Quantum account is required. It is stored "
                   "locally with owner-only permissions and never shown again.")
        with st.form("ibm-token", clear_on_submit=True):
            token = st.text_input("IBM Quantum API token", type="password")
            instance = st.text_input("Instance (optional)", placeholder="crn:... or hub/group/project")
            if st.form_submit_button("Save token") and token:
                st.success("Saved.") if HW.store_token(token, instance) else st.error("Could not write the token file.")
                st.rerun()
    else:
        st.success("Token configured (from the %s)" % info["token_source"])
        if info["instance"]:
            st.caption("Instance: `%s`" % info["instance"])
        if st.button("Forget token", key="ibm-forget"):
            HW.forget_token()
            st.rerun()

    st.divider()
    st.markdown('<span class="qf-eyebrow">Jobs</span>', unsafe_allow_html=True)

    if info["ready"]:
        if st.button("List devices", key="ibm-devices"):
            try:
                SS.ibm_devices = [(d.name, d.qubits, d.pending_jobs) for d in HW.devices()]
            except Exception as exc:                                   # noqa: BLE001
                SS.ibm_devices = []
                st.error(str(exc))
        for name, qubits, pending in SS.get("ibm_devices", []):
            st.caption("`%s` · %d qubits · %d queued" % (name, qubits, pending))

        target = st.text_input("Device", value=SS.get("ibm_devices", [("", 0, 0)])[0][0]
                               if SS.get("ibm_devices") else "", key="ibm-target")
        if st.button("Submit current circuit", key="ibm-submit") and target:
            try:
                record = HW.submit(SS.circuit, target, SS.shots)
                st.success("Submitted as `%s`" % record.job_id)
            except Exception as exc:                                   # noqa: BLE001
                st.error(str(exc))

    for job in HW.recall()[:5]:
        st.markdown("`%s`" % job.job_id)
        st.caption("%s · %d qubits · %s" % (job.backend, job.qubits, HW.elapsed(job)))
        cols = st.columns(2)
        if cols[0].button("Status", key="st-" + job.job_id):
            try:
                st.json(HW.job_status(job.job_id))
            except Exception as exc:                                   # noqa: BLE001
                st.error(str(exc))
        if cols[1].button("Result", key="rs-" + job.job_id):
            try:
                SS.hw_counts = HW.fetch(job.job_id)
                st.success("Retrieved %d outcomes" % len(SS.hw_counts))
            except Exception as exc:                                   # noqa: BLE001
                st.error(str(exc))
    if SS.get("hw_counts"):
        st.bar_chart(SS.hw_counts)

    if not HW.recall():
        st.caption("No jobs submitted from this installation yet.")


def qbraid_panel():
    """Credentials for the hosted qBraid provider."""
    st.caption("qBraid fronts several quantum backends behind one account. The adapter is "
               "written and tested to the network boundary — no job has been submitted "
               "from this installation, so treat the first run as the first run.")
    info = QBR.status()
    if not info["sdk_installed"]:
        st.warning("Client library not installed")
        st.code('"%s" -m pip install qbraid' % sys.executable, language="bash")
    if info["key_present"]:
        st.success("API key configured (from the %s)" % info["key_source"])
        if st.button("Forget key", key="qb-forget"):
            QBR.forget_key()
            st.rerun()
        device = st.text_input("Device id", value=os.environ.get(
            "QUBUILD_QBRAID_DEVICE", "qbraid_qir_simulator"), key="qb-dev")
        if device:
            os.environ["QUBUILD_QBRAID_DEVICE"] = device
        if st.button("List devices", key="qb-list"):
            try:
                for d in QBR.devices():
                    st.caption("`%s` · %d qubits · %s%s"
                               % (d.id, d.qubits, d.status,
                                  " · simulator" if d.simulator else ""))
            except Exception as exc:                                  # noqa: BLE001
                st.error(str(exc))
    else:
        with st.form("qb-key", clear_on_submit=True):
            key = st.text_input("qBraid API key", type="password")
            if st.form_submit_button("Save key", **WIDE) and key:
                if QBR.store_key(key):
                    st.success("Saved.")
                    st.rerun()
                else:
                    st.error("Could not write the key file.")
        st.caption("Stored locally with owner-only permissions, and never shown again.")


def account_panel():
    """Sign-in. Progress follows the account when one is used."""
    user = SS.get("user")
    if user is not None:
        st.success("%s · %s" % (user.display, user.role))
        if user.cohort_name:
            st.caption("Class: %s" % user.cohort_name)
        if user.is_instructor and getattr(user, "cohort_code", None):
            st.caption("Classroom code: `%s`" % user.cohort_code)
        if user.is_learner:
            with st.form("join-class", clear_on_submit=True):
                code = st.text_input("Join a class with a code", placeholder="QB7K2M")
                if st.form_submit_button("Join", **WIDE) and code.strip():
                    room = AC.cohort_by_code(code)
                    if room is None:
                        st.error("No class answers to that code.")
                    else:
                        AC.set_cohort(user.id, int(room["id"]))
                        AC.set_role(user.id, "student")
                        SS.user = AC.get_user(user.id)
                        st.rerun()
        if st.button("Sign out", key="sign-out"):
            AC.save_progress(user.id, PROGRESS)
            SS.user = None
            SS.pop("progress_saved", None)
            st.rerun()
        return

    # Unreachable in normal use — the sign-in gate runs before any page does —
    # but kept so the panel degrades sanely rather than rendering blank.
    st.caption("Not signed in.")


def sidebar():
    with st.sidebar:
        st.markdown(
            '<div style="display:flex;gap:.6rem;align-items:center;margin-bottom:.2rem">'
            '<span style="font-size:1.5rem">⚛</span>'
            '<div><div style="font-size:1.15rem;font-weight:700;line-height:1.1">QuBuild</div>'
            '<div class="qf-eyebrow">quantum studio</div></div></div>',
            unsafe_allow_html=True)
        st.divider()
        pages = visible_pages()
        # A learner who was last on an instructor page — or who signed out of an
        # instructor account into this one — must not be left pointing at it.
        if SS.get("page") not in pages:
            SS.page = pages[0]
        st.radio("Navigate", pages, key="page", label_visibility="collapsed")

        # The nav labels are the page keys, so the count cannot go inside one.
        # It sits directly under the list instead, where it is still the first
        # thing the eye lands on when something is waiting.
        waiting = NT.unread_count(SS.user.id) if SS.get("user") else 0
        if waiting:
            st.markdown(
                '<div style="margin:-.3rem 0 .2rem;padding:.35rem .6rem;'
                'border:1px solid #39DCDC55;border-radius:8px;background:#39DCDC12">'
                '<span class="qf-eyebrow" style="color:#39DCDC">%d unread</span>'
                '</div>' % waiting, unsafe_allow_html=True)
            if st.button("Open notifications", key="nt-open", **WIDE):
                goto("Notifications")
        st.divider()

        xp = PROGRESS["xp"]
        lvl = ST.level(xp)
        floor, ceiling = ST.level_floor(lvl), ST.level_floor(lvl + 1)
        a, b = st.columns(2)
        a.metric("Level", lvl)
        b.metric("XP", xp)
        st.progress((xp - floor) / max(1, ceiling - floor),
                    text="%d XP to level %d" % (ceiling - xp, lvl + 1))
        st.caption("%d/%d lessons · %d/%d challenges"
                   % (len(PROGRESS["lessons"]), len(CT.LESSONS),
                      len(PROGRESS["challenges"]), len(CT.CHALLENGES)))

        with st.expander("Simulation backends", expanded=False):
            for backend in BK.BACKENDS:
                mark = "🟢" if backend.available else "⚪"
                st.markdown("%s **%s**" % (mark, backend.name))
                st.caption(backend.note if backend.available
                           else "Not installed — `%s`" % backend.install)

        with st.expander("Real quantum hardware", expanded=False):
            hardware_panel()

        with st.expander("qBraid", expanded=False):
            qbraid_panel()

        with st.expander("Account", expanded=False):
            account_panel()

        model = T.model_status()

        with st.expander("AI tutor · language model", expanded=False):
            st.caption(
                "The analysis layer — walkthrough, error detection, optimisation, "
                "recommendations — is computed from your circuit and always works with no "
                "key and no network. A model only adds free-form Q&A.")

            if model["ready"]:
                st.success("%s · `%s`" % (model["label"], model["model"] or "default"))
                if CFG.load_saved() and st.button("Disconnect model", key="tk-forget"):
                    CFG.clear_settings()
                    CFG.PROVIDER, CFG.API_KEY, CFG.MODEL = "none", "", ""
                    st.rerun()
            else:
                st.info("Local knowledge base")
                st.caption("Add a key below and the tutor will answer free-form "
                           "questions too. It is stored in a local file with owner-only "
                           "permissions — you do not need to edit any source file.")
                with st.form("tutor-key", clear_on_submit=True):
                    choices = [p for p in CFG.PROVIDERS if p != "none"]
                    provider = st.selectbox(
                        "Provider", choices,
                        index=choices.index("gemini") if "gemini" in choices else 0,
                        key="tk-prov")
                    key = st.text_input("API key", type="password", key="tk-key")
                    override = st.text_input(
                        "Model (optional)", key="tk-model",
                        placeholder="leave blank for the sensible default")
                    if st.form_submit_button("Save and connect", **WIDE):
                        needs_key = provider not in ("ollama", "custom")
                        if needs_key and not key.strip():
                            st.error("That provider needs a key.")
                        elif CFG.save_settings(provider, key, override):
                            CFG.apply_saved()
                            st.success("Saved. Reloading…")
                            st.rerun()
                        else:
                            st.error("Could not write the settings file.")
                st.caption("Ollama needs no key — it talks to a model running on this "
                           "machine. Everything else does.")

            if model.get("error"):
                st.warning(model["error"])
            if model.get("last_error"):
                st.warning(model["last_error"])


# ==========================================================================
# tutor panel
# ==========================================================================

def render_tutor_message(entry: dict):
    with st.chat_message("assistant" if entry["who"] == "ai" else "user", avatar="⚛" if entry["who"] == "ai" else "🧑"):
        if entry.get("title"):
            st.markdown("**%s**" % entry["title"])
        if entry.get("text"):
            st.markdown(entry["text"])
        for step in entry.get("steps", []):
            st.markdown('<div class="qf-issue info"><b>%s</b><p>%s</p></div>'
                        % (step.heading, step.body), unsafe_allow_html=True)
        for i, issue in enumerate(entry.get("issues", [])):
            st.markdown('<div class="qf-issue %s"><b>%s</b><p>%s</p></div>'
                        % (issue.level, issue.title, issue.body), unsafe_allow_html=True)
            if issue.fix and st.button("Apply fix", key="fix-%s-%d" % (entry["key"], i)):
                push_undo()
                T.apply_fix(SS.circuit, issue.fix)
                st.toast("Applied")
                st.rerun()
        for i, sugg in enumerate(entry.get("suggestions", [])):
            st.markdown('<div class="qf-issue info"><b>%s</b><p>%s</p></div>'
                        % (sugg.title, sugg.body), unsafe_allow_html=True)
            if sugg.fix and st.button("Apply", key="opt-%s-%d" % (entry["key"], i)):
                push_undo()
                T.apply_fix(SS.circuit, sugg.fix)
                st.toast("Applied")
                st.rerun()
        for i, rec in enumerate(entry.get("recs", [])):
            st.markdown('<div class="qf-issue info"><b>%s</b><p>%s</p></div>'
                        % (rec.title, rec.why), unsafe_allow_html=True)
            if rec.goto and st.button("Open", key="rec-%s-%d" % (entry["key"], i)):
                goto(rec.goto["page"], **{k: v for k, v in rec.goto.items() if k != "page"})
        if entry.get("code"):
            st.code(entry["code"], language="python")


def tutor_action(action: str, label: str = ""):
    key = str(len(SS.tutor_log))
    if label:
        SS.tutor_log.append({"who": "me", "text": label, "key": key + "u"})
    entry = {"who": "ai", "key": key}
    if action == "explain":
        entry.update(title="Walking through your circuit", steps=T.explain(SS.circuit))
    elif action == "analyse":
        issues = T.analyse(SS.circuit)
        entry.update(title="%d finding%s" % (len(issues), "" if len(issues) == 1 else "s"),
                     issues=issues)
    elif action == "optimise":
        entry.update(title="Optimisation pass", suggestions=T.optimise(SS.circuit))
    elif action == "recommend":
        entry.update(title="Based on what you have done so far", recs=T.recommend(PROGRESS))
    elif action == "code":
        entry.update(title="Your circuit in Qiskit", code=C.to_qiskit(SS.circuit))
    SS.tutor_log.append(entry)


def tutor_context() -> dict:
    """What the model is told about the screen. Circuits go as readable text,
    not JSON — a model reasons better about `H q0; CX q0,q1` than about a dict.

    On the Lessons page the open lesson goes too, so "what does that mean?"
    resolves against the paragraph the learner is actually looking at."""
    circuit = SS.circuit
    try:
        outcomes = current_result().counts
        top = sorted(outcomes.items(), key=lambda kv: -kv[1])[:6]
        total = sum(outcomes.values()) or 1
        state = ", ".join("%s %d%%" % (k, round(100 * v / total)) for k, v in top)
    except Exception:                                              # noqa: BLE001
        state = ""
    context = {"circuit": C.to_qasm(circuit), "qubits": circuit.qubits,
               "depth": circuit.depth, "state": state, "page": SS.page}
    if SS.page == "Lessons":
        lesson = CT.LESSON_BY_ID.get(SS.lesson)
        if lesson:
            context["lesson"] = lesson.title
            context["lesson_body"] = " ".join(lesson.body.split())[:1400]
    return context


# Three questions a learner actually asks while reading each lesson.  They seed
# the rail so the first click is never a blank box.
LESSON_PROMPTS = {
    "l1": ["What is an amplitude?", "Why squared magnitudes?", "What does normalisation mean?"],
    "l2": ["What is superposition, really?", "How do I read the Bloch sphere?",
           "Is a qubit just a random coin?"],
    "l3": ["Why does measuring destroy the state?", "What is the Born rule?",
           "Can I measure a qubit twice?"],
    "l4": ["What does the H gate do?", "X, Y and Z — what's the difference?",
           "What is a unitary?"],
    "l5": ["What is phase?", "Global vs relative phase?", "How does interference give speedup?"],
    "l6": ["What is a tensor product?", "Why 2ⁿ amplitudes?", "How do I read |01⟩?"],
    "l7": ["What is entanglement?", "Why is the gloves analogy wrong?",
           "How do I make a Bell state?"],
    "l8": ["What does CNOT actually do?", "What is a universal gate set?",
           "Why is there no quantum AND?"],
    "l9": ["What is phase kickback?", "What does the oracle do?",
           "Why does Deutsch–Jozsa need one query?"],
    "l10": ["Why is Grover only √N faster?", "What does the oracle do?",
            "How many Grover iterations?"],
    "l11": ["What is the QFT for?", "How is it different from the Fourier transform?",
            "Why can't I read the QFT output?"],
    "l12": ["What is decoherence?", "What are shots?", "What are T1 and T2?"],
    "l13": ["Why do Qiskit and Cirq disagree?", "What is qubit ordering?",
            "Which SDK should I learn first?"],
}

GENERAL_PROMPTS = ["What is a qubit?", "What is superposition?", "What should I learn next?"]


def rail_prompts() -> list:
    """Quick-ask chips for whatever is on screen."""
    if SS.page == "Lessons":
        return LESSON_PROMPTS.get(SS.lesson, GENERAL_PROMPTS)
    if SS.page in ("Circuit Studio", "Challenges", "Algorithm library"):
        return ["What does this circuit do?", "Check my circuit for mistakes",
                "How is this graded?"]
    return GENERAL_PROMPTS


def ask_tutor(question: str):
    """One question in, one exchange appended to the log."""
    key = str(len(SS.tutor_log))
    SS.tutor_log.append({"who": "me", "text": question, "key": key + "u"})
    reply = T.ask(question, tutor_context())
    if reply.action:
        tutor_action(reply.action)
    else:
        SS.tutor_log.append({"who": "ai", "key": key, "title": reply.title,
                             "text": reply.text + ("\n\n*(%s)*" % reply.source)})


def tutor_rail():
    """The tutor, docked to the right of every page.

    It stays open while the learner reads, so a question about the paragraph in
    front of them costs one click rather than a change of page."""
    st.markdown(RAIL_CSS % {"w": RAIL_WIDTH,
                            "pad": RAIL_WIDTH + 1.5 if SS.tutor_open else 3.0},
                unsafe_allow_html=True)

    if not SS.tutor_open:
        with st.container(key="qf_railtab"):
            if st.button("⚛", key="rail-open", help="Open the AI tutor"):
                SS.tutor_open = True
                st.rerun()
        return

    model = T.model_status()
    with st.container(key="qf_rail"):
        head, shut = st.columns([4, 1])
        head.markdown('<div class="qf-rail-head"><span class="dot%s"></span>'
                      '<b>AI tutor</b></div>'
                      '<span class="qf-eyebrow">%s</span>'
                      % ("" if model["ready"] else " off",
                         model["label"] if model["ready"] else "local knowledge base"),
                      unsafe_allow_html=True)
        if shut.button("✕", key="rail-close", help="Hide the tutor"):
            SS.tutor_open = False
            st.rerun()

        # What the tutor can see right now — so the learner knows why the
        # answers are specific, and trusts them more.
        if SS.page == "Lessons":
            lesson = CT.LESSON_BY_ID.get(SS.lesson, CT.LESSONS[0])
            seeing = "Reading with you: <b>%s</b>" % lesson.title
        else:
            seeing = ("Looking at your circuit: %d qubits, depth %d"
                      % (SS.circuit.qubits, SS.circuit.depth))
        st.markdown('<div class="qf-seeing">%s</div>' % seeing, unsafe_allow_html=True)

        st.markdown('<span class="qf-eyebrow">Ask about this</span>', unsafe_allow_html=True)
        for i, prompt in enumerate(rail_prompts()):
            if st.button(prompt, key="rp-%d" % i, **WIDE):
                SS.tutor_pending = prompt
                st.rerun()

        if SS.page in ("Circuit Studio", "Challenges"):
            st.markdown('<span class="qf-eyebrow">On your circuit</span>',
                        unsafe_allow_html=True)
            actions = [("Explain circuit", "explain"), ("Check for mistakes", "analyse"),
                       ("Optimise", "optimise"), ("Generate code", "code")]
            grid = st.columns(2)
            for i, (label, action) in enumerate(actions):
                if grid[i % 2].button(label, key="ta-" + action, **WIDE):
                    tutor_action(action, label)
                    st.rerun()

        st.divider()

        if SS.tutor_log:
            for entry in SS.tutor_log[-8:]:
                render_tutor_message(entry)
        else:
            st.caption("Ask me anything on this page — a word you don't recognise, why a "
                       "result looks wrong, or for a plain-English version of the paragraph "
                       "you're stuck on.")

        question = st.text_input("Ask the tutor", key="tutor_q",
                                 placeholder="Ask anything about this page…",
                                 label_visibility="collapsed")
        send, clear = st.columns([3, 1])
        if send.button("Ask", key="tutor_ask", type="primary", **WIDE) and question.strip():
            SS.tutor_pending = question
            st.rerun()
        if clear.button("Clear", key="tutor_clear", **WIDE):
            SS.tutor_log = []
            st.rerun()

        # Answer after the rerun, so the learner sees their own question land
        # first and the spinner sits where the reply will appear.
        if SS.tutor_pending:
            pending, SS.tutor_pending = SS.tutor_pending, None
            with st.spinner("Thinking…"):
                ask_tutor(pending)
            st.rerun()


# ==========================================================================
# results panel
# ==========================================================================

def mps_panel(circuit: C.Circuit):
    """Bond-dimension control and the fidelity the run actually retained.

    The fidelity is the whole reason this backend is trustworthy: an
    approximate simulator that does not tell you how approximate it was being
    is just a simulator that is quietly wrong.
    """
    from qubuild import mps as MPS
    default = MPS.recommended_chi(circuit.qubits)
    st.markdown('<span class="qf-eyebrow">Tensor network</span>', unsafe_allow_html=True)
    chi = st.select_slider(
        "Bond dimension", options=[2, 4, 8, 16, 32, 64, 128],
        value=SS.get("chi") or default, key="chi_pick",
        help="How much entanglement the chain is allowed to carry. Higher is more "
             "accurate and slower; the memory cost is roughly n · chi².")
    if chi != SS.get("chi", 0):
        SS.chi = chi
        st.rerun()

    fid = _mps_fidelity(SS.get("last_detail", ""))
    if fid is not None:
        colour = "#3DD68C" if fid > 0.99 else ("#F2C14E" if fid > 0.9 else "#FF6F6F")
        gauge("retained fidelity", fid, colour, "%.4f" % fid)
        if fid < 0.99:
            st.warning(
                "This run discarded %.2f%% of the state to fit bond dimension %d. "
                "The histogram above is an approximation — raise the bond dimension "
                "until this reads 1.0000, or accept it knowingly."
                % (100 * (1 - fid), chi))


def _mps_fidelity(detail: str):
    import re as _re
    m = _re.search(r"fidelity ([0-9.]+)", detail or "")
    return float(m.group(1)) if m else None




_CROSS_CSS = """<style>
.qf-x{width:100%;border-collapse:collapse;margin:.3rem 0 .15rem}
.qf-x th{font-family:'IBM Plex Mono',monospace;font-size:.6rem;letter-spacing:.08em;
         text-transform:uppercase;color:#55627A;text-align:left;font-weight:500;
         padding:0 .35rem .25rem}
.qf-x td{padding:.2rem .35rem;border-top:1px solid #1B2537}
.qf-x-sdk{font-size:.7rem;color:#8A99B4;white-space:nowrap}
.qf-x-bits{font-family:'IBM Plex Mono',monospace;font-size:.78rem;letter-spacing:.06em}
.qf-x-mark{width:1.1rem;text-align:center}
.qf-xs{font-size:.68rem;line-height:1.45}
</style>"""

@st.cache_data(show_spinner=False, max_entries=64)
def _cross_rows(circuit_json: str):
    return BK.cross_check(C.Circuit.from_dict(json.loads(circuit_json)))


def cross_sdk_panel(circuit):
    """Show what each SDK calls this circuit's most likely outcome.

    This is the one place in QuBuild where the normalisation is deliberately
    undone.  Everywhere else the learner is shown a single corrected answer,
    which is right — but it hides the fact that the SDKs disagree about how to
    write a bit string, and that disagreement is worth a lesson of its own.
    """
    useful, why = BK.cross_check_is_useful(circuit)
    st.markdown('<div class="qf-eyebrow" style="margin-top:.9rem">CROSS-SDK CHECK</div>',
                unsafe_allow_html=True)
    if not useful:
        st.markdown('<div class="qf-xs" style="color:#8A99B4">%s</div>' % html.escape(why),
                    unsafe_allow_html=True)
        return

    rows = _cross_rows(json.dumps(circuit.to_dict()))
    live = [r for r in rows if r.available]
    agree = all(r.agrees for r in live)
    differ = any(r.flipped and r.native != r.normalised for r in live)

    body = []
    for r in rows:
        if not r.available:
            body.append(
                '<tr><td class="qf-x-sdk" style="opacity:.45">%s</td>'
                '<td colspan="3" style="opacity:.45;font-size:.66rem">%s</td></tr>'
                % (html.escape(r.sdk), html.escape(r.note)))
            continue
        mark = ('<span style="color:#F2C14E">&#8634;</span>' if r.flipped else
                '<span style="opacity:.25">&middot;</span>')
        native_colour = "#F2C14E" if (r.flipped and r.native != r.normalised) else "#E6ECF7"
        body.append(
            '<tr>'
            '<td class="qf-x-sdk">%s</td>'
            '<td class="qf-x-bits" style="color:%s">%s</td>'
            '<td class="qf-x-mark">%s</td>'
            '<td class="qf-x-bits" style="color:#39DCDC">%s</td>'
            '</tr>' % (html.escape(r.sdk), native_colour, html.escape(r.native),
                       mark, html.escape(r.normalised)))

    # NB: the stylesheet is concatenated, never %-formatted — it contains
    # literal '%' characters (width:100%) that %-formatting would read as
    # format specifiers.
    st.markdown(
        _CROSS_CSS
        + '<table class="qf-x"><tr><th>SDK</th><th>its own words</th><th></th>'
          '<th>normalised</th></tr>' + "".join(body) + '</table>',
        unsafe_allow_html=True)

    if differ and agree:
        st.markdown(
            '<div class="qf-xs" style="color:#8A99B4">Same state, three spellings. '
            'Cirq and PennyLane put wire&nbsp;0 on the <b style="color:#F2C14E">left</b>; '
            'Qiskit and QuBuild put it on the <b style="color:#39DCDC">right</b>. '
            'QuBuild flips them back, so you are never told you are wrong because a '
            'library disagreed with another library.</div>',
            unsafe_allow_html=True)
    elif agree:
        st.markdown('<div class="qf-xs" style="color:#8A99B4">Every installed SDK '
                    'returns this same state.</div>', unsafe_allow_html=True)
    else:
        bad = ", ".join(r.sdk for r in live if not r.agrees)
        st.markdown('<div class="qf-xs" style="color:#FF6F6F">Disagreement after '
                    'normalising: %s. That is a real bug, not a convention \u2014 '
                    'run <code>tests/test_backends.py</code>.</div>' % html.escape(bad),
                    unsafe_allow_html=True)

def results_panel(result):
    circuit = SS.circuit
    SS.last_detail = result.detail
    # Past the dense limit the tensor-network backend holds no full statevector,
    # so anything derived from one is unavailable and says so.
    dense = (result.state is not None
             and result.state.size == (1 << circuit.qubits))
    entangled = sum(1 for v in result.blochs if v.entangled)
    chips([("qubits %d" % circuit.qubits, ""), ("depth %d" % circuit.depth, ""),
           ("gates %d" % circuit.gate_count, ""),
           ("2-qubit %d" % circuit.two_qubit_count, ""),
           ("entangled %d" % entangled, "warn" if entangled else ""),
           ("%d ms" % result.ms, "")])
    st.caption("Executed by **%s** — %s" % (result.executed_by, result.detail))
    cross_sdk_panel(circuit)

    if result.backend.id == "mps_tn":
        mps_panel(circuit)

    tabs = st.tabs(["Outcomes", "Bloch spheres", "Amplitudes"])
    with tabs[0]:
        exact = (BK.exact_marginal(result.state, circuit.qubits, circuit.measured or None)
                 if dense else {})
        draw("histogram", exact, result.counts)
        if not dense:
            st.caption("Sampled counts only — at this width there is no exact "
                       "distribution to compare against, which is exactly why the "
                       "tensor network is being used.")
        st.caption(("Measured q%s" % ", q".join(str(q) for q in circuit.measured))
                   if circuit.measured else "No measurement gates — showing all qubits.")
        if result.counts is not None and st.button("Re-sample shots"):
            SS.seed = random.randint(1, 10 ** 6)
            st.rerun()
    with tabs[1]:
        if not result.blochs:
            st.info("Bloch spheres are read out of the full statevector. Past "
                    "%d qubits that array is never built — the tensor network "
                    "stores the circuit, not its 2\u207f amplitudes."
                    % BK.DENSE_LIMIT)
        cols = st.columns(min(2, max(1, len(result.blochs))))
        for q, vec in enumerate(result.blochs):
            with cols[q % len(cols)]:
                draw("bloch", [vec.x, vec.y, vec.z, vec.p0, vec.p1],
                     "q%d" % q, stretch=False)
                if vec.entangled:
                    st.caption("|r| = %.3f — entangled, no state of its own" % vec.length)
                else:
                    st.caption("|r| = %.3f · P(1) = %.3f" % (vec.length, vec.p1))
    with tabs[2]:
        if not dense:
            st.info("The amplitude table lists every basis state. At %d qubits "
                    "there are 2\u207f of them and none are held in memory — "
                    "run under %d qubits to inspect them."
                    % (circuit.qubits, BK.DENSE_LIMIT))
            return
        rows = viz.amplitude_rows(result.state, circuit.qubits)
        st.dataframe(
            [{k: v for k, v in row.items() if not k.startswith("_")} for row in rows],
            hide_index=True, **WIDE)
        draw("phase_wheel", result.state.real.tolist(),
             result.state.imag.tolist(), circuit.qubits, stretch=False)
        st.caption("Each spoke is a basis state: length is |amplitude|, angle is the complex "
                   "phase. Only relative phase is physical.")


# ==========================================================================
# circuit editor
# ==========================================================================

GATE_GROUPS = {
    "Single qubit": ["H", "X", "Y", "Z", "S", "SDG", "T", "TDG", "SX", "I"],
    "Rotations": ["RX", "RY", "RZ", "P", "U"],
    "Two & three qubit": ["CX", "CZ", "CY", "CH", "CRZ", "CRY", "CP", "SWAP", "CCX", "CSWAP"],
    "Non-unitary": ["MEASURE", "BARRIER"],
}
ALL_GATES = [g for group in GATE_GROUPS.values() for g in group]


def op_label(op: C.Op) -> str:
    spec = E.GATES[op.name]
    param = "(%s)" % C.fmt_param(op.params[0]) if spec.param and op.params else ""
    return "col %d · %s%s %s" % (int(op.col), op.name, param,
                                 " ".join("q%d" % q for q in op.qubits))


def gate_adder(circuit: C.Circuit):
    st.markdown('<span class="qf-eyebrow">Add a gate</span>', unsafe_allow_html=True)
    group = st.selectbox("Family", list(GATE_GROUPS), key="add_group",
                         label_visibility="collapsed")
    gate = st.selectbox("Gate", GATE_GROUPS[group], key="add_gate",
                        format_func=lambda g: "%s — %s" % (g, E.GATES[g].desc.split("—")[0].strip()),
                        label_visibility="collapsed")
    spec = E.GATES[gate]
    qubits = []
    cols = st.columns(max(1, spec.arity))
    for i in range(spec.arity):
        role = "control" if i < spec.ctrl else ("target" if spec.arity > 1 else "qubit")
        if gate in ("SWAP", "CSWAP") and i >= spec.ctrl:
            role = "swap"
        default = min(i, circuit.qubits - 1)
        qubits.append(cols[i].selectbox("%s %d" % (role, i + 1) if spec.arity > 1 else role,
                                        list(range(circuit.qubits)),
                                        index=default, key="add_q%d" % i,
                                        format_func=lambda q: "q%d" % q))
    params = []
    if spec.param:
        angle = st.select_slider(
            spec.param, options=[-PI, -3 * PI / 4, -PI / 2, -PI / 4, -PI / 8, 0.0,
                                 PI / 8, PI / 4, PI / 2, 3 * PI / 4, PI],
            value=PI / 2, key="add_param", format_func=C.fmt_param)
        params = [angle] + ([0.0, 0.0] if spec.nparams == 3 else [])

    disabled = len(set(qubits)) != len(qubits)
    if disabled:
        st.caption(":red[Pick distinct qubits — a gate cannot act on the same wire twice.]")
    if st.button("Add %s" % gate, type="primary", disabled=disabled, **WIDE):
        push_undo()
        circuit.add(gate, qubits, params)
        SS.selected = circuit.ops[-1].id
        SS.code_buffer = None
        st.rerun()


def inspector(circuit: C.Circuit):
    if not circuit.ops:
        st.caption("The circuit is empty. Add a gate, or load one from the algorithm library.")
        return
    st.markdown('<span class="qf-eyebrow">Inspect / edit</span>', unsafe_allow_html=True)
    ops = circuit.ordered_ops()
    ids = [o.id for o in ops]
    index = ids.index(SS.selected) if SS.selected in ids else 0
    chosen = st.selectbox("Gate", ops, index=index, key="inspect",
                          format_func=op_label, label_visibility="collapsed")
    SS.selected = chosen.id
    spec = E.GATES[chosen.name]
    st.caption(spec.desc)

    if spec.arity <= circuit.qubits:
        cols = st.columns(spec.arity)
        for i in range(spec.arity):
            role = "control" if i < spec.ctrl else ("target" if spec.arity > 1 else "qubit")
            new = cols[i].selectbox(role, list(range(circuit.qubits)),
                                    index=chosen.qubits[i], key="ins_q%d_%d" % (chosen.id, i),
                                    format_func=lambda q: "q%d" % q)
            if new != chosen.qubits[i]:
                push_undo()
                if new in chosen.qubits:
                    chosen.qubits[chosen.qubits.index(new)] = chosen.qubits[i]
                chosen.qubits[i] = new
                circuit.pack()
                st.rerun()

    if spec.param:
        current = chosen.params[0] if chosen.params else 0.0
        new = st.slider(spec.param, -2 * PI, 2 * PI, float(current), PI / 32,
                        key="ins_p_%d" % chosen.id, format="%.3f")
        if abs(new - current) > 1e-9:
            push_undo()
            if chosen.params:
                chosen.params[0] = new
            else:
                chosen.params = [new]
            st.rerun()
        st.caption("%s = %s" % (spec.param, C.fmt_param(chosen.params[0] if chosen.params else 0)))

    left, right = st.columns(2)
    if left.button("Delete gate", **WIDE):
        push_undo()
        circuit.remove(chosen.id)
        SS.selected = None
        st.rerun()
    if right.button("Duplicate", **WIDE):
        push_undo()
        circuit.add(chosen.name, chosen.qubits, chosen.params)
        st.rerun()


def toolbar(circuit: C.Circuit):
    # Shots holds a four-digit number next to a chevron; at the larger type
    # scale 1.3 was a hair too narrow and clipped the last digit.
    top = st.columns([2.8, 1.6, 1.1])
    options = [b.id for b in BK.available()]
    top[0].selectbox("Backend", options, key="backend",
                     index=options.index(SS.backend) if SS.backend in options else 0,
                     format_func=lambda i: BK.BY_ID[i].name)
    top[1].selectbox("Shots", [128, 512, 1024, 4096, 8192], key="shots",
                     index=[128, 512, 1024, 4096, 8192].index(SS.shots))
    # The tensor-network backend is the only one that can go wide, so the cap
    # follows the chosen backend instead of being one number for all of them.
    cap = BK.MPS_LIMIT if SS.backend == "mps_tn" else MAX_QUBITS
    if circuit.qubits > cap:
        circuit.set_qubits(cap)
    top[2].number_input("Qubits", 1, cap, circuit.qubits, key="nq",
                        on_change=lambda: circuit.set_qubits(SS.nq))

    row = st.columns(4)
    if row[0].button("Undo", **WIDE, disabled=not SS.undo):
        SS.circuit = C.Circuit.from_dict(json.loads(SS.undo.pop()))
        SS.selected = None
        st.rerun()
    if row[1].button("Clear", **WIDE):
        push_undo()
        circuit.ops = []
        SS.selected = None
        st.rerun()
    if row[2].button("Measure all", **WIDE):
        push_undo()
        for q in range(circuit.qubits):
            if q not in circuit.measured:
                circuit.add("MEASURE", [q])
        st.rerun()
    if row[3].button("Drop measures", **WIDE):
        push_undo()
        circuit.ops = [o for o in circuit.ops if o.name != "MEASURE"]
        circuit.pack()
        st.rerun()


def code_panel(circuit: C.Circuit):
    st.markdown('<span class="qf-eyebrow">Code — read and write four dialects</span>',
                unsafe_allow_html=True)
    dialects = list(C.GENERATORS)
    tabs = st.tabs(dialects)
    for tab, name in zip(tabs, dialects):
        with tab:
            st.code(C.GENERATORS[name](circuit), language="python" if name != "OpenQASM" else "text")

    with st.expander("Build a circuit from source", expanded=False):
        st.caption("Paste Qiskit, Cirq, PennyLane or OpenQASM — the parser normalises all four.")
        default = SS.code_buffer if SS.code_buffer is not None else C.to_qiskit(circuit)
        text = st.text_area("Source", value=default, height=220, label_visibility="collapsed")
        if st.button("Build circuit from code", type="primary"):
            parsed, errors = C.parse(text)
            SS.code_buffer = text
            if errors:
                for err in errors[:6]:
                    st.error("line %d — %s" % (err.line, err.message))
            if parsed.ops:
                set_circuit(parsed)
                st.toast("Circuit updated from code")
                st.rerun()
            elif not errors:
                st.warning("No gates found in that source.")


# ==========================================================================
# pages
# ==========================================================================

# The page opens on the machine the reader already owns, because "quantum" only
# means something against a baseline — and the baseline is the thing they have
# never had to think about.
CLASSICAL_VS_QUANTUM = [
    ("Unit of information",
     "A bit. One switch, either 0 or 1.",
     "A qubit. A blend of 0 and 1 until it is read."),
    ("Describing n units",
     "n numbers. Thirty bits is thirty numbers.",
     "2ⁿ numbers. Thirty qubits is over a billion."),
    ("What you get when you read it",
     "Exactly what was stored. Reading changes nothing.",
     "A single 0 or 1, chosen by chance. Reading destroys the blend."),
    ("How it computes",
     "Steps in sequence. Each one has a definite result.",
     "Amplitudes interfere — wrong answers cancel, the right one adds up."),
    ("Running it twice",
     "Same input, same output, every time.",
     "Same circuit, different samples. You need many runs to see the pattern."),
    ("Good at",
     "Essentially everything you do today.",
     "Chemistry, factoring, some optimisation and search."),
    ("Bad at",
     "Simulating quantum systems. It runs out of memory.",
     "Everything else — including ordinary arithmetic."),
    ("State today",
     "Mature, cheap, everywhere.",
     "Noisy prototypes. No proven commercial advantage yet."),
]


def page_overview():
    st.markdown(
        '<div class="qf-hero qf-hero-line">'
        '<span class="qf-eyebrow">Interactive quantum computing platform</span>'
        '<h2>Where classical stops, quantum begins.</h2></div>',
        unsafe_allow_html=True)
    st.write("")

    st.markdown('<span class="qf-eyebrow">Start here</span>', unsafe_allow_html=True)
    st.subheader("The machine you already have")

    st.markdown(
        "Every computer you have ever used — phone, laptop, the servers behind every "
        "website — is built from **bits**. A bit is one switch, held open or closed by a "
        "transistor, and it is either **0** or **1**. Nothing in between, ever.\n\n"
        "Stack enough of those switches and you get everything: text, photographs, video, "
        "machine learning. A modern processor holds billions of them and flips them "
        "billions of times a second. It is, by any reasonable measure, one of the great "
        "achievements of engineering — and for almost every job you can name, nothing "
        "will beat it.\n\n"
        "But it has one structural weakness, and it is not speed. To describe a quantum "
        "system of **n** particles, a classical machine needs **2ⁿ** numbers. Thirty "
        "particles is a billion numbers. Fifty is a thousand trillion. Add one more and "
        "the bookkeeping **doubles**. Around fifty, the largest supercomputer on Earth "
        "simply runs out of memory — not for a while, but permanently. No faster chip "
        "fixes a problem that doubles.")

    st.write("")
    st.markdown('<span class="qf-eyebrow">The differences</span>', unsafe_allow_html=True)
    st.subheader("Two different kinds of machine")
    html_table(["", "Classical computer", "Quantum computer"],
               CLASSICAL_VS_QUANTUM, ["20%", "40%", "40%"])
    st.caption("Read the last two rows together. A quantum computer is not an upgrade — "
               "it is a specialist that is worse than your phone at almost everything, "
               "and unmatched at a handful of problems nothing else can touch.")

    st.write("")
    intro = st.columns([1.15, 1])
    with intro[0]:
        st.markdown(
            "**The part most explanations skip.** A qubit holds a blend of 0 and 1 — "
            "a **superposition**. But **when you read it you still only get 0 or 1.** "
            "You never see the blend, only where it landed.\n\n"
            "So a single run tells you almost nothing. You run the circuit many times "
            "and read the pattern. The work of an algorithm is making sure that pattern "
            "points at the right answer.")
    with intro[1]:
        draw("bit_vs_qubit", stretch=True)

    growth = st.columns([1, 1.15])
    with growth[0]:
        draw("state_growth", stretch=True)
    with growth[1]:
        st.markdown(
            "**The doubling, drawn.** The blue line is what a classical machine must "
            "store to track a quantum state; the grey line is what it stores for ordinary "
            "bits. That gap is the whole argument: if you want to simulate a quantum "
            "system, the only practical instrument is another quantum system.")

    st.markdown("**Where it is expected to matter first**")
    draw("use_case", stretch=True)
    st.caption("Notice what is missing: spreadsheets, websites, games, ordinary machine "
               "learning. Those stay classical — and today's quantum machines are noisy "
               "prototypes with no proven commercial advantage yet.")

    if st.button("Start with the first lesson", type="primary"):
        goto("Lessons", lesson=CT.LESSONS[0].id)

    st.divider()

    cols = st.columns(5)
    cols[0].metric("Level", ST.level(PROGRESS["xp"]))
    cols[1].metric("XP", PROGRESS["xp"])
    cols[2].metric("Lessons", "%d/%d" % (len(PROGRESS["lessons"]), len(CT.LESSONS)))
    cols[3].metric("Challenges", "%d/%d" % (len(PROGRESS["challenges"]), len(CT.CHALLENGES)))
    cols[4].metric("Active days", len(PROGRESS["days"]))

    st.divider()
    left, right = st.columns([1.35, 1])

    with left:
        st.subheader("What is inside")
        cards = [
            ("Lessons", "Four tracks, %d lessons, each with a runnable demo circuit and "
                        "five questions you must clear to move on." % len(CT.LESSONS),
             "Lessons"),
            ("Circuit Studio", "Build a circuit gate by gate or paste Qiskit. Statevector, Bloch "
                               "spheres and shot histograms update as you go.", "Circuit Studio"),
            ("Algorithm library", "Bell, GHZ, W, Deutsch–Jozsa, Bernstein–Vazirani, Grover, QFT, "
                                  "teleportation, superdense coding.", "Algorithm library"),
            ("Challenges", "Eight problems graded by state fidelity, not string matching. "
                           "Constraints are enforced.", "Challenges"),
            ("Assessment", "Eighteen questions across five topics with an explanation behind "
                           "every answer.", "Assessment"),
            ("Instructor view", "Cohort completion, score distribution and a ranked list of the "
                                "concepts a class is getting wrong.", "Instructor view"),
            ("Deliverables", "Every objective in the problem statement mapped to what is built, "
                             "how it is verified, and what is deliberately left for phase two.",
             "Deliverables"),
        ]
        for title, body, page in cards:
            if page in INSTRUCTOR_ONLY and not teaching():
                continue
            st.markdown('<div class="qf-card"><h4>%s</h4><p>%s</p></div>' % (title, body),
                        unsafe_allow_html=True)
            if st.button("Open " + title, key="ov-" + page, **WIDE):
                goto(page)

    with right:
        st.subheader("Recommended next")
        for i, rec in enumerate(T.recommend(PROGRESS)):
            st.markdown('<div class="qf-card"><h4>%s</h4><p>%s</p></div>' % (rec.title, rec.why),
                        unsafe_allow_html=True)
            if rec.goto and st.button("Go", key="rec-ov-%d" % i, **WIDE):
                goto(rec.goto["page"], **{k: v for k, v in rec.goto.items() if k != "page"})

        st.subheader("Execution backends")
        for backend in BK.BACKENDS:
            chips([(backend.name, "good" if backend.available else "")])
            st.caption(backend.note if backend.available
                       else "Not installed — install with `%s`" % backend.install)


def _inline_code(text: str) -> str:
    """`x` inside a raw-HTML card is not markdown, so turn it into <code> here."""
    parts = text.split("`")
    return "".join(p if i % 2 == 0 else "<code>%s</code>" % p for i, p in enumerate(parts))


_MATH_BLOCK = re.compile(r"\$\$(.+?)\$\$", re.S)
_FIG_LINE = re.compile(r"^@fig[ \t]+(\w+)[ \t]*$", re.M)

# Teaching diagrams a lesson body can drop in with a line reading "@fig <key>".
# Kept as a whitelist rather than a getattr on viz so a typo in the prose can
# never reach into the module namespace.
FIGURES = ("bit_vs_qubit", "state_growth", "use_case", "measurement")


def render_prose(text: str):
    """Render lesson copy: markdown, $$...$$ display math, and @fig diagrams.

    Streamlit hands display math to KaTeX only when the whole $$...$$ sits on a
    single line.  An equation broken across two source lines leaves the closing
    delimiter unmatched, so KaTeX swallows the rest of the paragraph and paints
    it in its error red.  Pulling the blocks out first makes line breaks inside
    an equation safe, and st.latex renders them centred either way.

    A line reading "@fig <key>" becomes the matching diagram from FIGURES, so
    lesson authors can place a picture exactly where the argument needs it
    without touching this file.
    """
    pos = 0
    for m in _MATH_BLOCK.finditer(text):
        _render_markdown(text[pos:m.start()])
        st.latex(" ".join(m.group(1).split()))
        pos = m.end()
    _render_markdown(text[pos:])


def _render_markdown(chunk: str):
    """Markdown, with any @fig lines pulled out and drawn in place."""
    at = 0
    for m in _FIG_LINE.finditer(chunk):
        before = chunk[at:m.start()]
        if before.strip():
            st.markdown(before)
        if m.group(1) in FIGURES:
            draw(m.group(1), stretch=False)
        at = m.end()
    tail = chunk[at:]
    if tail.strip():
        st.markdown(tail)


def html_table(headers, rows, widths=None):
    """A wrapping HTML table. st.dataframe draws to a canvas and clips long sentences."""
    widths = widths or ["auto"] * len(headers)
    head = "".join('<th style="width:%s">%s</th>' % (w, h) for h, w in zip(headers, widths))
    body = "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % _inline_code(str(c)) for c in row)
                   for row in rows)
    st.markdown('<table class="qf-table"><thead><tr>%s</tr></thead><tbody>%s</tbody></table>'
                % (head, body), unsafe_allow_html=True)


def page_deliverables():
    header("Deliverables")
    st.caption("The six objectives from the problem statement, what this build actually "
               "provides for each, and how that claim is checked. Nothing here is a plan — "
               "every row is running in the app you are looking at.")

    done = sum(1 for row in DL.DELIVERY if row["status"].startswith("Delivered"))
    cols = st.columns(4)
    cols[0].metric("Objectives met", "%d/%d" % (done, len(DL.DELIVERY)))
    cols[1].metric("Automated tests", DL.test_count() or "—")
    cols[2].metric("Execution backends", len(BK.BACKENDS))
    cols[3].metric("SDK dialects", 4)
    st.caption("The test count is read from `tests/` at page load, so it cannot drift from the "
               "suite; `test_backends.py` runs a further agreement sweep over every installed "
               "SDK on top of it. `Execution backends` counts only what is installed here.")

    st.divider()
    st.subheader("Delivery table")
    for row in DL.DELIVERY:
        tone = "good" if row["status"] == "Delivered" else "on"
        st.markdown(
            '<div class="qf-card"><h4>%s &nbsp;·&nbsp; %s</h4>'
            '<p>%s</p></div>' % (row["id"], row["ask"], _inline_code(row["got"])),
            unsafe_allow_html=True)
        chips([(row["evidence"], ""), (row["status"], tone)])
        st.write("")

    st.divider()
    st.subheader("How each claim is verified")
    st.caption("Run it yourself: `python run_tests.py`. These are assertions in "
               "`tests/`, not screenshots.")
    html_table(["Claim", "What the test asserts"], DL.VERIFICATION, ["30%", "70%"])

    st.divider()
    storage = DBX.describe()
    st.markdown('<span class="qf-eyebrow">Storage in use right now</span>',
                unsafe_allow_html=True)
    st.caption("**%s** — %s  \n%s" % (storage["backend"], storage["target"], storage["note"]))

    st.subheader("Built since the first prototype")
    st.caption("Four of the original phase-two items have landed. The third column is the "
               "evidence, not a claim — and where verification stops, it says so.")
    html_table(["Item", "What it does", "How it is verified"],
               DL.SHIPPED_SINCE, ["18%", "44%", "38%"])

    st.subheader("Not built yet — and honestly why")
    st.caption("A prototype that claims everything is a prototype nobody can check. "
               "These are the items deliberately left for phase two.")
    html_table(["Item", "What it would add", "Why it is not here yet"],
               DL.PHASE_2, ["20%", "40%", "40%"])

    st.divider()
    st.subheader("Suggested demo order")
    st.caption("Eight steps, about five minutes, in the order that makes the platform "
               "prove itself.")
    for i, (step, note) in enumerate(DL.DEMO_ORDER, 1):
        st.markdown('<div class="qf-card"><h4>%d. %s</h4><p>%s</p></div>' % (i, step, note),
                    unsafe_allow_html=True)


def quiz_block(question: CT.Question, key: str, number: int | None = None):
    """One multiple-choice question, with teaching feedback and retries.

    A wrong answer is the most useful moment in a lesson, so it gets the fullest
    explanation: which option was right, and why the chosen one is not.  The
    question then unlocks so the learner can try again — the first attempt is
    still what the accuracy figures elsewhere are computed from, so retrying
    cannot inflate them.
    """
    label = "Check yourself" if number is None else "Question %d" % number
    mastered = bool(PROGRESS.get("mastered", {}).get(key))
    st.markdown('<span class="qf-eyebrow">%s%s</span>'
                % (label, "  ·  solved" if mastered else ""), unsafe_allow_html=True)
    st.markdown("**%s**" % question.prompt)

    wrong = SS.wrong_answers.get(key)          # index of the last wrong pick

    if mastered:
        st.success("Correct — %s" % question.why)
        return True

    choice = st.radio("Answer", question.options, key="q-" + key, index=None,
                      label_visibility="collapsed")

    if wrong is not None:
        st.error(
            "**Not quite.** You chose *%s*.\n\n"
            "**The correct answer is: %s**\n\n%s\n\n"
            "Pick again when you are ready — the question stays open until you get it."
            % (question.options[wrong], question.options[question.answer], question.why))

    if choice is not None and st.button("Submit answer", key="qs-" + key):
        picked = question.options.index(choice)
        correct = picked == question.answer
        # first attempt only — this is what the accuracy meters read
        ST.record_quiz(PROGRESS, key, correct, question.topic, xp=15)
        if correct:
            SS.wrong_answers.pop(key, None)
            if ST.record_mastery(PROGRESS, key):
                ST.add_xp(PROGRESS, 5)
        else:
            SS.wrong_answers[key] = picked
        st.rerun()
    return False


def lesson_index():
    """The contents page. Reading a lesson replaces this entirely.

    The list used to sit in a column beside the text, which meant the prose ran
    in a narrow gutter and the navigation competed with the thing being read.
    Index and reading view are now separate screens.
    """
    header("Lessons")
    done_count = len(PROGRESS["lessons"])
    st.progress(done_count / len(CT.LESSONS),
                text="%d of %d lessons complete" % (done_count, len(CT.LESSONS)))
    st.write("")

    current = SS.get("lesson", CT.LESSONS[0].id)
    for track in CT.TRACKS:
        st.markdown('<span class="qf-eyebrow">%s</span>' % track.name, unsafe_allow_html=True)
        st.caption(track.blurb)
        lessons = [l for l in CT.LESSONS if l.track == track.id]
        for row_start in range(0, len(lessons), 3):
            cols = st.columns(3)
            for col, lesson in zip(cols, lessons[row_start:row_start + 3]):
                done = lesson.id in PROGRESS["lessons"]
                cls = "done" if done else ("now" if lesson.id == current else "")
                with col:
                    st.markdown(
                        '<div class="qf-tile %s"><b>%s%s</b>'
                        '<span>%d min · %d question%s</span></div>'
                        % (cls, "✓ " if done else "", lesson.title,
                           lesson.minutes, len(lesson.quiz),
                           "" if len(lesson.quiz) == 1 else "s"),
                        unsafe_allow_html=True)
                    if st.button("Open", key="ln-" + lesson.id, **WIDE):
                        SS.lesson = lesson.id
                        SS.reading = True
                        st.rerun()
        st.write("")


def page_lessons():
    if not SS.get("reading"):
        lesson_index()
        return

    lesson = CT.LESSON_BY_ID.get(SS.lesson, CT.LESSONS[0])
    index = CT.LESSONS.index(lesson)

    bar = st.columns([1.1, 4.2, 1.1])
    if bar[0].button("← All lessons", key="back-index", **WIDE):
        SS.reading = False
        st.rerun()
    bar[1].markdown(
        '<div class="qf-crumb"><span>%s</span><span>·</span><span>lesson %d of %d</span>'
        '<span>·</span><span>%d min read</span></div>'
        % (CT.TRACK_BY_ID[lesson.track].name, index + 1, len(CT.LESSONS), lesson.minutes),
        unsafe_allow_html=True)
    if index + 1 < len(CT.LESSONS):
        if bar[2].button("Next →", key="skip-next", **WIDE):
            SS.lesson = CT.LESSONS[index + 1].id
            st.rerun()

    left, right = st.columns([5.4, 0.6])
    with left:
        st.markdown('<div class="qf-read">', unsafe_allow_html=True)
        st.header(lesson.title)
        render_prose(lesson.body)

        demo = lesson.demo()
        st.markdown('<span class="qf-eyebrow">Demo circuit</span>', unsafe_allow_html=True)
        draw("circuit", demo.to_dict(), None, stretch=False)
        st.caption(T.describe_state(E.statevector(demo), demo.qubits))
        if st.button("Open this circuit in the Studio", key="demo-" + lesson.id):
            set_circuit(lesson.demo())
            goto("Circuit Studio")

        if lesson.quiz:
            st.divider()
            st.markdown('<span class="qf-eyebrow">Before you move on</span>',
                        unsafe_allow_html=True)
            st.caption("Answer all %d correctly to unlock the next lesson. A wrong "
                       "answer is explained and then reopened — there is no penalty "
                       "for trying again." % len(lesson.quiz))
        solved = 0
        for i, question in enumerate(lesson.quiz):
            st.divider()
            if quiz_block(question, "lesson:%s:%d" % (lesson.id, i), number=i + 1):
                solved += 1

        st.divider()
        total = len(lesson.quiz)
        if total:
            st.progress(solved / total, text="%d of %d answered correctly" % (solved, total))
        ready = ST.lesson_mastered(PROGRESS, lesson.id, total)
        done = lesson.id in PROGRESS["lessons"]
        index = CT.LESSONS.index(lesson)
        last = index + 1 >= len(CT.LESSONS)

        if not ready:
            st.button("Answer all %d questions to continue" % total, disabled=True,
                      key="locked-" + lesson.id)
            st.caption("Stuck on one? Ask the tutor on the right — it will explain the "
                       "idea in plain language.")
        else:
            caption = "Next lesson" if done or last else "Mark complete and continue"
            if st.button(caption, type="primary", key="next-" + lesson.id):
                if not done:
                    PROGRESS["lessons"][lesson.id] = True
                    ST.add_xp(PROGRESS, 30)
                    st.toast("+30 XP")
                if last:
                    SS.reading = False          # end of the track — back to contents
                else:
                    SS.lesson = CT.LESSONS[index + 1].id
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)


def algorithm_detail(detail: CT.AlgoDetail):
    """The long-form explanation of one library algorithm.

    Deliberately always the same four sections in the same order — a learner
    comparing two algorithms should find the worked example in the same place
    both times.
    """
    st.markdown('<span class="qf-eyebrow">What it does</span>', unsafe_allow_html=True)
    st.markdown(detail.what)

    st.markdown('<span class="qf-eyebrow">How it works</span>', unsafe_allow_html=True)
    for i, step in enumerate(detail.how, 1):
        st.markdown("**%d.**  %s" % (i, step))

    st.markdown('<span class="qf-eyebrow">Worked example</span>', unsafe_allow_html=True)
    st.markdown(detail.example)

    st.markdown('<span class="qf-eyebrow">Why it matters</span>', unsafe_allow_html=True)
    st.markdown(detail.why)


def page_library():
    header("Algorithm library")
    st.caption("Each of these loads straight into the Studio, where you can take it apart gate "
               "by gate, ask the tutor to walk you through it, and export it to any of the four "
               "SDK dialects.")
    tags = sorted({a.tag for a in C.LIBRARY})
    for tag in tags:
        st.subheader(tag)
        for algorithm in [a for a in C.LIBRARY if a.tag == tag]:
            circuit = algorithm.make()
            with st.container(border=True):
                cols = st.columns([2, 1.1])
                with cols[0]:
                    st.markdown("**%s**" % algorithm.name)
                    st.caption(algorithm.blurb)
                    chips([(algorithm.level, ""), ("%d qubits" % circuit.qubits, ""),
                           ("depth %d" % circuit.depth, ""),
                           ("%d gates" % circuit.gate_count, "")])
                    if st.button("Load in the Studio", key="alg-" + algorithm.id):
                        set_circuit(algorithm.make())
                        goto("Circuit Studio")
                with cols[1]:
                    draw("circuit", circuit.to_dict(), None, stretch=False)

                detail = CT.ALGO_DETAIL.get(algorithm.id)
                if detail is not None:
                    with st.expander("How it works, step by step"):
                        algorithm_detail(detail)


def share_panel(circuit: C.Circuit):
    """Join or open a shared room for this circuit.

    Polling, not websockets — so it is labelled as polling. The refresh runs
    on a timer while a room is joined; a write that lost a race is reported
    rather than silently dropped.
    """
    user = SS.get("user")
    with st.expander("Share this circuit  ·  live room", expanded=bool(SS.get("room"))):
        st.caption("Everyone in the room sees the same circuit. Changes land in about a "
                   "second — this is a shared session with conflict detection, not "
                   "sub-second co-editing.")
        if SS.get("room"):
            room_body(circuit, user)
            return

        cols = st.columns([1.4, 1])
        with cols[0]:
            code = st.text_input("Room code", key="room-code",
                                 placeholder="6 letters, e.g. KJ4TQM").strip().upper()
            if st.button("Join room", key="room-join", **WIDE) and code:
                room = CO.get_room(code)
                if room is None:
                    st.error("No room with that code.")
                else:
                    SS.room = room.code
                    SS.room_version = room.version
                    set_circuit(C.Circuit.from_dict(room.circuit))
                    st.rerun()
        with cols[1]:
            title = st.text_input("Title", key="room-title", placeholder="Bell pair demo")
            if st.button("Open a room", key="room-new", **WIDE):
                room = CO.create_room(title or "Shared circuit", circuit.to_dict(),
                                      owner_id=user.id if user else None,
                                      cohort_id=user.cohort_id if user else None)
                SS.room = room.code
                SS.room_version = room.version
                st.rerun()


def room_body(circuit: C.Circuit, user):
    code = SS.room
    room = CO.get_room(code)
    if room is None:
        SS.room = None
        st.warning("That room has gone.")
        return
    if user is not None:
        CO.heartbeat(code, user.id)

    owner = user is not None and room.owner_id == user.id
    head = st.columns([1.1, 1.5, 1])
    head[0].markdown('<span class="qf-live"></span><span class="mono"><b>%s</b></span>'
                     % code, unsafe_allow_html=True)
    here = CO.who_is_here(code)
    head[1].caption("%d here: %s" % (len(here), ", ".join(p["display"] for p in here) or "—"))
    if owner:
        if head[2].toggle("Broadcast", value=room.locked, key="room-lock",
                          help="Locked: only you can change the circuit. Everyone else "
                               "follows along.") != room.locked:
            CO.set_lock(code, not room.locked, user.id)
            st.rerun()
    elif room.locked:
        head[2].caption("🔒 broadcast")

    bar = st.columns(3)
    if bar[0].button("Pull latest", key="room-pull", **WIDE):
        SS.room_version = room.version
        set_circuit(C.Circuit.from_dict(room.circuit))
        st.rerun()
    if bar[1].button("Push mine", key="room-push", **WIDE):
        ok, current = CO.push(code, circuit.to_dict(), SS.get("room_version", room.version),
                              user_id=user.id if user else None)
        if ok:
            SS.room_version = current.version
            st.success("Shared.")
        elif current.locked:
            st.warning("The room is in broadcast mode — only the owner can change it.")
        else:
            st.error("Someone else changed the room first. Pull latest, then push again — "
                     "your edit was not applied and theirs was not overwritten.")
        st.rerun()
    if bar[2].button("Leave", key="room-leave", **WIDE):
        SS.room = None
        st.rerun()

    if room.version != SS.get("room_version"):
        st.info("The room has moved on (version %d, you have %d). Pull latest to catch up."
                % (room.version, SS.get("room_version", 0)))

    log = CO.history(code, 5)
    if log:
        st.caption(" · ".join("%s edited" % h["display"] for h in log))


def drag_canvas(circuit: C.Circuit):
    """The drag-and-drop builder, above the read-only diagram.

    The canvas is a browser-side component, so it holds its own working copy
    and only hands a circuit back when the learner presses Apply.  That keeps a
    rerun caused by any other widget from discarding half-finished edits.
    """
    edited = DND.canvas(circuit.to_dict(), key="dnd-%d" % circuit.qubits)
    if edited and edited.get("stamp") != SS.get("dnd_stamp"):
        SS.dnd_stamp = edited.get("stamp")
        try:
            rebuilt = C.Circuit.from_dict(
                {"qubits": edited["qubits"], "ops": edited["ops"]})
        except (KeyError, TypeError, ValueError) as exc:          # noqa: BLE001
            st.error("Could not read the canvas circuit: %s" % exc)
            return
        set_circuit(rebuilt)
        st.rerun()


def studio_body(circuit: C.Circuit, challenge=None):
    left, right = st.columns([1.55, 1])
    with left:
        toolbar(circuit)
        share_panel(circuit)
        drag_canvas(circuit)
        draw("circuit", circuit.to_dict(), SS.selected, stretch=False)
        draw("legend", stretch=False)
        editor, inspect = st.columns(2)
        with editor:
            gate_adder(circuit)
        with inspect:
            inspector(circuit)
        if challenge is None:
            st.divider()
            code_panel(circuit)
    with right:
        result = current_result()
        results_panel(result)
        # The tutor used to sit here.  It is now docked to the right of every
        # page instead, so it stays with the learner when they leave the Studio.
    return result


def page_studio():
    header("Circuit Studio")
    studio_body(SS.circuit)


def grade(challenge: CT.Challenge):
    circuit = SS.circuit
    if circuit.qubits != challenge.qubits:
        return False, ("This challenge is set on %d qubit%s; your circuit has %d."
                       % (challenge.qubits, "" if challenge.qubits == 1 else "s", circuit.qubits))
    used = sorted({o.name for o in circuit.ops if o.name in challenge.banned})
    if used:
        return False, ("This one bars %s — your circuit uses %s."
                       % (", ".join(challenge.banned), ", ".join(used)))
    if challenge.max_two_qubit is not None and circuit.two_qubit_count > challenge.max_two_qubit:
        return False, ("Limit is %d two-qubit gates; this circuit has %d."
                       % (challenge.max_two_qubit, circuit.two_qubit_count))
    if not circuit.without_measurements().ops:
        return False, "The circuit is empty."
    score = challenge.score(E.statevector(circuit))
    if score >= 0.999:
        return True, ("Fidelity with the target state is %.4f. Depth %d, %d gates."
                      % (score, circuit.depth, circuit.gate_count))
    tail = ("The state is nearly orthogonal to the target, so the structure is off rather than "
            "the details." if score < 0.05 else
            "You are close — check phases and gate order." if score > 0.5 else
            "Partly there. Compare the amplitude table against what the task describes.")
    return False, "Fidelity with the target is %.4f — you need 0.999. %s" % (score, tail)


def page_challenges():
    header("Challenges")
    if SS.challenge is None:
        st.caption("Each challenge is graded by comparing the state your circuit produces against "
                   "the target, up to global phase — so any correct construction passes, not just "
                   "the one we had in mind.")
        for challenge in CT.CHALLENGES:
            solved = challenge.id in PROGRESS["challenges"]
            with st.container(border=True):
                cols = st.columns([3, 1])
                with cols[0]:
                    st.markdown("**%s**" % challenge.title)
                    st.caption(challenge.brief)
                    chips([("solved", "good")] if solved else [(challenge.level, "")])
                with cols[1]:
                    st.markdown('<span class="qf-chip">%d XP</span>' % challenge.xp,
                                unsafe_allow_html=True)
                    if st.button("Open", key="ch-" + challenge.id, **WIDE):
                        set_circuit(C.Circuit(challenge.qubits, []))
                        SS.challenge = challenge.id
                        st.rerun()
        return

    challenge = CT.CHALLENGE_BY_ID[SS.challenge]
    if st.button("← All challenges"):
        SS.challenge = None
        SS.grade = None
        st.rerun()

    with st.container(border=True):
        st.subheader(challenge.title)
        st.write(challenge.brief)
        constraints = ["Exactly %d qubit%s" % (challenge.qubits, "" if challenge.qubits == 1 else "s")]
        if challenge.banned:
            constraints.append("Not allowed: " + ", ".join(challenge.banned))
        if challenge.max_two_qubit is not None:
            constraints.append("At most %d two-qubit gates" % challenge.max_two_qubit)
        chips([(c, "") for c in constraints]
              + ([("solved", "good")] if challenge.id in PROGRESS["challenges"] else []))
        cols = st.columns([1, 1, 4])
        if cols[0].button("Submit", type="primary", **WIDE):
            ok, message = grade(challenge)
            SS.grade = (ok, message)
            if ok and challenge.id not in PROGRESS["challenges"]:
                PROGRESS["challenges"][challenge.id] = challenge.xp
                ST.add_xp(PROGRESS, challenge.xp)
                SS.grade = (True, message + "  +%d XP." % challenge.xp)
            st.rerun()
        if cols[1].button("Hint", **WIDE):
            st.toast(challenge.hint)
    if SS.grade:
        (st.success if SS.grade[0] else st.error)(SS.grade[1])

    studio_body(SS.circuit, challenge=challenge)


def page_assessment():
    header("Assessment")
    quiz = SS.quiz
    if quiz is None:
        st.caption("Eight questions drawn from a bank of %d across foundations, gates, "
                   "entanglement, algorithms and hardware. Every answer comes with the "
                   "reasoning, and results feed the mastery model on your progress page."
                   % len(CT.QUIZ_BANK))
        topics = {}
        for question in CT.QUIZ_BANK:
            topics[question.topic] = topics.get(question.topic, 0) + 1
        chips([("%s · %d" % (t, n), "") for t, n in sorted(topics.items())])
        st.write("")
        if st.button("Start assessment", type="primary"):
            pool = random.sample(CT.QUIZ_BANK, 8)
            SS.quiz = {"pool": pool, "i": 0, "right": 0, "answers": [],
                       "revealed": None, "chosen": None}
            st.rerun()

        history = [(k, v) for k, v in PROGRESS["quiz"].items() if k.startswith("assess:")]
        if history:
            st.divider()
            st.subheader("Your record")
            by_topic = {}
            for _, record in history:
                bucket = by_topic.setdefault(record["topic"], [0, 0])
                bucket[1] += 1
                bucket[0] += 1 if record["correct"] else 0
            draw("completion", [t for t in by_topic],
                 [v[0] / v[1] for v in by_topic.values()], stretch=False)
        return

    pool = quiz["pool"]
    if quiz["i"] >= len(pool):
        score = quiz["right"] / len(pool)
        st.header("%d out of %d" % (quiz["right"], len(pool)))
        st.write("A clean sweep. Try the advanced challenges next." if score == 1 else
                 "Solid. The misses below are the ones worth rereading." if score >= 0.75 else
                 "Worth a second pass through the lessons on the topics you missed.")
        for question, correct in quiz["answers"]:
            with st.container(border=True):
                chips([("right", "good")] if correct else [("wrong", "crit")])
                st.markdown("**%s**" % question.prompt)
                st.caption(question.why)
        cols = st.columns(2)
        if cols[0].button("Back to assessment", type="primary"):
            SS.quiz = None
            st.rerun()
        if cols[1].button("See my progress"):
            SS.quiz = None
            goto("My progress")
        return

    question = pool[quiz["i"]]
    st.markdown('<span class="qf-eyebrow">Question %d of %d · %s</span>'
                % (quiz["i"] + 1, len(pool), question.topic), unsafe_allow_html=True)
    st.progress(quiz["i"] / len(pool))
    st.subheader(question.prompt)

    if quiz["revealed"] is None:
        choice = st.radio("Answer", question.options, index=None, key="aq-%d" % quiz["i"],
                          label_visibility="collapsed")
        if choice is not None and st.button("Submit answer", type="primary"):
            chosen = question.options.index(choice)
            correct = chosen == question.answer
            quiz["revealed"] = correct
            quiz["chosen"] = chosen
            quiz["answers"].append((question, correct))
            quiz["right"] += 1 if correct else 0
            ST.record_quiz(PROGRESS, "assess:%d:%s" % (quiz["i"], question.prompt[:18]),
                           correct, question.topic)
            st.rerun()
    else:
        for i, option in enumerate(question.options):
            if i == question.answer:
                mark = "✅"
            elif i == quiz.get("chosen"):
                mark = "❌"
            else:
                mark = "▫️"
            st.markdown("%s &nbsp;%s" % (mark, option), unsafe_allow_html=True)
        (st.success if quiz["revealed"] else st.error)(question.why)
        if st.button("Next question" if quiz["i"] + 1 < len(pool) else "See results",
                     type="primary"):
            quiz["i"] += 1
            quiz["revealed"] = None
            quiz["chosen"] = None
            st.rerun()


def profile_card():
    """Who is signed in, and what this installation knows about them."""
    user = SS.get("user")
    if user is None:
        return
    xp = PROGRESS["xp"]
    level = ST.level(xp)
    initials = "".join(part[0] for part in user.display.split()[:2]).upper() or "?"

    # Identity only — Level, XP and the rest are already in the metric row that
    # follows, and repeating them here just made the page look padded.
    cols = st.columns([0.62, 3.2, 1.2])
    cols[0].markdown(
        '<div style="width:58px;height:58px;border-radius:50%%;'
        'background:linear-gradient(140deg,#12707A,#0C3D57);border:1px solid #1E8D98;'
        'display:flex;align-items:center;justify-content:center;font-family:IBM Plex Mono,'
        'monospace;font-size:1.2rem;color:#EAFDFD;letter-spacing:.04em">%s</div>' % initials,
        unsafe_allow_html=True)
    with cols[1]:
        st.markdown("### %s" % user.display)
        st.caption("`%s` · %s%s · level %d"
                   % (user.username, user.role,
                      (" · " + user.cohort_name) if user.cohort_name else "", level))
    with cols[2]:
        if st.button("Sign out", key="prof-out", **WIDE):
            AC.save_progress(user.id, PROGRESS)
            SS.user = None
            SS.pop("progress_saved", None)
            SS.progress = ST.blank()
            st.rerun()

    assigned = []
    if user.cohort_id:
        assigned = list(AC.assignments(user.cohort_id))
    if assigned:
        st.markdown('<span class="qf-eyebrow">Assigned to you</span>', unsafe_allow_html=True)
        for row in assigned:
            if row["kind"] == "lesson":
                item = CT.LESSON_BY_ID.get(row["item_id"])
                label = item.title if item else row["item_id"]
            else:
                item = CT.CHALLENGE_BY_ID.get(row["item_id"])
                label = item.title if item else row["item_id"]
            done = (row["item_id"] in PROGRESS["lessons"] if row["kind"] == "lesson"
                    else row["item_id"] in PROGRESS["challenges"])
            st.markdown("%s **%s**%s" % ("✓" if done else "○", label,
                                         ("  ·  due %s" % row["due"]) if row["due"] else ""))
    st.divider()


def page_progress():
    header("My progress")
    profile_card()
    xp = PROGRESS["xp"]
    lvl = ST.level(xp)
    cols = st.columns(5)
    cols[0].metric("Level", lvl)
    cols[1].metric("XP", xp)
    cols[2].metric("To next level", ST.level_floor(lvl + 1) - xp)
    cols[3].metric("Active days", len(PROGRESS["days"]))
    cols[4].metric("Circuits run", PROGRESS.get("runs", 0))

    st.divider()
    st.subheader("Mastery")
    rows = ST.mastery(PROGRESS)
    draw("completion", ["%s (%s)" % (r["name"], r["detail"]) for r in rows],
         [r["value"] for r in rows], stretch=False)

    st.subheader("What to do next")
    for i, rec in enumerate(T.recommend(PROGRESS)):
        with st.container(border=True):
            st.markdown("**%s**" % rec.title)
            st.caption(rec.why)
            if rec.goto and st.button("Open", key="pg-rec-%d" % i):
                goto(rec.goto["page"], **{k: v for k, v in rec.goto.items() if k != "page"})

    st.subheader("Challenges")
    st.dataframe([{"Challenge": c.title, "Level": c.level, "XP": c.xp,
                   "Status": "solved" if c.id in PROGRESS["challenges"] else "open"}
                  for c in CT.CHALLENGES], hide_index=True, **WIDE)

    st.divider()
    st.caption("Progress is stored in `%s`. In a deployed installation this is the seam where "
               "the platform would sync to a learner-record service." % ST.PROGRESS_PATH)
    if st.button("Reset progress"):
        SS.progress = ST.reset()
        st.rerun()


def cohort_console(user):
    """Real cohorts, real rosters, real exports — as opposed to the demo table."""
    st.markdown('<span class="qf-eyebrow">Cohorts</span>', unsafe_allow_html=True)
    cohorts = AC.cohorts()
    if not cohorts:
        st.caption("No cohorts yet. Create one and import a roster to begin.")

    names = [c["name"] for c in cohorts]
    chosen = st.selectbox("Cohort", names, key="coh-pick") if names else None
    row = next((c for c in cohorts if c["name"] == chosen), None)
    cohort_id = row["id"] if row is not None else None

    if row is not None:
        code = AC.cohort_code(int(cohort_id))
        if code:
            st.markdown(
                '<div class="qf-card"><h4>Classroom code</h4>'
                '<p style="font-size:1.6rem;letter-spacing:.22em;font-family:monospace">'
                '%s</p><p>Give this to your students. Anyone who signs up as a Student '
                'with this code joins <b>%s</b> straight away.</p></div>'
                % (code, chosen), unsafe_allow_html=True)
        else:
            st.warning("This cohort has no classroom code yet, so students cannot "
                       "join it by themselves.")
            if st.button("Create a classroom code", key="coh-code-gen"):
                AC.set_cohort_code(int(cohort_id), AC.generate_code())
                st.rerun()

    with st.expander("Create a cohort or import a roster"):
        new_name = st.text_input("New cohort name", key="coh-new")
        new_code = st.text_input("Classroom code (leave blank and one is made for you)",
                                 key="coh-newcode", placeholder="QB7K2M")
        if st.button("Create", key="coh-create") and new_name.strip():
            wanted = AC.normalise_code(new_code) or AC.generate_code()
            clash = AC.cohort_by_code(wanted)
            if clash is not None:
                st.error("That classroom code is already in use. Choose another.")
            else:
                cid = AC.create_cohort(new_name, wanted, user.id)
                AC.set_cohort_code(cid, wanted)
                st.rerun()
        st.caption("Roster CSV needs a `username` column; `display` is optional. Temporary "
                   "passwords are generated and shown once — they cannot be recovered "
                   "afterwards, only reset.")
        uploaded = st.file_uploader("Roster CSV", type=["csv"], key="coh-csv")
        if uploaded is not None and chosen and st.button("Import", key="coh-import"):
            report = AC.import_roster(uploaded.getvalue().decode("utf-8"), chosen)
            if report["created"]:
                st.success("Created %d accounts." % len(report["created"]))
                st.dataframe(report["created"], hide_index=True, **WIDE)
            if report["skipped"]:
                st.warning("Already existed: %s" % ", ".join(report["skipped"]))
            for err in report["errors"]:
                st.error(err)

    if cohort_id is None:
        return

    rows = AC.cohort_progress(cohort_id)
    if not rows:
        st.caption("No learners in this cohort yet.")
        return

    st.markdown('<span class="qf-eyebrow">Roster</span>', unsafe_allow_html=True)
    enriched = LMS.enrich(rows, len(CT.LESSONS), len(CT.CHALLENGES))
    html_table(["Learner", "XP", "Lessons", "Accuracy", "Score", "Last active"],
               [[r["display"], r["xp"], r["lessons"], "%.0f%%" % r["accuracy_pct"],
                 "%.1f%%" % r["score_pct"], r["updated_iso"]] for r in enriched],
               ["30%", "10%", "12%", "14%", "12%", "22%"])

    st.markdown('<span class="qf-eyebrow">Assign work</span>', unsafe_allow_html=True)
    cols = st.columns([2, 2, 1])
    kind = cols[0].selectbox("Kind", ["lesson", "challenge"], key="as-kind")
    items = ([(l.id, l.title) for l in CT.LESSONS] if kind == "lesson"
             else [(c.id, c.title) for c in CT.CHALLENGES])
    label = cols[1].selectbox("Item", [t for _, t in items], key="as-item")
    item_id = next(i for i, t in items if t == label)
    due = cols[2].text_input("Due", placeholder="2026-10-01", key="as-due")
    if st.button("Assign", key="as-go"):
        AC.assign(cohort_id, kind, item_id, due, by=user.id if user else None)
        reached = NT.announce_assignment(cohort_id, kind, item_id, label, due,
                                         by=user.id if user else None)
        st.toast("Assigned. %d student%s notified." % (reached, "" if reached == 1 else "s"))
        st.rerun()
    current = AC.assignments(cohort_id)
    if current:
        html_table(["Kind", "Item", "Due"],
                   [[r["kind"], r["item_id"], r["due"] or "—"] for r in current],
                   ["20%", "55%", "25%"])

    st.markdown('<span class="qf-eyebrow">Export to your LMS</span>', unsafe_allow_html=True)
    st.caption("Score = half coverage (lessons and challenges completed), half first-attempt "
               "quiz accuracy. Spelled out because you will be asked to justify it.")
    cols = st.columns(2)
    cols[0].download_button(
        "Gradebook CSV", LMS.to_csv(rows, len(CT.LESSONS), len(CT.CHALLENGES)),
        file_name="qubuild-%s.csv" % chosen.replace(" ", "-"), mime="text/csv", **WIDE)
    package = LMS.scorm_package(rows, len(CT.LESSONS), len(CT.CHALLENGES),
                                title="QuBuild — %s" % chosen)
    report = LMS.validate_package(package)
    cols[1].download_button(
        "SCORM 1.2 package", package,
        file_name="qubuild-%s-scorm.zip" % chosen.replace(" ", "-"),
        mime="application/zip", disabled=not report["ok"], **WIDE)
    if report["ok"]:
        st.caption("Package re-opened and checked before download: manifest parses, "
                   "schemaversion 1.2, every declared resource present.")
    else:
        st.error("Package failed its own validation: %s" % "; ".join(report["errors"]))


NOTIF_ICON = {NT.ASSIGNMENT: "📌", NT.ROOM: "🔴", NT.ROSTER: "👥", NT.NOTE: "•"}


def page_notifications():
    header("Notifications")
    user = SS.get("user")
    if user is None:
        return

    rows = NT.for_user(user.id, limit=60)
    unread = [n for n in rows if n.unread]

    cols = st.columns([1, 1, 3])
    if cols[0].button("Mark all read", disabled=not unread, **WIDE):
        NT.mark_read(user.id)
        st.rerun()
    if cols[1].button("Clear read", disabled=len(rows) == len(unread), **WIDE):
        NT.clear(user.id, read_only=True)
        st.rerun()

    if not rows:
        st.info("Nothing yet. Work your instructor sets, and activity in a shared "
                "circuit room, both land here."
                if not user.is_instructor else
                "Nothing yet. When a shared circuit room goes live in your cohort, "
                "it appears here with who is editing what.")
        return

    st.caption("%d unread of %d" % (len(unread), len(rows)))
    for note in rows:
        icon = NOTIF_ICON.get(note.kind, "•")
        times = (" · %d times" % note.count) if note.count > 1 else ""
        st.markdown(
            '<div class="qf-issue" style="border-left:3px solid %s">'
            '<b>%s %s</b><p>%s<span style="color:#55627A"> — %s%s</span></p></div>'
            % ("#39DCDC" if note.unread else "#1B2537", icon, html.escape(note.title),
               html.escape(note.body), NT.ago(note.updated), times),
            unsafe_allow_html=True)
        row = st.columns([1, 1, 4])
        if note.link and note.link in PAGES and row[0].button(
                "Open " + note.link, key="nt-go-%d" % note.id, **WIDE):
            NT.mark_read(user.id, note.id)
            goto(note.link)
        if note.unread and row[1].button("Mark read", key="nt-rd-%d" % note.id, **WIDE):
            NT.mark_read(user.id, note.id)
            st.rerun()


def live_rooms_panel(user):
    """What is happening in shared circuits right now, and who is doing it."""
    st.markdown('<span class="qf-eyebrow">Live circuit rooms</span>',
                unsafe_allow_html=True)
    rooms = CO.live_rooms(user.cohort_id) if user.cohort_id else []
    if not rooms:
        st.caption("No room has been active in the last 15 minutes. When a student "
                   "opens a shared circuit, it appears here with every change as "
                   "it is made.")
        return

    for room in rooms:
        present = ", ".join(room["present"]) if room["present"] else "nobody right now"
        st.markdown(
            '<div class="qf-card"><h4>%s <span class="qf-chip">%s</span>%s</h4>'
            '<p>In the room: <b>%s</b> · version %d · last change %s</p></div>'
            % (html.escape(room["title"]), room["code"],
               ' <span class="qf-chip">broadcast</span>' if room["locked"] else "",
               html.escape(present), room["version"], NT.ago(room["updated"])),
            unsafe_allow_html=True)
        html_table(["Who", "What they did", "When"],
                   [[html.escape(h["display"]),
                     html.escape(h["detail"] or h["action"]),
                     NT.ago(h["at"])] for h in room["recent"]],
                   ["22%", "58%", "20%"])


def page_instructor():
    header("Instructor view")

    user = SS.get("user")
    if user is None or not user.is_instructor:
        # Not a redirect: a learner or a student has no business here at all,
        # and silently bouncing them somewhere else is more confusing than
        # saying so.
        st.info("This page belongs to instructors. Your work lives under "
                "**My progress**.")
        return

    cohort_console(user)
    st.divider()
    live_rooms_panel(user)
    st.divider()
    st.markdown('<span class="qf-eyebrow">Demonstration cohort</span>',
                unsafe_allow_html=True)

    st.warning("Demonstration cohort — 24 synthetic learners generated from a fixed seed so the "
               "view is stable. Your own row is real and comes from this installation.")
    rows = ST.cohort()
    average_lessons = sum(r["lessons"] for r in rows) / len(rows)
    average_accuracy = sum(r["accuracy"] for r in rows) / len(rows)
    at_risk = [r for r in rows if r["accuracy"] < 0.5 or r["days_since_active"] > 7]

    cols = st.columns(4)
    cols[0].metric("Learners", len(rows) + 1)
    cols[1].metric("Avg lessons", "%.1f" % average_lessons)
    cols[2].metric("Avg quiz accuracy", "%d%%" % round(average_accuracy * 100))
    cols[3].metric("Need attention", len(at_risk))

    st.divider()
    st.subheader("Completion by lesson")
    share = [sum(1 for r in rows if r["lessons"] > i) / len(rows) for i in range(len(CT.LESSONS))]
    draw("completion", [l.title for l in CT.LESSONS], share, stretch=False)

    st.subheader("Quiz accuracy distribution")
    draw("distribution", [r["accuracy"] for r in rows], stretch=False)

    st.subheader("Where the cohort is going wrong")
    st.caption("Ranked by how often the question is answered incorrectly. These are the concepts "
               "to spend class time on.")
    st.dataframe([{"Question": m["question"], "Topic": m["topic"],
                   "Miss rate": "%d%%" % round(m["miss_rate"] * 100)}
                  for m in ST.miss_rates()[:6]], hide_index=True, **WIDE)

    st.subheader("Roster")
    quiz = list(PROGRESS["quiz"].values())
    mine = {"Learner": "You (this installation)",
            "Lessons": "%d/%d" % (len(PROGRESS["lessons"]), len(CT.LESSONS)),
            "Challenges": "%d/%d" % (len(PROGRESS["challenges"]), len(CT.CHALLENGES)),
            "Quiz accuracy": ("%d%%" % round(100 * sum(1 for q in quiz if q["correct"]) / len(quiz))
                              if quiz else "—"),
            "XP": PROGRESS["xp"], "Last active": "today"}
    table = [mine] + [{"Learner": r["name"],
                       "Lessons": "%d/%d" % (r["lessons"], len(CT.LESSONS)),
                       "Challenges": "%d/%d" % (r["challenges"], len(CT.CHALLENGES)),
                       "Quiz accuracy": "%d%%" % round(r["accuracy"] * 100),
                       "XP": r["xp"],
                       "Last active": "today" if r["days_since_active"] == 0
                       else "%d days ago" % r["days_since_active"]} for r in rows]
    st.dataframe(table, hide_index=True, height=430, **WIDE)


# ==========================================================================
# main
# ==========================================================================

def sign_in_screen():
    """The whole app sits behind this.

    Progress, cohort membership and instructor assignments are all per-account,
    so there is no sensible anonymous mode any more.  The first account created
    on a fresh installation becomes the instructor — otherwise a new deployment
    would have no way to reach the cohort tools at all.
    """
    # Streamlit closes each markdown block, so a wrapper div cannot contain the
    # widgets that follow it — the column is what actually centres this.
    _, mid, _ = st.columns([1, 1.25, 1])
    st.markdown("", unsafe_allow_html=True)
    ctx = mid
    with ctx:
        st.markdown(
            '<div class="qf-gate">'
            '<div class="qf-eyebrow">Quantum studio</div>'
            '<p class="mark">QuBuild</p>'
            '<p class="tag">Quantum computing is not just faster computing &mdash; '
            'it&rsquo;s a new way of thinking, where wrong answers cancel each other '
            'out and the right one is what remains.</p></div>',
            unsafe_allow_html=True)

    with ctx:
        tabs = st.tabs(["Sign in", "Create account"])

    with tabs[0]:
        with st.form("gate-in"):
            username = st.text_input("Username", key="gi-u")
            password = st.text_input("Password", type="password", key="gi-p")
            if st.form_submit_button("Sign in", type="primary", **WIDE):
                user = AC.authenticate(username, password)
                if user is None:
                    st.error("Username or password is wrong.")
                else:
                    stored = AC.load_progress(user.id)
                    if stored:
                        SS.progress = stored
                    SS.user = user
                    SS.pop("progress_saved", None)
                    st.rerun()

    with tabs[1]:
        # The role picker sits outside the form on purpose: a form does not
        # re-run until it is submitted, so the classroom fields would never
        # appear if the radio lived inside it.
        label = st.radio(
            "I am joining as", list(ROLE_CHOICES), key="gu-role", horizontal=True,
            captions=[ROLE_CHOICES[k][1] for k in ROLE_CHOICES])
        role = ROLE_CHOICES[label][0]

        if role == "instructor" and not SS.get("gu-suggested"):
            # Generated once and kept, so it does not change under the
            # instructor's fingers on every rerun.
            SS["gu-suggested"] = AC.generate_code()

        with st.form("gate-up"):
            new_user = st.text_input("Choose a username", key="gu-u")
            display = st.text_input("Your name", key="gu-d")

            classroom, code = "", ""
            if role == "student":
                code = st.text_input(
                    "Classroom code", key="gu-code", placeholder="e.g. QB7K2M",
                    help="The code your instructor gave you. It puts you in their class.")
            elif role == "instructor":
                classroom = st.text_input("Class name", key="gu-class",
                                          placeholder="CSE-AIML-2A")
                code = st.text_input(
                    "Classroom code for your students", key="gu-code",
                    value=SS.get("gu-suggested", ""),
                    help="Students type this when they sign up, and land straight "
                         "in your class. Change it to anything you like.")

            pw1 = st.text_input("Password", type="password", key="gu-p1")
            pw2 = st.text_input("Confirm password", type="password", key="gu-p2")

            if st.form_submit_button("Create account", type="primary", **WIDE):
                if len(pw1) < 8:
                    st.error("Use at least 8 characters.")
                elif pw1 != pw2:
                    st.error("The two passwords do not match.")
                else:
                    user, why = AC.register(new_user, pw1, display, role,
                                            classroom=classroom, code=code)
                    if user is None:
                        st.error(why)
                    else:
                        SS.user = user
                        SS.pop("progress_saved", None)
                        SS.progress = ST.blank()
                        SS.page = "Overview"
                        SS.pop("gu-suggested", None)
                        st.rerun()

        if role == "student":
            st.caption("No code yet? Ask your instructor, or sign up as a Learner and "
                       "join a class later.")
        elif role == "instructor":
            st.caption("Write the classroom code on the board. Everyone who signs up "
                       "with it appears in your cohort automatically.")
        st.caption("Passwords are stored as salted scrypt hashes — never in plain text, "
                   "and never recoverable. A forgotten password is reset by an instructor.")


if SS.get("user") is None:
    sign_in_screen()
    st.stop()

sidebar()

PAGE_FUNCS = {
    "Overview": page_overview,
    "Deliverables": page_deliverables,
    "Lessons": page_lessons,
    "Algorithm library": page_library,
    "Circuit Studio": page_studio,
    "Challenges": page_challenges,
    "Assessment": page_assessment,
    "My progress": page_progress,
    "Instructor view": page_instructor,
    "Notifications": page_notifications,
}

PAGE_FUNCS[SS.page]()

# The account is the source of truth now, so mirror the working copy back after
# every interaction rather than only on sign-out — a closed tab should not cost
# a learner their session.  Most interactions change nothing about progress,
# though: clicking a tab, opening the sidebar, typing in the tutor box.  A
# fingerprint of the working copy decides whether a write is actually owed, so
# the database is touched when something happened and not on every click.
_snapshot = json.dumps(PROGRESS, sort_keys=True, default=str)
if SS.get("progress_saved") != _snapshot:
    AC.save_progress(SS.user.id, PROGRESS)
    SS.progress_saved = _snapshot

# The tutor is rendered last so it sits above the page in the stacking order,
# but it is positioned out of the document flow — the page above never moves.
tutor_rail()
