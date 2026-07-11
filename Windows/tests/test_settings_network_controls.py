import settings_ui


def _settings_payload():
    payload = {key: False for key in settings_ui._REQUIRED_SETTINGS_KEYS}
    payload.update(
        {
            "client_id": "",
            "discord_status_display": "artist",
            "privacy_blocked_keywords": "",
            "game_mode_processes": "",
            "custom_albums": [],
            "song_link_provider": "amazon",
            "amazon_music_link_region": "com",
            "amazon_music_launcher_override": "",
            "listenbrainz_token": "",
        }
    )
    return payload


def test_settings_payload_requires_network_controls():
    assert {
        "automatic_update_checks",
        "deezer_lookup_enabled",
        "itunes_lookup_enabled",
    }.issubset(settings_ui._REQUIRED_SETTINGS_KEYS)


def test_settings_payload_applies_network_controls():
    payload = _settings_payload()
    payload.update(
        {
            "automatic_update_checks": True,
            "deezer_lookup_enabled": False,
            "itunes_lookup_enabled": True,
        }
    )
    config = settings_ui._settings_config_from_payload(payload, {})
    assert config["automatic_update_checks"] is True
    assert config["deezer_lookup_enabled"] is False
    assert config["itunes_lookup_enabled"] is True


def test_settings_html_exposes_network_controls():
    assert 'id="automaticUpdateChecks"' in settings_ui.HTML_TEMPLATE
    assert 'id="deezerLookupEnabled"' in settings_ui.HTML_TEMPLATE
    assert 'id="itunesLookupEnabled"' in settings_ui.HTML_TEMPLATE
