# MIT License - Copyright (c) 2026 eripum9

import base64
import ctypes
import hashlib
import json
import os
import random
import re
import socket
import struct
import subprocess
import sys
import time
import uuid
from ctypes import wintypes
from urllib.parse import quote, urlparse, urlunparse
import requests
from config import load_config, normalize_amazon_music_link_region
from amazon_domains import AMAZON_MUSIC_HOSTS, AMAZON_WEBAPP_HOSTS, is_amazon_webapp_url
from launcher_diagnostics import format_launcher_failure, launcher_attempt_failure, launcher_candidate_label


APP_USER_MODEL_ID = "AmazonMobileLLC.AmazonMusic_kc6t79cpj4tp0!AmazonMobileLLC.AmazonMusic"
COMMON_DEVTOOLS_PORT = 9222
DEVTOOLS_PORT_ENV = "AMRPC_DEVTOOLS_PORT"
DEVTOOLS_PORT_MIN = 49152
DEVTOOLS_PORT_MAX = 60999
AMAZON_PACKAGE_NAME = "AmazonMobileLLC.AmazonMusic"
AMAZON_PACKAGE_PUBLISHER_ID = "kc6t79cpj4tp0"
AMAZON_EXECUTABLE_NAMES = frozenset({"amazon music.exe", "amazonmusic.exe"})
AMAZON_HELPER_EXECUTABLE_NAMES = frozenset({"amazon music helper.exe", "amazonmusichelper.exe"})
LAUNCH_FAILURE_HELP = "Could not launch Amazon Music with enhanced metadata. Open Diagnostics and check the Amazon Music launcher entry, or paste the launcher ID from Get-StartApps."
LAUNCH_READY_TIMEOUT_SECONDS = 45
PROCESS_STOP_TIMEOUT_SECONDS = 8
HELPER_SETTLE_SECONDS = 3
SHORTCUT_NAME = "Amazon Music Metadata.lnk"
OLD_SHORTCUT_NAMES = ("Amazon Music Beta Metadata.lnk",)
SHORTCUT_DIR_NAME = "Amazon Music RPC"
_CACHE = {"key": None, "expires": 0, "value": None}
_EXPLICIT_RE = re.compile(r"\s*\[Explicit\]\s*$", re.IGNORECASE)
_TIME_RE = re.compile(r"^-?\d{1,2}:\d{2}(?::\d{2})?$")
_ASIN_RE = re.compile(r"^[A-Z0-9]{10}$", re.IGNORECASE)
_DEVTOOLS_PAGE_PATH_RE = re.compile(r"^/devtools/page/([A-Za-z0-9._:-]+)$")
_STORE_PACKAGE_FULL_NAME_RE = re.compile(
    rf"^{re.escape(AMAZON_PACKAGE_NAME)}_\d+(?:\.\d+){{3}}_(?:x86|x64|arm|arm64|neutral)_[A-Za-z0-9]*_{re.escape(AMAZON_PACKAGE_PUBLISHER_ID)}$",
    re.IGNORECASE,
)
_DEVTOOLS_PORT = None
_LAST_LAUNCH = {}
_PORT_OWNER_CACHE = {"port": 0, "expires": 0.0, "value": None}


def _valid_devtools_port(value):
    try:
        port = int(value)
    except (TypeError, ValueError):
        return None
    if DEVTOOLS_PORT_MIN <= port <= DEVTOOLS_PORT_MAX:
        return port
    return None


def _is_local_port_open(port, timeout=0.15):
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def _pick_devtools_port():
    ports = list(range(DEVTOOLS_PORT_MIN, DEVTOOLS_PORT_MAX + 1))
    random.shuffle(ports)
    for port in ports:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind(("127.0.0.1", port))
                return port
            except OSError:
                pass
    raise RuntimeError("Could not find a free local metadata port")


def _reserve_devtools_port(port=None):
    ports = [int(port)] if port else list(range(DEVTOOLS_PORT_MIN, DEVTOOLS_PORT_MAX + 1))
    if not port:
        random.shuffle(ports)
    for candidate in ports:
        if not _valid_devtools_port(candidate):
            continue
        reservation = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            reservation.bind(("127.0.0.1", candidate))
            return candidate, reservation
        except OSError:
            reservation.close()
    raise RuntimeError("Could not reserve a free local metadata port")


def set_devtools_port(port):
    global _DEVTOOLS_PORT
    selected = _valid_devtools_port(port)
    if not selected:
        raise ValueError("Invalid DevTools port")
    _DEVTOOLS_PORT = selected
    _clear_cache()
    return _DEVTOOLS_PORT


def reset_devtools_port():
    global _DEVTOOLS_PORT
    _DEVTOOLS_PORT = None
    _clear_cache()


def get_devtools_port(create=True):
    global _DEVTOOLS_PORT
    if _DEVTOOLS_PORT is None:
        env_port = _valid_devtools_port(os.environ.get(DEVTOOLS_PORT_ENV))
        if env_port:
            _DEVTOOLS_PORT = env_port
    if _DEVTOOLS_PORT is None and create:
        _DEVTOOLS_PORT = _pick_devtools_port()
    return _DEVTOOLS_PORT


def devtools_environment(base_env=None):
    env = dict(base_env or os.environ)
    env[DEVTOOLS_PORT_ENV] = str(get_devtools_port(True))
    return env


def _clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _ps_literal(value):
    return "'" + str(value or "").replace("'", "''") + "'"


def _powershell_executable():
    windows_dir = os.environ.get("SystemRoot") or os.environ.get("WINDIR") or r"C:\Windows"
    candidates = [
        os.path.join(windows_dir, "System32", "WindowsPowerShell", "v1.0", "powershell.exe"),
        os.path.join(windows_dir, "Sysnative", "WindowsPowerShell", "v1.0", "powershell.exe"),
        os.path.join(windows_dir, "SysWOW64", "WindowsPowerShell", "v1.0", "powershell.exe"),
        "powershell.exe",
    ]
    for candidate in candidates:
        if os.path.isabs(candidate):
            if os.path.exists(candidate):
                return candidate
        else:
            return candidate
    return "powershell.exe"


def _run_powershell(script, timeout=8):
    return subprocess.run(
        [_powershell_executable(), "-NoProfile", "-Command", script],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        creationflags=0x08000000 if os.name == "nt" else 0,
    )


def _json_items(value):
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        return [value]
    return []


def _powershell_json(script, timeout=8):
    try:
        completed = _run_powershell(script, timeout)
    except Exception:
        return []
    if completed.returncode != 0:
        return []
    text = completed.stdout.strip()
    if not text:
        return []
    try:
        return _json_items(json.loads(text))
    except json.JSONDecodeError:
        return []


def _amazon_process_entries():
    script = rf"""
$storePattern = '\WindowsApps\{AMAZON_PACKAGE_NAME}_*__{AMAZON_PACKAGE_PUBLISHER_ID}\'
$desktopRoot = Join-Path $env:LOCALAPPDATA 'Amazon Music'
$items = @()
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | ForEach-Object {{
    $path = [string]$_.ExecutablePath
    $name = [string]$_.Name
    $parent = if ($path) {{ Split-Path -Parent $path }} else {{ '' }}
    $storeMatch = $path -and $path -like "*$storePattern*"
    $desktopMatch = $path -and $parent -and $parent.Equals($desktopRoot, [System.StringComparison]::OrdinalIgnoreCase)
    $mainMatch = $name -ieq 'Amazon Music.exe' -or $name -ieq 'AmazonMusic.exe'
    $helperMatch = $name -ieq 'Amazon Music Helper.exe' -or $name -ieq 'AmazonMusicHelper.exe'
    if (($storeMatch -or $desktopMatch) -and ($mainMatch -or $helperMatch)) {{
        $items += [PSCustomObject]@{{
            Pid = [int]$_.ProcessId
            ParentPid = [int]$_.ParentProcessId
            Name = $name
            Path = $path
            Kind = if ($helperMatch) {{ 'helper' }} else {{ 'main' }}
        }}
    }}
}}
$items | ConvertTo-Json -Compress
"""
    return _powershell_json(script, timeout=8)


