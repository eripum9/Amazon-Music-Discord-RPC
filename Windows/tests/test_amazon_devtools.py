# MIT License - Copyright (c) 2026 eripum9

import inspect
import os
from types import SimpleNamespace

import amazon_devtools


def test_devtools_payload_normalises_secondary_time_pause_and_link_region():
    payload = amazon_devtools._normalise_track_payload(
        {
            "status": "found",
            "title": "Treehome95 [Explicit]",
            "secondary": "Tyler, The Creator • Wolf [Explicit]",
            "art_url": "https://example.com/art.jpg",
            "track_asin": "B00C3O5D3A",
            "position_text": "2:18",
            "remaining_text": "-0:41",
            "playback_status": "paused",
        },
        "de",
    )
    assert payload["status"] == "found"
    assert payload["title"] == "Treehome95"
    assert payload["artist"] == "Tyler, The Creator"
    assert payload["album"] == "Wolf"
    assert payload["position"] == 138
    assert payload["duration"] == 179
    assert payload["playback_status"] == "paused"
    assert payload["track_link"] == "https://music.amazon.de/tracks/B00C3O5D3A"


def test_devtools_single_secondary_label_populates_artist():
    payload = amazon_devtools._normalise_track_payload(
        {
            "status": "found",
            "title": "Song",
            "secondary": "Artist Only",
        }
    )
    assert payload["status"] == "found"
    assert payload["artist"] == "Artist Only"
    assert payload["album"] == ""


def test_devtools_target_validation_and_search_links():
    good_target = {
        "type": "page",
        "url": "https://music.amazon.de/morpho/webapp/index.html",
        "title": "Amazon Music",
    }
    regional_target = {
        "type": "page",
        "url": "https://www.amazon.de/morpho/webapp/index.html#/home",
        "title": "Amazon Music Desktop",
    }
    bad_target = {
        "type": "page",
        "url": "https://example.com/morpho/webapp/index.html",
        "title": "Amazon Music",
    }
    suffix_confusion = {
        "type": "page",
        "url": "https://music.amazon.de.evil.example/morpho/webapp/index.html",
        "title": "Amazon Music",
    }
    invented_region = {
        "type": "page",
        "url": "https://music.amazon.invalid/morpho/webapp/index.html",
        "title": "Amazon Music",
    }
    assert amazon_devtools._is_amazon_music_target(good_target)
    assert amazon_devtools._is_amazon_music_target(regional_target)
    assert not amazon_devtools._is_amazon_music_target(bad_target)
    assert not amazon_devtools._is_amazon_music_target(suffix_confusion)
    assert not amazon_devtools._is_amazon_music_target(invented_region)
    assert amazon_devtools.amazon_music_search_link("Noid", "Tyler, The Creator", "de") == "https://music.amazon.de/search/Noid%20Tyler%2C%20The%20Creator"


def test_devtools_launcher_candidate_ordering_and_fallbacks():
    existing_path = r"C:\Amazon Music\Amazon Music.exe"
    exists = lambda path: path == existing_path
    start_apps = [
        {"Name": "Amazon Music", "AppID": "Website.Package!AmazonMusic"},
        {"Name": "Amazon Music", "AppID": "Amazon.Music"},
        {"Name": "Amazon Music", "AppID": existing_path},
        {"Name": "Amazon Music", "AppID": r"C:\Missing\Amazon Music.exe"},
        {"Name": "Amazon Music RPC", "AppID": r"C:\Amazon Music RPC\AmazonMusicRPC.exe"},
    ]
    appx_apps = [
        {"PackageFamilyName": "AmazonMobileLLC.AmazonMusic_alt", "AppId": "AmazonMusic"},
    ]
    candidates = amazon_devtools._launcher_candidates("Override.Package!App", start_apps, appx_apps, exists)
    assert [candidate["value"] for candidate in candidates[:4]] == [
        "Override.Package!App",
        "Website.Package!AmazonMusic",
        existing_path,
        "AmazonMobileLLC.AmazonMusic_alt!AmazonMusic",
    ]
    assert [candidate["method"] for candidate in candidates[:4]] == [
        "override-aumid",
        "auto-aumid",
        "auto-exe",
        "auto-aumid",
    ]
    assert candidates[-1]["method"] == "hardcoded-store"
    assert candidates[-1]["value"] == amazon_devtools.APP_USER_MODEL_ID
    assert all(candidate["value"] != "Amazon.Music" for candidate in candidates)
    assert not amazon_devtools._start_app_candidates(
        [{"Name": "Amazon Music", "AppID": r"C:\Missing\Amazon Music.exe"}],
        lambda path: False,
    )
    failure = amazon_devtools._attempt_failure(
        {"method": "auto-aumid", "value": "Missing.Package!App"},
        "Package was not found. 0x80073CF1",
    )
    assert "package was not found" in failure.lower()


