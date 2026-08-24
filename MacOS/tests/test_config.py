# MIT License - Copyright (c) 2026 eripum9

import json
import plistlib
from types import SimpleNamespace

import pytest

from MacOS import config


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    store = {}
    config_dir = tmp_path / "Application Support" / config.APP_NAME
    monkeypatch.setattr(config, "CONFIG_DIR", str(config_dir))
    monkeypatch.setattr(config, "CONFIG_PATH", str(config_dir / "config.json"))
    monkeypatch.setattr(config, "LOG_PATH", str(config_dir / "console.log"))
    monkeypatch.setattr(config, "LAUNCH_AGENT_PATH", str(tmp_path / "LaunchAgents" / "app.plist"))

    def security(args, **kwargs):
        command = args[0]
        account = args[args.index("-a") + 1]
        if command == "find-generic-password":
            if account not in store:
                return SimpleNamespace(returncode=44, stdout="", stderr="missing")
            return SimpleNamespace(returncode=0, stdout=store[account] + "\n", stderr="")
        if command == "add-generic-password":
            store[account] = args[args.index("-w") + 1]
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if command == "delete-generic-password":
            store.pop(account, None)
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        raise AssertionError(args)

    monkeypatch.setattr(config, "_security", security)
    return config_dir, store


def test_defaults_enable_devtools_primary_without_disruptive_auto_restart(isolated_config):
    loaded = config.load_config()
    assert loaded["amazon_devtools_enabled"] is True
    assert loaded["amazon_devtools_auto_launch"] is False
    assert loaded["show_paused"] is True
    assert loaded["song_link_enabled"] is True


def test_secrets_are_written_only_to_keychain(isolated_config):
    config_dir, store = isolated_config
    saved = config.update_config_fields(
        {
            "listenbrainz_token": "lb-secret",
            "lastfm_session_key": "fm-secret",
            "lastfm_enabled": True,
        }
    )
    public = json.loads((config_dir / "config.json").read_text(encoding="utf-8"))
    assert "listenbrainz_token" not in public
    assert "lastfm_session_key" not in public
    assert store["listenbrainz_token"] == "lb-secret"
    assert store["lastfm_session_key"] == "fm-secret"
    assert config.load_config()["listenbrainz_token"] == "lb-secret"
    assert saved[config.CONFIG_REVISION_KEY] == 1


def test_revisions_prevent_lost_updates(isolated_config):
    first = config.update_config_fields({"show_paused": False})
    second = config.update_config_fields({"song_link_enabled": False})
    first["show_paused"] = True
    with pytest.raises(config.ConfigConflictError):
        config.save_config(first)
    assert config.load_config()["song_link_enabled"] is False
    assert second[config.CONFIG_REVISION_KEY] == 2


def test_plaintext_legacy_secret_is_migrated(isolated_config):
    config_dir, store = isolated_config
    config_dir.mkdir(parents=True)
    (config_dir / "config.json").write_text(
        json.dumps({"listenbrainz_token": "legacy-token"}), encoding="utf-8"
    )
    assert config.load_config()["listenbrainz_token"] == "legacy-token"
    assert store["listenbrainz_token"] == "legacy-token"
    assert "listenbrainz_token" not in json.loads(
        (config_dir / "config.json").read_text(encoding="utf-8")
    )


def test_redaction_removes_secret_values(isolated_config):
    payload = {
        "listenbrainz_token": "top-secret-token",
        "message": "Authorization: Token top-secret-token",
    }
    redacted = config.redact_data(payload, payload)
    assert redacted["listenbrainz_token"] == config.REDACTION_TEXT
    assert "top-secret-token" not in redacted["message"]


def test_startup_uses_launch_agent(isolated_config, monkeypatch):
    monkeypatch.setattr(config.sys, "argv", ["/repo/MacOS/main.py"])
    config.set_startup(True, start_minimized=True)
    with open(config.LAUNCH_AGENT_PATH, "rb") as handle:
        payload = plistlib.load(handle)
    assert payload["Label"] == config.BUNDLE_IDENTIFIER
    assert payload["RunAtLoad"] is True
    assert payload["ProgramArguments"][-1] == "--startup"
    assert config.is_startup_enabled() is True
    config.set_startup(False)
    assert config.is_startup_enabled() is False


def test_unknown_setting_is_rejected(isolated_config):
    with pytest.raises(KeyError):
        config.update_config_fields({"not_a_setting": True})
