"""qBraid as an execution provider.

qBraid is a hosted service that fronts several quantum backends behind one
account, which is why the problem statement lists it alongside Aer, Cirq and
PennyLane.  Unlike those three it cannot be pip-installed and used offline —
it needs an API key and a network round-trip.

**Verification status, stated honestly.**  Like the IBM integration, everything
up to the network boundary is tested: OpenQASM translation, device listing,
result normalisation and every error path are exercised against a stand-in
service in ``tests/test_qbraid.py``.  No job has been submitted to qBraid from
this codebase, because there is no account behind it.  Do not describe this as
"working with qBraid" — describe it as "the adapter is written and tested to
the boundary".

The circuit is handed over as **OpenQASM 2**, which QuBuild already generates
for the code panel.  That avoids depending on qBraid's own circuit classes and
means the same translation is exercised by the existing code-export tests.
"""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from typing import Dict, List, Optional

from .circuits import Circuit

TOKEN_ENV = "QBRAID_API_KEY"
TOKEN_PATH = os.environ.get(
    "QUBUILD_QBRAID_TOKEN_FILE",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 ".qbraid_token.json"))

INSTALL_HINT = "pip install qbraid"


def _has_sdk() -> bool:
    try:
        import qbraid                       # noqa: F401
        return True
    except Exception:                       # noqa: BLE001
        return False


HAS_SDK = _has_sdk()


# --------------------------------------------------------------------------
# credentials — same shape as the IBM module so the UI can treat them alike
# --------------------------------------------------------------------------

def read_key() -> Optional[str]:
    key = os.environ.get(TOKEN_ENV, "").strip()
    if key:
        return key
    try:
        with open(TOKEN_PATH, "r", encoding="utf-8") as fh:
            stored = json.load(fh).get("key", "").strip()
        return stored or None
    except (OSError, ValueError):
        return None


def store_key(key: str) -> bool:
    key = (key or "").strip()
    if not key:
        return False
    try:
        with open(TOKEN_PATH, "w", encoding="utf-8") as fh:
            json.dump({"key": key}, fh)
        try:
            os.chmod(TOKEN_PATH, stat.S_IRUSR | stat.S_IWUSR)      # 0600
        except OSError:
            pass
        return True
    except OSError:
        return False


def forget_key() -> None:
    try:
        os.remove(TOKEN_PATH)
    except OSError:
        pass


def status() -> dict:
    """Never returns the key itself."""
    key = read_key()
    return {
        "sdk_installed": HAS_SDK,
        "key_present": bool(key),
        "key_source": ("environment" if os.environ.get(TOKEN_ENV, "").strip()
                       else ("file" if key else "none")),
        "ready": bool(HAS_SDK and key),
        "install_hint": INSTALL_HINT,
    }


def _client():
    key = read_key()
    if not key:
        raise RuntimeError(
            "No qBraid API key configured. Add one in Simulation backends, or set "
            "the %s environment variable." % TOKEN_ENV)
    try:
        from qbraid.runtime import QbraidProvider
    except ImportError as exc:
        raise RuntimeError(
            "The qbraid package is not installed — run `%s`." % INSTALL_HINT) from exc
    return QbraidProvider(api_key=key)


# --------------------------------------------------------------------------
# devices and execution
# --------------------------------------------------------------------------

@dataclass
class QDevice:
    id: str
    name: str
    qubits: int
    simulator: bool
    status: str


def devices() -> List[QDevice]:
    provider = _client()
    out: List[QDevice] = []
    for dev in provider.get_devices():
        meta = getattr(dev, "metadata", lambda: {})() or {}
        out.append(QDevice(
            id=str(getattr(dev, "id", meta.get("device_id", "?"))),
            name=str(meta.get("name", getattr(dev, "id", "?"))),
            qubits=int(meta.get("num_qubits", 0) or 0),
            simulator=str(meta.get("device_type", "")).upper() == "SIMULATOR",
            status=str(getattr(dev, "status", lambda: meta.get("status", "UNKNOWN"))())))
    return out


def run(circuit: Circuit, device_id: str, shots: int = 1024) -> Dict[str, int]:
    """Submit and block until counts come back.

    Handing over OpenQASM 2 rather than a qBraid circuit object keeps this
    adapter independent of their class hierarchy — and the same exporter is
    already covered by the code-generation tests.
    """
    from .circuits import GENERATORS

    provider = _client()
    device = provider.get_device(device_id)
    qasm = GENERATORS["OpenQASM"](circuit)
    job = device.run(qasm, shots=shots)
    result = job.result()
    return normalise_counts(result)


def normalise_counts(result) -> Dict[str, int]:
    """Pull a plain {bitstring: count} out of whatever the SDK returns.

    qBraid has moved this between ``measurement_counts()``, ``data.get_counts()``
    and a bare ``counts`` attribute across releases, so all three are accepted
    rather than pinning one version.
    """
    for attr in ("measurement_counts", "get_counts"):
        fn = getattr(result, attr, None)
        if callable(fn):
            return {str(k): int(v) for k, v in fn().items()}
    data = getattr(result, "data", None)
    if data is not None:
        fn = getattr(data, "get_counts", None)
        if callable(fn):
            return {str(k): int(v) for k, v in fn().items()}
    counts = getattr(result, "counts", None)
    if isinstance(counts, dict):
        return {str(k): int(v) for k, v in counts.items()}
    raise RuntimeError("qBraid returned a result with no recognisable counts.")
