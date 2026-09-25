"""=========================================================================
   PUT YOUR API KEY HERE.  This is the only file you need to edit.
   =========================================================================

To turn on the AI tutor's language layer, set PROVIDER and API_KEY below,
save the file, and restart the app.  Nothing else in the project changes.

    PROVIDER = "anthropic"
    API_KEY  = "sk-ant-..."

Supported values for PROVIDER:

    "none"       the built-in knowledge base only (default, no key needed)
    "anthropic"  Claude          — key from console.anthropic.com
    "openai"     GPT             — key from platform.openai.com
    "gemini"     Google Gemini   — key from aistudio.google.com
    "groq"       Llama on Groq   — key from console.groq.com
    "openrouter" many models     — key from openrouter.ai
    "ollama"     a model running on your own machine — no key needed
    "custom"     your own service — see CUSTOM_URL at the bottom

The analysis layer — circuit walkthrough, error detection, optimisation,
recommendations — never uses any of this.  It is computed from your circuit
and runs with no key and no network.  A key only adds free-form Q&A.

-----------------------------------------------------------------------
SAFETY: a key written here is plain text in a file.  Do not commit this
file to a public GitHub repo and do not deploy the app publicly with a
key in it — anyone who can read the file can spend your credits.  For
anything shared, leave PROVIDER = "none" here and set the environment
variable QUBUILD_API_KEY instead (see OVERRIDES at the bottom).
-----------------------------------------------------------------------
"""

import json as _json
import os as _os
import stat as _stat

# ==========================================================================
#  1.  Pick a provider and paste your key
# ==========================================================================

PROVIDER = "none"

API_KEY = ""

# Leave MODEL empty to use the sensible default for your provider
# (listed in DEFAULT_MODEL below).  Override it if you want a specific one.
MODEL = ""


# ==========================================================================
#  2.  Optional knobs — the defaults are fine
# ==========================================================================

MAX_TOKENS = 700        # length cap on a single answer
TEMPERATURE = 0.3       # lower is more factual, higher is more creative
TIMEOUT = 30            # seconds to wait before giving up and answering locally

SYSTEM_PROMPT = (
    "You are the tutor inside QuBuild, a quantum computing learning platform. Your "
    "student is a beginner — usually an undergraduate meeting this material for the "
    "first time — so write for someone smart who does not yet know the vocabulary.\n"
    "\n"
    "How to answer:\n"
    "- Use everyday words. Say 'chance' before 'probability amplitude', 'undo' before "
    "'inverse', 'linked' before 'entangled'. Technical terms are fine, but define each "
    "one in plain language the first time you use it.\n"
    "- Start with a one-sentence direct answer, then explain.\n"
    "- Reach for a real-world comparison whenever it genuinely helps — a spinning coin, "
    "a dial, two speakers interfering, a globe being rotated. Say where the comparison "
    "breaks down; an analogy that is not corrected becomes a misconception.\n"
    "- If you write an equation, immediately explain what each symbol means. Never "
    "leave a symbol undefined.\n"
    "- Prefer concrete numbers over abstraction. '4 items, 1 iteration, 100% success' "
    "teaches more than 'O(sqrt N) queries'.\n"
    "- Keep it under 200 words unless the question genuinely needs more.\n"
    "- Use the state and circuit context you are given, and refer to what the student "
    "actually built.\n"
    "\n"
    "Conventions: QuBuild uses qubit 0 as the least significant bit and writes qubit 0 "
    "on the right of a bit string, matching Qiskit. If a claim depends on a convention, "
    "say which one.\n"
    "\n"
    "Be honest. If you are not sure of something, say so instead of inventing it, and "
    "do not oversell what quantum computers can do today — today's machines are noisy "
    "and have no proven commercial advantage yet. Encouragement is welcome; hype is not."
)

# Only used when PROVIDER = "custom".  QuBuild POSTs
#   {"question": ..., "context": {...}}
# and reads the answer from {"text": ...} or {"answer": ...}.
CUSTOM_URL = ""
CUSTOM_HEADERS = {}     # e.g. {"Authorization": "Bearer ..."}

# Only used when PROVIDER = "ollama".  Start Ollama first: `ollama serve`.
OLLAMA_URL = "http://localhost:11434"


# ==========================================================================
#  3.  Defaults and overrides — you can stop reading here
# ==========================================================================

