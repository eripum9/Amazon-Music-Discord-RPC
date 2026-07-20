# MIT License - Copyright (c) 2026 eripum9
# pyright: reportMissingImports=false

import inspect
import plistlib
from types import SimpleNamespace

import pytest

from MacOS import amazon_devtools


def _target(**overrides):
    value = {
        "id": "page-123",
        "type": "page",
        "title": "Amazon Music",
        "url": "https://music.amazon.de/morpho/webapp/index.html#/home",
        "webSocketDebuggerUrl": "ws://127.0.0.1:52856/devtools/page/page-123",
    }
    value.update(overrides)
    return value


def _installation(tmp_path):
    app = tmp_path / "Amazon Music.app"
    executable = app / "Contents" / "MacOS" / "Amazon Music"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"test executable")
    executable.chmod(0o755)
    with (app / "Contents" / "Info.plist").open("wb") as stream:
        plistlib.dump(
            {
                "CFBundleIdentifier": "com.amazon.music",
                "CFBundleExecutable": "Amazon Music",
                "CFBundleShortVersionString": "9.5.2",
            },
            stream,
        )
    return app


def _metadata(**overrides):
    value = {
        "status": "found",
        "title": "Treehome95 [Explicit]",
        "artist": "Tyler, The Creator",
        "album": "Wolf [Explicit]",
        "art_url": "https://m.media-amazon.com/images/I/example.jpg",
        "track_link": "https://music.amazon.de/albums/B00C3O5D3A?trackAsin=B00C3O5D3A",
        "position": 138.25,
        "duration": 179,
        "playback_status": "paused",
    }
    value.update(overrides)
    return value


def test_validate_app_bundle_requires_expected_identity_and_executable(tmp_path):
    app = _installation(tmp_path)
    descriptor = amazon_devtools._validate_app_bundle(
        app,
        require_standard_location=False,
        signature_checker=lambda path: path == app,
    )
    assert descriptor == {
        "app_path": str(app),
        "executable": str(app / "Contents" / "MacOS" / "Amazon Music"),
        "bundle_id": "com.amazon.music",
        "version": "9.5.2",
    }

    with (app / "Contents" / "Info.plist").open("wb") as stream:
        plistlib.dump(
            {"CFBundleIdentifier": "com.amazon.music.evil", "CFBundleExecutable": "Amazon Music"},
            stream,
        )
    assert amazon_devtools._validate_app_bundle(
        app,
        require_standard_location=False,
        signature_checker=lambda path: True,
    ) is None


def test_signature_identity_accepts_only_amazon_team_and_bundle():
    def runner(command, **kwargs):
        return SimpleNamespace(
            returncode=0,
            stdout="",
            stderr=(
                "Identifier=com.amazon.music\n"
                "Authority=Developer ID Application: AMZN Mobile LLC (94KV3E626L)\n"
                "TeamIdentifier=94KV3E626L\n"
            ),
        )

    assert amazon_devtools._official_signature_identity(amazon_devtools.AMAZON_MUSIC_APP, runner)

    def impostor(command, **kwargs):
        return SimpleNamespace(
            returncode=0,
            stdout="",
            stderr=(
                "Identifier=com.amazon.music\n"
                "Authority=Developer ID Application: AMZN Mobile LLC (EVIL)\n"
                "TeamIdentifier=EVIL\n"
            ),
        )

    assert not amazon_devtools._official_signature_identity(amazon_devtools.AMAZON_MUSIC_APP, impostor)


@pytest.mark.parametrize(
    "url",
    [
        "http://music.amazon.de/morpho/webapp/index.html",
        "https://www.amazon.de/gp/your-account",
        "https://music.amazon.de.evil.test/morpho/webapp/index.html",
        "https://music.amazon.invalid/morpho/webapp/index.html",
        "https://user:password@music.amazon.de/morpho/webapp/index.html",
        "https://music.amazon.de:8443/morpho/webapp/index.html",
    ],
)
def test_page_target_rejects_untrusted_origins(url):
    assert not amazon_devtools._is_amazon_music_target(_target(url=url))


