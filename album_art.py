import requests
from urllib.parse import quote

_cache = {}


def _clean_title(title):
    """Remove common suffixes like [Explicit], (feat. X), etc. for better search."""
    import re
    title = re.sub(r'\s*\[.*?\]', '', title)  # [Explicit], [Deluxe], etc.
    title = re.sub(r'\s*\(feat\..*?\)', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s*\(ft\..*?\)', '', title, flags=re.IGNORECASE)
    return title.strip()


def _search_deezer(title, artist):
    """Search Deezer for album art. Returns (cover_url, album_name) or (None, None)."""
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
                    return art, album.get("title", "")
    except (requests.RequestException, KeyError, IndexError, ValueError):
        pass
    return None, None


def _search_itunes(title, artist):
    """Fallback: search iTunes for album art. Returns (cover_url, album_name) or (None, None)."""
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
    """Get album art URL and album name for a song. Uses cache.
    Returns (art_url, album_name). Either can be None."""
    cache_key = f"{title}|{artist}".lower()
    if cache_key in _cache:
        return _cache[cache_key]

    art_url, album_name = _search_deezer(title, artist)
    if not art_url:
        art_url, album_name = _search_itunes(title, artist)

    result = (art_url, album_name or "")
    _cache[cache_key] = result
    return result


if __name__ == "__main__":
    test_title = "Blinding Lights"
    test_artist = "The Weeknd"
    url, album = get_album_art(test_title, test_artist)
    if url:
        print(f"Album art for '{test_title}' by {test_artist}:")
        print(f"  URL:   {url}")
        print(f"  Album: {album}")
    else:
        print("No album art found.")