def _process_id(entry):
    try:
        value = int(entry.get("Pid") or entry.get("ProcessId"))
    except (AttributeError, TypeError, ValueError):
        return 0
    return value if value > 0 else 0


def _is_helper_process(entry):
    kind = _clean(entry.get("Kind")).lower() if isinstance(entry, dict) else ""
    name = _clean(entry.get("Name")).lower() if isinstance(entry, dict) else ""
    return kind == "helper" or name in AMAZON_HELPER_EXECUTABLE_NAMES


def _is_main_process(entry):
    return bool(_process_id(entry)) and not _is_helper_process(entry)


def _store_package_full_names(entries):
    names = []
    seen = set()
    for entry in entries or []:
        path = _clean(entry.get("Path")) if isinstance(entry, dict) else ""
        for part in re.split(r"[\\/]", path):
            if not _STORE_PACKAGE_FULL_NAME_RE.fullmatch(part):
                continue
            key = part.lower()
            if key not in seen:
                names.append(part)
                seen.add(key)
            break
    return names


def _terminate_amazon_processes(entries, force=False):
    ids = sorted({_process_id(entry) for entry in entries if _process_id(entry)})
    if not ids:
        return {"ok": True, "stopped": [], "errors": []}
    id_list = ",".join(str(pid) for pid in ids)
    force_text = "$true" if force else "$false"
    script = rf"""
$ids = @({id_list})
$force = {force_text}
$storePattern = '\WindowsApps\{AMAZON_PACKAGE_NAME}_*__{AMAZON_PACKAGE_PUBLISHER_ID}\'
$desktopRoot = Join-Path $env:LOCALAPPDATA 'Amazon Music'
$results = @()
foreach ($id in $ids) {{
    try {{
        $item = Get-CimInstance Win32_Process -Filter "ProcessId=$id" -ErrorAction Stop
        $path = [string]$item.ExecutablePath
        $name = [string]$item.Name
        $parent = if ($path) {{ Split-Path -Parent $path }} else {{ '' }}
        $storeMatch = $path -and $path -like "*$storePattern*"
        $desktopMatch = $path -and $parent -and $parent.Equals($desktopRoot, [System.StringComparison]::OrdinalIgnoreCase)
        $nameMatch = $name -ieq 'Amazon Music.exe' -or $name -ieq 'AmazonMusic.exe' -or $name -ieq 'Amazon Music Helper.exe' -or $name -ieq 'AmazonMusicHelper.exe'
        if (-not (($storeMatch -or $desktopMatch) -and $nameMatch)) {{
            $results += [PSCustomObject]@{{ Pid = $id; Stopped = $false; Error = 'Process identity changed' }}
            continue
        }}
        $process = Get-Process -Id $id -ErrorAction Stop
        if ($force) {{
            Stop-Process -Id $id -Force -ErrorAction Stop
            $results += [PSCustomObject]@{{ Pid = $id; Stopped = $true; Error = '' }}
        }} else {{
            $closed = $process.CloseMainWindow()
            $results += [PSCustomObject]@{{ Pid = $id; Stopped = [bool]$closed; Error = '' }}
        }}
    }} catch {{
        $results += [PSCustomObject]@{{ Pid = $id; Stopped = $false; Error = [string]$_.Exception.Message }}
    }}
}}
$results | ConvertTo-Json -Compress
"""
    rows = _powershell_json(script, timeout=10)
    stopped = [str(_process_id(row)) for row in rows if row.get("Stopped") and _process_id(row)]
    errors = [_clean(row.get("Error")) for row in rows if row.get("Error")]
    return {"ok": not errors, "stopped": stopped, "errors": errors}


def stop_amazon_music(
    timeout=PROCESS_STOP_TIMEOUT_SECONDS,
    poll_interval=0.35,
    process_entries_fn=None,
    terminate_fn=None,
    sleep_fn=None,
):
    entries_fn = process_entries_fn or _amazon_process_entries
    stop_fn = terminate_fn or _terminate_amazon_processes
    sleeper = sleep_fn or time.sleep
    initial = entries_fn()
    if not initial:
        return {"ok": True, "stopped": [], "remaining": [], "errors": []}
    seen = {_process_id(entry) for entry in initial if _process_id(entry)}
    errors = []
    graceful = stop_fn(initial, False)
    errors.extend(graceful.get("errors", []))
    sleeper(min(1.2, max(0.0, timeout)))
    attempts = max(2, int(max(0.1, timeout) / max(0.05, poll_interval)))
    empty_polls = 0
    remaining = initial
    for _ in range(attempts):
        remaining = entries_fn()
        if not remaining:
            empty_polls += 1
            if empty_polls >= 2:
                return {
                    "ok": True,
                    "stopped": [str(pid) for pid in sorted(seen)],
                    "remaining": [],
                    "errors": errors,
                }
        else:
            empty_polls = 0
            seen.update(_process_id(entry) for entry in remaining if _process_id(entry))
            forced = stop_fn(remaining, True)
            errors.extend(forced.get("errors", []))
        sleeper(poll_interval)
    remaining = entries_fn()
    remaining_ids = [str(_process_id(entry)) for entry in remaining if _process_id(entry)]
    return {
        "ok": not remaining_ids,
        "stopped": [str(pid) for pid in sorted(seen) if str(pid) not in remaining_ids],
        "remaining": remaining_ids,
        "errors": errors,
        "error": "Amazon Music processes did not exit" if remaining_ids else "",
    }


def stop_amazon_music_for_restart(
    timeout=15,
    poll_interval=0.5,
    process_entries_fn=None,
    terminate_fn=None,
    sleep_fn=None,
):
    entries_fn = process_entries_fn or _amazon_process_entries
    stop_fn = terminate_fn or _terminate_amazon_processes
    sleeper = sleep_fn or time.sleep
    initial = entries_fn()
    mains = [entry for entry in initial if _is_main_process(entry)]
    helpers = [entry for entry in initial if _is_helper_process(entry)]
    helper_ids = [str(_process_id(entry)) for entry in helpers if _process_id(entry)]
    if not mains:
        return {
            "ok": True,
            "stopped": [],
            "remaining": [],
            "preserved_helpers": helper_ids,
            "errors": [],
        }
    main_ids = {_process_id(entry) for entry in mains if _process_id(entry)}
    roots = [
        entry
        for entry in mains
        if int(entry.get("ParentPid") or 0) not in main_ids
    ] or mains
    graceful = stop_fn(roots, False)
    errors = list(graceful.get("errors", []))
    attempts = max(2, int(max(0.1, timeout) / max(0.05, poll_interval)))
    empty_polls = 0
    for _ in range(attempts):
        remaining = [entry for entry in entries_fn() if _is_main_process(entry)]
        if not remaining:
            empty_polls += 1
            if empty_polls >= 2:
                return {
                    "ok": True,
                    "stopped": [str(pid) for pid in sorted(main_ids)],
                    "remaining": [],
                    "preserved_helpers": helper_ids,
                    "errors": errors,
                }
        else:
            empty_polls = 0
        sleeper(poll_interval)
    remaining = [entry for entry in entries_fn() if _is_main_process(entry)]
    remaining_ids = [str(_process_id(entry)) for entry in remaining if _process_id(entry)]
    return {
        "ok": False,
        "stopped": [str(pid) for pid in sorted(main_ids) if str(pid) not in remaining_ids],
        "remaining": remaining_ids,
        "preserved_helpers": helper_ids,
        "errors": errors,
        "error": "Amazon Music did not close cleanly. Close it normally, then try enhanced metadata again.",
    }