def test_page_target_accepts_only_exact_page_target_with_valid_id():
    assert amazon_devtools._is_amazon_music_target(_target())
    assert amazon_devtools._is_amazon_music_target(
        _target(url="https://www.amazon.de/morpho/webapp")
    )
    assert not amazon_devtools._is_amazon_music_target(_target(type="service_worker"))
    assert not amazon_devtools._is_amazon_music_target(_target(id="../../browser"))


def test_websocket_target_is_bound_to_selected_loopback_page():
    assert amazon_devtools._valid_target_websocket(_target(), 52856)
    assert not amazon_devtools._valid_target_websocket(
        _target(webSocketDebuggerUrl="ws://example.test:52856/devtools/page/page-123"),
        52856,
    )
    assert not amazon_devtools._valid_target_websocket(
        _target(webSocketDebuggerUrl="ws://127.0.0.1:52857/devtools/page/page-123"),
        52856,
    )
    assert not amazon_devtools._valid_target_websocket(
        _target(webSocketDebuggerUrl="ws://user:password@127.0.0.1:52856/devtools/page/page-123"),
        52856,
    )
    assert not amazon_devtools._valid_target_websocket(
        _target(webSocketDebuggerUrl="ws://127.0.0.1:52856/devtools/page/other"),
        52856,
    )
    assert not amazon_devtools._valid_target_websocket(_target(), 9222)


def test_private_port_selection_rejects_common_and_out_of_range_ports():
    amazon_devtools.reset_devtools_port()
    selected = amazon_devtools.get_devtools_port()
    assert selected is not None
    assert amazon_devtools.DEVTOOLS_PORT_MIN <= selected <= amazon_devtools.DEVTOOLS_PORT_MAX
    with pytest.raises(ValueError):
        amazon_devtools.set_devtools_port(9222)
    amazon_devtools.reset_devtools_port()


def test_owner_verification_fails_closed_and_rejects_other_process(monkeypatch):
    installation: dict[str, object] = {"app_path": "/Applications/Amazon Music.app"}
    monkeypatch.setattr(amazon_devtools, "_listener_pids", lambda port: [])
    assert amazon_devtools._devtools_owner_trust(52856, installation)["status"] == "unavailable"

    monkeypatch.setattr(amazon_devtools, "_listener_pids", lambda port: [44])
    monkeypatch.setattr(amazon_devtools, "_is_trusted_amazon_pid", lambda pid, install: False)
    rejected = amazon_devtools._devtools_owner_trust(52856, installation)
    assert rejected["trusted"] is False
    assert rejected["status"] == "rejected"

    monkeypatch.setattr(amazon_devtools, "_is_trusted_amazon_pid", lambda pid, install: pid == 44)
    assert amazon_devtools._devtools_owner_trust(52856, installation)["trusted"] is True


def test_listener_discovery_enumerates_only_private_loopback_ports_with_trusted_owners(monkeypatch):
    installation: dict[str, object] = {"app_path": "/Applications/Amazon Music.app"}
    commands = []

    def runner(command, **kwargs):
        commands.append((command, kwargs))
        return SimpleNamespace(
            returncode=0,
            stdout=(
                "p41\nf10\nn127.0.0.1:52856\n"
                "f11\nn[::1]:52857\n"
                "f12\nn*:52858\n"
                "f13\nn127.0.0.1:9222\n"
                "p99\nf20\nn127.0.0.1:52856\n"
                "pbad\nf30\nn127.0.0.1:52859\n"
                "p41\nf31\nn10.0.0.2:52860\n"
            ),
            stderr="",
        )

    monkeypatch.setattr(
        amazon_devtools,
        "_is_trusted_amazon_pid",
        lambda pid, install: pid == 41 and install is installation,
    )
    assert amazon_devtools._trusted_listener_ports(installation, runner) == [52857]
    assert commands[0][0] == [
        "/usr/sbin/lsof",
        "-nP",
        "-a",
        "-iTCP",
        "-sTCP:LISTEN",
        "-Fpfn",
    ]


