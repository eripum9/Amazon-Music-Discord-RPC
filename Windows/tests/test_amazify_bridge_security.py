# MIT License - Copyright (c) 2026 eripum9

import json
import socket
import urllib.error
import urllib.request

import pytest

import amazify_compat
from amazify_rpc_bridge import AmazifyRpcBridge, TOKEN_HEADER


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def test_amazify_bridge_requires_token_and_exact_amazon_origin():
    port = free_port()
    token = "a" * 64
    bridge = AmazifyRpcBridge(lambda: {"snapshot": {"rpc": "On"}}, lambda command: None, port=port, token=token)
    assert bridge.start()
    try:
        with pytest.raises(urllib.error.HTTPError) as unauthorized:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/state", timeout=2)
        assert unauthorized.value.code == 401

        for origin in (
            "https://evil.example",
            "https://music.amazon.com.evil.com",
            "http://music.amazon.com",
            "https://music.amazon.com/path",
            "https://music.amazon.invalid",
        ):
            bad_origin = urllib.request.Request(
                f"http://127.0.0.1:{port}/state",
                headers={"Origin": origin, "Access-Control-Request-Headers": TOKEN_HEADER},
                method="OPTIONS",
            )
            with pytest.raises(urllib.error.HTTPError) as forbidden:
                urllib.request.urlopen(bad_origin, timeout=2)
            assert forbidden.value.code == 403

        good_origin = urllib.request.Request(
            f"http://127.0.0.1:{port}/state",
            headers={"Origin": "https://music.amazon.com", "Access-Control-Request-Headers": TOKEN_HEADER},
            method="OPTIONS",
        )
        with urllib.request.urlopen(good_origin, timeout=2) as response:
            assert response.headers["Access-Control-Allow-Origin"] == "https://music.amazon.com"

        state_request = urllib.request.Request(f"http://127.0.0.1:{port}/state", headers={TOKEN_HEADER: token})
        state = json.loads(urllib.request.urlopen(state_request, timeout=2).read().decode("utf-8"))
        assert state["snapshot"]["rpc"] == "On"
    finally:
        bridge.stop()


def test_amazify_cleanup_removes_only_rpc_integration(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    root = amazify_compat.amazify_root()
    plugin = amazify_compat.amazify_plugin_root() / amazify_compat.AMAZIFY_PLUGIN_ID
    plugin.mkdir(parents=True)
    (plugin / "plugin.js").write_text("test", encoding="utf-8")
    unrelated = amazify_compat.amazify_plugin_root() / "unrelated.plugin"
    unrelated.mkdir(parents=True)
    amazify_compat._write_json_atomic(root / amazify_compat.AMAZIFY_PLUGIN_STATE, {"enabled": {amazify_compat.AMAZIFY_PLUGIN_ID: True, "unrelated.plugin": True}})
    (root / amazify_compat.AMAZIFY_BRIDGE_TOKEN).write_text("a" * 64, encoding="ascii")
    assert amazify_compat.remove_rpc_plugin()
    state = amazify_compat._read_plugin_state()
    assert not plugin.exists()
    assert unrelated.exists()
    assert state["enabled"] == {"unrelated.plugin": True}
    assert not (root / amazify_compat.AMAZIFY_BRIDGE_TOKEN).exists()
