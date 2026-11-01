# MIT License - Copyright (c) 2026 eripum9

import re
import unicodedata


def base_track_for_devtools():
    return {
        "title": "",
        "artist": "",
        "album": "",
        "status": "playing",
        "position": None,
        "duration": 0,
    }


def apply_devtools_source(track, devtools, apply_fn):
    if not isinstance(devtools, dict) or devtools.get("status") != "found":
        return track, False, False
    merged, changed = apply_fn(track or base_track_for_devtools(), devtools)
    return merged, changed, True


def merge_notification_metadata(track, notification):
    if not isinstance(track, dict) or not isinstance(notification, dict):
        return track, None, True
    notif_title = (notification.get("title") or "").lower().strip()
    smtc_title = (track.get("title") or "").lower().strip()
    if not smtc_title or not notif_title:
        return track, None, False
    if not (smtc_title == notif_title or smtc_title in notif_title or notif_title in smtc_title):
        return track, None, False
    merged = dict(track)
    notif_album = None
    if notification.get("title"):
        merged["title"] = notification["title"]
    if notification.get("artist"):
        merged["artist"] = notification["artist"]
    if notification.get("album"):
        merged["album"] = notification["album"]
        notif_album = notification["album"]
    return merged, notif_album, True


def selected_button_link(song_link_provider, amazon_music_link_region, amazon_track_link, deezer_track_link, title="", artist="", amazon_search_link=None):
    if song_link_provider == "deezer":
        return "Listen on Deezer", deezer_track_link
    fallback = amazon_search_link(title, artist, amazon_music_link_region) if amazon_search_link else ""
    return "Listen on Amazon Music", amazon_track_link or fallback


def link_buttons(song_link_enabled, song_link_provider, amazon_music_link_region, amazon_track_link, deezer_track_link, title="", artist="", amazon_search_link=None):
    if not song_link_enabled:
        return None
    label, url = selected_button_link(
        song_link_provider,
        amazon_music_link_region,
        amazon_track_link,
        deezer_track_link,
        title,
        artist,
        amazon_search_link,
    )
    if not url:
        return None
    return [{"label": label, "url": url}]


def diagnostics_track_link(track, song_link_provider, amazon_music_link_region, amazon_track_link, deezer_track_link, amazon_search_link=None):
    track = track or {}
    title = track.get("title", "")
    artist = track.get("artist", "")
    _, url = selected_button_link(
        song_link_provider,
        amazon_music_link_region,
        amazon_track_link,
        deezer_track_link,
        title,
        artist,
        amazon_search_link,
    )
    return url or amazon_track_link or deezer_track_link or ""


def should_lookup_deezer_button(song_link_provider, deezer_track_link, title, artist):
    return song_link_provider == "deezer" and not deezer_track_link and bool(title) and bool(artist)


# Amazon Music's player bar shows "Artist \u2022 <what is playing>", and that
# second part is the playback source (album, playlist, station or autoplay),
# not necessarily the album of the current track.
_PLAY_CONTEXT_PREFIXES = (
    "reproducci\u00f3n autom\u00e1tica",
    "reproduccion automatica",
    "autoplay",
    "auto play",
    "lecture automatique",
    "riproduzione automatica",
    "reprodu\u00e7\u00e3o autom\u00e1tica",
    "automatische wiedergabe",
)


def _fold(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^\w\s]", " ", text.casefold())
    return " ".join(text.split())


def album_from_player_label(label):
    """Album hint from Amazon's player bar, or "" when it names a play context."""
    text = str(label or "").strip()
    folded = _fold(text)
    for prefix in _PLAY_CONTEXT_PREFIXES:
        if folded.startswith(_fold(prefix)) and ":" in text:
            return ""
    return text


def _choose_album(player_album, looked_up_album):
    if looked_up_album:
        if player_album and _fold(player_album) == _fold(looked_up_album):
            return player_album
        return looked_up_album
    return player_album


def apply_art_result(track, resolved=None, fetched=None, notification_album=None, previous_album=""):
    """Combine the sources for the current track's artwork and album.

    Amazon's own artwork is kept when available, but the album name comes from
    the Deezer/iTunes match because Amazon only exposes the playback source.
    """
    album = previous_album
    art_url = ""
    deezer_link = ""
    duration = 0
    amazon_link = ""
    player_album = album_from_player_label(track.get("album", ""))
    if resolved:
        art_url, album, deezer_link, duration = resolved
    else:
        looked_up_album = ""
        if fetched:
            art_url, looked_up_album, deezer_link, duration = fetched
            art_url = art_url or ""
        album = _choose_album(player_album, looked_up_album) or album
    if notification_album:
        album = notification_album
    if track.get("_amazon_art_url"):
        art_url = track.get("_amazon_art_url")
        duration = track.get("duration") or duration
    if track.get("_amazon_track_link"):
        amazon_link = track.get("_amazon_track_link")
    return {
        "art_url": art_url,
        "album": album,
        "deezer_link": deezer_link,
        "duration": duration,
        "amazon_link": amazon_link,
    }
