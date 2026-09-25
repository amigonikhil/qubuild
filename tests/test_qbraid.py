"""qBraid adapter — everything up to the network boundary."""
import os
import sys
import tempfile
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qubuild import circuits as C, qbraid_provider as QB

B = C.Circuit.build


def _isolate():
    QB.TOKEN_PATH = os.path.join(tempfile.mkdtemp(), ".qbraid_token.json")
    os.environ.pop(QB.TOKEN_ENV, None)


# ---- credentials --------------------------------------------------------

def test_status_with_nothing_configured():
    _isolate()
    st = QB.status()
    assert st["key_present"] is False and st["ready"] is False
    assert st["key_source"] == "none"


def test_key_round_trip_and_never_leaks():
    _isolate()
    assert QB.store_key("qbraid-secret-key") is True
    assert QB.read_key() == "qbraid-secret-key"
    assert "qbraid-secret-key" not in str(QB.status())
    QB.forget_key()
    assert QB.read_key() is None


def test_environment_beats_file():
    _isolate()
    QB.store_key("from-file")
    os.environ[QB.TOKEN_ENV] = "from-env"
    try:
        assert QB.read_key() == "from-env"
        assert QB.status()["key_source"] == "environment"
    finally:
        os.environ.pop(QB.TOKEN_ENV)


def test_missing_key_is_explained_not_crashed():
    _isolate()
    try:
        QB._client()
    except RuntimeError as exc:
        assert "key" in str(exc).lower()
    else:
        raise AssertionError("expected RuntimeError")


# ---- result normalisation: three SDK shapes, one output -----------------

class R1:
    def measurement_counts(self):
        return {"00": 500, "11": 524}


class R2:
    def get_counts(self):
        return {"00": 1, "11": 2}


class R3:
    def __init__(self):
        self.data = types.SimpleNamespace(get_counts=lambda: {"01": 7})


class R4:
    counts = {"10": 3}


class RBad:
    pass


def test_normalise_accepts_every_known_shape():
    assert QB.normalise_counts(R1()) == {"00": 500, "11": 524}
    assert QB.normalise_counts(R2()) == {"00": 1, "11": 2}
    assert QB.normalise_counts(R3()) == {"01": 7}
    assert QB.normalise_counts(R4()) == {"10": 3}


def test_normalise_rejects_an_unknown_shape():
    try:
        QB.normalise_counts(RBad())
    except RuntimeError as exc:
        assert "counts" in str(exc).lower()
    else:
        raise AssertionError("expected RuntimeError")


def test_counts_are_coerced_to_int():
    class Loose:
        def measurement_counts(self):
            return {0: "12", 11: 3.0}
    assert QB.normalise_counts(Loose()) == {"0": 12, "11": 3}


# ---- submission path against a stand-in service -------------------------

class FakeJob:
    def __init__(self, counts):
        self._c = counts

    def result(self):
        return R1() if self._c is None else type("R", (), {
            "measurement_counts": lambda s, c=self._c: c})()


class FakeDevice:
    def __init__(self):
        self.seen = {}

    def run(self, program, shots=None):
        self.seen = {"program": program, "shots": shots}
        return FakeJob({"00": 7, "11": 9})


class FakeProvider:
    def __init__(self):
        self.device = FakeDevice()

    def get_device(self, device_id):
        self.device.device_id = device_id
        return self.device

    def get_devices(self):
        d = types.SimpleNamespace(
            id="qbraid_qir_simulator",
            metadata=lambda: {"name": "QIR simulator", "num_qubits": 64,
                              "device_type": "SIMULATOR", "status": "ONLINE"},
            status=lambda: "ONLINE")
        return [d]


def test_run_sends_openqasm_and_returns_counts():
    _isolate()
    QB.store_key("k")
    provider = FakeProvider()
    QB._client = lambda: provider

    circuit = B(2, [("H", [0]), ("CX", [0, 1]), ("MEASURE", [0]), ("MEASURE", [1])])
    counts = QB.run(circuit, "qbraid_qir_simulator", shots=16)

    assert counts == {"00": 7, "11": 9}
    assert provider.device.seen["shots"] == 16
    program = provider.device.seen["program"]
    assert "OPENQASM" in program.upper()          # it really is QASM
    assert "cx" in program.lower()                # and it really is this circuit


def test_device_listing_is_normalised():
    _isolate()
    QB.store_key("k")
    QB._client = lambda: FakeProvider()
    devices = QB.devices()
    assert len(devices) == 1
    d = devices[0]
    assert d.id == "qbraid_qir_simulator"
    assert d.qubits == 64 and d.simulator is True and d.status == "ONLINE"
