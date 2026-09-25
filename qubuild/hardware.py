"""Submitting circuits to real IBM Quantum hardware.

Everything above this module is a simulator.  This one sends a circuit to a
physical superconducting processor, waits in the queue with everyone else, and
brings back counts measured on real qubits.

**Read this before demonstrating it.**  The code here is real and complete, but
it has never executed against IBM's service from the machine that wrote it —
there was no account to test with.  What *is* verified is everything up to the
network boundary: circuit translation, payload shape, status parsing and error
handling are exercised by the test suite against a stand-in service.  The first
real submission is still the first real submission, so connect a token and run
a two-qubit Bell circuit well before you need this in front of anyone.

**On the token.**  It is a bearer credential for your IBM account and anyone
holding it can spend your quota.  It is read from the ``QUBUILD_IBM_TOKEN``
environment variable first; only if that is unset does it fall back to a local
file, which is written with owner-only permissions and must never be committed.
Nothing here ever logs or displays the token after it is stored.

Queue reality check: free-tier jobs routinely wait minutes to hours. Anything
depending on a live result during a five-minute demo should submit in advance
and retrieve by job id, which is why :func:`fetch` takes an id and works in a
completely separate session from :func:`submit`.
"""

from __future__ import annotations

import json
import os
import stat
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .circuits import Circuit

TOKEN_ENV = "QUBUILD_IBM_TOKEN"
TOKEN_PATH = os.environ.get(
    "QUBUILD_IBM_TOKEN_FILE",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 ".ibm_token.json"))
JOBS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "ibm_jobs.json")


def _has_runtime() -> bool:
    try:
        import qiskit_ibm_runtime           # noqa: F401
        return True
    except Exception:                       # noqa: BLE001
        return False


HAS_RUNTIME = _has_runtime()
INSTALL_HINT = "pip install qiskit qiskit-ibm-runtime"


# --------------------------------------------------------------------------
# credentials
# --------------------------------------------------------------------------

def read_token() -> Optional[str]:
    token = os.environ.get(TOKEN_ENV, "").strip()
    if token:
        return token
    try:
        with open(TOKEN_PATH, "r", encoding="utf-8") as fh:
            stored = json.load(fh).get("token", "").strip()
        return stored or None
    except (OSError, ValueError):
        return None


def store_token(token: str, instance: str = "") -> bool:
    """Persist a token with owner-only permissions. Returns False on failure."""
    token = (token or "").strip()
    if not token:
        return False
    try:
        with open(TOKEN_PATH, "w", encoding="utf-8") as fh:
            json.dump({"token": token, "instance": instance.strip()}, fh)
        try:
            os.chmod(TOKEN_PATH, stat.S_IRUSR | stat.S_IWUSR)   # 0600; no-op on Windows
        except OSError:
            pass
        return True
    except OSError:
        return False


def forget_token() -> None:
    try:
        os.remove(TOKEN_PATH)
    except OSError:
        pass


def read_instance() -> str:
    try:
        with open(TOKEN_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh).get("instance", "")
    except (OSError, ValueError):
        return ""


def status() -> dict:
    """What the UI needs to decide what to show. Never returns the token."""
    token = read_token()
    return {
        "sdk_installed": HAS_RUNTIME,
        "token_present": bool(token),
        "token_source": ("environment" if os.environ.get(TOKEN_ENV, "").strip()
                         else ("file" if token else "none")),
        "instance": read_instance(),
        "ready": bool(HAS_RUNTIME and token),
        "install_hint": INSTALL_HINT,
    }


# --------------------------------------------------------------------------
# service
# --------------------------------------------------------------------------

def _service():
    # Order matters: check the things we can explain before the import, so a
    # missing token reports "no token" rather than a ModuleNotFoundError that
    # sends the user off installing a package they may already need anyway.
    token = read_token()
    if not token:
        raise RuntimeError(
            "No IBM Quantum token configured. Add one in Simulation backends, "
            "or set the %s environment variable." % TOKEN_ENV)
    try:
        from qiskit_ibm_runtime import QiskitRuntimeService
    except ImportError as exc:
        raise RuntimeError(
            "qiskit-ibm-runtime is not installed — run `%s`." % INSTALL_HINT) from exc
    kwargs = {"channel": "ibm_quantum_platform", "token": token}
    instance = read_instance()
    if instance:
        kwargs["instance"] = instance
    return QiskitRuntimeService(**kwargs)


