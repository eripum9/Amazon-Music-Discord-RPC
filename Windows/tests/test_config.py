# MIT License - Copyright (c) 2026 eripum9

import json

import pytest

import config


class MemoryCredentialStore:
    def __init__(self, available=True, writable=True):
        self.available = available
        self.writable = writable
        self.values = {}

    def write(self, key, value):
        if not self.available or not self.writable:
            return False
        self.values[key] = value
        return True

    def read(self, key):
        return self.values.get(key, "") if self.available else ""

    def delete(self, key):
        self.values.pop(key, None)
        return self.available


@pytest.fixture(autouse=True)
def isolated_credential_storage(tmp_path, monkeypatch):
    store = MemoryCredentialStore()
    monkeypatch.setattr(config, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(config, "CONFIG_PATH", str(tmp_path / "config.json"))
    monkeypatch.setattr(config, "_credential_store", lambda: store)


def test_enhanced_metadata_defaults_and_region_normalisation():
    assert config.DEFAULTS["amazon_devtools_enabled"] is False
    assert config.DEFAULTS["amazon_devtools_auto_launch"] is False
    assert config.DEFAULTS["enhanced_metadata_prompt_seen"] is False
    assert config.DEFAULTS["setup_wizard_seen"] is False
    assert config.DEFAULTS["notification_enrichment_enabled"] is False
    assert config.DEFAULTS["amazon_music_link_region"] == "com"
    assert config.DEFAULTS["discord_status_display"] == "artist"
    assert config.DEFAULTS["automatic_update_checks"] is True
    assert config.DEFAULTS["deezer_lookup_enabled"] is True
    assert config.DEFAULTS["itunes_lookup_enabled"] is True
    assert config.normalize_amazon_music_link_region("de") == "de"
    assert config.normalize_amazon_music_link_region(".com") == "com"
    assert config.normalize_amazon_music_link_region("bad") == "com"
    assert config.normalize_discord_status_display("album") == "album"
    assert config.normalize_discord_status_display("TRACK") == "track"
    assert config.normalize_discord_status_display("bad") == "artist"


def test_existing_user_enhanced_metadata_migration():
    migrated = config._complete_config({"discord_client_id": config.DEFAULT_CLIENT_ID})
    fresh = config._complete_config({})
    assert migrated["amazon_devtools_enabled"] is True
    assert migrated["amazon_devtools_auto_launch"] is True
    assert migrated["setup_wizard_seen"] is True
    assert fresh["amazon_devtools_enabled"] is False
    assert fresh["amazon_devtools_auto_launch"] is False
    assert fresh["setup_wizard_seen"] is False


def test_config_save_is_atomic_and_update_reads_stay_strict(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    monkeypatch.setattr(config, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(config, "CONFIG_PATH", str(path))
    payload = {**config.DEFAULTS, "amazon_music_link_region": "de"}
    config.save_config(payload)
    assert json.loads(path.read_text(encoding="utf-8"))["amazon_music_link_region"] == "de"
    path.write_text("", encoding="utf-8")
    assert config.load_config()["amazon_music_link_region"] == "com"
    with pytest.raises(json.JSONDecodeError):
        config.load_config_for_update()


def test_sensitive_values_use_credential_manager_and_stay_plain_in_memory(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    store = MemoryCredentialStore()
    monkeypatch.setattr(config, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(config, "CONFIG_PATH", str(path))
    monkeypatch.setattr(config, "_credential_store", lambda: store)
    payload = {
        **config.DEFAULTS,
        "listenbrainz_token": "plain-listenbrainz-token",
        "lastfm_session_key": "plain-lastfm-session",
    }
    config.save_config(payload)
    stored = path.read_text(encoding="utf-8")
    assert "plain-listenbrainz-token" not in stored
    assert "plain-lastfm-session" not in stored
    assert "listenbrainz_token" not in json.loads(stored)
    assert "lastfm_session_key" not in json.loads(stored)
    assert not (tmp_path / "secrets.dpapi.json").exists()
    assert store.values["listenbrainz_token"] == "plain-listenbrainz-token"
    assert store.values["lastfm_session_key"] == "plain-lastfm-session"
    loaded = config.load_config_for_update()
    assert loaded["listenbrainz_token"] == "plain-listenbrainz-token"
    assert loaded["lastfm_session_key"] == "plain-lastfm-session"


def test_sensitive_values_migrate_to_credential_manager(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    store = MemoryCredentialStore()
    monkeypatch.setattr(config, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(config, "CONFIG_PATH", str(path))
    monkeypatch.setattr(config, "_credential_store", lambda: store)
    path.write_text(
        json.dumps(
            {
                **config.DEFAULTS,
                "listenbrainz_token": "legacy-listenbrainz-token",
                "lastfm_session_key": "legacy-lastfm-session",
            }
        ),
        encoding="utf-8",
    )
    loaded = config.load_config_for_update()
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["listenbrainz_token"] == "legacy-listenbrainz-token"
    assert loaded["lastfm_session_key"] == "legacy-lastfm-session"
    assert "listenbrainz_token" not in stored
    assert "lastfm_session_key" not in stored
    assert store.values["listenbrainz_token"] == "legacy-listenbrainz-token"
    assert store.values["lastfm_session_key"] == "legacy-lastfm-session"
    assert not (tmp_path / "secrets.dpapi.json").exists()


def test_credential_manager_failure_keeps_dpapi_fallback(tmp_path, monkeypatch):
    if not config._dpapi_available():
        pytest.skip("DPAPI is only available on Windows")
    path = tmp_path / "config.json"
    store = MemoryCredentialStore(writable=False)
    monkeypatch.setattr(config, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(config, "CONFIG_PATH", str(path))
    monkeypatch.setattr(config, "_credential_store", lambda: store)
    config.save_config({**config.DEFAULTS, "listenbrainz_token": "dpapi-fallback-token"})
    fallback = (tmp_path / "secrets.dpapi.json").read_text(encoding="utf-8")
    assert "dpapi-fallback-token" not in fallback
    assert "dpapi:" in fallback
    assert config.load_config_for_update()["listenbrainz_token"] == "dpapi-fallback-token"

    store.writable = True
    loaded = config.load_config_for_update()
    assert loaded["listenbrainz_token"] == "dpapi-fallback-token"
    assert store.values["listenbrainz_token"] == "dpapi-fallback-token"
    assert not (tmp_path / "secrets.dpapi.json").exists()


@pytest.mark.parametrize("delete_result", [False, True])
def test_clearing_secret_rejects_failed_or_ineffective_delete(tmp_path, monkeypatch, delete_result):
    store = MemoryCredentialStore()
    store.values["listenbrainz_token"] = "old-token"
    monkeypatch.setattr(config, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(config, "CONFIG_PATH", str(tmp_path / "config.json"))
    monkeypatch.setattr(config, "_credential_store", lambda: store)
    monkeypatch.setattr(store, "delete", lambda key: delete_result)

    with pytest.raises(OSError):
        config._write_secret_config({})
    assert store.values["listenbrainz_token"] == "old-token"


@pytest.mark.parametrize("available,writable", [(True, True), (True, False), (False, False)])
def test_secret_clear_and_fallback_with_isolated_store(tmp_path, monkeypatch, available, writable):
    store = MemoryCredentialStore(available=available, writable=writable)
    monkeypatch.setattr(config, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(config, "CONFIG_PATH", str(tmp_path / "config.json"))
    monkeypatch.setattr(config, "_credential_store", lambda: store)
    monkeypatch.setattr(config, "protect_sensitive_config", lambda values: dict(values))
    monkeypatch.setattr(config, "unprotect_sensitive_config", lambda values: dict(values))

    config._write_secret_config({"listenbrainz_token": "token"})
    assert config._read_secret_config()["listenbrainz_token"] == "token"
    assert (tmp_path / "secrets.dpapi.json").exists() == (not available or not writable)
    config._write_secret_config({})
    assert not any(config._read_secret_config().values())
    assert (tmp_path / "secrets.dpapi.json").exists() == (not available)


@pytest.mark.parametrize("clear_all", [False, True])
def test_cleared_secret_cannot_return_after_store_recovers(tmp_path, monkeypatch, clear_all):
    store = MemoryCredentialStore()
    store.values["listenbrainz_token"] = "old-token"
    monkeypatch.setattr(config, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(config, "CONFIG_PATH", str(tmp_path / "config.json"))
    monkeypatch.setattr(config, "_credential_store", lambda: store)
    store.available = False
    if clear_all:
        assert not config.clear_sensitive_credentials()
    else:
        config._write_secret_config({})
    store.available = True
    assert not config._read_secret_config().get("listenbrainz_token")
    if clear_all:
        config.load_config_for_update()
    else:
        config._write_secret_config(config._read_secret_config())
    assert "listenbrainz_token" not in store.values
    assert not (tmp_path / "secrets.dpapi.json").exists()


def test_fallback_token_takes_precedence_until_store_recovers(tmp_path, monkeypatch):
    store = MemoryCredentialStore(available=False)
    store.values["listenbrainz_token"] = "old-token"
    monkeypatch.setattr(config, "CONFIG_PATH", str(tmp_path / "config.json"))
    monkeypatch.setattr(config, "_credential_store", lambda: store)
    monkeypatch.setattr(config, "protect_sensitive_config", lambda values: dict(values))
    monkeypatch.setattr(config, "unprotect_sensitive_config", lambda values: dict(values))
    config._write_secret_config({"listenbrainz_token": "replacement-token"})
    store.available = True
    assert config._read_secret_config()["listenbrainz_token"] == "replacement-token"
    config._write_secret_config(config._read_secret_config())
    assert store.values["listenbrainz_token"] == "replacement-token"
    assert not (tmp_path / "secrets.dpapi.json").exists()


def test_partial_secret_failure_invalidates_stale_revision(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    store = MemoryCredentialStore()
    monkeypatch.setattr(config, "CONFIG_PATH", str(path))
    monkeypatch.setattr(config, "SENSITIVE_CONFIG_KEYS", ("listenbrainz_token", "lastfm_session_key"))
    monkeypatch.setattr(config, "_credential_store", lambda: store)
    config.save_config({**config.DEFAULTS, "listenbrainz_token": "old-token", "lastfm_session_key": "old-session"})
    stale = config.load_config_for_update()
    monkeypatch.setattr(store, "delete", lambda key: False)
    with pytest.raises(OSError):
        config.update_config_fields({"listenbrainz_token": "new-token", "lastfm_session_key": "", "show_paused": False})
    saved_public = json.loads(path.read_text(encoding="utf-8"))
    assert saved_public[config.CONFIG_REVISION_KEY] == stale[config.CONFIG_REVISION_KEY] + 1
    assert saved_public["show_paused"] == stale["show_paused"]
    assert store.values["listenbrainz_token"] == "new-token"
    with pytest.raises(config.ConfigConflictError):
        config.save_config(stale)


@pytest.mark.parametrize("operation", ["update", "mutate"])
@pytest.mark.parametrize("available,writable", [(False, False), (True, False)])
def test_public_updates_preserve_unavailable_credentials(tmp_path, monkeypatch, operation, available, writable):
    store = MemoryCredentialStore(available=available, writable=writable)
    store.values["listenbrainz_token"] = "existing-token"
    monkeypatch.setattr(config, "_credential_store", lambda: store)
    if operation == "update":
        config.update_config_fields({"privacy_private_session": True})
    else:
        config.mutate_config_fields({"show_paused"}, lambda current: {"show_paused": not current["show_paused"]})
    assert store.values["listenbrainz_token"] == "existing-token"
    assert not (tmp_path / "secrets.dpapi.json").exists()
    store.available = True
    assert config.load_config()["listenbrainz_token"] == "existing-token"


def test_partial_secret_update_preserves_other_pending_fallbacks(tmp_path, monkeypatch):
    store = MemoryCredentialStore(available=False)
    monkeypatch.setattr(config, "_credential_store", lambda: store)
    monkeypatch.setattr(config, "protect_sensitive_config", lambda values: dict(values))
    monkeypatch.setattr(config, "unprotect_sensitive_config", lambda values: dict(values))
    config.update_config_fields({"listenbrainz_token": "first-token"})
    config.update_config_fields({"lastfm_session_key": "second-token"})
    config.update_config_fields({"listenbrainz_token": ""})
    store.available = True
    restored = config.load_config()
    assert restored["listenbrainz_token"] == ""
    assert restored["lastfm_session_key"] == "second-token"
    assert store.values["lastfm_session_key"] == "second-token"
    assert not (tmp_path / "secrets.dpapi.json").exists()


def test_whole_save_rejects_unknown_unavailable_credentials(tmp_path, monkeypatch):
    store = MemoryCredentialStore()
    monkeypatch.setattr(config, "_credential_store", lambda: store)
    config.save_config({**config.DEFAULTS, "listenbrainz_token": "existing-token"})
    store.available = False
    unknown_snapshot = config.load_config()
    unknown_snapshot["show_paused"] = False
    with pytest.raises(OSError, match="field-specific"):
        config.save_config(unknown_snapshot)
    assert store.values["listenbrainz_token"] == "existing-token"


def test_public_only_revisioned_save_preserves_unknown_secrets_and_privacy(monkeypatch):
    store = MemoryCredentialStore()
    monkeypatch.setattr(config, "_credential_store", lambda: store)
    saved = config.save_config({**config.DEFAULTS, "listenbrainz_token": "existing-token", "privacy_private_session": True})
    store.available = False
    result = config.save_config({config.CONFIG_REVISION_KEY: saved[config.CONFIG_REVISION_KEY], "show_paused": False})
    assert result["privacy_private_session"] is True
    assert store.values["listenbrainz_token"] == "existing-token"
    store.available = True
    assert config.load_config()["listenbrainz_token"] == "existing-token"


@pytest.mark.parametrize("effective_delete", [False, True])
def test_pending_deletion_preserves_privacy_when_repair_fails(tmp_path, monkeypatch, effective_delete):
    store = MemoryCredentialStore()
    store.values["listenbrainz_token"] = "old-token"
    monkeypatch.setattr(config, "_credential_store", lambda: store)
    config.update_config_fields({"privacy_private_session": True, "privacy_blocked_keywords": "Blocked"})
    store.available = False
    cleared = config.update_config_fields({"listenbrainz_token": ""})
    store.available = True
    monkeypatch.setattr(store, "delete", lambda key: effective_delete)
    for loader in (config.load_config, config.load_config_for_update):
        loaded = loader()
        assert loaded["privacy_private_session"] is True
        assert loaded["privacy_blocked_keywords"] == "Blocked"
        assert loaded["listenbrainz_token"] == ""
        assert loaded[config.CONFIG_REVISION_KEY] == cleared[config.CONFIG_REVISION_KEY]
    updated = config.update_config_fields({"show_paused": False})
    assert updated["privacy_private_session"] is True
    assert (tmp_path / "secrets.dpapi.json").exists()


@pytest.mark.parametrize("location", ["fallback", "legacy"])
def test_failed_dpapi_decode_is_not_a_deletion_request(tmp_path, monkeypatch, location):
    store = MemoryCredentialStore()
    monkeypatch.setattr(config, "_credential_store", lambda: store)
    config.save_config({**config.DEFAULTS, "listenbrainz_token": "existing-token", "privacy_private_session": True})
    path = tmp_path / ("secrets.dpapi.json" if location == "fallback" else "config.json")
    payload = {} if location == "fallback" else json.loads(path.read_text(encoding="utf-8"))
    payload["listenbrainz_token"] = "dpapi:invalid"
    path.write_text(json.dumps(payload), encoding="utf-8")
    original = path.read_bytes()
    monkeypatch.setattr(config, "_dpapi_unprotect_text", lambda value: "" if value.startswith("dpapi:") else value)
    with pytest.raises(OSError, match="decrypt"):
        config.load_config_for_update()
    assert store.values["listenbrainz_token"] == "existing-token"
    assert path.read_bytes() == original
    assert config.load_config()["privacy_private_session"] is True


@pytest.mark.parametrize("payload", [[], "invalid", None])
def test_invalid_secret_file_preserves_public_privacy(tmp_path, payload):
    config.update_config_fields({"privacy_private_session": True, "privacy_blocked_keywords": "Blocked"})
    path = tmp_path / "secrets.dpapi.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    original = path.read_bytes()
    with pytest.raises(OSError, match="JSON object"):
        config.load_config_for_update()
    loaded = config.load_config()
    assert loaded["privacy_private_session"] is True
    assert loaded["privacy_blocked_keywords"] == "Blocked"
    assert path.read_bytes() == original


def test_secret_redaction_covers_text_and_nested_data():
    secrets = {
        "listenbrainz_token": "listenbrainz_secret_value",
        "lastfm_session_key": "lastfm_secret_value",
        "lastfm_api_secret": "lastfm_app_secret_value",
    }
    text = 'Token listenbrainz_secret_value "lastfm_session_key": "lastfm_secret_value" lastfm_app_secret_value'
    redacted_text = config.redact_text(text, secrets)
    redacted_data = config.redact_data(
        {
            "listenbrainz_token": secrets["listenbrainz_token"],
            "nested": {"value": secrets["lastfm_session_key"]},
        },
        secrets,
    )
    combined = redacted_text + json.dumps(redacted_data)
    assert all(secret not in combined for secret in secrets.values())
    assert config.REDACTION_TEXT in combined


def test_stale_whole_save_cannot_restore_privacy_or_cleared_tokens(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    store = MemoryCredentialStore()
    monkeypatch.setattr(config, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(config, "CONFIG_PATH", str(path))
    monkeypatch.setattr(config, "_credential_store", lambda: store)

    config.save_config({**config.DEFAULTS, "listenbrainz_token": "old-token"})
    stale = config.load_config_for_update()
    secured = config.update_config_fields(
        {
            "listenbrainz_token": "",
            "listenbrainz_enabled": False,
            "privacy_private_session": True,
        }
    )
    stale["show_paused"] = False

    with pytest.raises(config.ConfigConflictError):
        config.save_config(stale)

    current = config.load_config_for_update()
    assert current["privacy_private_session"] is True
    assert current["listenbrainz_token"] == ""
    assert current[config.CONFIG_REVISION_KEY] == secured[config.CONFIG_REVISION_KEY]


def test_field_specific_updates_merge_against_current_revision(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    monkeypatch.setattr(config, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(config, "CONFIG_PATH", str(path))
    config.save_config({**config.DEFAULTS, "privacy_private_session": False})
    stale_revision = config.load_config()[config.CONFIG_REVISION_KEY]
    config.update_config_fields({"privacy_private_session": True})
    merged = config.update_config_fields({"show_paused": False}, expected_revision=stale_revision)
    assert merged["privacy_private_session"] is True
    assert merged["show_paused"] is False