def test_devtools_aumid_launch_prefers_native_activation(monkeypatch):
    monkeypatch.setattr(amazon_devtools, "_activate_aumid_native", lambda app_id, args: 4321)
    monkeypatch.setattr(
        amazon_devtools,
        "_run_powershell",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("PowerShell fallback should not run")),
    )
    result = amazon_devtools._launch_aumid("Package.Family!AmazonMusic", 52856)
    assert result == {"ok": True, "pid": "4321", "activation": "native"}


def test_devtools_aumid_launch_uses_powershell_fallback(monkeypatch):
    monkeypatch.setattr(
        amazon_devtools,
        "_activate_aumid_native",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("native activation failed")),
    )
    monkeypatch.setattr(
        amazon_devtools,
        "_run_powershell",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="4321\n", stderr=""),
    )
    result = amazon_devtools._launch_aumid("Package.Family!AmazonMusic", 52856)
    assert result == {"ok": True, "pid": "4321", "activation": "powershell-fallback"}


def test_devtools_stop_waits_for_respawned_helper():
    main = {"Pid": 10, "Name": "Amazon Music.exe", "Kind": "main"}
    helper = {"Pid": 11, "Name": "Amazon Music Helper.exe", "Kind": "helper"}
    respawned = {"Pid": 12, "Name": "Amazon Music Helper.exe", "Kind": "helper"}
    states = [[main, helper], [helper], [respawned], [], []]
    calls = []

    def entries():
        return states.pop(0) if states else []

    def terminate(items, force):
        calls.append((force, [_entry["Pid"] for _entry in items]))
        return {"ok": True, "stopped": [str(_entry["Pid"]) for _entry in items], "errors": []}

    result = amazon_devtools.stop_amazon_music(
        timeout=2,
        poll_interval=0.1,
        process_entries_fn=entries,
        terminate_fn=terminate,
        sleep_fn=lambda delay: None,
    )
    assert result["ok"] is True
    assert result["remaining"] == []
    assert (False, [10, 11]) in calls
    assert (True, [11]) in calls
    assert (True, [12]) in calls


def test_devtools_restart_closes_main_processes_and_preserves_helper():
    root = {"Pid": 20, "ParentPid": 1, "Name": "Amazon Music.exe", "Kind": "main"}
    child = {"Pid": 21, "ParentPid": 20, "Name": "Amazon Music.exe", "Kind": "main"}
    helper = {"Pid": 22, "ParentPid": 20, "Name": "Amazon Music Helper.exe", "Kind": "helper"}
    states = [[root, child, helper], [root, child, helper], [helper], [helper]]
    calls = []

    def entries():
        return states.pop(0) if states else [helper]

    def terminate(items, force):
        calls.append((force, [entry["Pid"] for entry in items]))
        return {"ok": True, "stopped": [str(entry["Pid"]) for entry in items], "errors": []}

    result = amazon_devtools.stop_amazon_music_for_restart(
        timeout=2,
        poll_interval=0.1,
        process_entries_fn=entries,
        terminate_fn=terminate,
        sleep_fn=lambda delay: None,
    )
    assert result["ok"] is True
    assert result["preserved_helpers"] == ["22"]
    assert calls == [(False, [20])]


def test_devtools_restart_refuses_to_force_a_running_main_process():
    main = {"Pid": 20, "ParentPid": 1, "Name": "Amazon Music.exe", "Kind": "main"}
    calls = []

    def terminate(items, force):
        calls.append(force)
        return {"ok": True, "stopped": [], "errors": []}

    result = amazon_devtools.stop_amazon_music_for_restart(
        timeout=0.2,
        poll_interval=0.1,
        process_entries_fn=lambda: [main],
        terminate_fn=terminate,
        sleep_fn=lambda delay: None,
    )
    assert result["ok"] is False
    assert result["remaining"] == ["20"]
    assert calls == [False]


