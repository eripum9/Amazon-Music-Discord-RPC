# MIT License - Copyright (c) 2026 eripum9

import security_trust


def test_redaction_audit_detects_token_leaks_and_tracks_storage(monkeypatch):
    monkeypatch.setattr(
        security_trust,
        "credential_storage_status",
        lambda: {"credential_manager_available": True, "credential_manager_keys": ["listenbrainz_token"], "dpapi_fallback_keys": []},
    )
    config = {
        "listenbrainz_token": "listenbrainz_secret_value",
        "lastfm_session_key": "lastfm_secret_value",
        "lastfm_api_secret": "lastfm_app_secret_value",
    }
    clean = security_trust.redaction_audit(config, {"report": {"token": "[redacted]"}})
    leaked = security_trust.redaction_audit(config, {"report": f"Token {config['listenbrainz_token']}"})
    review = security_trust.token_storage_review(config)
    assert clean["ok"] is True
    assert leaked["ok"] is False
    assert leaked["leaks"] == [{"key": "listenbrainz_token", "location": "report"}]
    assert review["storage"] == "windows-credential-manager"
    assert review["redaction_required"] is True
    assert "listenbrainz_token" in review["present_keys"]
    assert review["at_rest_protection"] == "Windows Credential Manager with DPAPI fallback"


def test_release_notes_trust_check_requires_installer_changelog_and_compatibility():
    good = """
## What's New

- Fixed enhanced metadata compatibility for Microsoft Store users.

## Installation

Download AmazonMusicRPC_Setup.exe and its checksum sidecar.

Fallback mode remains available when enhanced metadata cannot attach.
"""
    bad = "AmazonMusicRPC_Setup.exe"
    assert security_trust.release_notes_trust_errors(good) == []
    errors = security_trust.release_notes_trust_errors(bad)
    assert "Release notes do not include a compatibility note" in errors
    assert "Release notes do not include a changelog bullet" in errors
