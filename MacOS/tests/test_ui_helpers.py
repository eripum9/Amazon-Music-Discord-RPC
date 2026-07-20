import pytest

from MacOS import config
from MacOS.ui import (
    UIValidationError,
    clean_custom_albums,
    diagnostic_document,
    settings_export_payload,
    settings_import_updates,
    snapshot_rows,
)
from Shared.track_picker_ui import search_page, track_payload


def test_clean_custom_albums_normalizes_aliases_and_empty_rows():
    value = clean_custom_albums(
        """[
          {"album":" Album ","aliases":["Deluxe", "deluxe", " Live "],"art_url":"https://example.test/a.jpg"},
          {"album":"", "aliases":[], "art_url":""}
        ]"""
    )

    assert value == [
        {
            "album": "Album",
            "aliases": ["Deluxe", "Live"],
            "art_url": "https://example.test/a.jpg",
        }
    ]


@pytest.mark.parametrize(
    "value, message",
    [
        ("not json", "invalid"),
        ({"album": "x"}, "array"),
        ([{"album": "Album", "art_url": "file:///tmp/x.png"}], "HTTP"),
        ([{"album": "Album"}], "artwork URL"),
    ],
)
def test_clean_custom_albums_rejects_unsafe_or_invalid_rows(value, message):
    with pytest.raises(UIValidationError, match=message):
        clean_custom_albums(value)


def test_settings_export_secrets_are_explicit_opt_in():
    settings = {
        **config.DEFAULTS,
        "listenbrainz_token": "lb-secret-value",
        "lastfm_session_key": "lastfm-session-value",
    }

    public = settings_export_payload(settings, False, "2026-07-20T12:00:00+00:00")
    private = settings_export_payload(settings, True, "2026-07-20T12:00:00+00:00")

    assert public["format"] == "AmazonMusicRPC.settings"
    assert public["include_tokens"] is False
    assert public["includes_secrets"] is False
    assert "listenbrainz_token" not in public["config"]
    assert "lastfm_session_key" not in public["config"]
    assert private["config"]["listenbrainz_token"] == "lb-secret-value"
    assert private["config"]["lastfm_session_key"] == "lastfm-session-value"
    assert private["include_tokens"] is True


def test_settings_import_accepts_wrapper_ignores_unknown_and_normalizes():
    updates = settings_import_updates(
        {
            "format": "amazon-music-rpc-settings",
            "config": {
                "show_paused": False,
                "amazon_music_link_region": ".DE",
                "discord_status_display": "unexpected",
                "future_setting": "ignored",
            },
        }
    )

    assert updates == {
        "show_paused": False,
        "amazon_music_link_region": "de",
        "discord_status_display": "artist",
    }


def test_settings_import_does_not_coerce_ambiguous_boolean():
    with pytest.raises(UIValidationError, match="show_paused"):
        settings_import_updates({"show_paused": "false"})


def test_wrapped_import_only_accepts_secrets_when_declared():
    hidden = settings_import_updates(
        {"config": {"listenbrainz_token": "secret", "show_paused": True}}
    )
    included = settings_import_updates(
        {
            "include_tokens": True,
            "config": {"listenbrainz_token": "secret", "show_paused": True},
        }
    )

    assert "listenbrainz_token" not in hidden
    assert included["listenbrainz_token"] == "secret"


def test_snapshot_rows_surface_live_service_and_privacy_state():
    rows = snapshot_rows(
        {
            "rpc_status": "running",
            "discord_status": "connected",
            "presence_visible": True,
            "source": "Amazon metadata",
            "amazon_devtools": {"detail": "Loopback endpoint found"},
            "scrobbling": {"lastfm": "active", "listenbrainz": "missing_token"},
            "privacy": {"hidden": True, "reason": "Matched privacy keyword"},
        }
    )

    assert rows[0][0:2] == ("Runtime", "running")
    assert rows[1][0:2] == ("Discord", "connected")
    assert rows[3][1] == "active"
    assert rows[4][1] == "missing_token"
    assert rows[5][1:] == ("hidden", "Matched privacy keyword")


def test_diagnostic_document_redacts_runtime_and_omits_secret_settings(monkeypatch):
    monkeypatch.setattr(
        config,
        "credential_storage_status",
        lambda: {"keychain_available": True, "keychain_keys": ["listenbrainz_token"]},
    )
    settings = {
        **config.DEFAULTS,
        "listenbrainz_token": "super-secret-token",
        "lastfm_session_key": "lastfm-secret-token",
    }
    document = diagnostic_document(
        {"last_error": "Authorization: Token super-secret-token"},
        settings,
        [{"detail": "super-secret-token"}],
        "2026-07-20T12:00:00+00:00",
    )

    serialized = str(document)
    assert "super-secret-token" not in serialized
    assert "lastfm-secret-token" not in serialized
    assert "[redacted]" in serialized
    assert "listenbrainz_token" not in document["settings"]


def test_shared_track_payload_and_legacy_search_paging():
    calls = []

    def legacy_search(query, limit):
        calls.append((query, limit))
        return [{"title": "Only result", "duration": "12.5"}]

    assert search_page("song artist", 5, 1, legacy_search) == []
    assert calls == []
    assert track_payload({"title": "  Song ", "duration": "12.5"}) == {
        "title": "Song",
        "artist": "",
        "album": "",
        "art_url": "",
        "track_link": "",
        "duration": 12.5,
    }