def test_devtools_extracts_exact_store_package_identity():
    valid = "AmazonMobileLLC.AmazonMusic_9.5.2.0_x86__kc6t79cpj4tp0"
    entries = [
        {"Path": rf"C:\Program Files\WindowsApps\{valid}\Amazon Music Helper.exe"},
        {"Path": r"C:\Users\user\AppData\Local\Amazon Music\Amazon Music.exe"},
        {"Path": r"C:\Program Files\WindowsApps\AmazonMobileLLC.AmazonMusic_bad\Amazon Music.exe"},
    ]
    assert amazon_devtools._store_package_full_names(entries) == [valid]


def test_devtools_store_package_stop_waits_for_full_exit():
    package = "AmazonMobileLLC.AmazonMusic_9.5.2.0_x86__kc6t79cpj4tp0"
    helper = {"Pid": 30, "Path": rf"C:\Program Files\WindowsApps\{package}\Amazon Music Helper.exe", "Kind": "helper"}
    states = [[helper], [], []]
    terminated = []

    result = amazon_devtools.stop_amazon_store_packages(
        [package],
        timeout=2,
        poll_interval=0.1,
        process_entries_fn=lambda: states.pop(0) if states else [],
        terminate_package_fn=terminated.append,
        sleep_fn=lambda delay: None,
    )
    assert result["ok"] is True
    assert result["stopped"] == ["30"]
    assert result["packages"] == [package]
    assert terminated == [package]


def test_devtools_restart_preserves_helper_and_skips_package_reset(monkeypatch):
    package = "AmazonMobileLLC.AmazonMusic_9.5.2.0_x86__kc6t79cpj4tp0"
    helper = {"Pid": 31, "Path": rf"C:\Program Files\WindowsApps\{package}\Amazon Music Helper.exe", "Kind": "helper"}
    monkeypatch.setattr(
        amazon_devtools,
        "stop_amazon_music_for_restart",
        lambda: {"ok": True, "stopped": ["30"], "preserved_helpers": ["31"]},
    )
    monkeypatch.setattr(
        amazon_devtools,
        "stop_amazon_store_packages",
        lambda packages: (_ for _ in ()).throw(AssertionError("Restart must preserve the Store package lifecycle")),
    )
    monkeypatch.setattr(
        amazon_devtools,
        "stop_amazon_helpers",
        lambda: (_ for _ in ()).throw(AssertionError("Restart must preserve Amazon Music Helper")),
    )
    monkeypatch.setattr(amazon_devtools, "launch_amazon_music_devtools", lambda: {"ok": True, "method": "auto-aumid"})
    result = amazon_devtools.restart_amazon_music_devtools()
    assert result["ok"] is True
    assert result["preserved_helpers"] == [str(helper["Pid"])]
    assert result["retired_helpers"] == []
    assert result["reset_packages"] == []


def test_devtools_helper_stop_handles_respawn_before_launch():
    helper = {"Pid": 30, "Name": "Amazon Music Helper.exe", "Kind": "helper"}
    respawned = {"Pid": 31, "Name": "Amazon Music Helper.exe", "Kind": "helper"}
    states = [[helper], [respawned], [], []]
    calls = []

    def entries():
        return states.pop(0) if states else []

    def terminate(items, force):
        calls.append((force, [entry["Pid"] for entry in items]))
        return {"ok": True, "stopped": [str(entry["Pid"]) for entry in items], "errors": []}

    result = amazon_devtools.stop_amazon_helpers(
        timeout=2,
        poll_interval=0.1,
        process_entries_fn=entries,
        terminate_fn=terminate,
        sleep_fn=lambda delay: None,
    )
    assert result["ok"] is True
    assert result["stopped"] == ["30", "31"]
    assert calls == [(True, [30]), (True, [31])]


