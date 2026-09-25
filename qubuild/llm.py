"""The language-model seam.

One function matters: :func:`complete`. Give it a question and some context
about the circuit on screen; it returns the model's answer, or ``None`` if no
model is configured or the call failed. ``None`` is not an error condition —
the tutor simply answers from its knowledge base instead, which is why a wrong
key degrades the app quietly rather than breaking it.

Everything the user is meant to change lives in ``config.py``. This module
only knows how to speak each provider's HTTP dialect.

urllib is used rather than ``requests`` so the language layer adds no
dependency: a clone with an empty ``config.py`` still installs with three
packages.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Optional, Tuple

from . import config as CFG

# Set by the last call to complete(); the sidebar shows it so a
# misconfigured key is visible instead of silently doing nothing.
LAST_ERROR: str = ""


# ==========================================================================
# status
# ==========================================================================

def status() -> dict:
    """What the app should display about the language layer."""
    resolved = CFG.resolve()
    provider = resolved["provider"]
    ready = bool(
        provider != "none"
        and not resolved["error"]
        and (resolved["key"] or provider in ("ollama", "custom"))
    )
    return dict(resolved, ready=ready, label=_LABEL.get(provider, provider),
                last_error=LAST_ERROR)


def is_configured() -> bool:
    return status()["ready"]


_LABEL = {
    "none": "Local knowledge base",
    "anthropic": "Anthropic Claude",
    "openai": "OpenAI",
    "gemini": "Google Gemini",
    "groq": "Groq",
    "openrouter": "OpenRouter",
    "ollama": "Ollama (local)",
    "custom": "Custom endpoint",
}


# ==========================================================================
# the one entry point
# ==========================================================================

def complete(question: str, context: Optional[dict] = None) -> Optional[str]:
    """Ask the configured model. Returns the answer, or None to fall back."""
    global LAST_ERROR
    state = CFG.resolve()
    provider = state["provider"]
    if provider == "none":
        return None
    if state["error"]:
        LAST_ERROR = state["error"]
        return None

    prompt = _with_context(question, context)
    try:
        url, headers, payload, pick = _build(provider, state, prompt)
    except ValueError as exc:
        LAST_ERROR = str(exc)
        return None

    request = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers}, method="POST")

    try:
        with urllib.request.urlopen(request, timeout=CFG.TIMEOUT) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        LAST_ERROR = _http_error(provider, exc)
        return None
    except urllib.error.URLError as exc:
        LAST_ERROR = ("Could not reach %s (%s). The tutor is answering from its "
                      "knowledge base instead." % (_LABEL.get(provider, provider), exc.reason))
        return None
    except (TimeoutError, OSError) as exc:
        LAST_ERROR = "The model did not answer in %ds (%s)." % (CFG.TIMEOUT, exc)
        return None
    except ValueError:
        LAST_ERROR = "The model returned something that was not JSON."
        return None

    try:
        text = pick(body)
    except (KeyError, IndexError, TypeError):
        text = ""
    if not text:
        LAST_ERROR = "The model replied, but with no usable text."
        return None

    LAST_ERROR = ""
    return text.strip()


def _http_error(provider: str, exc: urllib.error.HTTPError) -> str:
    """Turn a status code into something a student can act on."""
    try:
        detail = json.loads(exc.read().decode("utf-8"))
        detail = (detail.get("error", {}) or {}).get("message") or json.dumps(detail)[:200]
    except Exception:                                              # noqa: BLE001
        detail = exc.reason
    hint = {
        401: "The API key was rejected. Check API_KEY in qubuild/config.py.",
        403: "The key is valid but not allowed to use this model.",
        404: "That model name was not found. Check MODEL in qubuild/config.py.",
        429: "Rate limited, or the account is out of credit.",
    }.get(exc.code, "")
    return "%s returned HTTP %d. %s %s" % (_LABEL.get(provider, provider), exc.code, hint, detail)


# ==========================================================================
# prompt assembly
# ==========================================================================

def _with_context(question: str, context: Optional[dict]) -> str:
    """Give the model the circuit on screen, so answers are about *this* circuit."""
    if not context:
        return question
    lines = []
    if context.get("lesson"):
        lines.append("The student is reading the lesson '%s'." % context["lesson"])
    if context.get("lesson_body"):
        lines.append("That lesson says:\n" + str(context["lesson_body"]))
    if context.get("circuit"):
        lines.append("Circuit currently open: " + str(context["circuit"]))
    if context.get("qubits") is not None:
        lines.append("Qubits: %s   Depth: %s" % (context.get("qubits"), context.get("depth")))
    if context.get("state"):
        lines.append("Measurement outcomes: " + str(context["state"]))
    if context.get("page"):
        lines.append("The student is on the %s page." % context["page"])
    if not lines:
        return question
    return "%s\n\n---\nContext:\n%s" % (question, "\n".join(lines))


# ==========================================================================
# per-provider request shapes
# ==========================================================================

def _build(provider: str, state: dict, prompt: str) -> Tuple[str, dict, dict, callable]:
    """Return (url, headers, json payload, function that digs the text out)."""
    key, model = state["key"], state["model"]

    if provider == "anthropic":
        return (
            "https://api.anthropic.com/v1/messages",
            {"x-api-key": key, "anthropic-version": "2023-06-01"},
            {"model": model, "max_tokens": CFG.MAX_TOKENS, "temperature": CFG.TEMPERATURE,
             "system": CFG.SYSTEM_PROMPT,
             "messages": [{"role": "user", "content": prompt}]},
            lambda b: b["content"][0]["text"],
        )

    if provider in ("openai", "groq", "openrouter"):
        base = {
            "openai": "https://api.openai.com/v1",
            "groq": "https://api.groq.com/openai/v1",
            "openrouter": "https://openrouter.ai/api/v1",
        }[provider]
        return (
            base + "/chat/completions",
            {"Authorization": "Bearer " + key},
            {"model": model, "max_tokens": CFG.MAX_TOKENS, "temperature": CFG.TEMPERATURE,
             "messages": [{"role": "system", "content": CFG.SYSTEM_PROMPT},
                          {"role": "user", "content": prompt}]},
            lambda b: b["choices"][0]["message"]["content"],
        )

    if provider == "gemini":
        return (
            "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent?key=%s"
            % (model, key),
            {},
            {"systemInstruction": {"parts": [{"text": CFG.SYSTEM_PROMPT}]},
             "contents": [{"role": "user", "parts": [{"text": prompt}]}],
             "generationConfig": {"maxOutputTokens": CFG.MAX_TOKENS,
                                  "temperature": CFG.TEMPERATURE}},
            lambda b: b["candidates"][0]["content"]["parts"][0]["text"],
        )

    if provider == "ollama":
        return (
            CFG.OLLAMA_URL.rstrip("/") + "/api/chat",
            {},
            {"model": model, "stream": False,
             "options": {"temperature": CFG.TEMPERATURE, "num_predict": CFG.MAX_TOKENS},
             "messages": [{"role": "system", "content": CFG.SYSTEM_PROMPT},
                          {"role": "user", "content": prompt}]},
            lambda b: b["message"]["content"],
        )

    if provider == "custom":
        if not CFG.CUSTOM_URL:
            raise ValueError("PROVIDER is \"custom\" but CUSTOM_URL is empty in config.py.")
        return (
            CFG.CUSTOM_URL,
            dict(CFG.CUSTOM_HEADERS),
            {"question": prompt, "context": {}},
            lambda b: b.get("text") or b.get("answer") or "",
        )

    raise ValueError("Unknown provider %r in config.py." % provider)