@dataclass
class DeviceInfo:
    name: str
    qubits: int
    simulator: bool
    operational: bool
    pending_jobs: int


def devices(min_qubits: int = 1) -> List[DeviceInfo]:
    """Real backends visible to this account, least busy first."""
    service = _service()
    out: List[DeviceInfo] = []
    for backend in service.backends(min_num_qubits=min_qubits, operational=True):
        try:
            st = backend.status()
            pending = int(getattr(st, "pending_jobs", 0))
            operational = bool(getattr(st, "operational", True))
        except Exception:                               # noqa: BLE001
            pending, operational = 0, True
        out.append(DeviceInfo(
            name=backend.name,
            qubits=int(getattr(backend, "num_qubits", 0) or 0),
            simulator=bool(getattr(getattr(backend, "configuration", lambda: None)(),
                                   "simulator", False)),
            operational=operational,
            pending_jobs=pending))
    return sorted(out, key=lambda d: d.pending_jobs)


# --------------------------------------------------------------------------
# jobs
# --------------------------------------------------------------------------

@dataclass
class JobRecord:
    job_id: str
    backend: str
    shots: int
    submitted: float
    qubits: int
    note: str = ""

    def to_dict(self) -> dict:
        return dict(job_id=self.job_id, backend=self.backend, shots=self.shots,
                    submitted=self.submitted, qubits=self.qubits, note=self.note)


def remember(record: JobRecord) -> None:
    """Keep a local index of submitted jobs so results survive a restart."""
    jobs = recall()
    jobs = [j for j in jobs if j.job_id != record.job_id]
    jobs.insert(0, record)
    try:
        with open(JOBS_PATH, "w", encoding="utf-8") as fh:
            json.dump([j.to_dict() for j in jobs[:50]], fh, indent=1)
    except OSError:
        pass


def recall() -> List[JobRecord]:
    try:
        with open(JOBS_PATH, "r", encoding="utf-8") as fh:
            return [JobRecord(**item) for item in json.load(fh)]
    except (OSError, ValueError, TypeError):
        return []


def submit(circuit: Circuit, backend_name: str, shots: int = 1024,
           note: str = "") -> JobRecord:
    """Transpile for the target device and submit. Returns immediately."""
    from qiskit import transpile
    from qiskit_ibm_runtime import SamplerV2

    from .backends import to_qiskit_circuit

    service = _service()
    backend = service.backend(backend_name)
    qc = to_qiskit_circuit(circuit, with_measurements=True)
    if not qc.clbits:
        qc.measure_all()
    # optimization_level 3 matters on real hardware: the device's coupling map
    # rarely matches the circuit, and unrouted two-qubit gates become swap
    # chains that eat the error budget.
    compiled = transpile(qc, backend=backend, optimization_level=3)
    job = SamplerV2(mode=backend).run([compiled], shots=shots)
    record = JobRecord(job_id=job.job_id(), backend=backend_name, shots=shots,
                       submitted=time.time(), qubits=circuit.qubits, note=note)
    remember(record)
    return record


def job_status(job_id: str) -> dict:
    """Queue position and state, cheap enough to poll."""
    service = _service()
    job = service.job(job_id)
    state = str(job.status())
    info = {"job_id": job_id, "status": state,
            "done": state.upper() in ("DONE", "COMPLETED"),
            "failed": state.upper() in ("ERROR", "CANCELLED", "FAILED"),
            "queue_position": None}
    try:
        info["queue_position"] = job.queue_position()
    except Exception:                                   # noqa: BLE001
        pass
    return info


def fetch(job_id: str) -> Dict[str, int]:
    """Counts from a finished job. Works in a session that never submitted it."""
    service = _service()
    job = service.job(job_id)
    result = job.result()
    pub = result[0]
    data = pub.data
    # SamplerV2 names the register after the circuit's classical register, so
    # take whichever bit array is actually present rather than guessing "c".
    for name in dir(data):
        if name.startswith("_"):
            continue
        item = getattr(data, name)
        if hasattr(item, "get_counts"):
            return {k: int(v) for k, v in item.get_counts().items()}
    raise RuntimeError("No classical register found in the job result.")


def elapsed(record: JobRecord) -> str:
    seconds = max(0, int(time.time() - record.submitted))
    if seconds < 90:
        return "%ds ago" % seconds
    if seconds < 5400:
        return "%dm ago" % (seconds // 60)
    return "%dh ago" % (seconds // 3600)