def test_devtools_launch_preparation_preserves_existing_helpers():
    main = {"Pid": 20, "Name": "Amazon Music.exe", "Kind": "main"}
    helper = {"Pid": 21, "Name": "Amazon Music Helper.exe", "Kind": "helper"}
    running = amazon_devtools._prepare_amazon_launch(process_entries_fn=lambda: [main, helper])
    prepared = amazon_devtools._prepare_amazon_launch(process_entries_fn=lambda: [helper])
    assert running["ok"] is False
    assert running["main_processes"] == ["20"]
    assert prepared["ok"] is True
    assert prepared["preserved_helpers"] == ["21"]
    assert prepared["retired_helpers"] == []
    assert prepared["reset_packages"] == []


def test_devtools_waits_for_splash_screen_to_clear():
    states = iter(
        [
            {"ready": False, "status": "loading", "detail": "loading"},
            {"ready": False, "status": "loading", "detail": "loading"},
            {"ready": True, "status": "ready", "detail": "ready"},
            {"ready": True, "status": "ready", "detail": "ready"},
            {"ready": True, "status": "ready", "detail": "ready"},
        ]
    )
    result = amazon_devtools._wait_for_app_ready(
        52856,
        timeout=1,
        poll_interval=0.2,
        boot_state_fn=lambda port: next(states),
        sleep_fn=lambda delay: None,
    )
    assert result["ok"] is True
    assert result["status"] == "ready"
    assert result["stable_polls"] == amazon_devtools.APP_READY_STABLE_POLLS


def test_devtools_transport_shell_is_not_enough_for_app_readiness():
    loading = amazon_devtools._boot_state_result(
        {
            "readyState": "complete",
            "transport": True,
            "navigationReady": True,
            "mainContentReady": False,
            "mainTextLength": 0,
            "mainChildren": 0,
            "splashVisible": False,
            "bodyChildren": 4,
        }
    )
    ready = amazon_devtools._boot_state_result(
        {
            "readyState": "complete",
            "transport": True,
            "navigationReady": True,
            "mainContentReady": True,
            "mainTextLength": 120,
            "mainChildren": 2,
            "splashVisible": False,
            "bodyChildren": 4,
        }
    )
    assert loading["ready"] is False
    assert ready["ready"] is True


def test_devtools_readiness_stability_resets_after_loading_state():
    states = iter(
        [
            {"ready": True, "status": "ready", "detail": "ready"},
            {"ready": True, "status": "ready", "detail": "ready"},
            {"ready": False, "status": "loading", "detail": "loading"},
            {"ready": True, "status": "ready", "detail": "ready"},
            {"ready": True, "status": "ready", "detail": "ready"},
            {"ready": True, "status": "ready", "detail": "ready"},
        ]
    )
    result = amazon_devtools._wait_for_app_ready(
        52856,
        timeout=2,
        poll_interval=0.2,
        boot_state_fn=lambda port: next(states),
        sleep_fn=lambda delay: None,
    )
    assert result["ok"] is True
    assert result["stable_polls"] == amazon_devtools.APP_READY_STABLE_POLLS


def test_devtools_failed_splash_launch_is_cleaned_up(monkeypatch):
    class Reservation:
        def close(self):
            return None

    amazon_devtools.set_devtools_port(52856)
    monkeypatch.setattr(amazon_devtools, "_is_local_port_open", lambda port: False)
    monkeypatch.setattr(amazon_devtools, "_prepare_amazon_launch", lambda: {"ok": True, "stale_helpers": []})
    monkeypatch.setattr(amazon_devtools, "_reserve_devtools_port", lambda port=None: (52856, Reservation()))
    monkeypatch.setattr(
        amazon_devtools,
        "_launcher_candidates",
        lambda launcher_override=None: [{"kind": "aumid", "value": "Package.Family!AmazonMusic", "method": "auto-aumid"}],
    )
    monkeypatch.setattr(amazon_devtools, "_launch_candidate", lambda candidate, port: {"ok": True, "pid": "44", "activation": "native"})
    monkeypatch.setattr(amazon_devtools, "_wait_for_page_target", lambda port: True)
    monkeypatch.setattr(amazon_devtools, "_devtools_owner_trust", lambda *args, **kwargs: {"trusted": True})
    monkeypatch.setattr(
        amazon_devtools,
        "_wait_for_app_ready",
        lambda port, timeout=amazon_devtools.LAUNCH_READY_TIMEOUT_SECONDS: {
            "ok": False,
            "ready": False,
            "status": "loading",
            "detail": "Amazon Music remained on its loading screen",
        },
    )
    cleanup_calls = []
    monkeypatch.setattr(
        amazon_devtools,
        "stop_amazon_music_for_restart",
        lambda timeout=amazon_devtools.PROCESS_STOP_TIMEOUT_SECONDS: cleanup_calls.append(timeout) or {"ok": True, "stopped": ["44"]},
    )
    result = amazon_devtools.launch_amazon_music_devtools()
    assert result["ok"] is False
    assert cleanup_calls == [6]
    assert "loading screen" in result["error"]
    amazon_devtools.reset_devtools_port()


