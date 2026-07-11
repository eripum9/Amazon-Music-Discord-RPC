import io
import json
import threading

from app_models import DiagnosticsSnapshot, PlaybackStatus, TrackSnapshot
from runtime_state import ApplicationState
from structured_logging import StructuredLogTee, rotate_logs
from task_supervisor import TaskSupervisor
from command_controller import CommandController
from rpc_controller import RpcController
from window_controller import WindowController


def test_typed_track_and_diagnostics_snapshots_normalise_boundaries():
    track = TrackSnapshot.from_mapping(
        {
            "title": " Song ",
            "artist": "Artist",
            "album": "Album",
            "status": "playing",
            "position": "12.5",
            "duration": "180",
        }
    )
    snapshot = DiagnosticsSnapshot.from_state(100.0, "5.0.0", {"rpc_status": "running", "track": track.to_dict()})
    payload = snapshot.to_dict()
    assert track.status is PlaybackStatus.PLAYING
    assert track.key == "Song|Artist"
    assert track.has_identity
    assert payload["track"]["position"] == 12.5
    assert payload["rpc_status"] == "running"


def test_application_state_returns_isolated_snapshots():
    state = ApplicationState()
    config = {"amazon_devtools_enabled": True}
    state.replace_config(config)
    config["amazon_devtools_enabled"] = False
    state.set_rpc_running(True)
    state.set_current_track("Song|Artist", {"title": "Song", "artist": "Artist", "status": "paused"})
    snapshot = state.snapshot()
    snapshot["config"]["amazon_devtools_enabled"] = False
    assert state.config()["amazon_devtools_enabled"] is True
    assert state.rpc_running() is True
    assert state.track().status is PlaybackStatus.PAUSED


def test_task_supervisor_tracks_workers_and_shutdown():
    started = threading.Event()
    release = threading.Event()
    errors = []
    supervisor = TaskSupervisor(lambda name, error, trace: errors.append((name, str(error))))

    def worker():
        started.set()
        release.wait(2)

    thread = supervisor.start("worker", worker, daemon=False)
    assert started.wait(1)
    assert supervisor.snapshot()["worker"]["alive"] is True
    assert supervisor.start("worker", worker) is thread
    release.set()
    assert supervisor.join(2)
    supervisor.start("failure", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    assert supervisor.join(2)
    assert errors == [("failure", "boom")]


def test_structured_log_tee_writes_redacted_json_and_rotates(tmp_path):
    text_path = tmp_path / "console.log"
    event_path = tmp_path / "events.jsonl"
    original = io.StringIO()
    tee = StructuredLogTee(original, str(text_path), str(event_path), "stdout", lambda value: value.replace("secret", "[redacted]"))
    tee.write("[RPC] Connected with secret\n")
    tee.close()
    event = json.loads(event_path.read_text(encoding="utf-8").strip())
    assert original.getvalue() == "[RPC] Connected with secret\n"
    assert event["component"] == "RPC"
    assert event["message"] == "Connected with [redacted]"
    assert event["thread"]
    rotate_logs(str(tmp_path), "events.jsonl", 5)
    assert (tmp_path / "events.1.jsonl").exists()


def test_command_and_rpc_controllers_own_dispatch_and_lifecycle():
    commands = []
    controller = CommandController({"settings": lambda: commands.append("settings")})
    assert controller.dispatch(" SETTINGS ") is True
    assert controller.dispatch("missing") is False
    assert commands == ["settings"]

    class FakeThread:
        def join(self, timeout=None):
            return None

        def is_alive(self):
            return False

    class FakeTasks:
        def start(self, name, target, daemon=True):
            assert name == "rpc"
            assert daemon is False
            return FakeThread()

    state = ApplicationState()
    state.replace_config({})
    running = []
    diagnostics = []
    rpc = RpcController(FakeTasks(), state, state.config, lambda **value: diagnostics.append(value), lambda: None, lambda: None, "client", lambda value: (running.append(value), state.set_rpc_running(value)))
    rpc.start()
    rpc.stop()
    assert running == [True, False]
    assert diagnostics[0]["rpc_status"] == "starting"


def test_window_controller_owns_child_processes(monkeypatch, tmp_path):
    class FakeProcess:
        def __init__(self):
            self.closed = False

        def poll(self):
            return 0 if self.closed else None

        def terminate(self):
            self.closed = True

        def wait(self, timeout=None):
            return 0

    class FakeTasks:
        def start(self, name, target, args=()):
            return None

        def wait(self, seconds):
            return True

    processes = []

    def fake_popen(*args, **kwargs):
        process = FakeProcess()
        processes.append(process)
        return process

    monkeypatch.setattr("window_controller.subprocess.Popen", fake_popen)
    controller = WindowController(FakeTasks(), str(tmp_path), lambda devtools: {}, lambda: {}, lambda value: {}, lambda *args: None)
    controller.open_settings()
    controller.open_diagnostics()
    assert controller.snapshot() == {"settings_open": True, "diagnostics_open": True}
    controller.close()
    assert all(process.closed for process in processes)