DEFAULT_MODEL = {
    "anthropic": "claude-sonnet-4-5",
    "openai": "gpt-4o-mini",
    "gemini": "gemini-2.0-flash",
    "groq": "llama-3.3-70b-versatile",
    "openrouter": "anthropic/claude-3.5-sonnet",
    "ollama": "llama3.2",
    "custom": "",
    "none": "",
}

PROVIDERS = tuple(DEFAULT_MODEL)

# Where each provider's key normally lives, so QuBuild can pick up a key you
# have already set in your shell without you editing this file at all.
ENV_KEYS = {
    "anthropic": ("QUBUILD_API_KEY", "ANTHROPIC_API_KEY"),
    "openai": ("QUBUILD_API_KEY", "OPENAI_API_KEY"),
    "gemini": ("QUBUILD_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY"),
    "groq": ("QUBUILD_API_KEY", "GROQ_API_KEY"),
    "openrouter": ("QUBUILD_API_KEY", "OPENROUTER_API_KEY"),
    "custom": ("QUBUILD_API_KEY",),
    "ollama": (),
    "none": (),
}


# --------------------------------------------------------------------------
# settings saved from the sidebar
#
# Editing this file to add an API key is fine for a developer and hopeless for
# anyone demonstrating the app on a borrowed machine.  These three functions
# let the sidebar store the same three values in a local file instead, with
# owner-only permissions, so a key never has to be pasted into source.
# --------------------------------------------------------------------------

SETTINGS_PATH = _os.path.join(
    _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), ".tutor_model.json")


def load_saved() -> dict:
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as fh:
            data = _json.load(fh)
        return {"provider": str(data.get("provider", "")).strip(),
                "key": str(data.get("key", "")).strip(),
                "model": str(data.get("model", "")).strip()}
    except (OSError, ValueError, AttributeError):
        return {}


def save_settings(provider: str, key: str, model: str = "") -> bool:
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as fh:
            _json.dump({"provider": provider.strip(), "key": key.strip(),
                        "model": model.strip()}, fh)
        try:
            _os.chmod(SETTINGS_PATH, _stat.S_IRUSR | _stat.S_IWUSR)   # 0600
        except OSError:
            pass
        return True
    except OSError:
        return False


def clear_settings() -> None:
    try:
        _os.remove(SETTINGS_PATH)
    except OSError:
        pass


def apply_saved() -> bool:
    """Push a saved provider/key/model into the module globals resolve() reads."""
    global PROVIDER, API_KEY, MODEL
    saved = load_saved()
    if not saved.get("provider") or saved["provider"] == "none":
        return False
    PROVIDER = saved["provider"]
    API_KEY = saved.get("key", "")
    MODEL = saved.get("model", "")
    return True


def resolve():
    """Work out the live settings: environment variables beat this file.

    OVERRIDES, in order of priority:
      1. QUBUILD_PROVIDER / QUBUILD_API_KEY / QUBUILD_MODEL environment vars
      2. the provider's own conventional variable (ANTHROPIC_API_KEY, ...)
      3. what is written above

    This is what lets you keep a key out of the file for a shared or
    deployed copy while still editing the file for a local one.
    """
    import os

    provider = (os.environ.get("QUBUILD_PROVIDER") or PROVIDER or "none").strip().lower()
    if provider not in DEFAULT_MODEL:
        return dict(provider="none", key="", model="", error=(
            "config.py: PROVIDER is %r, which is not one of %s"
            % (provider, ", ".join(PROVIDERS))))

    key = (API_KEY or "").strip()
    for name in ENV_KEYS.get(provider, ()):
        key = (os.environ.get(name) or key).strip() or key
    # QUBUILD_API_KEY should win over the file even when the file has a value.
    key = (os.environ.get("QUBUILD_API_KEY") or key).strip()

    model = (os.environ.get("QUBUILD_MODEL") or MODEL or DEFAULT_MODEL[provider]).strip()

    error = ""
    if provider not in ("none", "ollama", "custom") and not key:
        error = ("config.py: PROVIDER is %r but API_KEY is empty — paste your key, "
                 "or set the QUBUILD_API_KEY environment variable." % provider)
    if provider == "custom" and not CUSTOM_URL:
        error = "config.py: PROVIDER is \"custom\" but CUSTOM_URL is empty."

    return dict(provider=provider, key=key, model=model, error=error)
