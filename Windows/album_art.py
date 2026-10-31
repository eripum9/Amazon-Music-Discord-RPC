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


# ---------------------------------------------------------------------------
# Artwork matching
#
# Amazon Music only reports "title", "artist" and sometimes "album" to Windows.
# Instead of trusting the first search hit, collect candidates from several
# queries (Deezer strict, Deezer with album, Deezer free text, iTunes) and
# score each one against what Amazon reported.  The best scoring candidate
# above a minimum confidence wins.
# ---------------------------------------------------------------------------

import re
import unicodedata
from difflib import SequenceMatcher

_VERSION_WORDS = (
    "remaster", "remastered", "remasterizado", "remasterizada", "version", "versión",
    "edit", "radio edit", "mono", "stereo", "deluxe", "explicit", "clean",
    "single", "album version", "original mix",
)
_FEAT_RE = re.compile(r"\s*[\(\[]\s*(feat\.?|ft\.?|featuring|con|with)\s.*?[\)\]]", re.IGNORECASE)
_BRACKET_RE = re.compile(r"\s*[\(\[][^\)\]]*[\)\]]")
_DASH_SUFFIX_RE = re.compile(r"\s+-\s+.*$")
_ARTIST_SPLIT_RE = re.compile(r"\s*(?:,|&|/|;|\+|\bfeat\.?\b|\bft\.?\b|\bfeaturing\b|\bx\b|\by\b|\band\b|\bwith\b)\s*", re.IGNORECASE)

MIN_MATCH_SCORE = 0.62
GOOD_MATCH_SCORE = 0.9


def _fold(value):
    """Lowercase, strip accents and punctuation for fuzzy comparisons."""
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.casefold().replace("&", " and ")
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


def _core_title(title):
    """Title without featured artists, brackets or ' - Remastered 2011' style suffixes."""
    text = _FEAT_RE.sub("", str(title or ""))
    text = _BRACKET_RE.sub("", text)
    text = _DASH_SUFFIX_RE.sub("", text)
    return _fold(text) or _fold(title)


def _version_tags(title):
    """Version words such as 'live', 'acoustic', 'remix' that should match when present."""
    folded = _fold(title)
    tags = set()
    for word in ("live", "en vivo", "acoustic", "acustico", "remix", "instrumental", "sped up", "slowed", "demo", "unplugged"):
        if re.search(rf"\b{re.escape(word)}\b", folded):
            tags.add(word)
    return tags


def _artist_parts(artist):
    parts = [_fold(part) for part in _ARTIST_SPLIT_RE.split(str(artist or ""))]
    parts = [part for part in parts if part]
    whole = _fold(artist)
    if whole and whole not in parts:
        parts.append(whole)
    return parts


def _primary_artist(artist):
    parts = [p.strip() for p in re.split(r"\s*(?:,|;|\bfeat\.?\s|\bft\.?\s)\s*", str(artist or ""), flags=re.IGNORECASE) if p.strip()]
    return parts[0] if parts else str(artist or "").strip()


def _ratio(left, right):
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    ratio = SequenceMatcher(None, left, right).ratio()
    shorter, longer = sorted((left, right), key=len)
    if len(shorter) >= 4 and re.search(rf"\b{re.escape(shorter)}\b", longer):
        ratio = max(ratio, 0.88)
    return ratio


def _artist_score(wanted_artist, candidate_artist):
    wanted = _artist_parts(wanted_artist)
    found = _artist_parts(candidate_artist)
    if not wanted or not found:
        return 0.0
    return max(_ratio(w, f) for w in wanted for f in found)


def score_candidate(candidate, title, artist, album="", duration=0):
    """Return 0..1 confidence that ``candidate`` is the track Amazon is playing."""
    title_score = _ratio(_core_title(title), _core_title(candidate.get("title", "")))
    artist_score = _artist_score(artist, candidate.get("artist", ""))
    if title_score < 0.55 or artist_score < 0.5:
        return 0.0

    score = title_score * 0.55 + artist_score * 0.35

    wanted_album = _core_title(album)
    if wanted_album:
        album_score = _ratio(wanted_album, _core_title(candidate.get("album", "")))
        score += album_score * 0.10
    else:
        score += 0.05

    # Prefer the same version (live / remix / acoustic ...).
    wanted_tags = _version_tags(title)
    found_tags = _version_tags(f"{candidate.get('title', '')} {candidate.get('album', '')}")
    if wanted_tags != found_tags:
        score -= 0.06 * len(wanted_tags.symmetric_difference(found_tags))

    try:
        wanted_duration = float(duration or 0)
        found_duration = float(candidate.get("duration") or 0)
    except (TypeError, ValueError):
        wanted_duration = found_duration = 0
    if wanted_duration > 0 and found_duration > 0:
        gap = abs(wanted_duration - found_duration)
        if gap <= 3:
            score += 0.05
        elif gap > 20:
            score -= min(0.15, gap / 600)

    if not candidate.get("art_url"):
        score -= 0.5
    return max(0.0, min(1.0, score))