def stop_amazon_helpers(
    timeout=6,
    poll_interval=0.35,
    process_entries_fn=None,
    terminate_fn=None,
    sleep_fn=None,
):
    entries_fn = process_entries_fn or _amazon_process_entries
    stop_fn = terminate_fn or _terminate_amazon_processes
    sleeper = sleep_fn or time.sleep
    initial = [entry for entry in entries_fn() if _is_helper_process(entry)]
    if not initial:
        return {"ok": True, "stopped": [], "remaining": [], "errors": []}
    seen = {_process_id(entry) for entry in initial if _process_id(entry)}
    forced = stop_fn(initial, True)
    errors = list(forced.get("errors", []))
    attempts = max(2, int(max(0.1, timeout) / max(0.05, poll_interval)))
    empty_polls = 0
    for _ in range(attempts):
        remaining = [entry for entry in entries_fn() if _is_helper_process(entry)]
        if not remaining:
            empty_polls += 1
            if empty_polls >= 2:
                return {
                    "ok": True,
                    "stopped": [str(pid) for pid in sorted(seen)],
                    "remaining": [],
                    "errors": errors,
                }
        else:
            empty_polls = 0
            seen.update(_process_id(entry) for entry in remaining if _process_id(entry))
            retried = stop_fn(remaining, True)
            errors.extend(retried.get("errors", []))
        sleeper(poll_interval)
    remaining = [entry for entry in entries_fn() if _is_helper_process(entry)]
    remaining_ids = [str(_process_id(entry)) for entry in remaining if _process_id(entry)]
    return {
        "ok": not remaining_ids,
        "stopped": [str(pid) for pid in sorted(seen) if str(pid) not in remaining_ids],
        "remaining": remaining_ids,
        "errors": errors,
        "error": "Amazon Music Helper did not exit" if remaining_ids else "",
    }


def _prepare_amazon_launch(process_entries_fn=None, helper_stop_fn=None, package_stop_fn=None, sleep_fn=None):
    entries_fn = process_entries_fn or _amazon_process_entries
    sleeper = sleep_fn or time.sleep
    entries = entries_fn()
    mains = [entry for entry in entries if _is_main_process(entry)]
    if mains:
        return {
            "ok": False,
            "error": "Amazon Music is already running without enhanced metadata. Close it or use metadata restart repair before launching it again.",
            "main_processes": [str(_process_id(entry)) for entry in mains],
        }
    helpers = [entry for entry in entries if _is_helper_process(entry)]
    helper_ids = [str(_process_id(entry)) for entry in helpers if _process_id(entry)]
    if not helpers:
        return {"ok": True, "stale_helpers": [], "retired_helpers": []}
    package_names = _store_package_full_names(helpers)
    if package_names and package_stop_fn is None:
        cleanup = stop_amazon_store_packages(package_names, process_entries_fn=entries_fn)
    elif package_names:
        cleanup = package_stop_fn(package_names)
    elif helper_stop_fn is None:
        cleanup = stop_amazon_helpers(process_entries_fn=entries_fn)
    else:
        cleanup = helper_stop_fn()
    if not cleanup.get("ok"):
        return {
            "ok": False,
            "error": "Amazon Music Helper could not be prepared for enhanced metadata. End it in Task Manager and try again.",
            "stale_helpers": helper_ids,
            "retired_helpers": cleanup.get("stopped", []),
            "cleanup": cleanup,
        }
    sleeper(HELPER_SETTLE_SECONDS)
    return {
        "ok": True,
        "stale_helpers": helper_ids,
        "retired_helpers": cleanup.get("stopped", helper_ids),
        "reset_packages": cleanup.get("packages", []),
        "cleanup": cleanup,
    }


def _looks_like_path(value):
    text = _clean(value)
    return bool(
        text
        and (
            os.path.isabs(text)
            or text.lower().endswith(".exe")
            or "\\" in text
            or "/" in text
        )
    )


def _looks_like_aumid(value):
    text = _clean(value)
    if _looks_like_path(text) or text.count("!") != 1:
        return False
    family, app_id = text.split("!", 1)
    return bool(family.strip() and app_id.strip())


def _is_local_absolute_path(value):
    text = _clean(value)
    return bool(os.path.isabs(text) and not text.startswith(("\\\\", "//")))


def _is_allowed_amazon_exe(path, exists_fn=os.path.exists):
    text = _clean(path)
    if not text or not _is_local_absolute_path(text) or not text.lower().endswith(".exe"):
        return False
    if not exists_fn(text):
        return False
    normalised = os.path.normpath(text)
    if os.path.basename(normalised).casefold() not in AMAZON_EXECUTABLE_NAMES:
        return False
    parent = os.path.basename(os.path.dirname(normalised)).casefold()
    package_prefix = f"{AMAZON_PACKAGE_NAME.casefold()}_"
    package_suffix = f"__{AMAZON_PACKAGE_PUBLISHER_ID}"
    package_path = any(
        part.casefold().startswith(package_prefix) and part.casefold().endswith(package_suffix)
        for part in normalised.replace("/", "\\").split("\\")
    )
    return parent in {"amazon music", "amazonmusic"} or package_path


def _is_exact_amazon_package_exe(path, exists_fn=os.path.exists):
    text = _clean(path)
    if not text or not _is_local_absolute_path(text) or not exists_fn(text):
        return False
    normalised = os.path.normpath(text)
    if os.path.basename(normalised).casefold() not in AMAZON_EXECUTABLE_NAMES:
        return False
    package_prefix = f"{AMAZON_PACKAGE_NAME.casefold()}_"
    package_suffix = f"__{AMAZON_PACKAGE_PUBLISHER_ID}"
    return any(
        part.casefold().startswith(package_prefix) and part.casefold().endswith(package_suffix)
        for part in normalised.replace("/", "\\").split("\\")
    )


def validate_launcher_override(value, exists_fn=os.path.exists):
    text = _clean(value)
    if not text:
        return ""
    if _looks_like_path(text) and not _is_allowed_amazon_exe(text, exists_fn):
        raise ValueError("Executable launcher overrides must point to an existing local Amazon Music .exe.")
    if not _looks_like_path(text) and not _looks_like_aumid(text):
        raise ValueError("Launcher IDs must use the PackageFamily!Application format shown by Get-StartApps.")
    return text


def _launcher_candidate(kind, value, method, source):
    text = _clean(value)
    if not text:
        return None
    return {"kind": kind, "value": text, "method": method, "source": source}


def _launcher_candidate_from_value(value, aumid_method, exe_method, source, exists_fn=os.path.exists):
    text = _clean(value)
    if not text:
        return None
    if _looks_like_path(text):
        return _launcher_candidate("exe", text, exe_method, source) if _is_allowed_amazon_exe(text, exists_fn) else None
    return _launcher_candidate("aumid", text, aumid_method, source) if _looks_like_aumid(text) else None


def _build_aumid(package_family, app_id):
    family = _clean(package_family)
    app = _clean(app_id)
    return f"{family}!{app}" if family and app else ""


def _start_app_candidates(entries, exists_fn=os.path.exists):
    candidates = []
    for entry in _json_items(entries):
        name = _clean(entry.get("Name"))
        app_id = _clean(entry.get("AppID") or entry.get("AppId"))
        lower_name = name.lower()
        if not app_id or "amazon music" not in lower_name or "rpc" in lower_name:
            continue
        candidate = _launcher_candidate_from_value(app_id, "auto-aumid", "auto-exe", "start-apps", exists_fn)
        if candidate:
            candidates.append(candidate)
    return candidates


def _appx_aumid_candidates(entries):
    candidates = []
    for entry in _json_items(entries):
        aumid = _build_aumid(
            entry.get("PackageFamilyName") or entry.get("packageFamilyName"),
            entry.get("AppId") or entry.get("Id") or entry.get("appId"),
        )
        if aumid:
            candidates.append(_launcher_candidate("aumid", aumid, "auto-aumid", "appx-manifest"))
    return [candidate for candidate in candidates if candidate]


def _dedupe_launcher_candidates(candidates):
    seen = set()
    unique = []
    for candidate in candidates:
        if not candidate:
            continue
        key = (candidate.get("kind"), candidate.get("value", "").lower())
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def _configured_launcher_override():
    try:
        return _clean(load_config().get("amazon_music_launcher_override", ""))
    except Exception:
        return ""


