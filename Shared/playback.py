# MIT License - Copyright (c) 2026 eripum9

"""Pure playback rules used by every desktop runtime.

This module intentionally contains no UI, network, process-enumeration, or
credential code.  Keeping the decisions here platform neutral makes the
Windows and macOS builds agree on privacy, corrections, game mode, and
scrobble thresholds while allowing each runtime to supply native metadata.
"""

from __future__ import annotations

import math
import os
from collections.abc import Mapping


TEXT_LIMIT = 512
URL_LIMIT = 4096
SCROBBLE_MINIMUM_SECONDS = 30.0
SCROBBLE_HALF_DURATION = 0.5
SCROBBLE_FALLBACK_SECONDS = 240.0


def normalised_text(value):
    """Return case-insensitive, whitespace-stable text for comparisons."""

    return " ".join(str(value or "").strip().casefold().split())


def same_track_field(left, right):
    left = normalised_text(left)
    right = normalised_text(right)
    return bool(left and right and left == right)


def duration_value(value):
    """Return a non-negative whole-second duration for external APIs."""

    try:
        return max(0, int(float(value or 0)))
    except (OverflowError, TypeError, ValueError):
        return 0


def nonnegative_number(value, default=0.0):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, number) if math.isfinite(number) else default


def normalise_track(track, source=""):
    """Convert a native metadata mapping to the common playback shape."""

    if not isinstance(track, Mapping):
        return None
    title = str(track.get("title") or "").strip()[:TEXT_LIMIT]
    if not title:
        return None
    artist = str(track.get("artist") or "").strip()[:TEXT_LIMIT]
    status = str(track.get("status") or "").strip().casefold()
    if status not in {"playing", "paused"}:
        status = str(track.get("playback_status") or "playing").strip().casefold()
    if status not in {"playing", "paused"}:
        status = "playing"

    position = track.get("position")
    try:
        position = max(0.0, float(position)) if position is not None else None
    except (TypeError, ValueError):
        position = None
    duration = nonnegative_number(track.get("duration"))
    if position is not None and duration:
        position = min(position, duration)

    return {
        "title": title,
        "artist": artist,
        "album": str(track.get("album") or "").strip()[:TEXT_LIMIT],
        "status": status,
        "position": position,
        "duration": duration,
        "art_url": str(track.get("art_url") or track.get("_amazon_art_url") or "").strip()[:URL_LIMIT],
        "track_link": str(track.get("track_link") or track.get("_amazon_track_link") or "").strip()[:URL_LIMIT],
        "source": str(track.get("source") or source or "unknown").strip()[:80],
    }


def track_info_payload(track):
    track = track if isinstance(track, Mapping) else {}
    return {
        "title": track.get("title", ""),
        "artist": track.get("artist", ""),
        "album": track.get("album", ""),
        "art_url": track.get("art_url", ""),
        "track_link": track.get("track_link", ""),
        "duration": duration_value(track.get("duration", 0)),
    }


def privacy_keywords(config_or_value):
    if isinstance(config_or_value, Mapping):
        raw = config_or_value.get("privacy_blocked_keywords", "")
    else:
        raw = config_or_value
    items = raw if isinstance(raw, (list, tuple, set)) else str(raw or "").replace("\n", ",").split(",")
    return [normalised_text(item) for item in items if normalised_text(item)]


def privacy_match(config, title="", artist="", album=""):
    config = config if isinstance(config, Mapping) else {}
    if config.get("privacy_private_session"):
        return "Private session enabled"
    haystack = normalised_text(f"{title} {artist} {album}")
    for keyword in privacy_keywords(config):
        if keyword in haystack:
            return f"Matched privacy keyword: {keyword}"
    return ""


def privacy_reason(config, track):
    track = track if isinstance(track, Mapping) else {}
    return privacy_match(
        config,
        track.get("title", ""),
        track.get("artist", ""),
        track.get("album", ""),
    )


def normalise_process_name(value):
    """Normalise either Windows or POSIX executable paths on any host OS."""

    text = str(value or "").strip().strip('"').strip("'").replace("\\", "/")
    return text.rsplit("/", 1)[-1].casefold()