def _deezer_candidates(query, limit=10):
    url = f"https://api.deezer.com/search?q={quote(query)}&limit={limit}"
    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as error:
        _network_event("deezer", "artwork-lookup", "error", type(error).__name__)
        return []
    candidates = []
    for track in data.get("data", []) or []:
        album = track.get("album", {}) or {}
        candidates.append({
            "title": track.get("title", "") or "",
            "artist": (track.get("artist", {}) or {}).get("name", "") or "",
            "album": album.get("title", "") or "",
            "art_url": album.get("cover_xl") or album.get("cover_big") or album.get("cover_medium") or "",
            "track_link": track.get("link", "") or "",
            "duration": track.get("duration", 0) or 0,
            "source": "deezer",
        })
    return candidates


def _itunes_candidates(query, limit=15):
    url = f"https://itunes.apple.com/search?term={quote(query)}&media=music&entity=song&limit={limit}"
    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as error:
        _network_event("itunes", "artwork-lookup", "error", type(error).__name__)
        return []
    candidates = []
    for result in data.get("results", []) or []:
        art_url = result.get("artworkUrl100", "") or ""
        if art_url:
            art_url = art_url.replace("100x100bb", "600x600bb")
        candidates.append({
            "title": result.get("trackName", "") or "",
            "artist": result.get("artistName", "") or "",
            "album": result.get("collectionName", "") or "",
            "art_url": art_url,
            "track_link": "",
            "duration": round((result.get("trackTimeMillis") or 0) / 1000),
            "source": "itunes",
        })
    return candidates


def find_best_match(title, artist, album="", duration=0, deezer_enabled=None, itunes_enabled=None):
    """Search every enabled source and return (best_candidate, score)."""
    use_deezer, use_itunes = _lookup_policy(deezer_enabled, itunes_enabled)
    core = _core_title(title) or _fold(title)
    plain_title = _clean_title(title)
    primary = _primary_artist(artist)

    queries = []
    if use_deezer:
        queries.append(("deezer", f'artist:"{primary}" track:"{plain_title}"'))
        if album:
            queries.append(("deezer", f'artist:"{primary}" album:"{_clean_title(album)}" track:"{plain_title}"'))
        queries.append(("deezer", f"{primary} {core}"))
    if use_itunes:
        queries.append(("itunes", f"{plain_title} {primary}"))
        if core != _fold(plain_title):
            queries.append(("itunes", f"{core} {primary}"))

    best, best_score, seen = None, 0.0, set()
    for source, query in queries:
        fetch = _deezer_candidates if source == "deezer" else _itunes_candidates
        for candidate in fetch(query):
            key = (candidate["source"], candidate["title"], candidate["artist"], candidate["album"])
            if key in seen:
                continue
            seen.add(key)
            score = score_candidate(candidate, title, artist, album, duration)
            if score > best_score:
                best, best_score = candidate, score
        if best_score >= GOOD_MATCH_SCORE:
            break

    if best is not None and best_score >= MIN_MATCH_SCORE:
        _network_event(best["source"], "artwork-lookup", "success", f"match {best_score:.2f}")
        return best, best_score
    _network_event("deezer" if use_deezer else "itunes", "artwork-lookup", "success", "no confident match")
    return None, best_score


def get_album_art(title, artist, deezer_enabled=None, itunes_enabled=None, album="", duration=0):
    use_deezer, use_itunes = _lookup_policy(deezer_enabled, itunes_enabled)
    cache_key = f"{title}|{artist}|{album}|{int(use_deezer)}|{int(use_itunes)}".lower()
    if cache_key in _cache:
        return _cache[cache_key]
    if not use_deezer and not use_itunes:
        result = (None, "", "", 0)
        _cache[cache_key] = result
        return result

    best, score = find_best_match(title, artist, album, duration, use_deezer, use_itunes)
    if best:
        print(f"[Art] Best match ({best['source']}, score {score:.2f}): '{best['title']}' - '{best['artist']}' [{best['album']}]")
        result = (best["art_url"] or None, best["album"] or "", best["track_link"] or "", best["duration"] or 0)
    else:
        print(f"[Art] No confident match for '{title}' by '{artist}' (best score {score:.2f})")
        result = (None, "", "", 0)
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