def test_devtools_port_and_powershell_hardening():
    amazon_devtools.reset_devtools_port()
    port = amazon_devtools.get_devtools_port()
    env = amazon_devtools.devtools_environment({})
    powershell_path = amazon_devtools._powershell_executable()
    launch_source = inspect.getsource(amazon_devtools.launch_amazon_music_devtools)
    aumid_source = inspect.getsource(amazon_devtools._launch_aumid)
    assert amazon_devtools.DEVTOOLS_PORT_MIN <= port <= amazon_devtools.DEVTOOLS_PORT_MAX
    assert port != amazon_devtools.COMMON_DEVTOOLS_PORT
    assert int(env[amazon_devtools.DEVTOOLS_PORT_ENV]) == port
    assert f"--remote-debugging-port={amazon_devtools.COMMON_DEVTOOLS_PORT}" not in launch_source
    assert os.path.isabs(powershell_path) or powershell_path.lower() == "powershell.exe"
    assert '["powershell"' not in aumid_source
    amazon_devtools.reset_devtools_port()


def test_devtools_websocket_target_stays_on_selected_loopback_page():
    target = {
        "id": "page-123",
        "webSocketDebuggerUrl": "ws://127.0.0.1:52856/devtools/page/page-123",
    }
    assert amazon_devtools._valid_target_websocket(target, 52856)
    assert not amazon_devtools._valid_target_websocket({**target, "webSocketDebuggerUrl": "ws://example.com:52856/devtools/page/page-123"}, 52856)
    assert not amazon_devtools._valid_target_websocket({**target, "webSocketDebuggerUrl": "ws://127.0.0.1:52857/devtools/page/page-123"}, 52856)
    assert not amazon_devtools._valid_target_websocket({**target, "webSocketDebuggerUrl": "ws://127.0.0.1:52856/devtools/page/other"}, 52856)


def test_devtools_owner_rejects_confirmed_non_amazon_listener(monkeypatch):
    monkeypatch.setattr(amazon_devtools, "_port_owner_entries", lambda port: [{"Pid": "44", "Name": "malware", "Path": r"C:\Temp\malware.exe"}])
    result = amazon_devtools._devtools_owner_trust(52856, force=True)
    assert result["trusted"] is False
    assert result["status"] == "rejected"


def test_devtools_owner_fails_closed_and_requires_exact_install_identity(monkeypatch, tmp_path):
    monkeypatch.setattr(amazon_devtools, "_port_owner_entries", lambda port: [])
    unavailable = amazon_devtools._devtools_owner_trust(52856, force=True)
    assert unavailable == {
        "trusted": False,
        "status": "unavailable",
        "detail": "Windows could not verify the enhanced metadata listener owner",
    }

    fake = tmp_path / "not-amazonmusic-helper.exe"
    fake.write_bytes(b"fake")
    assert not amazon_devtools._amazon_owner_entry({"Paths": [str(fake)], "Pids": ["44"]}, "44")

    install_dir = tmp_path / "Amazon Music"
    install_dir.mkdir()
    amazon_exe = install_dir / "Amazon Music.exe"
    amazon_exe.write_bytes(b"fake")
    assert not amazon_devtools._amazon_owner_entry({"Paths": [str(amazon_exe)], "Pids": ["45"]}, "45")
    assert amazon_devtools._amazon_owner_entry(
        {"Paths": [str(amazon_exe)], "Pids": ["45"]},
        "45",
        str(amazon_exe),
    )