def _get_start_app_entries():
    script = """
$items = @(Get-StartApps | Where-Object {
    $_.Name -eq 'Amazon Music' -or ($_.Name -like '*Amazon Music*' -and $_.Name -notlike '*RPC*')
} | Select-Object Name, AppID)
$items | ConvertTo-Json -Compress
"""
    return _powershell_json(script)


def _get_appx_application_entries():
    script = """
$items = @()
Get-AppxPackage *AmazonMusic* | ForEach-Object {
    $pkg = $_
    try {
        $manifest = Get-AppxPackageManifest -Package $pkg.PackageFullName
        foreach ($app in @($manifest.Package.Applications.Application)) {
            $items += [PSCustomObject]@{
                PackageFamilyName = $pkg.PackageFamilyName
                AppId = $app.Id
            }
        }
    } catch {}
}
$items | ConvertTo-Json -Compress
"""
    return _powershell_json(script, timeout=10)


def _launcher_candidates(launcher_override=None, start_apps=None, appx_apps=None, exists_fn=os.path.exists):
    override = _configured_launcher_override() if launcher_override is None else _clean(launcher_override)
    candidates = []
    if override:
        candidates.append(_launcher_candidate_from_value(override, "override-aumid", "override-exe", "override", exists_fn))
    start_entries = _get_start_app_entries() if start_apps is None else start_apps
    appx_entries = _get_appx_application_entries() if appx_apps is None else appx_apps
    candidates.extend(_start_app_candidates(start_entries, exists_fn))
    candidates.extend(_appx_aumid_candidates(appx_entries))
    candidates.append(_launcher_candidate("aumid", APP_USER_MODEL_ID, "hardcoded-store", "hardcoded"))
    return _dedupe_launcher_candidates(candidates)


def amazon_music_launcher_candidates(launcher_override=None):
    return _launcher_candidates(launcher_override)


def _wait_for_page_target(port, timeout=9):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _page_target(port=port):
            return True
        time.sleep(0.35)
    return False


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]

    @classmethod
    def from_string(cls, value):
        return cls.from_buffer_copy(uuid.UUID(value).bytes_le)


def _activate_aumid_native(app_id, args):
    if os.name != "nt":
        raise OSError("Native application activation is only available on Windows")
    ole32 = ctypes.windll.ole32
    ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    ole32.CoInitializeEx.restype = ctypes.c_long
    ole32.CoCreateInstance.argtypes = [
        ctypes.POINTER(_GUID),
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_GUID),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    ole32.CoCreateInstance.restype = ctypes.c_long
    ole32.CoUninitialize.argtypes = []
    ole32.CoUninitialize.restype = None
    clsid = _GUID.from_string("45BA127D-10A8-46EA-8AB7-56EA9078943C")
    iid = _GUID.from_string("2E941141-7F97-4756-BA1D-9DECDE894A3D")
    instance = ctypes.c_void_p()
    coinit_hr = ole32.CoInitializeEx(None, 0x2)
    should_uninitialize = coinit_hr >= 0
    if coinit_hr < 0 and coinit_hr != -2147417850:
        raise OSError(f"CoInitializeEx failed: 0x{coinit_hr & 0xFFFFFFFF:08X}")
    try:
        hr = ole32.CoCreateInstance(
            ctypes.byref(clsid),
            None,
            0x1,
            ctypes.byref(iid),
            ctypes.byref(instance),
        )
        if hr < 0 or not instance.value:
            raise OSError(f"CoCreateInstance failed: 0x{hr & 0xFFFFFFFF:08X}")
        interface = ctypes.cast(instance, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))
        activate = ctypes.WINFUNCTYPE(
            ctypes.c_long,
            ctypes.c_void_p,
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        )(interface.contents[3])
        process_id = wintypes.DWORD()
        hr = activate(instance, app_id, args, 0, ctypes.byref(process_id))
        if hr < 0:
            raise OSError(f"ActivateApplication failed: 0x{hr & 0xFFFFFFFF:08X}")
        return int(process_id.value)
    finally:
        if instance.value:
            interface = ctypes.cast(instance, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))
            release = ctypes.WINFUNCTYPE(wintypes.ULONG, ctypes.c_void_p)(interface.contents[2])
            release(instance)
        if should_uninitialize:
            ole32.CoUninitialize()


def _terminate_store_package_native(package_full_name):
    if os.name != "nt":
        raise OSError("Package lifecycle control is only available on Windows")
    if not _STORE_PACKAGE_FULL_NAME_RE.fullmatch(_clean(package_full_name)):
        raise ValueError("Amazon Music package identity was invalid")
    ole32 = ctypes.windll.ole32
    ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    ole32.CoInitializeEx.restype = ctypes.c_long
    ole32.CoCreateInstance.argtypes = [
        ctypes.POINTER(_GUID),
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_GUID),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    ole32.CoCreateInstance.restype = ctypes.c_long
    ole32.CoUninitialize.argtypes = []
    ole32.CoUninitialize.restype = None
    clsid = _GUID.from_string("B1AEC16F-2383-4852-B0E9-8F0B1DC66B4D")
    iid = _GUID.from_string("F27C3930-8029-4AD1-94E3-3DBA417810C1")
    instance = ctypes.c_void_p()
    coinit_hr = ole32.CoInitializeEx(None, 0x2)
    should_uninitialize = coinit_hr >= 0
    if coinit_hr < 0 and coinit_hr != -2147417850:
        raise OSError(f"CoInitializeEx failed: 0x{coinit_hr & 0xFFFFFFFF:08X}")
    try:
        hr = ole32.CoCreateInstance(
            ctypes.byref(clsid),
            None,
            0x1,
            ctypes.byref(iid),
            ctypes.byref(instance),
        )
        if hr < 0 or not instance.value:
            raise OSError(f"CoCreateInstance failed: 0x{hr & 0xFFFFFFFF:08X}")
        interface = ctypes.cast(instance, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))
        terminate = ctypes.WINFUNCTYPE(
            ctypes.c_long,
            ctypes.c_void_p,
            wintypes.LPCWSTR,
        )(interface.contents[7])
        hr = terminate(instance, package_full_name)
        if hr < 0:
            raise OSError(f"TerminateAllProcesses failed: 0x{hr & 0xFFFFFFFF:08X}")
    finally:
        if instance.value:
            interface = ctypes.cast(instance, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))
            release = ctypes.WINFUNCTYPE(wintypes.ULONG, ctypes.c_void_p)(interface.contents[2])
            release(instance)
        if should_uninitialize:
            ole32.CoUninitialize()


def stop_amazon_store_packages(
    package_full_names,
    timeout=8,
    poll_interval=0.35,
    process_entries_fn=None,
    terminate_package_fn=None,
    sleep_fn=None,
):
    entries_fn = process_entries_fn or _amazon_process_entries
    terminate_fn = terminate_package_fn or _terminate_store_package_native
    sleeper = sleep_fn or time.sleep
    packages = []
    seen_packages = set()
    for value in package_full_names or []:
        name = _clean(value)
        key = name.lower()
        if _STORE_PACKAGE_FULL_NAME_RE.fullmatch(name) and key not in seen_packages:
            packages.append(name)
            seen_packages.add(key)
    if not packages:
        return {
            "ok": False,
            "stopped": [],
            "remaining": [],
            "packages": [],
            "errors": ["Amazon Music package identity was unavailable"],
            "error": "Amazon Music package identity was unavailable",
        }
    initial = entries_fn()
    seen = {_process_id(entry) for entry in initial if _process_id(entry)}
    errors = []
    for package in packages:
        try:
            terminate_fn(package)
        except Exception as error:
            errors.append(_clean(error))
    if errors:
        return {
            "ok": False,
            "stopped": [],
            "remaining": [str(pid) for pid in sorted(seen)],
            "packages": packages,
            "errors": errors,
            "error": "Windows could not reset the Amazon Music package lifecycle",
        }
    attempts = max(2, int(max(0.1, timeout) / max(0.05, poll_interval)))
    empty_polls = 0
    remaining = initial
    for _ in range(attempts):
        remaining = entries_fn()
        if not remaining:
            empty_polls += 1
            if empty_polls >= 2:
                return {
                    "ok": True,
                    "stopped": [str(pid) for pid in sorted(seen)],
                    "remaining": [],
                    "packages": packages,
                    "errors": [],
                }
        else:
            empty_polls = 0
            seen.update(_process_id(entry) for entry in remaining if _process_id(entry))
        sleeper(poll_interval)
    remaining_ids = [str(_process_id(entry)) for entry in remaining if _process_id(entry)]
    return {
        "ok": False,
        "stopped": [str(pid) for pid in sorted(seen) if str(pid) not in remaining_ids],
        "remaining": remaining_ids,
        "packages": packages,
        "errors": [],
        "error": "Amazon Music package processes did not exit",
    }