def test_discovery_probes_only_verified_owners_and_requires_one_match(monkeypatch):
    installation: dict[str, object] = {"app_path": "/Applications/Amazon Music.app"}
    page_probes = []
    owner_checks = []
    amazon_devtools.reset_devtools_port()
    monkeypatch.setattr(amazon_devtools, "_trusted_listener_ports", lambda install: [52856, 52857])

    def owner(port, install=None):
        owner_checks.append(port)
        return {"trusted": port == 52856}

    def page(port, verify_owner=True):
        page_probes.append((port, verify_owner))
        return _target() if port == 52856 else None

    monkeypatch.setattr(amazon_devtools, "_devtools_owner_trust", owner)
    monkeypatch.setattr(amazon_devtools, "_page_target", page)
    assert amazon_devtools.discover_devtools_port(installation) == 52856
    assert page_probes == [(52856, False)]
    assert owner_checks == [52856, 52856, 52857]
    assert amazon_devtools.get_devtools_port(False) == 52856

    amazon_devtools.reset_devtools_port()
    monkeypatch.setattr(amazon_devtools, "_trusted_listener_ports", lambda install: [52856, 52857])
    monkeypatch.setattr(
        amazon_devtools,
        "_devtools_owner_trust",
        lambda port, install=None: {"trusted": True},
    )
    monkeypatch.setattr(amazon_devtools, "_page_target", lambda port, verify_owner=True: _target())
    assert amazon_devtools.discover_devtools_port(installation) is None
    assert amazon_devtools.get_devtools_port(False) is None


def test_failed_discovery_is_briefly_negative_cached(monkeypatch):
    installation: dict[str, object] = {"app_path": "/Applications/Amazon Music.app"}
    scans = []
    clock = [10.0]
    amazon_devtools.reset_devtools_port()
    monkeypatch.setattr(amazon_devtools.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        amazon_devtools,
        "_trusted_listener_ports",
        lambda install: scans.append(install) or [],
    )
    assert amazon_devtools.discover_devtools_port(installation) is None
    clock[0] = 11.0
    assert amazon_devtools.discover_devtools_port(installation) is None
    clock[0] = 13.0
    assert amazon_devtools.discover_devtools_port(installation) is None
    assert scans == [installation, installation]


def test_status_rediscovers_existing_listener_after_fresh_process(monkeypatch):
    installation: dict[str, object] = {"app_path": "/Applications/Amazon Music.app"}
    amazon_devtools.reset_devtools_port()
    monkeypatch.setattr(amazon_devtools, "locate_amazon_music_app", lambda: installation)
    monkeypatch.setattr(amazon_devtools, "_running_amazon_pids", lambda install: [42])
    monkeypatch.setattr(amazon_devtools, "discover_devtools_port", lambda install: 52856)
    monkeypatch.setattr(
        amazon_devtools,
        "_devtools_owner_trust",
        lambda port, install=None: {"trusted": True},
    )
    monkeypatch.setattr(amazon_devtools, "_page_target", lambda port, verify_owner=True: _target())
    status = amazon_devtools.get_devtools_status()
    assert status["status"] == "ready"
    assert status["port"] == 52856


def test_normalise_metadata_reads_status_timing_art_and_direct_link():
    track = amazon_devtools._normalise_track_payload(_metadata(), "de")
    assert track == {
        "status": "found",
        "detail": "Amazon Music metadata found",
        "source": "amazon_devtools",
        "title": "Treehome95",
        "artist": "Tyler, The Creator",
        "album": "Wolf",
        "art_url": "https://m.media-amazon.com/images/I/example.jpg",
        "track_link": "https://music.amazon.de/albums/B00C3O5D3A?trackAsin=B00C3O5D3A",
        "position": 138.25,
        "duration": 179.0,
        "playback_status": "paused",
        "confidence": 98,
    }


def test_normalise_metadata_uses_transport_text_and_rejects_unsafe_urls():
    track = amazon_devtools._normalise_track_payload(
        _metadata(
            artist="",
            album="",
            secondary="Tyler, The Creator • Wolf",
            position=None,
            duration=None,
            position_text="2:18",
            remaining_text="-0:41",
            art_url="https://127.0.0.1/private",
            track_link="https://music.amazon.de.evil.test/track",
        ),
        "de",
    )
    assert track["artist"] == "Tyler, The Creator"
    assert track["album"] == "Wolf"
    assert track["position"] == 138
    assert track["duration"] == 179
    assert track["art_url"] == ""
    assert str(track["track_link"]).startswith("https://music.amazon.de/search/")


