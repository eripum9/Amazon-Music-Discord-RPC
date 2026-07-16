# MIT License - Copyright (c) 2026 eripum9

import json

import album_art
import network_audit


def test_disabled_lookup_services_do_not_send_requests(monkeypatch):
    album_art._cache.clear()
    monkeypatch.setattr(album_art.requests, "get", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network request")))
    assert album_art.search_tracks("Song Artist", deezer_enabled=False, itunes_enabled=False) == []
    assert album_art.get_album_art("Song", "Artist", deezer_enabled=False, itunes_enabled=False) == (None, "", "", 0)


def test_network_history_is_bounded_and_contains_no_query(tmp_path):
    for index in range(network_audit.MAX_EVENTS + 5):
        network_audit.record_network_event("deezer", "artwork-lookup", "success", f"event {index}", str(tmp_path))
    history = network_audit.network_history(str(tmp_path))
    stored = json.loads((tmp_path / "network-history.json").read_text(encoding="utf-8"))
    assert len(history) == network_audit.MAX_EVENTS
    assert history[-1]["detail"] == f"event {network_audit.MAX_EVENTS + 4}"
    assert stored == history
    assert all(set(item) == {"timestamp", "service", "operation", "status", "detail"} for item in history)
