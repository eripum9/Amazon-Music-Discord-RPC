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


@pytest.mark.parametrize("failure", ["write", "readback"])
def test_legacy_migration_failure_preserves_file(isolated_config, monkeypatch, failure):
    config_dir, store = isolated_config
    config_dir.mkdir(parents=True)
    path = config_dir / "config.json"
    original = json.dumps({"listenbrainz_token": "legacy-token", "show_paused": False,
                           config.CONFIG_REVISION_KEY: 7})
    path.write_text(original, encoding="utf-8")
    if failure == "write":
        monkeypatch.setattr(config, "_keychain_write", lambda key, value: False)
    else:
        monkeypatch.setattr(config, "_keychain_read", lambda key: "different-token")

    with pytest.raises(OSError):
        config.load_config()
    assert path.read_text(encoding="utf-8") == original


def test_partial_legacy_migration_retries_without_losing_values(isolated_config, monkeypatch):
    config_dir, store = isolated_config
    config_dir.mkdir(parents=True)
    path = config_dir / "config.json"
    keys = ("listenbrainz_token", "lastfm_session_key")
    monkeypatch.setattr(config, "SENSITIVE_CONFIG_KEYS", keys)
    original = json.dumps({keys[0]: "first", keys[1]: "second", "show_paused": False,
                           config.CONFIG_REVISION_KEY: 9})
    path.write_text(original, encoding="utf-8")
    write = config._keychain_write
    monkeypatch.setattr(config, "_keychain_write", lambda key, value: key != keys[1] and write(key, value))

    with pytest.raises(OSError):
        config.load_config()
    assert path.read_text(encoding="utf-8") == original
    assert store == {keys[0]: "first"}

    monkeypatch.setattr(config, "_keychain_write", write)
    loaded = config.load_config()
    assert [loaded[key] for key in keys] == ["first", "second"]
    assert store == {keys[0]: "first", keys[1]: "second"}
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "show_paused": False, config.CONFIG_REVISION_KEY: 9
    }


def test_redaction_removes_secret_values(isolated_config):
    payload = {
        "listenbrainz_token": "top-secret-token",
        "message": "Authorization: Token top-secret-token",
    }
    redacted = config.redact_data(payload, payload)
    assert redacted["listenbrainz_token"] == config.REDACTION_TEXT
    assert "top-secret-token" not in redacted["message"]


def test_partial_keychain_save_invalidates_stale_revision(isolated_config, monkeypatch):
    config_dir, store = isolated_config
    keys = ("listenbrainz_token", "lastfm_session_key")
    monkeypatch.setattr(config, "SENSITIVE_CONFIG_KEYS", keys)
    config.update_config_fields({keys[0]: "old-token", keys[1]: "old-session"})
    stale = config.load_config()
    write = config._keychain_write
    monkeypatch.setattr(config, "_keychain_write", lambda key, value: key != keys[1] and write(key, value))
    with pytest.raises(OSError):
        config.update_config_fields({keys[0]: "new-token", keys[1]: "", "show_paused": False})
    public = json.loads((config_dir / "config.json").read_text(encoding="utf-8"))
    assert public[config.CONFIG_REVISION_KEY] == stale[config.CONFIG_REVISION_KEY] + 1
    assert public["show_paused"] == stale["show_paused"]
    assert store[keys[0]] == "new-token"
    with pytest.raises(config.ConfigConflictError):
        config.save_config(stale)


@pytest.mark.parametrize("failure", [None, 1])
def test_keychain_read_failure_preserves_secrets_and_public_settings(isolated_config, monkeypatch, failure):
    config_dir, store = isolated_config
    config.update_config_fields({"listenbrainz_token": "existing-token"})
    original = (config_dir / "config.json").read_bytes()
    security = config._security
    def fail_read(args, **kwargs):
        if args[0] == "find-generic-password":
            return None if failure is None else SimpleNamespace(returncode=failure, stdout="", stderr="locked")
        return security(args, **kwargs)
    monkeypatch.setattr(config, "_security", fail_read)
    with pytest.raises(OSError, match="Keychain"):
        config.update_config_fields({"privacy_private_session": True})
    assert store["listenbrainz_token"] == "existing-token"
    assert (config_dir / "config.json").read_bytes() == original


@pytest.mark.parametrize("code,expected", [(None, False), (1, False), (0, True), (44, True)])
def test_keychain_deletion_requires_confirmed_result(isolated_config, monkeypatch, code, expected):
    monkeypatch.setattr(config, "_security", lambda *args, **kwargs: None if code is None else SimpleNamespace(returncode=code))
    assert config._keychain_delete("listenbrainz_token") is expected
    assert config.clear_sensitive_credentials() is expected


def test_public_update_does_not_rewrite_credentials(isolated_config, monkeypatch):
    _, store = isolated_config
    config.update_config_fields({"listenbrainz_token": "existing-token"})
    monkeypatch.setattr(config, "_keychain_write", lambda *args: (_ for _ in ()).throw(AssertionError("unrelated credential write")))
    config.update_config_fields({"privacy_private_session": True})
    config.mutate_config_fields({"show_paused"}, lambda current: {"show_paused": not current["show_paused"]})
    assert store["listenbrainz_token"] == "existing-token"


def test_public_only_revisioned_save_preserves_privacy_and_secrets(isolated_config):
    _, store = isolated_config
    saved = config.update_config_fields({"privacy_private_session": True, "listenbrainz_token": "existing-token"})
    result = config.save_config({config.CONFIG_REVISION_KEY: saved[config.CONFIG_REVISION_KEY], "show_paused": False})
    assert result["privacy_private_session"] is True
    assert result["listenbrainz_token"] == "existing-token"
    assert store["listenbrainz_token"] == "existing-token"


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
