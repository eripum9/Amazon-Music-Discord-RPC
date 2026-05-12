import ctypes
import os
import re
import time
from ctypes import wintypes


_DURATION_RE = re.compile(r"^\d{1,2}:\d{2}(?::\d{2})?$")
_BY_RE = re.compile(r"^(?P<title>.+?)\s+(?:by|from)\s+(?P<artist>.+)$", re.IGNORECASE)
_PROCESS_CACHE = {}
_CACHE = {"key": None, "expires": 0, "value": None}

_SKIP_TEXT = {
    "amazon music",
    "home",
    "library",
    "podcasts",
    "search",
    "settings",
    "queue",
    "shuffle",
    "repeat",
    "previous",
    "next",
    "play",
    "pause",
    "back",
    "forward",
    "upgrade",
    "browse",
    "download",
    "downloads",
    "now playing",
    "lyrics",
    "cast",
    "volume",
    "minimize",
    "maximize",
    "close",
}


def _clean_text(value):
    text = str(value or "").replace("\x00", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _normalise(value):
    value = _clean_text(value).casefold()
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _same(left, right):
    left = _normalise(left)
    right = _normalise(right)
    return bool(left and right and left == right)


def _contains(left, right):
    left = _normalise(left)
    right = _normalise(right)
    return bool(left and right and (left in right or right in left))


def _process_path(pid):
    if not pid:
        return ""
    if pid in _PROCESS_CACHE:
        return _PROCESS_CACHE[pid]
    path = ""
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(0x1000, False, int(pid))
        if handle:
            try:
                size = wintypes.DWORD(32768)
                buffer = ctypes.create_unicode_buffer(size.value)
                if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                    path = buffer.value
            finally:
                kernel32.CloseHandle(handle)
    except Exception:
        path = ""
    _PROCESS_CACHE[pid] = path
    return path


def _is_amazon_process(pid):
    path = _process_path(pid).casefold()
    name = os.path.basename(path)
    return "amazon" in path and ("music" in path or "amazonmusic" in name)


def _is_target_window(control):
    name = _normalise(getattr(control, "Name", ""))
    if "amazon music" in name:
        return True
    try:
        return _is_amazon_process(getattr(control, "ProcessId", 0))
    except Exception:
        return False


def _looks_like_metadata(text):
    value = _clean_text(text)
    low = _normalise(value)
    if not value or low in _SKIP_TEXT:
        return False
    if len(value) < 2 or len(value) > 140:
        return False
    if _DURATION_RE.match(value):
        return False
    if value.startswith(("http://", "https://")):
        return False
    if re.fullmatch(r"[\W_]+", value):
        return False
    return True


def _dedupe(values):
    seen = set()
    result = []
    for value in values:
        text = _clean_text(value)
        key = _normalise(text)
        if key and key not in seen and _looks_like_metadata(text):
            seen.add(key)
            result.append(text)
    return result


def _nearby_values(values, index, before=4, after=7):
    start = max(0, index - before)
    end = min(len(values), index + after + 1)
    candidates = []
    for i in range(index + 1, end):
        candidates.append(values[i])
    for i in range(index - 1, start - 1, -1):
        candidates.append(values[i])
    return candidates


def _choose_track_from_texts(texts, reference=None):
    values = _dedupe(texts)
    reference = reference or {}
    ref_title = _clean_text(reference.get("title", ""))
    ref_artist = _clean_text(reference.get("artist", ""))
    ref_album = _clean_text(reference.get("album", ""))
    candidates = []

    for text in values:
        match = _BY_RE.match(text)
        if match:
            title = _clean_text(match.group("title"))
            artist = _clean_text(match.group("artist"))
            score = 55
            if ref_title and _contains(title, ref_title):
                score += 25
            if ref_artist and _contains(artist, ref_artist):
                score += 20
            candidates.append({"title": title, "artist": artist, "album": "", "confidence": min(score, 95), "source": "amazon_app_probe"})

    for index, value in enumerate(values):
        if not ref_title or not _contains(value, ref_title):
            continue
        artist = ""
        album = ""
        for nearby in _nearby_values(values, index):
            if ref_artist and _contains(nearby, ref_artist):
                artist = nearby
                break
        if not artist:
            for nearby in _nearby_values(values, index):
                if not _same(nearby, value) and not _contains(nearby, ref_album):
                    artist = nearby
                    break
        if ref_album:
            for nearby in _nearby_values(values, index, before=3, after=9):
                if _contains(nearby, ref_album):
                    album = nearby
                    break
        elif artist:
            for nearby in _nearby_values(values, index, before=2, after=9):
                if not _same(nearby, value) and not _same(nearby, artist):
                    album = nearby
                    break
        if artist:
            score = 65
            if ref_artist and _contains(artist, ref_artist):
                score += 20
            if album:
                score += 5
            candidates.append({"title": value, "artist": artist, "album": album, "confidence": min(score, 95), "source": "amazon_app_probe"})

    if not candidates:
        return None
    candidates.sort(key=lambda item: item.get("confidence", 0), reverse=True)
    return candidates[0]


def _read_uia_texts(limit=700):
    import uiautomation as auto

    try:
        auto.SetGlobalSearchTimeout(0.3)
    except Exception:
        pass

    root = auto.GetRootControl()
    targets = []
    for child in root.GetChildren():
        if _is_target_window(child):
            targets.append(child)
    if not targets:
        return [], "Amazon Music window was not exposed to UI Automation"

    values = []
    visited = set()
    stack = list(targets)
    while stack and len(visited) < limit:
        control = stack.pop(0)
        try:
            runtime_id = tuple(control.GetRuntimeId())
        except Exception:
            runtime_id = (id(control),)
        if runtime_id in visited:
            continue
        visited.add(runtime_id)
        try:
            name = _clean_text(getattr(control, "Name", ""))
            if name:
                values.append(name)
        except Exception:
            pass
        try:
            children = control.GetChildren()
        except Exception:
            children = []
        for child in children:
            stack.append(child)
    return values, ""


def get_app_track_sync(reference=None):
    reference = reference or {}
    cache_key = "|".join([
        _normalise(reference.get("title", "")),
        _normalise(reference.get("artist", "")),
        _normalise(reference.get("album", "")),
    ])
    now = time.time()
    if _CACHE["key"] == cache_key and now < _CACHE["expires"]:
        return _CACHE["value"]
    try:
        texts, detail = _read_uia_texts()
        candidate = _choose_track_from_texts(texts, reference)
        if candidate:
            result = {"status": "found", "detail": "Amazon Music UI metadata found", **candidate}
        else:
            result = {"status": "no_match", "detail": detail or "No reliable Amazon Music UI metadata found", "source": "amazon_app_probe"}
    except ImportError:
        result = {"status": "unavailable", "detail": "uiautomation is not installed", "source": "amazon_app_probe"}
    except Exception as e:
        result = {"status": "error", "detail": str(e), "source": "amazon_app_probe"}
    _CACHE["key"] = cache_key
    _CACHE["expires"] = now + 2
    _CACHE["value"] = result
    return result


def apply_probe_to_track(track, probe):
    if not isinstance(track, dict) or not isinstance(probe, dict):
        return track, False
    if probe.get("status") != "found" or int(probe.get("confidence", 0) or 0) < 60:
        return track, False
    merged = dict(track)
    title = _clean_text(probe.get("title", ""))
    artist = _clean_text(probe.get("artist", ""))
    album = _clean_text(probe.get("album", ""))
    current_title = _clean_text(merged.get("title", ""))
    current_artist = _clean_text(merged.get("artist", ""))
    title_matches = title and (not current_title or _contains(title, current_title))
    broken_identity = _same(current_title, current_artist)
    changed = False

    if title and (not current_title or broken_identity or title_matches):
        if merged.get("title") != title:
            merged["title"] = title
            changed = True
    if artist and (not current_artist or broken_identity or title_matches or _contains(artist, current_artist)):
        if merged.get("artist") != artist:
            merged["artist"] = artist
            changed = True
    if album and (not merged.get("album") or title_matches or _contains(artist, merged.get("artist", ""))):
        if merged.get("album") != album:
            merged["album"] = album
            changed = True
    return merged, changed
