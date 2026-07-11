# MIT License - Copyright (c) 2026 eripum9

import os
import requests
from urllib.parse import quote

_cache = {}


def _lookup_policy(deezer_enabled=None, itunes_enabled=None):
    if deezer_enabled is not None and itunes_enabled is not None:
        return bool(deezer_enabled), bool(itunes_enabled)
    try:
        from config import load_config
        config = load_config()
    except Exception:
        config = {}
    deezer = config.get("deezer_lookup_enabled", True) if deezer_enabled is None else deezer_enabled
    itunes = config.get("itunes_lookup_enabled", True) if itunes_enabled is None else itunes_enabled
    return bool(deezer), bool(itunes)


def _network_event(service, operation, status, detail=""):
    try:
        from network_audit import record_network_event
        record_network_event(service, operation, status, detail)
    except Exception:
        pass


def _clean_title(title):
    import re
    title = re.sub(r'\s*\[.*?\]', '', title)
    title = re.sub(r'\s*\(feat\..*?\)', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s*\(ft\..*?\)', '', title, flags=re.IGNORECASE)
    return title.strip()


def _bounded_int(value, default, minimum=0):
    try:
        return max(minimum, int(value))
    except (TypeError, ValueError):
        return default


def search_tracks(query, limit=5, offset=0, deezer_enabled=None, itunes_enabled=None):
    limit = _bounded_int(limit, 5, 1)
    offset = _bounded_int(offset, 0, 0)
    use_deezer, use_itunes = _lookup_policy(deezer_enabled, itunes_enabled)
    if use_deezer:
        url = f"https://api.deezer.com/search?q={quote(query)}&limit={limit}&index={offset}"
        try:
            resp = requests.get(url, timeout=5)
            resp.raise_for_status()
            data = resp.json()
            results = []
            for track in data.get("data", []):
                album = track.get("album", {})
                art = album.get("cover_xl") or album.get("cover_big") or album.get("cover_medium")
                results.append({
                    "title": track.get("title", ""),
                    "artist": track.get("artist", {}).get("name", ""),
                    "album": album.get("title", ""),
                    "art_url": art or "",
                    "track_link": track.get("link", ""),
                    "duration": track.get("duration", 0) or 0,
                })
            _network_event("deezer", "track-search", "success", f"{len(results)} results")
            if results:
                return results
        except (requests.RequestException, KeyError, ValueError) as error:
            _network_event("deezer", "track-search", "error", type(error).__name__)

    if not use_itunes:
        return []
    fetch_limit = min(max(limit + offset, limit), 200)
    url = f"https://itunes.apple.com/search?term={quote(query)}&media=music&limit={fetch_limit}"
    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        results = []
        for r in data.get("results", [])[offset:offset + limit]:
            art_url = r.get("artworkUrl100", "")
            if art_url:
                art_url = art_url.replace("100x100bb", "600x600bb")
            results.append({
                "title": r.get("trackName", ""),
                "artist": r.get("artistName", ""),
                "album": r.get("collectionName", ""),
                "art_url": art_url,
                "track_link": r.get("trackViewUrl", ""),
                "duration": round((r.get("trackTimeMillis") or 0) / 1000),
            })
        _network_event("itunes", "track-search", "success", f"{len(results)} results")
        return results
    except (requests.RequestException, KeyError, ValueError) as error:
        _network_event("itunes", "track-search", "error", type(error).__name__)
    return []


def _normalise_name(value):
    return " ".join(str(value or "").strip().lower().split())


def _split_aliases(value):
    if isinstance(value, list):
        items = value
    else:
        items = str(value or "").replace("\n", ",").split(",")
    return [str(item).strip() for item in items if str(item).strip()]


def _normalise_art_value(value):
    art = str(value or "").strip()
    if not art:
        return ""
    if art.lower().startswith(("http://", "https://", "mp:", "file://")):
        return art
    if os.path.exists(art):
        return os.path.abspath(art)
    return art


def find_custom_album_art(config, *album_names):
    entries = config.get("custom_albums", [])
    if not isinstance(entries, list):
        return None
    candidates = {_normalise_name(name) for name in album_names if _normalise_name(name)}
    if not candidates:
        return None
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        album = str(entry.get("album", "")).strip()
        art_url = _normalise_art_value(entry.get("art_url", ""))
        names = [album] + _split_aliases(entry.get("aliases", []))
        normalised = {_normalise_name(name) for name in names if _normalise_name(name)}
        if art_url and candidates.intersection(normalised):
            return {"album": album or next(iter(candidates)), "art_url": art_url}
    return None


def _search_deezer(title, artist):
    clean = _clean_title(title)
    primary_artist = artist.split(' feat.')[0].split(' ft.')[0].strip()
    query = f'artist:"{primary_artist}" track:"{clean}"'
    url = f"https://api.deezer.com/search?q={quote(query)}&limit=3"
    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        if data.get("data"):
            for track in data["data"]:
                album = track.get("album", {})
                art = album.get("cover_xl") or album.get("cover_big") or album.get("cover_medium")
                if art:
                    _network_event("deezer", "artwork-lookup", "success", "match")
                    return art, album.get("title", ""), track.get("link", ""), track.get("duration", 0)
        _network_event("deezer", "artwork-lookup", "success", "no match")
    except (requests.RequestException, KeyError, IndexError, ValueError) as error:
        _network_event("deezer", "artwork-lookup", "error", type(error).__name__)
    return None, None, None, 0


def _search_itunes(title, artist):
    clean = _clean_title(title)
    primary_artist = artist.split(' feat.')[0].split(' ft.')[0].strip()
    query = f"{clean} {primary_artist}"
    url = f"https://itunes.apple.com/search?term={quote(query)}&media=music&limit=3"
    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        if data.get("results"):
            for result in data["results"]:
                art_url = result.get("artworkUrl100", "")
                if art_url:
                    _network_event("itunes", "artwork-lookup", "success", "match")
                    return art_url.replace("100x100bb", "600x600bb"), result.get("collectionName", "")
        _network_event("itunes", "artwork-lookup", "success", "no match")
    except (requests.RequestException, KeyError, IndexError, ValueError) as error:
        _network_event("itunes", "artwork-lookup", "error", type(error).__name__)
    return None, None


def get_album_art(title, artist, deezer_enabled=None, itunes_enabled=None):
    use_deezer, use_itunes = _lookup_policy(deezer_enabled, itunes_enabled)
    cache_key = f"{title}|{artist}|{int(use_deezer)}|{int(use_itunes)}".lower()
    if cache_key in _cache:
        return _cache[cache_key]

    art_url, album_name, track_link, track_duration = (None, None, None, 0)
    if use_deezer:
        art_url, album_name, track_link, track_duration = _search_deezer(title, artist)
    if not art_url and use_itunes:
        art_url, album_name = _search_itunes(title, artist)
        track_link = None
        track_duration = 0

    result = (art_url, album_name or "", track_link or "", track_duration or 0)
    _cache[cache_key] = result
    return result


if __name__ == "__main__":
    test_title = "Blinding Lights"
    test_artist = "The Weeknd"
    url, album, link, dur = get_album_art(test_title, test_artist)
    if url:
        print(f"Album art for '{test_title}' by {test_artist}:")
        print(f"  URL:      {url}")
        print(f"  Album:    {album}")
        print(f"  Duration: {dur}s")
    else:
        print("No album art found.")
