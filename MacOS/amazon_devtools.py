# MIT License - Copyright (c) 2026 eripum9

"""Opt-in Chromium DevTools metadata transport for Amazon Music on macOS.

The DevTools endpoint can inspect an authenticated renderer, so this module
deliberately exposes only a small, read-only surface.  It never requests
browser storage, network headers, cookies, or command-line details.
"""

from __future__ import annotations

import base64
import ctypes
import hashlib
import http.client
import json
import math
import os
import plistlib
import random
import re
import signal
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path
from typing import cast
from urllib.parse import quote, urlparse


AMAZON_MUSIC_APP = Path("/Applications/Amazon Music.app")
AMAZON_MUSIC_BUNDLE_ID = "com.amazon.music"
AMAZON_MUSIC_TEAM_ID = "94KV3E626L"
AMAZON_MUSIC_EXECUTABLE = "Amazon Music"
DEVTOOLS_PORT_MIN = 49152
DEVTOOLS_PORT_MAX = 60999
DISCOVERY_RETRY_SECONDS = 3.0
MAX_HTTP_RESPONSE_BYTES = 1024 * 1024
MAX_WEBSOCKET_MESSAGE_BYTES = 1024 * 1024
MAX_HANDSHAKE_BYTES = 32 * 1024

AMAZON_REGION_SUFFIXES = (
    "com",
    "de",
    "co.uk",
    "fr",
    "it",
    "es",
    "co.jp",
    "ca",
    "com.au",
    "com.br",
    "com.mx",
)
AMAZON_MUSIC_HOSTS = frozenset(f"music.amazon.{suffix}" for suffix in AMAZON_REGION_SUFFIXES)
AMAZON_EMBEDDED_WEBAPP_HOSTS = frozenset(
    f"www.amazon.{suffix}" for suffix in AMAZON_REGION_SUFFIXES
)
AMAZON_IMAGE_HOSTS = frozenset(
    {
        "m.media-amazon.com",
        "images-na.ssl-images-amazon.com",
        "images-eu.ssl-images-amazon.com",
        "images-fe.ssl-images-amazon.com",
    }
)

_EXPLICIT_RE = re.compile(r"\s*\[Explicit\]\s*$", re.IGNORECASE)
_TIME_RE = re.compile(r"^-?\d{1,3}:\d{2}(?::\d{2})?$")
_ASIN_RE = re.compile(r"^[A-Z0-9]{10}$", re.IGNORECASE)
_TARGET_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,256}$")
_DEVTOOLS_PAGE_PATH_RE = re.compile(r"^/devtools/page/([A-Za-z0-9._:-]{1,256})$")

_DEVTOOLS_PORT: int | None = None
_LAST_LAUNCH: dict[str, object] = {}
_CACHE: dict[str, object] = {"key": None, "expires": 0.0, "value": None}
_INSTALLATION_CACHE: dict[str, object] = {"fingerprint": None, "expires": 0.0, "value": None}
_DISCOVERY_RETRY_AFTER = 0.0


def _clean(value: object, limit: int = 2048) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _clean_label(value: object) -> str:
    return _EXPLICIT_RE.sub("", _clean(value, 512)).strip()


def _normalise_region(value: object = None) -> str:
    region = _clean(value, 32).lower().lstrip(".")
    return region if region in AMAZON_REGION_SUFFIXES else "com"


def _valid_devtools_port(value: object) -> int | None:
    try:
        port = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return port if DEVTOOLS_PORT_MIN <= port <= DEVTOOLS_PORT_MAX else None


def set_devtools_port(port: object) -> int:
    """Select a high port explicitly, primarily for an owning runtime instance."""

    global _DEVTOOLS_PORT
    selected = _valid_devtools_port(port)
    if selected is None:
        raise ValueError("DevTools port must be in the private high-port range")
    _DEVTOOLS_PORT = selected
    _clear_cache()
    return selected


def reset_devtools_port() -> None:
    global _DEVTOOLS_PORT, _DISCOVERY_RETRY_AFTER
    _DEVTOOLS_PORT = None
    _DISCOVERY_RETRY_AFTER = 0.0
    _clear_cache()


def _reserve_devtools_port(port: object = None) -> tuple[int, socket.socket]:
    if port is not None:
        selected = _valid_devtools_port(port)
        if selected is None:
            raise ValueError("DevTools port must be in the private high-port range")
        candidates = [selected]
    else:
        candidates = list(range(DEVTOOLS_PORT_MIN, DEVTOOLS_PORT_MAX + 1))
        random.SystemRandom().shuffle(candidates)

    for candidate in candidates:
        reservation = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            reservation.bind(("127.0.0.1", candidate))
            return candidate, reservation
        except OSError:
            reservation.close()
    raise RuntimeError("Could not reserve a private loopback metadata port")


def get_devtools_port(create: bool = True) -> int | None:
    global _DEVTOOLS_PORT
    if _DEVTOOLS_PORT is None and create:
        selected, reservation = _reserve_devtools_port()
        reservation.close()
        _DEVTOOLS_PORT = selected
    return _DEVTOOLS_PORT


