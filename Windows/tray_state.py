# MIT License - Copyright (c) 2026 eripum9


def trim(value, limit=58):
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    while "  " in text:
        text = text.replace("  ", " ")
    if len(text) <= limit:
        return text
    return text[:max(0, limit - 3)].rstrip() + "..."


def format_seconds(value):
    try:
        total = int(float(value))
    except (TypeError, ValueError):
        return ""
    if total < 0:
        return ""
    minutes, seconds = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def time_label(track):
    position = format_seconds(track.get("position"))
    duration = format_seconds(track.get("duration"))
    if position and duration:
        return f"{position} / {duration}"
    return duration or position


def build_snapshot(state, config, source, rpc_running, rpc_connected):
    track = state.get("track") if isinstance(state.get("track"), dict) else {}
    privacy = state.get("privacy") if isinstance(state.get("privacy"), dict) else {}
    amazon = state.get("amazon_devtools") if isinstance(state.get("amazon_devtools"), dict) else {}
    title = track.get("title") or ""
    artist = track.get("artist") or ""
    album = track.get("album") or state.get("album_name") or ""
    private = bool(config.get("privacy_private_session") or privacy.get("hidden"))
    return {
        "rpc": "On" if rpc_running else "Off",
        "discord": str(state.get("discord_status") or ("connected" if rpc_connected else "waiting")).title(),
        "presence": "Private" if private else ("Visible" if state.get("presence_visible") else "Hidden"),
        "source": source.get("label") or "Waiting",
        "source_detail": source.get("detail") or "",
        "title": title,
        "artist": artist,
        "album": album,
        "time": time_label(track),
        "track_link": state.get("track_link") or "",
        "has_track": bool(title or artist or album),
        "private": private,
        "devtools": "On" if config.get("amazon_devtools_enabled") else "Off",
        "devtools_status": str(amazon.get("status") or ("off" if not config.get("amazon_devtools_enabled") else "waiting")).title(),
        "game_mode": "On" if config.get("game_mode_enabled") else "Off",
        "link_provider": str(config.get("song_link_provider") or "amazon").title(),
    }


def signature(snapshot):
    keys = ("rpc", "discord", "presence", "source", "title", "artist", "album", "time", "track_link", "devtools", "devtools_status", "game_mode", "link_provider")
    return "|".join(str(snapshot.get(key) or "") for key in keys)


def icon_title(snapshot):
    if snapshot.get("private"):
        return "Amazon Music RPC - Private"
    if snapshot.get("title"):
        title = snapshot.get("title")
        artist = snapshot.get("artist")
        text = f"{title} - {artist}" if artist else title
        return trim(text, 120)
    return f"Amazon Music RPC - RPC {snapshot.get('rpc', 'Off')}"