def test_get_track_uses_read_only_runtime_evaluation_and_closes(monkeypatch):
    calls = []

    class Client:
        def __init__(self, url, **kwargs):
            calls.append(("init", url, kwargs))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            calls.append(("close",))

        def request(self, method, params):
            calls.append(("request", method, params))
            return {"result": {"result": {"value": _metadata()}}}

    monkeypatch.setattr(amazon_devtools, "_devtools_owner_trust", lambda *args, **kwargs: {"trusted": True})
    monkeypatch.setattr(amazon_devtools, "_page_target", lambda *args, **kwargs: _target())
    monkeypatch.setattr(amazon_devtools, "_CdpSocket", Client)
    amazon_devtools._clear_cache()
    track = amazon_devtools.get_devtools_track_sync("de", 52856)
    assert track["status"] == "found"
    assert track["port"] == 52856
    assert calls[-1] == ("close",)
    method_call = next(call for call in calls if call[0] == "request")
    assert method_call[1] == "Runtime.evaluate"
    assert method_call[2]["includeCommandLineAPI"] is False


def test_get_track_rediscovers_existing_listener_after_fresh_process(monkeypatch):
    class Client:
        def __init__(self, url, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def request(self, method, params):
            return {"result": {"result": {"value": _metadata()}}}

    amazon_devtools.reset_devtools_port()
    monkeypatch.setattr(amazon_devtools, "discover_devtools_port", lambda: 52856)
    monkeypatch.setattr(amazon_devtools, "_devtools_owner_trust", lambda *args, **kwargs: {"trusted": True})
    monkeypatch.setattr(amazon_devtools, "_page_target", lambda *args, **kwargs: _target())
    monkeypatch.setattr(amazon_devtools, "_CdpSocket", Client)
    result = amazon_devtools.get_devtools_track_sync("de")
    assert result["status"] == "found"
    assert result["port"] == 52856


def test_devtools_failure_does_not_echo_sensitive_renderer_data(monkeypatch):
    class Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def request(self, method, params):
            raise RuntimeError("session_token=do-not-return")

    monkeypatch.setattr(amazon_devtools, "_devtools_owner_trust", lambda *args, **kwargs: {"trusted": True})
    monkeypatch.setattr(amazon_devtools, "_page_target", lambda *args, **kwargs: _target())
    monkeypatch.setattr(amazon_devtools, "_CdpSocket", Client)
    amazon_devtools._clear_cache()
    result = amazon_devtools.get_devtools_track_sync(port=52856)
    assert result["status"] == "error"
    assert "do-not-return" not in str(result)


def test_launch_requires_restart_without_terminating_running_app(monkeypatch):
    installation = {"app_path": "/Applications/Amazon Music.app", "executable": "/Applications/Amazon Music.app/Contents/MacOS/Amazon Music"}
    monkeypatch.setattr(amazon_devtools, "locate_amazon_music_app", lambda: installation)
    monkeypatch.setattr(amazon_devtools, "_running_amazon_pids", lambda install: [42])
    monkeypatch.setattr(amazon_devtools, "get_devtools_port", lambda create=False: None)
    monkeypatch.setattr(amazon_devtools, "discover_devtools_port", lambda installation: None)
    result = amazon_devtools.launch_amazon_music_devtools()
    assert result["ok"] is False
    assert result["restart_required"] is True


def test_launch_reattaches_to_discovered_running_listener(monkeypatch):
    installation = {
        "app_path": "/Applications/Amazon Music.app",
        "executable": "/Applications/Amazon Music.app/Contents/MacOS/Amazon Music",
    }
    monkeypatch.setattr(amazon_devtools, "locate_amazon_music_app", lambda: installation)
    monkeypatch.setattr(amazon_devtools, "_running_amazon_pids", lambda install: [42])
    monkeypatch.setattr(amazon_devtools, "get_devtools_port", lambda create=False: None)
    monkeypatch.setattr(amazon_devtools, "discover_devtools_port", lambda install: 52856)
    monkeypatch.setattr(amazon_devtools, "_page_target", lambda port: _target())
    result = amazon_devtools.launch_amazon_music_devtools()
    assert result == {
        "ok": True,
        "status": "ready",
        "already_running": True,
        "port": 52856,
    }


def test_launch_uses_loopback_flag_and_preserves_normal_profile(monkeypatch):
    installation = {"app_path": "/Applications/Amazon Music.app", "executable": "/Applications/Amazon Music.app/Contents/MacOS/Amazon Music"}
    launched = []

    class Reservation:
        def close(self):
            launched.append(("reservation_closed",))

    def launch_process(install, arguments, popen=None):
        launched.append((install, arguments))
        return SimpleNamespace(pid=4242)

    monkeypatch.setattr(amazon_devtools, "locate_amazon_music_app", lambda: installation)
    monkeypatch.setattr(amazon_devtools, "_running_amazon_pids", lambda install: [])
    monkeypatch.setattr(amazon_devtools, "_reserve_devtools_port", lambda port=None: (52856, Reservation()))
    monkeypatch.setattr(amazon_devtools, "_launch_process", launch_process)
    monkeypatch.setattr(amazon_devtools, "_wait_for_page_target", lambda port, timeout, installation=None: _target())
    monkeypatch.setattr(amazon_devtools, "_devtools_owner_trust", lambda *args, **kwargs: {"trusted": True, "status": "verified"})
    result = amazon_devtools.launch_amazon_music_devtools()
    assert result["ok"] is True
    arguments = launched[1][1]
    assert arguments == ["--remote-debugging-address=127.0.0.1", "--remote-debugging-port=52856"]
    assert not any("user-data-dir" in argument for argument in arguments)


def test_stop_signals_only_reverified_amazon_processes(monkeypatch):
    installation = {
        "app_path": "/Applications/Amazon Music.app",
        "executable": "/Applications/Amazon Music.app/Contents/MacOS/Amazon Music",
    }
    reads = iter(([42, 43], []))
    signals = []
    monkeypatch.setattr(amazon_devtools, "locate_amazon_music_app", lambda: installation)
    monkeypatch.setattr(
        amazon_devtools,
        "_running_amazon_pids",
        lambda install, helpers=False: list(next(reads)),
    )
    monkeypatch.setattr(
        amazon_devtools,
        "_is_trusted_amazon_pid",
        lambda pid, install: pid == 42,
    )
    monkeypatch.setattr(amazon_devtools.os, "kill", lambda pid, requested_signal: signals.append((pid, requested_signal)))
    monkeypatch.setattr(amazon_devtools.time, "sleep", lambda seconds: None)
    result = amazon_devtools.stop_amazon_music(timeout=0.1)
    assert result["ok"] is True
    assert signals == [(42, amazon_devtools.signal.SIGTERM)]


def test_source_never_requests_browser_secrets_or_logs_them():
    expression = amazon_devtools._TRANSPORT_EXPRESSION.lower()
    source = inspect.getsource(amazon_devtools).lower()
    for forbidden in (
        "document.cookie",
        "network.getallcookies",
        "network.getcookies",
        "storage.getcookies",
        "localstorage",
        "sessionstorage",
    ):
        assert forbidden not in expression
    assert "import logging" not in source
    assert 'print(' not in source


def test_apply_devtools_metadata_matches_runtime_track_shape():
    enhanced = amazon_devtools._normalise_track_payload(_metadata())
    merged, changed = amazon_devtools.apply_devtools_to_track(
        {"title": "Fallback", "artist": "", "status": "playing"},
        enhanced,
    )
    assert changed is True
    assert merged["title"] == "Treehome95"
    assert merged["status"] == "paused"
    assert str(merged["_amazon_art_url"]).startswith("https://m.media-amazon.com/")
    assert str(merged["_amazon_track_link"]).startswith("https://music.amazon.de/")


def test_process_launch_uses_argv_without_shell(monkeypatch):
    calls = []

    def popen(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(pid=1)

    installation: dict[str, object] = {
        "executable": "/Applications/Amazon Music.app/Contents/MacOS/Amazon Music",
    }
    amazon_devtools._launch_process(installation, ["--remote-debugging-port=52856"], popen)  # type: ignore[arg-type]
    command, kwargs = calls[0]
    assert command == [
        "/Applications/Amazon Music.app/Contents/MacOS/Amazon Music",
        "--remote-debugging-port=52856",
    ]
    assert kwargs["close_fds"] is True
    assert "shell" not in kwargs
    assert kwargs["stdout"] == amazon_devtools.subprocess.DEVNULL