def _read_bundle_info(app_path: Path) -> dict[str, object]:
    try:
        with (app_path / "Contents" / "Info.plist").open("rb") as stream:
            value = plistlib.load(stream)
    except (OSError, plistlib.InvalidFileException, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _official_signature_identity(app_path: Path, runner=subprocess.run) -> bool:
    """Check the immutable signing identity without returning codesign output."""

    try:
        completed = runner(
            ["/usr/bin/codesign", "-dv", "--verbose=4", str(app_path)],
            capture_output=True,
            text=True,
            timeout=8,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    output = f"{completed.stdout or ''}\n{completed.stderr or ''}"
    fields: dict[str, list[str]] = {}
    for raw_line in output.splitlines():
        key, separator, value = raw_line.partition("=")
        if separator:
            fields.setdefault(key.strip(), []).append(value.strip())
    return bool(
        completed.returncode == 0
        and fields.get("Identifier") == [AMAZON_MUSIC_BUNDLE_ID]
        and fields.get("TeamIdentifier") == [AMAZON_MUSIC_TEAM_ID]
        and any("AMZN Mobile LLC" in authority for authority in fields.get("Authority", []))
    )


def _validate_app_bundle(
    app_path: Path,
    *,
    require_standard_location: bool = True,
    signature_checker=_official_signature_identity,
) -> dict[str, object] | None:
    try:
        resolved = app_path.resolve(strict=True)
    except OSError:
        return None
    if require_standard_location and resolved != AMAZON_MUSIC_APP:
        return None
    info = _read_bundle_info(resolved)
    if (
        info.get("CFBundleIdentifier") != AMAZON_MUSIC_BUNDLE_ID
        or info.get("CFBundleExecutable") != AMAZON_MUSIC_EXECUTABLE
    ):
        return None
    executable = resolved / "Contents" / "MacOS" / AMAZON_MUSIC_EXECUTABLE
    if not executable.is_file() or not os.access(executable, os.X_OK):
        return None
    if signature_checker is not None and not signature_checker(resolved):
        return None
    return {
        "app_path": str(resolved),
        "executable": str(executable),
        "bundle_id": AMAZON_MUSIC_BUNDLE_ID,
        "version": _clean(info.get("CFBundleShortVersionString"), 64),
    }


def locate_amazon_music_app() -> dict[str, object] | None:
    """Return a validated installation descriptor for the standard app."""

    if sys.platform != "darwin":
        return None
    info_path = AMAZON_MUSIC_APP / "Contents" / "Info.plist"
    executable = AMAZON_MUSIC_APP / "Contents" / "MacOS" / AMAZON_MUSIC_EXECUTABLE
    try:
        fingerprint = (
            info_path.stat().st_mtime_ns,
            info_path.stat().st_size,
            executable.stat().st_mtime_ns,
            executable.stat().st_size,
        )
    except OSError:
        fingerprint = None
    now = time.monotonic()
    if (
        fingerprint is not None
        and fingerprint == _INSTALLATION_CACHE["fingerprint"]
        and now < float(cast(float, _INSTALLATION_CACHE["expires"]))
    ):
        cached = _INSTALLATION_CACHE["value"]
        return dict(cached) if isinstance(cached, dict) else None
    installation = _validate_app_bundle(AMAZON_MUSIC_APP)
    _INSTALLATION_CACHE.update(
        {
            "fingerprint": fingerprint,
            "expires": now + (60.0 if installation else 3.0),
            "value": dict(installation) if installation else None,
        }
    )
    return installation


def amazon_music_installation_state() -> dict[str, object]:
    installation = locate_amazon_music_app()
    if not installation:
        return {
            "installed": False,
            "status": "missing",
            "detail": "The official Amazon Music app was not found in /Applications",
        }
    return {
        "installed": True,
        "status": "ready",
        "detail": "The official Amazon Music app is available",
        **installation,
    }


def _process_executable_path(pid: int) -> str:
    if sys.platform != "darwin" or pid <= 0:
        return ""
    try:
        libproc = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
        proc_pidpath = libproc.proc_pidpath
        proc_pidpath.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
        proc_pidpath.restype = ctypes.c_int
        buffer = ctypes.create_string_buffer(4096)
        length = proc_pidpath(pid, buffer, len(buffer))
    except (AttributeError, OSError):
        return ""
    if length <= 0:
        return ""
    return os.fsdecode(buffer.value)


def _trusted_process_paths(installation: dict[str, object]) -> frozenset[str]:
    app_path = Path(str(installation["app_path"]))
    relatives = (
        "Contents/MacOS/Amazon Music",
        "Contents/MacOS/Amazon Music Helper",
        "Contents/Frameworks/Amazon Music Renderer.app/Contents/MacOS/Amazon Music Renderer",
        "Contents/Frameworks/Amazon Music Renderer (GPU).app/Contents/MacOS/Amazon Music Renderer (GPU)",
        "Contents/Frameworks/Amazon Music Renderer (Renderer).app/Contents/MacOS/Amazon Music Renderer (Renderer)",
    )
    return frozenset(os.path.realpath(app_path / relative) for relative in relatives)


def _is_trusted_amazon_pid(pid: object, installation: dict[str, object]) -> bool:
    try:
        selected_pid = int(pid)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    path = _process_executable_path(selected_pid)
    return bool(path and os.path.realpath(path) in _trusted_process_paths(installation))


def _pids_named(name: str, runner=subprocess.run) -> list[int]:
    try:
        completed = runner(
            ["/usr/bin/pgrep", "-x", name],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if completed.returncode not in (0, 1):
        return []
    result = []
    for line in (completed.stdout or "").splitlines():
        try:
            result.append(int(line.strip()))
        except ValueError:
            continue
    return result


def _running_amazon_pids(installation: dict[str, object], *, helpers: bool = False) -> list[int]:
    names = [AMAZON_MUSIC_EXECUTABLE]
    if helpers:
        names.extend(
            [
                "Amazon Music Helper",
                "Amazon Music Renderer",
                "Amazon Music Renderer (GPU)",
                "Amazon Music Renderer (Renderer)",
            ]
        )
    candidates = {pid for name in names for pid in _pids_named(name)}
    return sorted(pid for pid in candidates if _is_trusted_amazon_pid(pid, installation))


def amazon_music_is_running() -> bool:
    installation = locate_amazon_music_app()
    return bool(installation and _running_amazon_pids(installation))


def _listener_pids(port: object, runner=subprocess.run) -> list[int]:
    selected = _valid_devtools_port(port)
    if selected is None:
        return []
    try:
        completed = runner(
            [
                "/usr/sbin/lsof",
                "-nP",
                "-a",
                f"-iTCP:{selected}",
                "-sTCP:LISTEN",
                "-Fp",
            ],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if completed.returncode != 0:
        return []
    pids = set()
    for line in (completed.stdout or "").splitlines():
        if line.startswith("p") and line[1:].isdigit():
            pids.add(int(line[1:]))
    return sorted(pids)


def _trusted_listener_ports(
    installation: dict[str, object],
    runner=subprocess.run,
) -> list[int]:
    """List private loopback listeners whose every owner is Amazon Music.

    This intentionally asks ``lsof`` only for socket ownership metadata.  It
    does not inspect Amazon Music's command line, environment, or profile.
    """

    try:
        completed = runner(
            [
                "/usr/sbin/lsof",
                "-nP",
                "-a",
                "-iTCP",
                "-sTCP:LISTEN",
                "-Fpfn",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if completed.returncode != 0:
        return []

    current_pid: int | None = None
    owners_by_port: dict[int, set[int]] = {}
    for line in (completed.stdout or "").splitlines():
        if line.startswith("p"):
            current_pid = int(line[1:]) if line[1:].isdigit() else None
            continue
        if not line.startswith("n") or current_pid is None:
            continue
        endpoint = line[1:]
        match = re.fullmatch(r"(?:127\.0\.0\.1|\[::1\]):(\d+)", endpoint)
        if not match:
            continue
        selected = _valid_devtools_port(match.group(1))
        if selected is not None:
            owners_by_port.setdefault(selected, set()).add(current_pid)

    return sorted(
        port
        for port, owners in owners_by_port.items()
        if owners and all(_is_trusted_amazon_pid(pid, installation) for pid in owners)
    )


def _devtools_owner_trust(port: object, installation: dict[str, object] | None = None) -> dict[str, object]:
    selected = _valid_devtools_port(port)
    if selected is None:
        return {
            "trusted": False,
            "status": "rejected",
            "detail": "The metadata listener port was outside the private high-port range",
        }
    installation = installation or locate_amazon_music_app()
    if not installation:
        return {
            "trusted": False,
            "status": "unavailable",
            "detail": "The official Amazon Music installation could not be verified",
        }
    pids = _listener_pids(selected)
    if not pids:
        return {
            "trusted": False,
            "status": "unavailable",
            "detail": "No verifiable Amazon Music metadata listener was found",
        }
    if not all(_is_trusted_amazon_pid(pid, installation) for pid in pids):
        return {
            "trusted": False,
            "status": "rejected",
            "detail": "The metadata port is owned by a non-Amazon process",
        }
    return {
        "trusted": True,
        "status": "verified",
        "detail": "The metadata listener belongs to Amazon Music",
        "pids": pids,
    }


def _http_json(path: str, *, port: object, timeout: float = 1.5) -> object:
    selected = _valid_devtools_port(port)
    if selected is None or path not in {"/json", "/json/list", "/json/version"}:
        raise ConnectionError("Untrusted DevTools HTTP endpoint")
    connection = http.client.HTTPConnection("127.0.0.1", selected, timeout=max(0.1, timeout))
    try:
        connection.request(
            "GET",
            path,
            headers={"Host": f"127.0.0.1:{selected}", "Accept": "application/json", "Connection": "close"},
        )
        response = connection.getresponse()
        if response.status != 200:
            raise ConnectionError("DevTools HTTP endpoint was unavailable")
        content_length = response.getheader("Content-Length")
        if content_length:
            try:
                if int(content_length) > MAX_HTTP_RESPONSE_BYTES:
                    raise ValueError("DevTools HTTP response was too large")
            except ValueError as error:
                if str(error) == "DevTools HTTP response was too large":
                    raise
        body = response.read(MAX_HTTP_RESPONSE_BYTES + 1)
        if len(body) > MAX_HTTP_RESPONSE_BYTES:
            raise ValueError("DevTools HTTP response was too large")
        return json.loads(body.decode("utf-8"))
    finally:
        connection.close()


def _exact_https_music_url(value: object) -> str:
    text = _clean(value, 4096)
    try:
        parsed = urlparse(text)
        port = parsed.port
    except ValueError:
        return ""
    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme.lower() != "https"
        or host not in AMAZON_MUSIC_HOSTS
        or port not in (None, 443)
        or parsed.username
        or parsed.password
    ):
        return ""
    return text


def _exact_https_webapp_url(value: object) -> str:
    """Accept the music site or Amazon's exact legacy Morpho CEF shell."""

    text = _clean(value, 4096)
    try:
        parsed = urlparse(text)
        port = parsed.port
    except ValueError:
        return ""
    host = (parsed.hostname or "").lower()
    morpho_path = parsed.path.rstrip("/")
    allowed_morpho = (
        host in AMAZON_EMBEDDED_WEBAPP_HOSTS
        and (morpho_path == "/morpho/webapp" or morpho_path.startswith("/morpho/webapp/"))
    )
    if (
        parsed.scheme.lower() != "https"
        or (host not in AMAZON_MUSIC_HOSTS and not allowed_morpho)
        or port not in (None, 443)
        or parsed.username
        or parsed.password
    ):
        return ""
    return text


def _safe_artwork_url(value: object) -> str:
    text = _clean(value, 4096)
    try:
        parsed = urlparse(text)
        port = parsed.port
    except ValueError:
        return ""
    if (
        parsed.scheme.lower() != "https"
        or (parsed.hostname or "").lower() not in AMAZON_IMAGE_HOSTS
        or port not in (None, 443)
        or parsed.username
        or parsed.password
    ):
        return ""
    return text


def _is_amazon_music_target(target: object) -> bool:
    if not isinstance(target, dict) or target.get("type") != "page":
        return False
    target_id = _clean(target.get("id"), 256)
    return bool(_TARGET_ID_RE.fullmatch(target_id) and _exact_https_webapp_url(target.get("url")))


def _valid_target_websocket(target: object, port: object) -> bool:
    selected = _valid_devtools_port(port)
    if selected is None or not isinstance(target, dict):
        return False
    target_id = _clean(target.get("id"), 256)
    try:
        parsed = urlparse(_clean(target.get("webSocketDebuggerUrl"), 4096))
        websocket_port = parsed.port
    except ValueError:
        return False
    match = _DEVTOOLS_PAGE_PATH_RE.fullmatch(parsed.path or "")
    return bool(
        parsed.scheme.lower() == "ws"
        and (parsed.hostname or "").lower() in {"127.0.0.1", "localhost", "::1"}
        and websocket_port == selected
        and not parsed.username
        and not parsed.password
        and not parsed.params
        and not parsed.query
        and not parsed.fragment
        and match
        and match.group(1) == target_id
    )


def _page_target(port: object = None, *, verify_owner: bool = True) -> dict[str, object] | None:
    selected = _valid_devtools_port(port if port is not None else get_devtools_port(False))
    if selected is None:
        return None
    if verify_owner and not _devtools_owner_trust(selected).get("trusted"):
        return None
    try:
        targets = _http_json("/json/list", port=selected)
    except (ConnectionError, OSError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(targets, list):
        return None
    for target in targets:
        if _is_amazon_music_target(target) and _valid_target_websocket(target, selected):
            return target
    return None


def discover_devtools_port(installation: dict[str, object] | None = None) -> int | None:
    """Rediscover one trusted existing Amazon Music DevTools listener.

    A fresh RPC process deliberately does not read Amazon Music's profile or
    command line.  It considers only loopback listeners owned by processes
    from the verified official bundle, validates the exposed page target, and
    fails closed when more than one listener matches.
    """

    global _DEVTOOLS_PORT, _DISCOVERY_RETRY_AFTER
    now = time.monotonic()
    if now < _DISCOVERY_RETRY_AFTER:
        return None
    installation = installation or locate_amazon_music_app()
    if not installation:
        return None

    matches: list[int] = []
    for candidate in _trusted_listener_ports(installation):
        if not _devtools_owner_trust(candidate, installation).get("trusted"):
            continue
        if not _page_target(candidate, verify_owner=False):
            continue
        # Recheck after probing so a listener ownership race fails closed.
        if _devtools_owner_trust(candidate, installation).get("trusted"):
            matches.append(candidate)

    if len(matches) != 1:
        _DISCOVERY_RETRY_AFTER = time.monotonic() + DISCOVERY_RETRY_SECONDS
        return None
    _DEVTOOLS_PORT = matches[0]
    _DISCOVERY_RETRY_AFTER = 0.0
    _clear_cache()
    return _DEVTOOLS_PORT


class _CdpSocket:
    def __init__(self, websocket_url: str, *, expected_port: object, expected_target_id: str, timeout: float = 2.0):
        target = {"id": expected_target_id, "webSocketDebuggerUrl": websocket_url}
        if not _valid_target_websocket(target, expected_port):
            raise ConnectionError("DevTools websocket did not match the trusted page target")
        parsed = urlparse(websocket_url)
        self._host = parsed.hostname or "127.0.0.1"
        self._port = int(parsed.port or 0)
        self._path = parsed.path
        self._id = 0
        self._socket = socket.create_connection((self._host, self._port), timeout=timeout)
        self._socket.settimeout(timeout)
        self._handshake()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
        return False

    def close(self) -> None:
        try:
            self._send_frame(b"", opcode=8)
        except Exception:
            pass
        try:
            self._socket.close()
        except Exception:
            pass

    def _read_exact(self, length: int) -> bytes:
        chunks = []
        remaining = length
        while remaining:
            chunk = self._socket.recv(remaining)
            if not chunk:
                raise ConnectionError("DevTools websocket closed")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def _handshake(self) -> None:
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            f"GET {self._path} HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{self._port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self._socket.sendall(request.encode("ascii"))
        response = b""
        while b"\r\n\r\n" not in response:
            response += self._socket.recv(4096)
            if len(response) > MAX_HANDSHAKE_BYTES:
                raise ConnectionError("DevTools websocket handshake was too large")
        status_line, _, header_block = response.partition(b"\r\n")
        if b" 101 " not in status_line:
            raise ConnectionError("DevTools websocket handshake failed")
        headers: dict[bytes, bytes] = {}
        for line in header_block.split(b"\r\n"):
            name, separator, value = line.partition(b":")
            if separator:
                headers[name.strip().lower()] = value.strip()
        expected = base64.b64encode(
            hashlib.sha1(
                (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii"),
                usedforsecurity=False,
            ).digest()
        )
        if headers.get(b"sec-websocket-accept") != expected:
            raise ConnectionError("DevTools websocket accept key did not match")

    def _send_frame(self, payload: str | bytes, *, opcode: int = 1) -> None:
        data = payload if isinstance(payload, bytes) else payload.encode("utf-8")
        if len(data) > MAX_WEBSOCKET_MESSAGE_BYTES:
            raise ValueError("DevTools request was too large")
        header = bytearray([0x80 | opcode])
        if len(data) < 126:
            header.append(0x80 | len(data))
        elif len(data) <= 0xFFFF:
            header.extend((0x80 | 126,))
            header.extend(struct.pack("!H", len(data)))
        else:
            header.extend((0x80 | 127,))
            header.extend(struct.pack("!Q", len(data)))
        mask = os.urandom(4)
        header.extend(mask)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(data))
        self._socket.sendall(bytes(header) + masked)

    def _recv_frame(self) -> tuple[int, bytes]:
        first, second = self._read_exact(2)
        if not first & 0x80:
            raise ConnectionError("Fragmented DevTools websocket frame was rejected")
        if second & 0x80:
            raise ConnectionError("Masked DevTools server frame was rejected")
        opcode = first & 0x0F
        length = second & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._read_exact(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._read_exact(8))[0]
        if length > MAX_WEBSOCKET_MESSAGE_BYTES:
            raise ConnectionError("DevTools websocket message was too large")
        return opcode, self._read_exact(length) if length else b""

    def request(self, method: str, params: dict[str, object] | None = None) -> dict[str, object]:
        self._id += 1
        request_id = self._id
        self._send_frame(json.dumps({"id": request_id, "method": method, "params": params or {}}))
        while True:
            opcode, payload = self._recv_frame()
            if opcode == 8:
                raise ConnectionError("DevTools websocket closed")
            if opcode == 9:
                self._send_frame(payload, opcode=10)
                continue
            if opcode == 10:
                continue
            if opcode != 1:
                raise ConnectionError("Unexpected DevTools websocket frame")
            message = json.loads(payload.decode("utf-8"))
            if isinstance(message, dict) and message.get("id") == request_id:
                return message


_TRANSPORT_EXPRESSION = r"""
(() => {
  const clean = (value, limit = 2048) => String(value || '').replace(/\s+/g, ' ').trim().slice(0, limit);
  const root = document.querySelector('#transportContainer.hasTrackLoaded') ||
    document.querySelector('#transportContainer') || document.querySelector('#transport');
  if (!root) {
    return {status: 'no_match', detail: 'Amazon Music transport was not found'};
  }
  const first = (...selectors) => selectors.map((selector) => root.querySelector(selector)).find(Boolean) || null;
  const text = (element) => element ? clean(element.getAttribute('title') || element.innerText || element.textContent) : '';
  const titleElement = first('.trackMetadataWrapper .primaryContainer', '.trackMetadata .primaryContainer',
    '.trackMetadata .title', '[data-testid="transport-title"]');
  const secondaryElement = first('.trackMetadataWrapper .secondaryText', '.trackMetadata .secondaryText');
  const secondaryParts = Array.from(root.querySelectorAll(
    '.trackMetadataWrapper .secondaryInnerText, .trackMetadata .secondaryInnerText'
  )).map(text).filter(Boolean).slice(0, 2);
  const image = first('.trackMetadataWrapper .albumArt img.artImage', '.albumArt img.artImage', 'img.artImage');
  const titleLink = titleElement ?
    (titleElement.matches('a[href]') ? titleElement : titleElement.querySelector('a[href]')) : null;
  const positionElement = first('.currentPlaybackPosition');
  const remainingElement = first('.currentRemainingPosition');
  const playPause = first('button.playPause');
  const media = document.querySelector('audio, video');
  let playbackStatus = '';
  if (media && clean(media.currentSrc || media.src)) {
    playbackStatus = media.paused ? 'paused' : 'playing';
  } else {
    const markup = playPause ? clean(playPause.innerHTML, 8192) : '';
    if (/#pause|svg-icon--pause/i.test(markup)) playbackStatus = 'playing';
    else if (/#play|svg-icon--play/i.test(markup)) playbackStatus = 'paused';
  }
  const finite = (value) => Number.isFinite(Number(value)) ? Number(value) : null;
  const title = text(titleElement);
  const secondary = text(secondaryElement);
  return {
    status: title && (secondaryParts[0] || secondary) ? 'found' : 'no_match',
    detail: title ? 'Amazon Music transport found' : 'Amazon Music transport had no title',
    title,
    artist: secondaryParts[0] || '',
    album: secondaryParts[1] || '',
    secondary,
    art_url: image ? clean(image.currentSrc || image.src, 4096) : '',
    track_link: titleLink ? clean(titleLink.href, 4096) : '',
    position: media ? finite(media.currentTime) : null,
    duration: media ? finite(media.duration) : null,
    position_text: text(positionElement),
    remaining_text: text(remainingElement),
    playback_status: playbackStatus
  };
})()
"""


def _seconds(value: object) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return max(0.0, number) if math.isfinite(number) else None


def _parse_time(value: object) -> int | None:
    text = _clean(value, 16)
    if not _TIME_RE.fullmatch(text):
        return None
    negative = text.startswith("-")
    if negative:
        text = text[1:]
    parts = [int(part) for part in text.split(":")]
    seconds = parts[0] * 60 + parts[1] if len(parts) == 2 else parts[0] * 3600 + parts[1] * 60 + parts[2]
    return -seconds if negative else seconds


def amazon_music_search_link(title: object, artist: object, link_region: object = None) -> str:
    query = " ".join(part for part in (_clean(title, 512), _clean(artist, 512)) if part)
    if not query:
        return ""
    return f"https://music.amazon.{_normalise_region(link_region)}/search/{quote(query, safe='')}"


def _track_link(payload: dict[str, object], title: str, artist: str, link_region: object = None) -> str:
    asin = _clean(payload.get("track_asin"), 16).upper()
    if _ASIN_RE.fullmatch(asin):
        return f"https://music.amazon.{_normalise_region(link_region)}/tracks/{asin}"
    direct = _exact_https_music_url(payload.get("track_link"))
    return direct or amazon_music_search_link(title, artist, link_region)


def _normalise_track_payload(payload: object, link_region: object = None) -> dict[str, object]:
    if not isinstance(payload, dict):
        return {
            "status": "no_match",
            "detail": "No Amazon Music transport metadata was returned",
            "source": "amazon_devtools",
        }
    if payload.get("status") != "found":
        return {
            "status": "no_match",
            "detail": "Amazon Music does not currently have a track loaded",
            "source": "amazon_devtools",
        }
    title = _clean_label(payload.get("title"))
    artist = _clean(payload.get("artist"), 512)
    album = _clean_label(payload.get("album"))
    secondary = _clean(payload.get("secondary"), 1024)
    if secondary and (not artist or not album):
        if " • " in secondary:
            left, right = secondary.split(" • ", 1)
            artist = artist or _clean(left, 512)
            album = album or _clean_label(right)
        elif not artist:
            artist = secondary[:512]
    if not title or not artist:
        return {
            "status": "no_match",
            "detail": "Amazon Music transport metadata was incomplete",
            "source": "amazon_devtools",
        }

    position = _seconds(payload.get("position"))
    duration = _seconds(payload.get("duration"))
    if position is None:
        parsed_position = _parse_time(payload.get("position_text"))
        position = float(parsed_position) if parsed_position is not None and parsed_position >= 0 else None
    if not duration:
        remaining = _parse_time(payload.get("remaining_text"))
        if position is not None and remaining is not None and remaining < 0:
            duration = position + abs(remaining)
    if duration and position is not None:
        position = min(position, duration)

    playback_status = _clean(payload.get("playback_status"), 16).lower()
    if playback_status not in {"playing", "paused"}:
        playback_status = "playing"
    return {
        "status": "found",
        "detail": "Amazon Music metadata found",
        "source": "amazon_devtools",
        "title": title,
        "artist": artist,
        "album": album,
        "art_url": _safe_artwork_url(payload.get("art_url")),
        "track_link": _track_link(payload, title, artist, link_region),
        "position": position,
        "duration": duration or 0.0,
        "playback_status": playback_status,
        "confidence": 98,
    }


def get_devtools_status(port: object = None) -> dict[str, object]:
    selected = _valid_devtools_port(port if port is not None else get_devtools_port(False))
    installation = locate_amazon_music_app()
    if not installation:
        return {
            "status": "missing",
            "detail": "The official Amazon Music app was not found",
            "source": "amazon_devtools",
        }
    running = bool(_running_amazon_pids(installation))
    if selected is None and port is None:
        selected = discover_devtools_port(installation)
    if selected is None:
        return {
            "status": "off" if not running else "restart_required",
            "detail": "Amazon Music is not running with enhanced metadata",
            "source": "amazon_devtools",
            "running": running,
        }
    owner = _devtools_owner_trust(selected, installation)
    if not owner.get("trusted"):
        return {
            "status": owner.get("status", "unavailable"),
            "detail": owner.get("detail", "Amazon Music enhanced metadata is unavailable"),
            "source": "amazon_devtools",
            "port": selected,
            "running": running,
        }
    target = _page_target(selected, verify_owner=False)
    if not target:
        return {
            "status": "starting" if running else "unavailable",
            "detail": "Waiting for a validated Amazon Music page target",
            "source": "amazon_devtools",
            "port": selected,
            "running": running,
        }
    return {
        "status": "ready",
        "detail": "Amazon Music enhanced metadata is ready",
        "source": "amazon_devtools",
        "port": selected,
        "running": True,
        "owner": owner,
    }


def get_devtools_track_sync(
    link_region: object = None,
    port: object = None,
    method: str = "",
) -> dict[str, object]:
    selected = _valid_devtools_port(port if port is not None else get_devtools_port(False))
    if selected is None and port is None:
        selected = discover_devtools_port()
    if selected is None:
        return {
            "status": "unavailable",
            "detail": "Amazon Music enhanced metadata has not been started",
            "source": "amazon_devtools",
        }
    owner = _devtools_owner_trust(selected)
    if not owner.get("trusted"):
        return {
            "status": "error" if owner.get("status") == "rejected" else "unavailable",
            "detail": owner.get("detail", "Amazon Music enhanced metadata is unavailable"),
            "source": "amazon_devtools",
            "port": selected,
        }
    target = _page_target(selected, verify_owner=False)
    if not target:
        return {
            "status": "unavailable",
            "detail": "No validated Amazon Music page target was found",
            "source": "amazon_devtools",
            "port": selected,
        }
    if not _devtools_owner_trust(selected).get("trusted"):
        return {
            "status": "error",
            "detail": "The Amazon Music metadata listener owner changed",
            "source": "amazon_devtools",
            "port": selected,
        }

    cache_key = f"{selected}|{target.get('id')}|{_normalise_region(link_region)}"
    now = time.monotonic()
    if _CACHE["key"] == cache_key and now < float(cast(float, _CACHE["expires"])):
        cached = _CACHE["value"]
        return dict(cached) if isinstance(cached, dict) else cached  # type: ignore[return-value]

    try:
        with _CdpSocket(
            str(target["webSocketDebuggerUrl"]),
            expected_port=selected,
            expected_target_id=str(target["id"]),
        ) as client:
            response = client.request(
                "Runtime.evaluate",
                {
                    "expression": _TRANSPORT_EXPRESSION,
                    "returnByValue": True,
                    "awaitPromise": False,
                    "includeCommandLineAPI": False,
                    "userGesture": False,
                },
            )
        if response.get("error") or response.get("result", {}).get("exceptionDetails"):  # type: ignore[union-attr]
            raise RuntimeError("CDP evaluation failed")
        result = response.get("result", {}).get("result", {}).get("value")  # type: ignore[union-attr]
        track = _normalise_track_payload(result, link_region)
        track["port"] = selected
        if method:
            track["method"] = _clean(method, 64)
        elif _LAST_LAUNCH.get("port") == selected:
            track["method"] = _clean(_LAST_LAUNCH.get("method"), 64)
    except (ConnectionError, OSError, ValueError, KeyError, json.JSONDecodeError, RuntimeError, TypeError):
        track = {
            "status": "error",
            "detail": "Amazon Music did not return safe transport metadata",
            "source": "amazon_devtools",
            "port": selected,
        }
    _CACHE.update({"key": cache_key, "expires": now + 1.0, "value": dict(track)})
    return track


def _clear_cache() -> None:
    _CACHE.update({"key": None, "expires": 0.0, "value": None})


def apply_devtools_to_track(track: object, devtools: object) -> tuple[dict[str, object], bool]:
    merged = dict(track) if isinstance(track, dict) else {}
    if not isinstance(devtools, dict) or devtools.get("status") != "found":
        return merged, False
    changed = False
    for key in ("title", "artist", "album"):
        value = _clean(devtools.get(key), 512)
        if value and value != merged.get(key):
            merged[key] = value
            changed = True
    if devtools.get("position") is not None:
        merged["position"] = devtools["position"]
    if devtools.get("duration"):
        merged["duration"] = devtools["duration"]
    if devtools.get("playback_status") in {"playing", "paused"}:
        merged["status"] = devtools["playback_status"]
    if devtools.get("art_url"):
        merged["_amazon_art_url"] = devtools["art_url"]
    if devtools.get("track_link"):
        merged["_amazon_track_link"] = devtools["track_link"]
    return merged, changed


def _wait_for_page_target(
    port: int,
    timeout: float,
    installation: dict[str, object] | None = None,
) -> dict[str, object] | None:
    deadline = time.monotonic() + max(0.1, timeout)
    while time.monotonic() < deadline:
        if _devtools_owner_trust(port, installation).get("trusted"):
            target = _page_target(port, verify_owner=False)
            if target:
                return target
        time.sleep(0.25)
    return None


def _launch_process(installation: dict[str, object], arguments: list[str], popen=subprocess.Popen):
    executable = str(installation["executable"])
    return popen(
        [executable, *arguments],
        cwd=str(Path(executable).parent),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        start_new_session=True,
    )


def _terminate_failed_launch(process: object, installation: dict[str, object]) -> None:
    """Best-effort cleanup so a failed launch does not leave CDP exposed."""

    try:
        pid = int(getattr(process, "pid"))
    except (TypeError, ValueError, AttributeError):
        reset_devtools_port()
        return
    if _is_trusted_amazon_pid(pid, installation):
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    reset_devtools_port()


def launch_amazon_music_devtools(*, port: object = None, wait_timeout: float = 12.0) -> dict[str, object]:
    """Launch Amazon Music with CDP, or request an explicit restart if open."""

    global _DEVTOOLS_PORT
    installation = locate_amazon_music_app()
    if not installation:
        return {"ok": False, "status": "missing", "error": "The official Amazon Music app was not found"}
    if _running_amazon_pids(installation):
        selected = _valid_devtools_port(port if port is not None else get_devtools_port(False))
        if selected is None and port is None:
            selected = discover_devtools_port(installation)
        if selected and _page_target(selected):
            return {"ok": True, "status": "ready", "already_running": True, "port": selected}
        return {
            "ok": False,
            "status": "restart_required",
            "restart_required": True,
            "error": "Amazon Music must be restarted once to enable enhanced metadata",
        }
    try:
        selected, reservation = _reserve_devtools_port(port)
    except (RuntimeError, ValueError) as error:
        return {"ok": False, "status": "error", "error": str(error)}
    _DEVTOOLS_PORT = selected
    _clear_cache()
    reservation.close()
    try:
        process = _launch_process(
            installation,
            ["--remote-debugging-address=127.0.0.1", f"--remote-debugging-port={selected}"],
        )
    except (OSError, subprocess.SubprocessError):
        reset_devtools_port()
        return {"ok": False, "status": "error", "error": "Could not launch Amazon Music"}
    target = _wait_for_page_target(selected, wait_timeout, installation)
    if not target:
        _terminate_failed_launch(process, installation)
        return {
            "ok": False,
            "status": "error",
            "error": "Amazon Music did not expose a validated metadata page",
            "port": selected,
            "pid": int(process.pid),
        }
    owner = _devtools_owner_trust(selected, installation)
    if not owner.get("trusted"):
        _terminate_failed_launch(process, installation)
        return {
            "ok": False,
            "status": "error",
            "error": owner.get("detail", "The metadata listener could not be verified"),
            "port": selected,
        }
    _LAST_LAUNCH.clear()
    _LAST_LAUNCH.update({"port": selected, "pid": int(process.pid), "method": "direct-executable"})
    return {
        "ok": True,
        "status": "ready",
        "port": selected,
        "pid": int(process.pid),
        "method": "direct-executable",
        "owner": owner,
    }


def stop_amazon_music(*, timeout: float = 8.0) -> dict[str, object]:
    installation = locate_amazon_music_app()
    if not installation:
        return {"ok": False, "status": "missing", "error": "The official Amazon Music app was not found", "stopped": []}
    pids = _running_amazon_pids(installation, helpers=True)
    if not pids:
        return {"ok": True, "status": "stopped", "stopped": []}
    for pid in pids:
        if not _is_trusted_amazon_pid(pid, installation):
            continue
        try:
            os.kill(pid, signal.SIGTERM)
        except (OSError, ProcessLookupError):
            pass
    deadline = time.monotonic() + max(0.1, timeout)
    remaining = pids
    while remaining and time.monotonic() < deadline:
        time.sleep(0.1)
        remaining = [pid for pid in _running_amazon_pids(installation, helpers=True) if pid in pids]
    for pid in remaining:
        if not _is_trusted_amazon_pid(pid, installation):
            continue
        try:
            os.kill(pid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            pass
    _clear_cache()
    return {"ok": True, "status": "stopped", "stopped": pids, "forced": bool(remaining)}


def restart_amazon_music_devtools(*, wait_timeout: float = 12.0) -> dict[str, object]:
    stop_result = stop_amazon_music()
    if not stop_result.get("ok"):
        return stop_result
    reset_devtools_port()
    launch_result = launch_amazon_music_devtools(wait_timeout=wait_timeout)
    return {**launch_result, "stopped": stop_result.get("stopped", [])}


def disable_amazon_music_devtools(*, relaunch: bool = True) -> dict[str, object]:
    """Remove the listener by stopping Amazon Music, optionally reopening normally."""

    installation = locate_amazon_music_app()
    if not installation:
        return {"ok": False, "status": "missing", "error": "The official Amazon Music app was not found"}
    stop_result = stop_amazon_music()
    if not stop_result.get("ok"):
        return stop_result
    reset_devtools_port()
    _LAST_LAUNCH.clear()
    if not relaunch:
        return {"ok": True, "status": "stopped", "stopped": stop_result.get("stopped", [])}
    try:
        process = _launch_process(installation, [])
    except (OSError, subprocess.SubprocessError):
        return {"ok": False, "status": "error", "error": "Could not reopen Amazon Music without enhanced metadata"}
    return {
        "ok": True,
        "status": "disabled",
        "pid": int(process.pid),
        "stopped": stop_result.get("stopped", []),
    }