def configured_game_mode_processes(config_or_value):
    if isinstance(config_or_value, Mapping):
        value = config_or_value.get("game_mode_processes", "")
    else:
        value = config_or_value
    parts = value if isinstance(value, (list, tuple, set)) else str(value or "").replace(";", ",").replace("\n", ",").split(",")
    return {name for name in (normalise_process_name(part) for part in parts) if name}


def _process_aliases(value):
    clean = normalise_process_name(value)
    if not clean:
        return set()
    aliases = {clean}
    stem, extension = os.path.splitext(clean)
    if stem and extension in {".exe", ".app"}:
        aliases.add(stem)
    return aliases


def game_mode_matches_processes(configured, running_names):
    running = set()
    for name in running_names or ():
        running.update(_process_aliases(name))
    for name in configured or ():
        if _process_aliases(name).intersection(running):
            return True
    return False


def remembered_track_mapping_key(title, artist=""):
    title_key = normalised_text(title)
    artist_key = normalised_text(artist)
    return f"{title_key}|{artist_key}" if artist_key else title_key


def _track_mappings(config_or_mappings):
    if not isinstance(config_or_mappings, Mapping):
        return {}
    if "track_mappings" in config_or_mappings:
        mappings = config_or_mappings.get("track_mappings")
        return mappings if isinstance(mappings, Mapping) else {}
    return config_or_mappings


def remembered_track_mapping(config_or_mappings, title, artist=""):
    """Find a correction saved under either track+artist or legacy title key."""

    mappings = _track_mappings(config_or_mappings)
    normalised_mappings = {
        normalised_text(key): value
        for key, value in mappings.items()
        if isinstance(value, Mapping)
    }
    keys = (
        remembered_track_mapping_key(title, artist),
        remembered_track_mapping_key(title),
    )
    for key in keys:
        value = normalised_mappings.get(normalised_text(key))
        if isinstance(value, Mapping):
            return value
    return None


def apply_track_mapping(config_or_mappings, track):
    if not isinstance(track, Mapping):
        return track
    mapping = remembered_track_mapping(
        config_or_mappings,
        track.get("title", ""),
        track.get("artist", ""),
    )
    if not mapping:
        return dict(track)
    merged = dict(track)
    for field in ("title", "artist", "album", "art_url", "track_link", "duration"):
        if mapping.get(field) not in (None, ""):
            merged[field] = mapping[field]
    return merged


def _split_aliases(value):
    items = value if isinstance(value, (list, tuple, set)) else str(value or "").replace("\n", ",").split(",")
    return [str(item).strip() for item in items if str(item).strip()]


def _normalise_art_value(value):
    art = str(value or "").strip()
    if not art:
        return ""
    if art.casefold().startswith(("http://", "https://", "mp:", "file://")):
        return art
    if os.path.exists(art):
        return os.path.abspath(art)
    return art


def find_custom_album_art(config, *album_names):
    """Return the first custom-art entry matching an album or alias."""

    config = config if isinstance(config, Mapping) else {}
    entries = config.get("custom_albums", [])
    if not isinstance(entries, list):
        return None
    candidates = {normalised_text(name) for name in album_names if normalised_text(name)}
    if not candidates:
        return None
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        album = str(entry.get("album", "")).strip()
        art_url = _normalise_art_value(entry.get("art_url", ""))
        names = [album, *_split_aliases(entry.get("aliases", []))]
        aliases = {normalised_text(name) for name in names if normalised_text(name)}
        if art_url and candidates.intersection(aliases):
            return {"album": album or next(iter(candidates)), "art_url": art_url}
    return None


def scrobble_eligible(elapsed, duration=0):
    """Apply the Last.fm-compatible 30s + half-track/4-minute rule."""

    elapsed = nonnegative_number(elapsed)
    duration = nonnegative_number(duration)
    if elapsed < SCROBBLE_MINIMUM_SECONDS:
        return False
    return bool(
        (duration > 0 and elapsed >= duration * SCROBBLE_HALF_DURATION)
        or elapsed >= SCROBBLE_FALLBACK_SECONDS
    )
