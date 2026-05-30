import json

import pytest

import config


def test_enhanced_metadata_defaults_and_region_normalisation():
    assert config.DEFAULTS["amazon_devtools_enabled"] is False
    assert config.DEFAULTS["amazon_devtools_auto_launch"] is False
    assert config.DEFAULTS["enhanced_metadata_prompt_seen"] is False
    assert config.DEFAULTS["notification_enrichment_enabled"] is False
    assert config.DEFAULTS["amazon_music_link_region"] == "com"
    assert config.normalize_amazon_music_link_region("de") == "de"
    assert config.normalize_amazon_music_link_region(".com") == "com"
    assert config.normalize_amazon_music_link_region("bad") == "com"


def test_existing_user_enhanced_metadata_migration():
    migrated = config._complete_config({"discord_client_id": config.DEFAULT_CLIENT_ID})
    fresh = config._complete_config({})
    assert migrated["amazon_devtools_enabled"] is True
    assert migrated["amazon_devtools_auto_launch"] is True
    assert fresh["amazon_devtools_enabled"] is False
    assert fresh["amazon_devtools_auto_launch"] is False


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
