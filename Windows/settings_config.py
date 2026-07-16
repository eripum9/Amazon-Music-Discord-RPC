# MIT License - Copyright (c) 2026 eripum9

from datetime import datetime

from config import APP_VERSION, DEFAULTS, DEFAULT_CLIENT_ID, SENSITIVE_CONFIG_KEYS, normalize_amazon_music_link_region, normalize_discord_status_display, redact_data


REQUIRED_SETTINGS_KEYS = {
    "use_custom",
    "client_id",
    "discord_status_display",
    "start_on_startup",
    "start_minimized",
    "show_paused",
    "privacy_private_session",
    "privacy_disable_scrobbling",
    "privacy_blocked_keywords",
    "game_mode_enabled",
    "game_mode_processes",
    "custom_albums",
    "song_link_enabled",
    "song_link_provider",
    "amazon_music_link_region",
    "notification_enrichment_enabled",
    "amazon_devtools_enabled",
    "amazon_devtools_auto_launch",
    "amazon_music_launcher_override",
    "automatic_update_checks",
    "deezer_lookup_enabled",
    "itunes_lookup_enabled",
    "lastfm_enabled",
    "listenbrainz_enabled",
    "listenbrainz_token",
}
EDITABLE_CONFIG_KEYS = (
    "discord_client_id",
    "use_custom_client_id",
    "discord_status_display",
    "start_on_startup",
    "start_minimized",
    "show_paused",
    "privacy_private_session",
    "privacy_disable_scrobbling",
    "privacy_blocked_keywords",
    "game_mode_enabled",
    "game_mode_processes",
    "custom_albums",
    "song_link_enabled",
    "song_link_provider",
    "amazon_music_link_region",
    "notification_enrichment_enabled",
    "amazon_devtools_enabled",
    "amazon_devtools_auto_launch",
    "amazon_music_launcher_override",
    "automatic_update_checks",
    "deezer_lookup_enabled",
    "itunes_lookup_enabled",
    "lastfm_enabled",
    "listenbrainz_enabled",
    "listenbrainz_token",
)


def split_aliases(value):
    if isinstance(value, list):
        items = value
    else:
        items = str(value or "").replace("\n", ",").split(",")
    return [str(item).strip() for item in items if str(item).strip()]


def clean_custom_albums(items):
    if not isinstance(items, list):
        return []
    cleaned = []
    for item in items:
        if not isinstance(item, dict):
            continue
        album = str(item.get("album", "")).strip()
        art_url = str(item.get("art_url", "")).strip()
        aliases = split_aliases(item.get("aliases", []))
        if album and art_url:
            cleaned.append({"album": album, "aliases": aliases, "art_url": art_url})
    return cleaned


def settings_export_payload(config, include_tokens=False):
    exported = {}
    for key in DEFAULTS:
        if key in SENSITIVE_CONFIG_KEYS and not include_tokens:
            continue
        exported[key] = config.get(key, DEFAULTS.get(key))
    safe_config = exported if include_tokens else redact_data(exported, config)
    return {
        "format": "AmazonMusicRPC.settings",
        "app_version": APP_VERSION,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "include_tokens": bool(include_tokens),
        "config": safe_config,
    }


def settings_import_config(payload, existing):
    if not isinstance(payload, dict):
        raise ValueError("Settings file is invalid.")
    source = payload.get("config") if isinstance(payload.get("config"), dict) else payload
    include_tokens = bool(payload.get("include_tokens"))
    if not isinstance(source, dict):
        raise ValueError("Settings file does not contain settings.")
    merged = dict(existing)
    for key, value in source.items():
        if key not in DEFAULTS or key in SENSITIVE_CONFIG_KEYS and not include_tokens:
            continue
        merged[key] = value
    merged["amazon_music_link_region"] = normalize_amazon_music_link_region(merged.get("amazon_music_link_region"))
    merged["discord_status_display"] = normalize_discord_status_display(merged.get("discord_status_display"))
    from amazon_devtools import validate_launcher_override
    merged["amazon_music_launcher_override"] = validate_launcher_override(merged.get("amazon_music_launcher_override", ""))
    merged["custom_albums"] = clean_custom_albums(merged.get("custom_albums", []))
    return merged


def settings_config_from_payload(data, existing):
    if not isinstance(data, dict):
        raise ValueError("Settings payload is invalid.")
    missing = sorted(key for key in REQUIRED_SETTINGS_KEYS if key not in data)
    if missing:
        raise ValueError(f"Settings payload is incomplete: {', '.join(missing)}")
    use_custom = data.get("use_custom", False)
    client_id = data.get("client_id", "").strip() if use_custom else DEFAULT_CLIENT_ID
    listenbrainz_token = data.get("listenbrainz_token", "").strip() or existing.get("listenbrainz_token", "")
    from amazon_devtools import validate_launcher_override
    return {
        **existing,
        "discord_client_id": client_id,
        "use_custom_client_id": use_custom,
        "discord_status_display": normalize_discord_status_display(data.get("discord_status_display")),
        "start_on_startup": bool(data.get("start_on_startup")),
        "start_minimized": bool(data.get("start_minimized")),
        "show_paused": bool(data.get("show_paused", True)),
        "privacy_private_session": bool(data.get("privacy_private_session")),
        "privacy_disable_scrobbling": bool(data.get("privacy_disable_scrobbling", True)),
        "privacy_blocked_keywords": data.get("privacy_blocked_keywords", "").strip(),
        "game_mode_enabled": bool(data.get("game_mode_enabled")),
        "game_mode_processes": data.get("game_mode_processes", "").strip(),
        "custom_albums": clean_custom_albums(data.get("custom_albums", [])),
        "song_link_enabled": bool(data.get("song_link_enabled")),
        "song_link_provider": data.get("song_link_provider") if data.get("song_link_provider") in ("amazon", "deezer") else "amazon",
        "amazon_music_link_region": normalize_amazon_music_link_region(data.get("amazon_music_link_region")),
        "notification_enrichment_enabled": bool(data.get("notification_enrichment_enabled")),
        "amazon_devtools_enabled": bool(data.get("amazon_devtools_enabled")),
        "amazon_devtools_auto_launch": bool(data.get("amazon_devtools_auto_launch", False)),
        "amazon_music_launcher_override": validate_launcher_override(data.get("amazon_music_launcher_override", "")),
        "automatic_update_checks": bool(data.get("automatic_update_checks", True)),
        "deezer_lookup_enabled": bool(data.get("deezer_lookup_enabled", True)),
        "itunes_lookup_enabled": bool(data.get("itunes_lookup_enabled", True)),
        "lastfm_enabled": bool(data.get("lastfm_enabled")),
        "listenbrainz_enabled": bool(data.get("listenbrainz_enabled")),
        "listenbrainz_token": listenbrainz_token,
    }
