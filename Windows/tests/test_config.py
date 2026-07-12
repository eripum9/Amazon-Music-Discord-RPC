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
