import base64
import ctypes
import hashlib
import json
import os
import re
import socket
import struct
import subprocess
import time
import urllib.request
from ctypes import wintypes
from urllib.parse import urlparse


APP_USER_MODEL_ID = "AmazonMobileLLC.AmazonMusic_kc6t79cpj4tp0!AmazonMobileLLC.AmazonMusic"
DEVTOOLS_PORT = 9222
_CACHE = {"key": None, "expires": 0, "value": None}
_EXPLICIT_RE = re.compile(r"\s*\[Explicit\]\s*$", re.IGNORECASE)
_TIME_RE = re.compile(r"^-?\d{1,2}:\d{2}(?::\d{2})?$")


def _clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _clean_label(value):
    return _EXPLICIT_RE.sub("", _clean(value)).strip()


def _parse_time(value):
    text = _clean(value)
    if not _TIME_RE.match(text):
        return None
    negative = text.startswith("-")
    if negative:
        text = text[1:]
    parts = [int(part) for part in text.split(":")]
    if len(parts) == 2:
        seconds = parts[0] * 60 + parts[1]
    else:
        seconds = parts[0] * 3600 + parts[1] * 60 + parts[2]
    return -seconds if negative else seconds


def _normalise_track_payload(payload):
    if not isinstance(payload, dict):
        return {"status": "no_match", "detail": "No Amazon DevTools metadata payload"}
    if payload.get("status") != "found":
        return {
            "status": payload.get("status") or "no_match",
            "detail": payload.get("detail") or "No Amazon DevTools metadata found",
            "source": "amazon_devtools",
        }

    title = _clean_label(payload.get("title"))
    artist = _clean(payload.get("artist"))
    album = _clean_label(payload.get("album"))
    secondary = _clean(payload.get("secondary"))
    if secondary and (not artist or not album) and " • " in secondary:
        left, right = secondary.split(" • ", 1)
        artist = artist or _clean(left)
        album = album or _clean_label(right)

    position = _parse_time(payload.get("position_text"))
    remaining = _parse_time(payload.get("remaining_text"))
    duration = 0
    if position is not None and remaining is not None and remaining < 0:
        duration = max(0, position + abs(remaining))

    if not title or not artist:
        return {
            "status": "no_match",
            "detail": "Amazon DevTools transport metadata was incomplete",
            "source": "amazon_devtools",
        }

    return {
        "status": "found",
        "detail": "Amazon Music DevTools metadata found",
        "source": "amazon_devtools",
        "title": title,
        "artist": artist,
        "album": album,
        "art_url": _clean(payload.get("art_url")),
        "track_link": _clean(payload.get("track_link")),
        "position": position,
        "duration": duration,
        "confidence": 98,
    }


def _http_json(path, timeout=1.5):
    with urllib.request.urlopen(f"http://127.0.0.1:{DEVTOOLS_PORT}{path}", timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def _page_target():
    try:
        targets = _http_json("/json/list")
    except Exception:
        return None
    if not isinstance(targets, list):
        return None
    for target in targets:
        if target.get("type") == "page" and "morpho/webapp" in target.get("url", ""):
            return target
    for target in targets:
        if target.get("type") == "page" and "Amazon Music" in target.get("title", ""):
            return target
    return None


class _CdpSocket:
    def __init__(self, websocket_url, timeout=2):
        self._id = 0
        parsed = urlparse(websocket_url)
        self._host = parsed.hostname or "127.0.0.1"
        self._port = parsed.port or DEVTOOLS_PORT
        self._path = parsed.path
        if parsed.query:
            self._path += "?" + parsed.query
        self._socket = socket.create_connection((self._host, self._port), timeout=timeout)
        self._socket.settimeout(timeout)
        self._handshake()

    def close(self):
        try:
            self._socket.close()
        except Exception:
            pass

    def _read_exact(self, length):
        chunks = []
        remaining = length
        while remaining > 0:
            chunk = self._socket.recv(remaining)
            if not chunk:
                raise ConnectionError("DevTools socket closed")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def _handshake(self):
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            f"GET {self._path} HTTP/1.1\r\n"
            f"Host: {self._host}:{self._port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self._socket.sendall(request.encode("ascii"))
        response = b""
        while b"\r\n\r\n" not in response:
            response += self._socket.recv(4096)
        if b" 101 " not in response.split(b"\r\n", 1)[0]:
            raise ConnectionError("DevTools websocket handshake failed")
        accept = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()).decode("ascii")
        if accept.encode("ascii") not in response:
            raise ConnectionError("DevTools websocket accept key did not match")

    def _send_frame(self, payload):
        data = payload.encode("utf-8")
        header = bytearray([0x81])
        if len(data) < 126:
            header.append(0x80 | len(data))
        elif len(data) <= 0xFFFF:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", len(data)))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", len(data)))
        mask = os.urandom(4)
        header.extend(mask)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(data))
        self._socket.sendall(bytes(header) + masked)

    def _recv_frame(self):
        first, second = self._read_exact(2)
        opcode = first & 0x0F
        masked = bool(second & 0x80)
        length = second & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._read_exact(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._read_exact(8))[0]
        mask = self._read_exact(4) if masked else b""
        payload = self._read_exact(length) if length else b""
        if masked:
            payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        return opcode, payload

    def request(self, method, params=None):
        self._id += 1
        request_id = self._id
        self._send_frame(json.dumps({"id": request_id, "method": method, "params": params or {}}))
        while True:
            opcode, payload = self._recv_frame()
            if opcode == 8:
                raise ConnectionError("DevTools websocket closed")
            if opcode == 9:
                continue
            if opcode != 1:
                continue
            message = json.loads(payload.decode("utf-8", errors="replace"))
            if message.get("id") == request_id:
                return message