def _launch_aumid(app_id, port):
    args = f"--remote-debugging-port={port}"
    script = f"""
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
[AppActivator]::Activate({_ps_literal(app_id)}, {_ps_literal(args)})
"""
    try:
        pid = _activate_aumid_native(app_id, args)
        return {"ok": True, "pid": str(pid), "activation": "native"}
    except Exception as error:
        native_error = _clean(error)
    try:
        completed = _run_powershell(script, 15)
    except Exception as error:
        return {
            "ok": False,
            "error": f"Native activation failed: {native_error}; PowerShell activation failed: {_clean(error)}",
        }
    if completed.returncode != 0:
        powershell_error = _clean(completed.stderr) or "Could not launch Amazon Music"
        return {
            "ok": False,
            "error": f"Native activation failed: {native_error}; PowerShell activation failed: {powershell_error}",
        }
    pid = ""
    for line in reversed(completed.stdout.splitlines()):
        value = _clean(line)
        if value.isdigit() and int(value) > 0:
            pid = value
            break
    return {"ok": True, "pid": pid, "activation": "powershell-fallback"}


def _launch_exe(path, port):
    if not _is_allowed_amazon_exe(path):
        return {"ok": False, "error": "Launcher path must point to an existing local Amazon Music .exe"}
    try:
        proc = subprocess.Popen(
            [path, f"--remote-debugging-port={port}"],
            cwd=os.path.dirname(path) or None,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=0x08000000 if os.name == "nt" else 0,
        )
        return {"ok": True, "pid": str(proc.pid)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _launch_candidate(candidate, port):
    if candidate.get("kind") == "exe":
        return _launch_exe(candidate.get("value", ""), port)
    return _launch_aumid(candidate.get("value", ""), port)


def _candidate_label(candidate):
    return launcher_candidate_label(candidate)


def _attempt_failure(candidate, error):
    return launcher_attempt_failure(candidate, error)


def _format_launcher_failure(attempts):
    return format_launcher_failure(attempts, LAUNCH_FAILURE_HELP)


def _remember_launch(method, launcher, port, pid="", owner=None):
    _LAST_LAUNCH.clear()
    _LAST_LAUNCH.update({"method": method, "launcher": launcher, "port": port, "pid": str(pid or ""), "owner": owner or {}})


def _clean_label(value):
    return _EXPLICIT_RE.sub("", _clean(value)).strip()


def _clean_asin(value):
    text = _clean(value).upper()
    return text if _ASIN_RE.match(text) else ""


def _music_host(value):
    host = _clean(value).lower()
    return host if host in AMAZON_MUSIC_HOSTS else "music.amazon.com"


def _amazon_music_link_host(region=None):
    return f"music.amazon.{normalize_amazon_music_link_region(region)}"


def amazon_music_search_link(title, artist, link_region=None):
    host = _amazon_music_link_host(link_region)
    query = " ".join(part for part in (_clean(title), _clean(artist)) if part)
    return f"https://{host}/search/{quote(query, safe='')}" if query else ""


def _normalise_amazon_link(url, host):
    parsed = urlparse(url)
    if is_amazon_webapp_url(url) and host in AMAZON_MUSIC_HOSTS:
        return urlunparse(parsed._replace(netloc=host))
    return ""


def _amazon_track_link(payload, title, artist, link_region=None):
    host = _amazon_music_link_host(link_region)
    track_asin = _clean_asin(payload.get("track_asin"))
    if track_asin:
        return f"https://{host}/tracks/{track_asin}"

    search_link = amazon_music_search_link(title, artist, link_region)
    if search_link:
        return search_link

    direct_link = _clean(payload.get("track_link"))
    if direct_link:
        normalised = _normalise_amazon_link(direct_link, host)
        if normalised:
            return normalised

    return ""


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


def _normalise_track_payload(payload, link_region=None):
    if not isinstance(payload, dict):
        return {"status": "no_match", "detail": "No Amazon Music metadata payload"}
    if payload.get("status") != "found":
        return {
            "status": payload.get("status") or "no_match",
            "detail": payload.get("detail") or "No Amazon Music metadata found",
            "source": "amazon_devtools",
        }

    title = _clean_label(payload.get("title"))
    artist = _clean(payload.get("artist"))
    album = _clean_label(payload.get("album"))
    secondary = _clean(payload.get("secondary"))
    if secondary and (not artist or not album):
        if " • " in secondary:
            left, right = secondary.split(" • ", 1)
            artist = artist or _clean(left)
            album = album or _clean_label(right)
        elif not artist:
            artist = secondary

    position = _parse_time(payload.get("position_text"))
    remaining = _parse_time(payload.get("remaining_text"))
    duration = 0
    if position is not None and remaining is not None and remaining < 0:
        duration = max(0, position + abs(remaining))

    playback_status = _clean(payload.get("playback_status"))
    if playback_status not in {"playing", "paused"}:
        playback_status = "playing"

    if not title or not artist:
        return {
            "status": "no_match",
            "detail": "Amazon Music transport metadata was incomplete",
            "source": "amazon_devtools",
        }

    return {
        "status": "found",
        "detail": "Amazon Music metadata found",
        "source": "amazon_devtools",
        "title": title,
        "artist": artist,
        "album": album,
        "art_url": _clean(payload.get("art_url")),
        "track_link": _amazon_track_link(payload, title, artist, link_region),
        "position": position,
        "duration": duration,
        "playback_status": playback_status,
        "confidence": 98,
    }


def _http_json(path, timeout=1.5, port=None):
    selected_port = port or get_devtools_port(False)
    if not selected_port:
        raise ConnectionError("No enhanced metadata port selected")
    response = requests.get(f"http://127.0.0.1:{selected_port}{path}", timeout=timeout)
    response.raise_for_status()
    if len(getattr(response, "content", b"") or b"") > 1024 * 1024:
        raise ValueError("Enhanced metadata response exceeded 1 MiB")
    return response.json()


def _is_amazon_music_target(target):
    if not isinstance(target, dict) or target.get("type") != "page":
        return False
    title = _clean(target.get("title")).lower()
    parsed = urlparse(_clean(target.get("url")))
    host = (parsed.hostname or "").lower()
    path = parsed.path or ""
    try:
        port = parsed.port
    except ValueError:
        return False
    if (
        parsed.scheme != "https"
        or host not in AMAZON_WEBAPP_HOSTS
        or port not in (None, 443)
        or parsed.username
        or parsed.password
    ):
        return False
    if "morpho/webapp" in path and title.startswith("amazon music"):
        return True
    return host in AMAZON_MUSIC_HOSTS and title == "amazon music"


def _valid_target_websocket(target, port):
    if not isinstance(target, dict):
        return False
    try:
        selected_port = int(port)
    except (TypeError, ValueError):
        return False
    parsed = urlparse(_clean(target.get("webSocketDebuggerUrl")))
    try:
        parsed_port = parsed.port
    except ValueError:
        return False
    match = _DEVTOOLS_PAGE_PATH_RE.fullmatch(parsed.path or "")
    return bool(
        parsed.scheme == "ws"
        and (parsed.hostname or "").lower() in {"127.0.0.1", "localhost", "::1"}
        and parsed_port == selected_port
        and not parsed.username
        and not parsed.password
        and not parsed.query
        and not parsed.fragment
        and match
        and match.group(1) == _clean(target.get("id"))
    )


def _port_owner_entries(port):
    script = f"""
$items = @()
try {{
    Get-NetTCPConnection -State Listen -LocalPort {int(port)} -ErrorAction Stop | ForEach-Object {{
        $owner = $_.OwningProcess
        $current = $owner
        $names = @()
        $paths = @()
        $pids = @()
        for ($depth = 0; $depth -lt 6 -and $current -gt 0; $depth++) {{
            $process = Get-CimInstance Win32_Process -Filter "ProcessId=$current" -ErrorAction SilentlyContinue
            if (-not $process) {{ break }}
            $pids += $process.ProcessId
            $names += $process.Name
            $paths += $process.ExecutablePath
            if ($process.ParentProcessId -eq $current) {{ break }}
            $current = $process.ParentProcessId
        }}
        $items += [PSCustomObject]@{{
            Pid = $owner
            Pids = @($pids)
            Names = @($names)
            Paths = @($paths)
        }}
    }}
}} catch {{}}
$items | ConvertTo-Json -Compress
"""
    return _powershell_json(script, timeout=4)


def _entry_values(entry, plural, singular):
    value = entry.get(plural)
    if isinstance(value, list):
        return [_clean(item) for item in value if _clean(item)]
    if value:
        return [_clean(value)]
    value = _clean(entry.get(singular))
    return [value] if value else []


def _amazon_owner_entry(entry, launched_pid="", launcher="", registered_launchers=()):
    paths = _entry_values(entry, "Paths", "Path")
    trusted_launchers = {
        os.path.normcase(os.path.normpath(value))
        for value in (launcher, *registered_launchers)
        if _looks_like_path(value) and _is_allowed_amazon_exe(value)
    }
    for path in paths:
        if os.path.normcase(os.path.normpath(path)) in trusted_launchers:
            return True
        if _is_exact_amazon_package_exe(path):
            return True
    return False


def _devtools_owner_trust(port, launched_pid="", launcher="", force=False):
    now = time.time()
    if not force and _PORT_OWNER_CACHE["port"] == int(port) and now < _PORT_OWNER_CACHE["expires"]:
        return _PORT_OWNER_CACHE["value"]
    entries = _port_owner_entries(port)
    remembered_launcher = _LAST_LAUNCH.get("launcher", "")
    registered_launchers = []
    if not launcher and not remembered_launcher:
        registered_launchers = [
            candidate.get("value", "")
            for candidate in _launcher_candidates()
            if candidate.get("kind") == "exe"
        ]
    if not entries:
        result = {"trusted": False, "status": "unavailable", "detail": "Windows could not verify the enhanced metadata listener owner"}
    elif all(_amazon_owner_entry(entry, launched_pid, launcher or remembered_launcher, registered_launchers) for entry in entries):
        result = {"trusted": True, "status": "verified", "detail": "Enhanced metadata listener belongs to Amazon Music", "pids": [_clean(entry.get("Pid")) for entry in entries]}
    else:
        result = {"trusted": False, "status": "rejected", "detail": "The selected enhanced metadata port is owned by a non-Amazon process", "pids": [_clean(entry.get("Pid")) for entry in entries]}
    _PORT_OWNER_CACHE.update({"port": int(port), "expires": now + 10, "value": result})
    return result


def _page_target(port=None):
    try:
        targets = _http_json("/json/list", port=port)
    except Exception:
        return None
    if not isinstance(targets, list):
        return None
    for target in targets:
        if _is_amazon_music_target(target) and _valid_target_websocket(target, port or get_devtools_port(False)):
            return target
    return None


class _CdpSocket:
    def __init__(self, websocket_url, timeout=2, expected_port=None, expected_target_id=""):
        self._id = 0
        parsed = urlparse(websocket_url)
        selected_port = expected_port or get_devtools_port(False)
        target = {"id": expected_target_id, "webSocketDebuggerUrl": websocket_url}
        if not selected_port or not _valid_target_websocket(target, selected_port):
            raise ConnectionError("DevTools websocket endpoint did not match the trusted loopback target")
        self._host = parsed.hostname
        self._port = parsed.port
        self._path = parsed.path
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
        accept = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii"), usedforsecurity=False).digest()).decode("ascii")
        if accept.encode("ascii") not in response:
            raise ConnectionError("DevTools websocket accept key did not match")

    def _send_frame(self, payload, opcode=1):
        data = payload if isinstance(payload, bytes) else payload.encode("utf-8")
        header = bytearray([0x80 | opcode])
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
                self._send_frame(payload, opcode=10)
                continue
            if opcode == 10:
                continue
            if opcode != 1:
                continue
            message = json.loads(payload.decode("utf-8", errors="replace"))
            if message.get("id") == request_id:
                return message


_BOOT_STATE_EXPRESSION = r"""
(() => {
  const transport = document.querySelector('#transportContainer.hasTrackLoaded') || document.querySelector('#transportContainer') || document.querySelector('#transport');
  const splash = document.querySelector('.splashScreen');
  let splashVisible = false;
  if (splash) {
    const style = getComputedStyle(splash);
    const rect = splash.getBoundingClientRect();
    const opacity = Number.parseFloat(style.opacity || '1');
    splashVisible = style.display !== 'none' && style.visibility !== 'hidden' && (!Number.isFinite(opacity) || opacity > 0) && rect.width > 0 && rect.height > 0;
  }
  return {
    readyState: document.readyState,
    transport: Boolean(transport),
    splashVisible,
    bodyChildren: document.body ? document.body.children.length : 0
  };
})()
"""


def _page_boot_state(port):
    target = _page_target(port=port)
    if not target:
        return {"ready": False, "status": "target-missing", "detail": "Enhanced metadata page was not available"}
    client = None
    try:
        client = _CdpSocket(
            target["webSocketDebuggerUrl"],
            expected_port=port,
            expected_target_id=target.get("id", ""),
        )
        response = client.request(
            "Runtime.evaluate",
            {"expression": _BOOT_STATE_EXPRESSION, "returnByValue": True},
        )
        value = response.get("result", {}).get("result", {}).get("value")
        if not isinstance(value, dict):
            return {"ready": False, "status": "unknown", "detail": "Amazon Music startup state was unavailable"}
        transport = bool(value.get("transport"))
        splash_visible = bool(value.get("splashVisible"))
        document_ready = value.get("readyState") == "complete"
        body_ready = int(value.get("bodyChildren") or 0) > 0
        ready = transport or (document_ready and body_ready and not splash_visible)
        return {
            "ready": ready,
            "status": "ready" if ready else "loading",
            "detail": "Amazon Music interface is ready" if ready else "Amazon Music remained on its loading screen",
            "transport": transport,
            "splash_visible": splash_visible,
        }
    except Exception as error:
        return {"ready": False, "status": "error", "detail": _clean(error)}
    finally:
        if client:
            client.close()


def _wait_for_app_ready(
    port,
    timeout=LAUNCH_READY_TIMEOUT_SECONDS,
    poll_interval=0.5,
    boot_state_fn=None,
    sleep_fn=None,
):
    state_fn = boot_state_fn or _page_boot_state
    sleeper = sleep_fn or time.sleep
    attempts = max(1, int(max(0.1, timeout) / max(0.05, poll_interval)))
    state = {"ready": False, "status": "loading", "detail": "Amazon Music is loading"}
    for _ in range(attempts):
        state = state_fn(port)
        if state.get("ready"):
            return {"ok": True, **state}
        sleeper(poll_interval)
    return {"ok": False, **state, "detail": "Amazon Music remained on its loading screen"}


_TRANSPORT_EXPRESSION = r"""
(async () => {
  const clean = (value) => String(value || '').replace(/\s+/g, ' ').trim();
  const asin = (value) => {
    const text = clean(value).toUpperCase();
    return /^[A-Z0-9]{10}$/.test(text) ? text : '';
  };
  const musicHost = () => {
    const host = location.hostname.replace(/^www\./, 'music.').toLowerCase();
    const allowed = new Set(__AMAZON_MUSIC_HOSTS__);
    return allowed.has(host) ? host : 'music.amazon.com';
  };
  const albumAsinFromLocation = () => {
    const text = `${location.hash || ''} ${location.search || ''}`;
    const match = text.match(/\/album\/detail\/([A-Z0-9]{10})/i) || text.match(/[?&](?:asin|id)=([A-Z0-9]{10})/i);
    return match ? asin(match[1]) : '';
  };
  const queueTrackAsin = async () => {
    try {
      const openDb = (name) => new Promise((resolve, reject) => {
        const request = indexedDB.open(name);
        request.onerror = () => reject(request.error);
        request.onsuccess = () => resolve(request.result);
      });
      const getAll = (store) => new Promise((resolve, reject) => {
        const request = store.getAll();
        request.onerror = () => reject(request.error);
        request.onsuccess = () => resolve(request.result || []);
      });
      const db = await openDb('amplify-datastore');
      try {
        if (!db.objectStoreNames.contains('user_DevicePlaybackState') || !db.objectStoreNames.contains('user_QueueSequenceSlice')) {
          return '';
        }
        const transaction = db.transaction(['user_DevicePlaybackState', 'user_QueueSequenceSlice'], 'readonly');
        const states = await getAll(transaction.objectStore('user_DevicePlaybackState'));
        const active = states.find((state) => state.playbackState === 'PLAYING') || states.find((state) => state.playbackState === 'PAUSED') || states[0];
        const reference = asin(active && active.deviceCurrentPlaybackState && active.deviceCurrentPlaybackState.referenceId);
        if (reference) {
          return reference;
        }
        const queueId = active && active.queueId;
        const sequenceName = active && active.sequenceName;
        const sequenceVersion = active && active.sequenceVersion;
        if (!queueId) {
          return '';
        }
        const slices = (await getAll(transaction.objectStore('user_QueueSequenceSlice')))
          .filter((slice) => slice.queueId === queueId && (!sequenceName || slice.sequenceName === sequenceName) && (!sequenceVersion || slice.sequenceVersion === sequenceVersion))
          .sort((left, right) => (left.sliceOrdinal || 0) - (right.sliceOrdinal || 0));
        const firstReference = slices.flatMap((slice) => slice.entityReferences || []).map((item) => asin(item.identifier)).find(Boolean);
        return firstReference || '';
      } finally {
        db.close();
      }
    } catch (_) {
      return '';
    }
  };
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
  const playPause = root.querySelector('button.playPause');
  const playPauseMarkup = playPause ? playPause.innerHTML : '';
  let playbackStatus = '';
  if (/#pause|svg-icon--pause/i.test(playPauseMarkup)) {
    playbackStatus = 'playing';
  } else if (/#play|svg-icon--play/i.test(playPauseMarkup)) {
    playbackStatus = 'paused';
  }
  const title = clean((titleEl && (titleEl.getAttribute('title') || titleEl.innerText || titleEl.textContent)) || '');
  const secondary = clean((secondaryEl && (secondaryEl.getAttribute('title') || secondaryEl.innerText || secondaryEl.textContent)) || '');
  const trackAsin = await queueTrackAsin();
  return {
    status: title && (secondaryParts[0] || secondary) ? 'found' : 'no_match',
    detail: title ? 'Amazon Music transport found' : 'Amazon Music transport had no title',
    title,
    artist: secondaryParts[0] || '',
    album: secondaryParts[1] || '',
    secondary,
    art_url: img ? img.src : '',
    track_link: titleLink ? titleLink.href : '',
    track_asin: trackAsin,
    album_asin: albumAsinFromLocation(),
    music_host: musicHost(),
    page_url: location.href,
    position_text: positionEl ? clean(positionEl.innerText || positionEl.textContent) : '',
    remaining_text: remainingEl ? clean(remainingEl.innerText || remainingEl.textContent) : '',
    playback_status: playbackStatus
  };
})()
"""
_TRANSPORT_EXPRESSION = _TRANSPORT_EXPRESSION.replace(
    "__AMAZON_MUSIC_HOSTS__",
    json.dumps(sorted(AMAZON_MUSIC_HOSTS)),
)


def _selected_devtools_port(port=None):
    if port is None:
        return get_devtools_port(True)
    try:
        selected = int(port)
    except (TypeError, ValueError):
        return get_devtools_port(True)
    if 0 < selected < 65536:
        return selected
    return get_devtools_port(True)


def get_devtools_track_sync(link_region=None, port=None, method=""):
    port = _selected_devtools_port(port)
    unexpected_warning = ""
    if port != COMMON_DEVTOOLS_PORT and _is_local_port_open(COMMON_DEVTOOLS_PORT):
        unexpected_warning = f"Common DevTools port {COMMON_DEVTOOLS_PORT} is reachable and ignored"
    target = _page_target(port=port)
    if not target:
        payload = {
            "status": "unavailable",
            "detail": "Amazon Music is not running with enhanced metadata enabled",
            "source": "amazon_devtools",
            "port": port,
        }
        if method:
            payload["method"] = method
        if unexpected_warning:
            payload["warning"] = unexpected_warning
        return payload
    owner = _devtools_owner_trust(port, _LAST_LAUNCH.get("pid", ""))
    if not owner.get("trusted"):
        return {
            "status": "error",
            "detail": owner.get("detail"),
            "source": "amazon_devtools",
            "port": port,
            "owner": owner,
        }
    cache_key = f"{port}|{target.get('id')}|{normalize_amazon_music_link_region(link_region)}"
    now = time.time()
    if _CACHE["key"] == cache_key and now < _CACHE["expires"]:
        return _CACHE["value"]
    client = None
    try:
        client = _CdpSocket(target["webSocketDebuggerUrl"], expected_port=port, expected_target_id=target.get("id", ""))
        response = client.request("Runtime.evaluate", {
            "expression": _TRANSPORT_EXPRESSION,
            "returnByValue": True,
            "awaitPromise": True,
            "timeout": 3000,
        })
        result = response.get("result", {}).get("result", {}).get("value")
        track = _normalise_track_payload(result, link_region)
        track["port"] = port
        if method:
            track["method"] = method
        elif _LAST_LAUNCH.get("port") == port:
            track["method"] = _LAST_LAUNCH.get("method", "")
            track["launcher"] = _LAST_LAUNCH.get("launcher", "")
        if unexpected_warning:
            track["warning"] = unexpected_warning
    except Exception as e:
        track = {"status": "error", "detail": str(e), "source": "amazon_devtools", "port": port}
        if method:
            track["method"] = method
        if unexpected_warning:
            track["warning"] = unexpected_warning
        track["owner"] = owner
    finally:
        if client:
            client.close()
    _CACHE["key"] = cache_key
    _CACHE["expires"] = now + 1.5
    _CACHE["value"] = track
    return track


def _clear_cache():
    _CACHE["key"] = None
    _CACHE["expires"] = 0
    _CACHE["value"] = None


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
    playback_status = _clean(devtools.get("playback_status"))
    if position is not None:
        merged["position"] = position
    if duration:
        merged["duration"] = duration
    if playback_status in {"playing", "paused"}:
        merged["status"] = playback_status
    elif not merged.get("status"):
        merged["status"] = "playing"
    if devtools.get("art_url"):
        merged["_amazon_art_url"] = devtools.get("art_url")
    if devtools.get("track_link"):
        merged["_amazon_track_link"] = devtools.get("track_link")
    return merged, changed


def launch_amazon_music_devtools(launcher_override=None):
    port = get_devtools_port(True)
    if _is_local_port_open(port):
        if _page_target(port=port):
            owner = _devtools_owner_trust(port, force=True)
            if not owner.get("trusted"):
                return {"ok": False, "error": owner.get("detail"), "port": port, "owner": owner}
            readiness = _wait_for_app_ready(port, timeout=8)
            if not readiness.get("ok"):
                return {
                    "ok": False,
                    "error": readiness.get("detail"),
                    "port": port,
                    "owner": owner,
                    "readiness": readiness,
                }
            _remember_launch("existing", "", port, owner=owner)
            return {
                "ok": True,
                "pid": "",
                "port": port,
                "already_running": True,
                "method": "existing",
                "owner": owner,
                "readiness": readiness,
            }
        if _valid_devtools_port(os.environ.get(DEVTOOLS_PORT_ENV)) == port:
            return {"ok": False, "error": f"Shared metadata port {port} is already in use", "port": port}
        for _ in range(8):
            reset_devtools_port()
            port = get_devtools_port(True)
            if not _is_local_port_open(port):
                break
        else:
            return {"ok": False, "error": "Could not find a free local metadata port"}
    preparation = _prepare_amazon_launch()
    if not preparation.get("ok"):
        return {"ok": False, "error": preparation.get("error"), "port": port, "preparation": preparation}
    try:
        port, reservation = _reserve_devtools_port(port)
    except RuntimeError:
        reset_devtools_port()
        try:
            port, reservation = _reserve_devtools_port()
            set_devtools_port(port)
        except RuntimeError as error:
            return {"ok": False, "error": str(error)}
    attempts = []
    try:
        candidates = _launcher_candidates(launcher_override)
    finally:
        reservation.close()
    for candidate in candidates:
        result = _launch_candidate(candidate, port)
        if result.get("ok"):
            if _wait_for_page_target(port):
                owner = _devtools_owner_trust(
                    port,
                    result.get("pid", ""),
                    candidate.get("value", ""),
                    force=True,
                )
                if not owner.get("trusted"):
                    attempts.append(f"{_candidate_label(candidate)}: {owner.get('detail')}")
                    cleanup = stop_amazon_music(timeout=6)
                    return {
                        "ok": False,
                        "error": _format_launcher_failure(attempts),
                        "port": port,
                        "attempts": attempts,
                        "cleanup": cleanup,
                    }
                readiness = _wait_for_app_ready(port)
                if not readiness.get("ok"):
                    attempts.append(f"{_candidate_label(candidate)}: Amazon Music remained on its loading screen")
                    cleanup = stop_amazon_music(timeout=6)
                    _clear_cache()
                    return {
                        "ok": False,
                        "error": _format_launcher_failure(attempts),
                        "port": port,
                        "attempts": attempts,
                        "cleanup": cleanup,
                        "readiness": readiness,
                    }
                _remember_launch(candidate.get("method", ""), candidate.get("value", ""), port, result.get("pid", ""), owner)
                return {
                    "ok": True,
                    "pid": result.get("pid", ""),
                    "port": port,
                    "method": candidate.get("method", ""),
                    "launcher": candidate.get("value", ""),
                    "owner": owner,
                    "activation": result.get("activation", ""),
                    "preparation": preparation,
                    "readiness": readiness,
                }
            attempts.append(f"{_candidate_label(candidate)}: metadata target did not appear")
            cleanup = stop_amazon_music(timeout=6)
            if not cleanup.get("ok"):
                return {
                    "ok": False,
                    "error": f"{_format_launcher_failure(attempts)} Failed launch cleanup did not finish.",
                    "port": port,
                    "attempts": attempts,
                    "cleanup": cleanup,
                }
        else:
            attempts.append(_attempt_failure(candidate, result.get("error", "")))
    return {"ok": False, "error": _format_launcher_failure(attempts), "port": port, "attempts": attempts}


def amazon_music_is_running():
    script = rf"""
$package = '{AMAZON_PACKAGE_NAME}'
$targets = @(Get-Process | Where-Object {{
    $path = ""
    try {{ $path = $_.Path }} catch {{ }}
    $_.MainWindowHandle -ne 0 -and
    (($path -and $path -like "*$package*") -or
    ($_.ProcessName -eq "AmazonMusic") -or
    ($_.ProcessName -eq "Amazon Music")) -and
    ($_.ProcessName -ne "Amazon Music Helper")
}})
if ($targets.Count -gt 0) {{ "true" }} else {{ "false" }}
"""
    try:
        completed = _run_powershell(script, 5)
    except Exception:
        return False
    return completed.returncode == 0 and _clean(completed.stdout).lower() == "true"


def restart_amazon_music_devtools():
    package_names = _store_package_full_names(_amazon_process_entries())
    stop_result = stop_amazon_music_for_restart()
    if not stop_result.get("ok"):
        return stop_result
    if package_names:
        cleanup_result = stop_amazon_store_packages(package_names)
    else:
        cleanup_result = stop_amazon_helpers()
    if not cleanup_result.get("ok"):
        return cleanup_result
    _clear_cache()
    time.sleep(HELPER_SETTLE_SECONDS)
    launch_result = launch_amazon_music_devtools()
    return {
        **launch_result,
        "stopped": stop_result.get("stopped", []),
        "retired_helpers": cleanup_result.get("stopped", []),
        "reset_packages": cleanup_result.get("packages", []),
    }


def _start_menu_shortcut_path():
    appdata = os.environ.get("APPDATA", "")
    if not appdata:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), SHORTCUT_NAME)
    return os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs", SHORTCUT_DIR_NAME, SHORTCUT_NAME)


