# MIT License - Copyright (c) 2026 eripum9

import media_reader


def test_smtc_device_not_ready_is_treated_as_no_track(monkeypatch):
    async def unavailable():
        raise OSError(-2147024875, "The device is not ready")

    monkeypatch.setattr(media_reader, "get_current_track", unavailable)
    assert media_reader.get_track_sync(timeout=0.1) is None