_TRANSPORT_EXPRESSION = r"""
(() => {
  const clean = (value) => String(value || '').replace(/\s+/g, ' ').trim();
  const root = document.querySelector('#transportContainer.hasTrackLoaded') || document.querySelector('#transportContainer') || document.querySelector('#transport');
  if (!root) {
    return { status: 'no_match', detail: 'Amazon Music transport was not found' };
  }
  const titleEl = root.querySelector('.trackMetadataWrapper .primaryContainer') || root.querySelector('.trackMetadata .primaryContainer') || root.querySelector('.trackMetadata .title');
  const secondaryEl = root.querySelector('.trackMetadataWrapper .secondaryText') || root.querySelector('.trackMetadata .secondaryText');
  const secondaryParts = Array.from(root.querySelectorAll('.trackMetadataWrapper .secondaryInnerText, .trackMetadata .secondaryInnerText')).map((el) => clean(el.innerText || el.textContent)).filter(Boolean);
  const img = root.querySelector('.trackMetadataWrapper .albumArt img.artImage') || root.querySelector('.albumArt img.artImage') || root.querySelector('img.artImage');
  const titleLink = titleEl ? titleEl.querySelector('a') : null;
  const positionEl = root.querySelector('.currentPlaybackPosition');
  const remainingEl = root.querySelector('.currentRemainingPosition');
  const title = clean((titleEl && (titleEl.getAttribute('title') || titleEl.innerText || titleEl.textContent)) || '');
  const secondary = clean((secondaryEl && (secondaryEl.getAttribute('title') || secondaryEl.innerText || secondaryEl.textContent)) || '');
  return {
    status: title && (secondaryParts[0] || secondary) ? 'found' : 'no_match',
    detail: title ? 'Amazon Music transport found' : 'Amazon Music transport had no title',
    title,
    artist: secondaryParts[0] || '',
    album: secondaryParts[1] || '',
    secondary,
    art_url: img ? img.src : '',
    track_link: titleLink ? titleLink.href : '',
    position_text: positionEl ? clean(positionEl.innerText || positionEl.textContent) : '',
    remaining_text: remainingEl ? clean(remainingEl.innerText || remainingEl.textContent) : ''
  };
})()
"""


def get_devtools_track_sync():
    target = _page_target()
    if not target:
        return {
            "status": "unavailable",
            "detail": "Amazon Music is not running with DevTools metadata enabled",
            "source": "amazon_devtools",
        }
    cache_key = target.get("id")
    now = time.time()
    if _CACHE["key"] == cache_key and now < _CACHE["expires"]:
        return _CACHE["value"]
    client = None
    try:
        client = _CdpSocket(target["webSocketDebuggerUrl"])
        response = client.request("Runtime.evaluate", {
            "expression": _TRANSPORT_EXPRESSION,
            "returnByValue": True,
            "awaitPromise": True,
            "timeout": 3000,
        })
        result = response.get("result", {}).get("result", {}).get("value")
        track = _normalise_track_payload(result)
    except Exception as e:
        track = {"status": "error", "detail": str(e), "source": "amazon_devtools"}
    finally:
        if client:
            client.close()
    _CACHE["key"] = cache_key
    _CACHE["expires"] = now + 1.5
    _CACHE["value"] = track
    return track


def apply_devtools_to_track(track, devtools):
    if not isinstance(devtools, dict) or devtools.get("status") != "found":
        return track, False
    merged = dict(track or {})
    changed = False
    for key in ("title", "artist", "album"):
        value = _clean(devtools.get(key))
        if value and merged.get(key) != value:
            merged[key] = value
            changed = True
    position = devtools.get("position")
    duration = devtools.get("duration")
    if position is not None:
        merged["position"] = position
    if duration:
        merged["duration"] = duration
    if not merged.get("status"):
        merged["status"] = "playing"
    if devtools.get("art_url"):
        merged["_amazon_art_url"] = devtools.get("art_url")
    if devtools.get("track_link"):
        merged["_amazon_track_link"] = devtools.get("track_link")
    return merged, changed


def launch_amazon_music_devtools():
    script = rf"""
$code = @'
using System;
using System.Runtime.InteropServices;

[ComImport]
[Guid("2e941141-7f97-4756-ba1d-9decde894a3d")]
[InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IApplicationActivationManager
{{
    int ActivateApplication([MarshalAs(UnmanagedType.LPWStr)] string appUserModelId, [MarshalAs(UnmanagedType.LPWStr)] string arguments, int options, out uint processId);
}}

[ComImport]
[Guid("45BA127D-10A8-46EA-8AB7-56EA9078943C")]
class ApplicationActivationManager
{{
}}

public static class AppActivator
{{
    public static uint Activate(string appId, string args)
    {{
        IApplicationActivationManager manager = (IApplicationActivationManager)new ApplicationActivationManager();
        uint processId;
        int hr = manager.ActivateApplication(appId, args, 0, out processId);
        if (hr < 0)
        {{
            Marshal.ThrowExceptionForHR(hr);
        }}
        return processId;
    }}
}}
'@
Add-Type -TypeDefinition $code
[AppActivator]::Activate('{APP_USER_MODEL_ID}', '--remote-debugging-port={DEVTOOLS_PORT}')
"""
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15,
            creationflags=0x08000000 if os.name == "nt" else 0,
        )
    except Exception as e:
        return {"ok": False, "error": str(e)}
    if completed.returncode != 0:
        return {"ok": False, "error": _clean(completed.stderr) or "Could not launch Amazon Music"}
    return {"ok": True, "pid": _clean(completed.stdout)}