def _legacy_start_menu_shortcut_paths():
    appdata = os.environ.get("APPDATA", "")
    if not appdata:
        base = os.path.dirname(os.path.abspath(__file__))
    else:
        base = os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs", SHORTCUT_DIR_NAME)
    return [os.path.join(base, name) for name in OLD_SHORTCUT_NAMES]


def _shortcut_launcher_command():
    if getattr(sys, "frozen", False):
        target = sys.executable
        arguments = "--launch-amazon-devtools"
        working_dir = os.path.dirname(sys.executable)
        icon_path = sys.executable
    else:
        target = sys.executable
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")
        arguments = f'"{script}" --launch-amazon-devtools'
        working_dir = os.path.dirname(script)
        icon_path = os.path.join(working_dir, "icon.ico")
    return target, arguments, working_dir, icon_path


def amazon_devtools_launcher_state():
    path = _start_menu_shortcut_path()
    return {"installed": os.path.exists(path), "path": path}


def install_amazon_devtools_launcher():
    path = _start_menu_shortcut_path()
    target, arguments, working_dir, icon_path = _shortcut_launcher_command()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    for legacy_path in _legacy_start_menu_shortcut_paths():
        try:
            if os.path.exists(legacy_path):
                os.remove(legacy_path)
        except OSError:
            pass
    script = f"""
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut({_ps_literal(path)})
$shortcut.TargetPath = {_ps_literal(target)}
$shortcut.Arguments = {_ps_literal(arguments)}
$shortcut.WorkingDirectory = {_ps_literal(working_dir)}
$shortcut.IconLocation = {_ps_literal(icon_path)}
$shortcut.Save()
"""
    try:
        completed = _run_powershell(script, 15)
    except Exception as e:
        return {"ok": False, "error": str(e), **amazon_devtools_launcher_state()}
    if completed.returncode != 0:
        return {"ok": False, "error": _clean(completed.stderr) or "Could not create launcher shortcut", **amazon_devtools_launcher_state()}
    return {"ok": True, **amazon_devtools_launcher_state()}


def remove_amazon_devtools_launcher():
    path = _start_menu_shortcut_path()
    try:
        for shortcut_path in [path, *_legacy_start_menu_shortcut_paths()]:
            if os.path.exists(shortcut_path):
                os.remove(shortcut_path)
        parent = os.path.dirname(path)
        if os.path.isdir(parent) and not os.listdir(parent):
            os.rmdir(parent)
        return {"ok": True, **amazon_devtools_launcher_state()}
    except Exception as e:
        return {"ok": False, "error": str(e), **amazon_devtools_launcher_state()}
