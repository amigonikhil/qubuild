"""The API-key seam.

The point of these tests is that a *misconfigured* key must never break the
app. Every failure path has to land back on the local knowledge base.
"""

import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qubuild import config as CFG    # noqa: E402
from qubuild import llm             # noqa: E402
from qubuild import tutor as T      # noqa: E402


def clear_env():
    for name in ("QUBUILD_PROVIDER", "QUBUILD_API_KEY", "QUBUILD_MODEL",
                 "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY",
                 "GEMINI_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY"):
        os.environ.pop(name, None)


def with_config(provider="none", key="", model=""):
    """Set config.py's module-level values the way a user editing the file would."""
    clear_env()
    CFG.PROVIDER, CFG.API_KEY, CFG.MODEL = provider, key, model
    llm.LAST_ERROR = ""


# ---- resolution -----------------------------------------------------------

def test_default_config_is_off():
    with_config()
    assert CFG.resolve()["provider"] == "none"
    assert not llm.is_configured()
    assert llm.complete("what is a qubit") is None


def test_key_in_the_file_turns_it_on():
    with_config("anthropic", "sk-ant-test")
    state = CFG.resolve()
    assert state["provider"] == "anthropic" and state["key"] == "sk-ant-test"
    assert not state["error"]
    assert llm.is_configured()


def test_default_model_is_filled_in():
    with_config("openai", "sk-test")
    assert CFG.resolve()["model"] == CFG.DEFAULT_MODEL["openai"]
    with_config("openai", "sk-test", "gpt-4o")
    assert CFG.resolve()["model"] == "gpt-4o"


def test_environment_beats_the_file():
    with_config("anthropic", "file-key")
    os.environ["QUBUILD_API_KEY"] = "env-key"
    assert CFG.resolve()["key"] == "env-key"
    os.environ["QUBUILD_PROVIDER"] = "groq"
    assert CFG.resolve()["provider"] == "groq"
    clear_env()


def test_providers_own_variable_is_picked_up():
    with_config("openai", "")
    os.environ["OPENAI_API_KEY"] = "sk-from-shell"
    assert CFG.resolve()["key"] == "sk-from-shell"
    assert not CFG.resolve()["error"]
    clear_env()


def test_provider_without_a_key_is_reported_not_crashed():
    with_config("anthropic", "")
    state = CFG.resolve()
    assert "API_KEY is empty" in state["error"]
    assert not llm.is_configured()
    assert llm.complete("hello") is None


def test_typo_in_provider_name_is_reported():
    with_config("anthropc", "sk-test")
    assert "not one of" in CFG.resolve()["error"]
    assert llm.complete("hello") is None


def test_ollama_and_custom_need_no_key():
    with_config("ollama")
    assert not CFG.resolve()["error"] and llm.is_configured()
    with_config("custom")
    assert "CUSTOM_URL is empty" in CFG.resolve()["error"]


# ---- request shapes -------------------------------------------------------

def test_every_provider_builds_a_valid_request():
    for provider in CFG.PROVIDERS:
        if provider == "none":
            continue
        if provider == "custom":
            CFG.CUSTOM_URL = "https://example.invalid/tutor"
        with_config(provider, "test-key")
        state = CFG.resolve()
        url, headers, payload, pick = llm._build(provider, state, "why is a Bell state entangled?")
        assert url.startswith("http"), provider
        json.dumps(payload)                       # must be serialisable
        assert callable(pick), provider
    CFG.CUSTOM_URL = ""


def test_the_key_travels_where_each_provider_expects_it():
    with_config("anthropic", "sk-ant-1")
    _, headers, _, _ = llm._build("anthropic", CFG.resolve(), "q")
    assert headers["x-api-key"] == "sk-ant-1"

    with_config("openai", "sk-oai-1")
    _, headers, _, _ = llm._build("openai", CFG.resolve(), "q")
    assert headers["Authorization"] == "Bearer sk-oai-1"

    with_config("gemini", "goog-1")
    url, _, _, _ = llm._build("gemini", CFG.resolve(), "q")
    assert url.endswith("key=goog-1")


def test_each_picker_reads_its_providers_real_response_shape():
    samples = {
        "anthropic": ({"content": [{"type": "text", "text": "answer A"}]}, "answer A"),
        "openai": ({"choices": [{"message": {"content": "answer B"}}]}, "answer B"),
        "gemini": ({"candidates": [{"content": {"parts": [{"text": "answer C"}]}}]}, "answer C"),
        "ollama": ({"message": {"content": "answer D"}}, "answer D"),
        "custom": ({"text": "answer E"}, "answer E"),
    }
    CFG.CUSTOM_URL = "https://example.invalid/tutor"
    for provider, (body, expected) in samples.items():
        with_config(provider, "k")
        _, _, _, pick = llm._build(provider, CFG.resolve(), "q")
        assert pick(body) == expected, provider
    CFG.CUSTOM_URL = ""


def test_context_reaches_the_prompt():
    prompt = llm._with_context("why 50/50?", {"circuit": "h q[0];", "qubits": 2,
                                              "depth": 1, "state": "00 50%, 11 50%"})
    assert "h q[0];" in prompt and "00 50%" in prompt and "why 50/50?" in prompt


# ---- failure must be survivable ------------------------------------------

class _Fail:
    """Stand-in for urlopen that raises whatever we hand it."""

    def __init__(self, exc):
        self.exc = exc

    def __call__(self, *args, **kwargs):
        raise self.exc


def _complete_with(exc):
    real = urllib.request.urlopen
    urllib.request.urlopen = _Fail(exc)
    try:
        return llm.complete("what is superposition?")
    finally:
        urllib.request.urlopen = real


def test_bad_key_falls_back_and_says_why():
    with_config("openai", "sk-wrong")
    err = urllib.error.HTTPError("u", 401, "Unauthorized", {}, None)
    assert _complete_with(err) is None
    assert "401" in llm.LAST_ERROR and "config.py" in llm.LAST_ERROR


def test_no_network_falls_back_quietly():
    with_config("anthropic", "sk-test")
    assert _complete_with(urllib.error.URLError("no route to host")) is None
    assert "knowledge base" in llm.LAST_ERROR


def test_timeout_falls_back():
    with_config("anthropic", "sk-test")
    assert _complete_with(TimeoutError("too slow")) is None
    assert llm.LAST_ERROR


def test_the_tutor_still_answers_when_the_model_is_down():
    """The whole point: a broken key costs an answer, not the app."""
    with_config("anthropic", "sk-test")
    real = urllib.request.urlopen
    urllib.request.urlopen = _Fail(urllib.error.URLError("down"))
    try:
        answer = T.ask("what is entanglement")
    finally:
        urllib.request.urlopen = real
    assert answer.title == "Entanglement" and "Bloch" in answer.text


def test_local_actions_never_reach_the_network():
    """'explain my circuit' is answered from the circuit, never sent to a model."""
    with_config("anthropic", "sk-test")
    real = urllib.request.urlopen
    urllib.request.urlopen = _Fail(AssertionError("a local action must not call out"))
    try:
        assert T.ask("explain my circuit").action == "explain"
        assert T.ask("check this for mistakes").action == "analyse"
    finally:
        urllib.request.urlopen = real


def test_status_reports_something_displayable():
    with_config("gemini", "k")
    state = llm.status()
    assert state["ready"] and state["label"] == "Google Gemini"
    with_config()
    assert not llm.status()["ready"]


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
    with_config()
    print("\n%d passed, %d failed" % (len(tests) - fails, fails))
    sys.exit(1 if fails else 0)
