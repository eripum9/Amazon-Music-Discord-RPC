# MIT License - Copyright (c) 2026 eripum9

import requests
from urllib.parse import quote

_cache = {}


def _clean_title(title):
    import re
    title = re.sub(r'\s*\[.*?\]', '', title)
    title = re.sub(r'\s*\(feat\..*?\)', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s*\(ft\..*?\)', '', title, flags=re.IGNORECASE)
    return title.strip()


def search_tracks(query, limit=5):
    url = f"https://api.deezer.com/search?q={quote(query)}&limit={limit}"
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
            })
        if results:
            return results
    except (requests.RequestException, KeyError, ValueError):
        pass

    url = f"https://itunes.apple.com/search?term={quote(query)}&media=music&limit={limit}"
    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        results = []
        for r in data.get("results", []):
            art_url = r.get("artworkUrl100", "")
            if art_url:
                art_url = art_url.replace("100x100bb", "600x600bb")
            results.append({
                "title": r.get("trackName", ""),
                "artist": r.get("artistName", ""),
                "album": r.get("collectionName", ""),
                "art_url": art_url,
            })
        return results
    except (requests.RequestException, KeyError, ValueError):
        pass
    return []


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
                    return art, album.get("title", ""), track.get("link", ""), track.get("duration", 0)
    except (requests.RequestException, KeyError, IndexError, ValueError):
        pass
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
                    return art_url.replace("100x100bb", "600x600bb"), result.get("collectionName", "")
    except (requests.RequestException, KeyError, IndexError, ValueError):
        pass
    return None, None


def get_album_art(title, artist):
    cache_key = f"{title}|{artist}".lower()
    if cache_key in _cache:
        return _cache[cache_key]

    art_url, album_name, track_link, track_duration = _search_deezer(title, artist)
    if not art_url:
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
