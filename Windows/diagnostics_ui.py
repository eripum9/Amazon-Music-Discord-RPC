# MIT License - Copyright (c) 2026 eripum9
import base64
import json
import os
import platform
import sys
import time
import webbrowser
import zipfile
from datetime import datetime
import webview
from config import load_config, load_config_for_update, save_config, CONFIG_DIR, CONFIG_PATH, APP_VERSION, redact_data, redact_text
from status_summary import metadata_source_summary

if getattr(sys, 'frozen', False):
    _BUNDLE_DIR = sys._MEIPASS
else:
    _BUNDLE_DIR = os.path.dirname(os.path.abspath(__file__))

ICON_PATH = os.path.join(_BUNDLE_DIR, "icon.png")
LOG_PATH = os.path.join(CONFIG_DIR, "console.log")
DIAGNOSTICS_PATH = os.path.join(CONFIG_DIR, "diagnostics.json")
ISSUES_URL = "https://github.com/eripum9/Amazon-Music-Discord-RPC/issues"


def _icon_b64():
    if os.path.exists(ICON_PATH):
        with open(ICON_PATH, "rb") as f:
            return base64.b64encode(f.read()).decode()
    return ""


def _bounded_int(value, default, minimum):
    try:
        return max(minimum, int(value))
    except (TypeError, ValueError):
        return default


def _save_window_size(width, height):
    try:
        config = load_config_for_update()
    except Exception as e:
        print(f"[Diagnostics] Could not save window size: {e}")
        return
    config["diagnostics_window_width"] = _bounded_int(width, 940, 700)
    config["diagnostics_window_height"] = _bounded_int(height, 700, 520)
    save_config(config)


def _read_state():
    try:
        with open(DIAGNOSTICS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _log_files():
    files = []
    candidates = [("console.log", LOG_PATH)]
    for index in range(1, 6):
        candidates.append((f"console.{index}.log", os.path.join(CONFIG_DIR, f"console.{index}.log")))
    for label, path in candidates:
        if os.path.exists(path):
            try:
                size = os.path.getsize(path)
                modified = os.path.getmtime(path)
            except OSError:
                size = 0
                modified = 0
            files.append({"label": label, "path": path, "size": size, "modified": modified})
    if not files:
        files.append({"label": "console.log", "path": LOG_PATH, "size": 0, "modified": 0})
    return files


def _log_path_for(label):
    for item in _log_files():
        if item["label"] == label:
            return item["path"]
    return LOG_PATH


def _notification_access():
    try:
        from winsdk.windows.ui.notifications.management import (
            UserNotificationListener,
            UserNotificationListenerAccessStatus,
        )
        access = UserNotificationListener.current.get_access_status()
        if access == UserNotificationListenerAccessStatus.ALLOWED:
            return {"value": "Allowed", "state": "good"}
        if access == UserNotificationListenerAccessStatus.DENIED:
            return {"value": "Denied", "state": "bad"}
        name = str(access).split(".")[-1].replace("_", " ").title()
        return {"value": name or "Not requested", "state": "warn"}
    except Exception as e:
        return {"value": "Unavailable", "state": "bad", "detail": str(e)}


def _age_text(updated_at):
    if not updated_at:
        return "No data"
    age = max(0, int(time.time() - updated_at))
    if age < 2:
        return "Just now"
    if age < 60:
        return f"{age}s ago"
    minutes = age // 60
    if minutes < 60:
        return f"{minutes}m ago"
    return f"{minutes // 60}h ago"


def _scrobble_label(status):
    return {
        "active": "Active",
        "disabled": "Off",
        "not_authenticated": "Needs auth",
        "missing_token": "Missing token",
        "error": "Error",
    }.get(status, "Unknown")


def _amazify_state(state):
    compat = state.get("amazify") if isinstance(state.get("amazify"), dict) else {}
    if compat:
        return compat
    try:
        from amazify_compat import amazify_compat_state
        return amazify_compat_state(APP_VERSION)
    except Exception as e:
        return {"installed": False, "error": str(e)}


def _amazify_card(state):
    compat = _amazify_state(state)
    if compat.get("error"):
        return {"label": "Amazify", "value": "Error", "detail": compat.get("error"), "state": "bad"}
    if not compat.get("installed"):
        return {"label": "Amazify", "value": "Not installed", "detail": "Shared in-app UI disabled", "state": "muted"}
    parts = []
    if compat.get("plugin_enabled"):
        parts.append("plugin enabled")
    elif compat.get("plugin_installed"):
        parts.append("plugin installed")
    else:
        parts.append("plugin missing")
    bridge_port = compat.get("rpc_bridge_port")
    if bridge_port:
        parts.append(f"bridge {bridge_port}")
    devtools_port = compat.get("devtools_port")
    if devtools_port:
        parts.append(f"DevTools {devtools_port}")
    if compat.get("running"):
        parts.append("running")
    if compat.get("plugin_enabled") and compat.get("devtools_port"):
        return {"label": "Amazify", "value": "Connected", "detail": " · ".join(parts), "state": "good"}
    if compat.get("plugin_enabled"):
        parts.append("waiting for Amazify")
        return {"label": "Amazify", "value": "Ready", "detail": " · ".join(parts), "state": "muted"}
    return {"label": "Amazify", "value": "Needs setup", "detail": " · ".join(parts), "state": "warn"}


def _report_system_info():
    return {
        "app_version": APP_VERSION,
        "python": sys.version,
        "platform": platform.platform(),
        "frozen": bool(getattr(sys, "frozen", False)),
        "config_path": CONFIG_PATH,
        "diagnostics_path": DIAGNOSTICS_PATH,
        "log_path": LOG_PATH,
    }


def _report_launcher_candidates(config):
    try:
        from amazon_devtools import amazon_music_launcher_candidates
        return amazon_music_launcher_candidates(config.get("amazon_music_launcher_override", ""))
    except Exception as e:
        return [{"error": str(e)}]


def _write_diagnostics_report(path, include_tests=True):
    config = load_config()
    state = _read_state()
    report = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "system": _report_system_info(),
        "source_summary": metadata_source_summary(state, config),
        "notification_access": _notification_access(),
        "launcher_candidates": _report_launcher_candidates(config),
    }
    if include_tests:
        try:
            from self_tests import run_self_tests
            report["self_tests"] = run_self_tests(CONFIG_DIR, DIAGNOSTICS_PATH)
        except Exception as e:
            report["self_tests"] = [{"name": "Self-tests", "status": "fail", "detail": str(e)}]
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("report.json", json.dumps(redact_data(report, config), indent=2))
        archive.writestr("config.redacted.json", json.dumps(redact_data(config, config), indent=2))
        archive.writestr("diagnostics.redacted.json", json.dumps(redact_data(state, config), indent=2))
        for item in _log_files():
            log_path = item.get("path", "")
            label = os.path.basename(item.get("label", "") or os.path.basename(log_path) or "console.log")
            try:
                if os.path.exists(log_path):
                    size = os.path.getsize(log_path)
                    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                        if size > 1000000:
                            f.seek(max(0, size - 1000000))
                        content = f.read()
                else:
                    content = ""
                archive.writestr(f"logs/{label}", redact_text(content, config))
            except Exception as e:
                archive.writestr(f"logs/{label}.error.txt", redact_text(str(e), config))
    return path


def _build_cards(state, config, access):
    updated_at = state.get("updated_at")
    stale = not updated_at or time.time() - updated_at > 12
    track = state.get("track")
    scrobbling = state.get("scrobbling") or {}
    rpc_detail = state.get("last_error") or _age_text(updated_at)
    cards = []

    if not state:
        cards.append({"label": "RPC", "value": "No data", "detail": "Start the app to populate diagnostics", "state": "bad"})
    elif state.get("rpc_status") == "stopped":
        cards.append({"label": "RPC", "value": "Stopped", "detail": rpc_detail, "state": "muted"})
    elif stale:
        cards.append({"label": "RPC", "value": "Stale", "detail": rpc_detail, "state": "warn"})
    else:
        cards.append({"label": "RPC", "value": "Running", "detail": rpc_detail, "state": "good"})

    discord_status = state.get("discord_status", "unknown")
    if discord_status == "connected" and not stale:
        cards.append({"label": "Discord", "value": "Connected", "detail": f"Client {state.get('client_id', '')}", "state": "good"})
    elif discord_status == "retrying":
        cards.append({"label": "Discord", "value": "Retrying", "detail": "Waiting for Discord IPC", "state": "warn"})
    else:
        cards.append({"label": "Discord", "value": "Unknown", "detail": "No recent connection signal", "state": "muted"})

    if track:
        status = track.get("status") or "unknown"
        title = track.get("title") or "Unknown title"
        card_state = "good" if status == "playing" else "warn" if status == "paused" else "muted"
        cards.append({"label": "Amazon Music", "value": status.title(), "detail": title, "state": card_state})
    else:
        cards.append({"label": "Amazon Music", "value": "Not detected", "detail": "No active Amazon Music session found", "state": "bad" if state and not stale else "muted"})

    source = metadata_source_summary(state, config)
    cards.append({"label": "Source", "value": source["label"], "detail": source["detail"], "state": source["state"]})

    if config.get("notification_enrichment_enabled"):
        detail = access.get("detail") or "Notification fallback enabled"
        cards.append({"label": "Notifications", "value": access["value"], "detail": detail, "state": access["state"]})
    else:
        cards.append({"label": "Notifications", "value": "Off", "detail": "Notification fallback disabled", "state": "muted"})

    amazon_devtools = state.get("amazon_devtools") or {}
    if config.get("amazon_devtools_enabled"):
        devtools_status = amazon_devtools.get("status") or "waiting"
        devtools_warning = amazon_devtools.get("warning") or ""
        if devtools_status == "found":
            value = "Found"
            detail = amazon_devtools.get("title") or amazon_devtools.get("detail") or "Amazon Music metadata available"
            card_state = "good"
        elif devtools_status == "launching":
            value = "Launching"
            detail = amazon_devtools.get("detail") or "Amazon Music is starting for metadata"
            card_state = "warn"
        elif devtools_status == "restarting":
            value = "Restarting"
            detail = amazon_devtools.get("detail") or "Amazon Music is restarting for metadata"
            card_state = "warn"
        elif devtools_status in ("error", "unavailable"):
            value = "Unavailable"
            detail = amazon_devtools.get("detail") or "Amazon Music metadata failed"
            card_state = "bad"
        else:
            value = "Waiting"
            detail = amazon_devtools.get("detail") or "Waiting for Amazon Music metadata"
            card_state = "warn"
        if devtools_warning:
            detail = devtools_warning
            if card_state == "good":
                card_state = "warn"
        if amazon_devtools.get("method"):
            detail = f"{detail} ({amazon_devtools.get('method')})"
        cards.append({"label": "Amazon Metadata", "value": value, "detail": detail, "state": card_state})
    else:
        cards.append({"label": "Amazon Metadata", "value": "Off", "detail": "Enhanced metadata disabled", "state": "muted"})

    cards.append(_amazify_card(state))

    privacy = state.get("privacy") or {}
    if privacy.get("hidden"):
        cards.append({"label": "Privacy", "value": "Hiding", "detail": privacy.get("reason") or "Current activity hidden", "state": "warn"})
    elif config.get("privacy_private_session"):
        cards.append({"label": "Privacy", "value": "Private", "detail": "Private session enabled", "state": "warn"})
    elif config.get("privacy_blocked_keywords"):
        cards.append({"label": "Privacy", "value": "Enabled", "detail": "Keyword filters active", "state": "good"})
    else:
        cards.append({"label": "Privacy", "value": "Standard", "detail": "No privacy filters active", "state": "muted"})

    if state.get("album_art_url"):
        cards.append({"label": "Artwork", "value": "Found", "detail": state.get("album_name") or "Album art ready", "state": "good"})
    elif track:
        cards.append({"label": "Artwork", "value": "Missing", "detail": "No artwork URL for current track", "state": "warn"})
    else:
        cards.append({"label": "Artwork", "value": "Waiting", "detail": "No current track", "state": "muted"})

    lastfm = scrobbling.get("lastfm", "disabled")
    listenbrainz = scrobbling.get("listenbrainz", "disabled")
    enabled = [s for s in (lastfm, listenbrainz) if s != "disabled"]
    if not enabled:
        cards.append({"label": "Scrobbling", "value": "Off", "detail": "Last.fm and ListenBrainz disabled", "state": "muted"})
    elif all(s == "active" for s in enabled):
        cards.append({"label": "Scrobbling", "value": "Active", "detail": f"Last.fm {_scrobble_label(lastfm)}, ListenBrainz {_scrobble_label(listenbrainz)}", "state": "good"})
    else:
        bad = any(s == "error" for s in enabled)
        cards.append({"label": "Scrobbling", "value": "Needs attention", "detail": f"Last.fm {_scrobble_label(lastfm)}, ListenBrainz {_scrobble_label(listenbrainz)}", "state": "bad" if bad else "warn"})

    return cards


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
  * { box-sizing: border-box; }
  html, body { margin: 0; min-height: 100%; background: #202020; color: #e4e4e4; }
  body {
    font-family: 'Segoe UI Variable', 'Segoe UI', sans-serif;
    padding: 24px;
    user-select: none;
    overflow: hidden;
  }
  button {
    font-family: inherit;
    border: 1px solid #4a4a4a;
    background: #383838;
    color: #e4e4e4;
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
  }
  button:hover { border-color: #5865f2; background: #404040; }
  select {
    appearance: none;
    -webkit-appearance: none;
    background: #383838;
    color: #e4e4e4;
    border: 1px solid #4a4a4a;
    border-radius: 6px;
    padding: 7px 30px 7px 10px;
    font-size: 12px;
    font-family: inherit;
    outline: none;
  }
  select:hover { border-color: #5865f2; }
  .primary-action {
    background: #5865f2;
    border-color: #5865f2;
    color: #fff;
  }
  .primary-action:hover { background: #4752c4; }
  .shell {
    height: calc(100vh - 48px);
    display: flex;
    flex-direction: column;
    gap: 16px;
    min-width: 0;
  }
  .header {
    display: flex;
    align-items: center;
    gap: 14px;
    flex: 0 0 auto;
  }
  .header img {
    width: 46px;
    height: 46px;
    border-radius: 10px;
  }
  .title h1 {
    font-size: 20px;
    line-height: 1.2;
    margin: 0;
    color: #fff;
    font-weight: 600;
  }
  .title p {
    margin: 2px 0 0;
    color: #999;
    font-size: 12px;
  }
  .actions {
    margin-left: auto;
    display: flex;
    gap: 8px;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(160px, 1fr));
    gap: 10px;
    flex: 0 0 auto;
  }
  .card {
    background: #2d2d2d;
    border: 1px solid #3d3d3d;
    border-radius: 8px;
    padding: 14px;
    min-width: 0;
  }
  .card-label {
    color: #999;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0;
  }
  .card-value {
    margin-top: 6px;
    display: flex;
    align-items: center;
    gap: 8px;
    color: #fff;
    font-size: 16px;
    font-weight: 650;
    min-width: 0;
  }
  .card-detail {
    margin-top: 5px;
    color: #aaa;
    font-size: 12px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .dot {
    width: 9px;
    height: 9px;
    border-radius: 50%;
    flex: 0 0 auto;
    background: #777;
  }
  .good .dot { background: #43b581; }
  .warn .dot { background: #faa61a; }
  .bad .dot { background: #f04747; }
  .muted .dot { background: #666; }
  .track-row {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 12px;
    align-items: center;
    background: #2d2d2d;
    border: 1px solid #3d3d3d;
    border-radius: 8px;
    padding: 14px 16px;
    flex: 0 0 auto;
    min-width: 0;
  }
  .track-title {
    color: #fff;
    font-size: 15px;
    font-weight: 650;
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }
  .track-meta {
    margin-top: 3px;
    color: #999;
    font-size: 12px;
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }
  .paths {
    color: #999;
    font-size: 11px;
    text-align: right;
    line-height: 1.5;
    white-space: pre-line;
  }
  .main {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: auto minmax(0, 1fr);
    min-height: 0;
    flex: 1 1 auto;
    gap: 12px;
  }
  .tests-card {
    display: none;
    background: #2d2d2d;
    border: 1px solid #3d3d3d;
    border-radius: 8px;
    overflow: hidden;
    min-height: 0;
  }
  .tests-card.visible {
    display: flex;
    flex-direction: column;
  }
  .tests-head {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 12px;
    border-bottom: 1px solid #3d3d3d;
    background: #252525;
  }
  .tests-title {
    color: #fff;
    font-size: 12px;
    font-weight: 650;
  }
  .tests-results {
    padding: 12px;
    display: grid;
    gap: 8px;
    overflow: auto;
  }
  .dev-actions {
    display: grid;
    grid-template-columns: repeat(3, minmax(140px, 1fr));
    gap: 8px;
    padding: 12px;
    border-bottom: 1px solid #3d3d3d;
  }
  .dev-action-note {
    grid-column: 1 / -1;
    color: #999;
    font-size: 11px;
  }
  .test-result {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 10px;
    align-items: start;
    background: #383838;
    border: 1px solid #4a4a4a;
    border-radius: 8px;
    padding: 10px 12px;
  }
  .test-name {
    color: #fff;
    font-size: 13px;
    font-weight: 650;
  }
  .test-detail {
    color: #aaa;
    font-size: 11px;
    margin-top: 2px;
  }
  .test-pass .dot { background: #43b581; }
  .test-fail .dot { background: #f04747; }
  .log-card {
    min-height: 0;
    display: flex;
    flex-direction: column;
    background: #181818;
    border: 1px solid #3d3d3d;
    border-radius: 8px;
    overflow: hidden;
  }
  .log-head {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 12px;
    background: #252525;
    border-bottom: 1px solid #3d3d3d;
    flex: 0 0 auto;
  }
  .log-title {
    font-size: 12px;
    font-weight: 650;
    color: #fff;
  }
  .log-status {
    margin-left: auto;
    color: #888;
    font-size: 11px;
  }
  #log {
    margin: 0;
    padding: 12px;
    flex: 1 1 auto;
    min-height: 0;
    overflow: auto;
    color: #cfcfcf;
    font: 12px/1.45 Consolas, 'Cascadia Mono', monospace;
    white-space: pre-wrap;
    user-select: text;
  }
  .modal-overlay {
    position: fixed;
    inset: 0;
    z-index: 30;
    display: none;
    align-items: center;
    justify-content: center;
    padding: 24px;
    background: rgba(18, 18, 18, 0.86);
    backdrop-filter: blur(16px);
  }
  .modal-overlay.visible { display: flex; }
  .modal {
    width: min(460px, 100%);
    background: #2d2d2d;
    border: 1px solid #4a4a4a;
    border-radius: 10px;
    padding: 22px;
    box-shadow: 0 24px 70px rgba(0, 0, 0, 0.35);
  }
  .modal-title {
    color: #fff;
    font-size: 18px;
    font-weight: 650;
    margin-bottom: 8px;
  }
  .modal-copy {
    color: #bbb;
    font-size: 13px;
    line-height: 1.5;
    margin-bottom: 16px;
  }
  .modal-check {
    display: flex;
    align-items: center;
    gap: 8px;
    color: #bbb;
    font-size: 12px;
    margin-bottom: 18px;
  }
  .modal-actions {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
  }
  ::-webkit-scrollbar { width: 8px; height: 8px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: #555; border-radius: 4px; }
  @media (max-width: 760px) {
    body { padding: 16px; overflow: auto; }
    .shell { height: auto; min-height: calc(100vh - 32px); }
    .grid { grid-template-columns: 1fr; }
    .track-row { grid-template-columns: 1fr; }
    .paths { text-align: left; }
    .actions { flex-wrap: wrap; justify-content: flex-end; }
    .main { min-height: 360px; }
  }
</style>
</head>
<body>
<div class="shell">
  <div class="header">
    <img src="data:image/png;base64,{icon_b64}" alt="icon">
    <div class="title">
      <h1>Diagnostics</h1>
      <p>Amazon Music RPC v{version}</p>
    </div>
    <div class="actions">
      <button onclick="refreshNow()">Refresh</button>
      <button onclick="exportReport()">Export Report</button>
      <button onclick="openTests()">Tests</button>
      <button onclick="pywebview.api.open_report_issue()">Report Issue</button>
      <button id="pauseBtn" onclick="togglePause()">Pause Log</button>
      <button onclick="pywebview.api.close_window()">Close</button>
    </div>
  </div>

  <div class="grid" id="cards"></div>

  <div class="track-row">
    <div>
      <div class="track-title" id="trackTitle">No current track</div>
      <div class="track-meta" id="trackMeta">Waiting for Amazon Music</div>
    </div>
    <div class="paths" id="paths"></div>
  </div>

  <div class="main">
    <div class="tests-card" id="testsCard">
      <div class="tests-head">
        <span class="tests-title">Development Tests</span>
        <button class="primary-action" onclick="runTests()">Run Tests</button>
        <button onclick="hideTests()">Hide</button>
      </div>
      <div class="dev-actions">
        <button onclick="resetIntroFlag()">Reset Intro</button>
        <button onclick="resetTestsWarning()">Reset Tests Warning</button>
        <button onclick="clearPrivateSession()">Clear Private Session</button>
        <div class="dev-action-note" id="devActionStatus">Use these only while testing local behavior.</div>
      </div>
      <div class="tests-results" id="testsResults"></div>
    </div>
    <div class="log-card">
      <div class="log-head">
        <span class="log-title">Console</span>
        <select id="logSelect" onchange="changeLogFile()"></select>
        <span class="log-status" id="logStatus">Loading</span>
      </div>
      <pre id="log"></pre>
    </div>
  </div>
</div>

<div class="modal-overlay" id="testsWarning">
  <div class="modal">
    <div class="modal-title">Development Area</div>
    <div class="modal-copy">this is meant for development and should not be used by a normal user, only interact with this if you KNOW WHAT YOU ARE DOING</div>
    <label class="modal-check">
      <input type="checkbox" id="dontShowTestsWarning">
      <span>Don't say again</span>
    </label>
    <div class="modal-actions">
      <button onclick="closeTestsWarning()">Cancel</button>
      <button class="primary-action" onclick="acceptTestsWarning()">Continue</button>
    </div>
  </div>
</div>

<script>
let logOffset = 0;
let logPaused = false;
let firstLogLoad = true;
let selectedLog = 'console.log';

function text(value) {
  return value === undefined || value === null || value === '' ? '' : String(value);
}

function renderLogFiles(files) {
  const select = document.getElementById('logSelect');
  const current = selectedLog;
  select.innerHTML = '';
  for (const item of files || []) {
    const option = document.createElement('option');
    option.value = item.label;
    const size = item.size ? Math.round(item.size / 1024) + ' KB' : 'empty';
    option.textContent = item.label + ' · ' + size;
    select.appendChild(option);
  }
  const labels = Array.from(select.options).map(option => option.value);
  selectedLog = labels.includes(current) ? current : (labels[0] || 'console.log');
  select.value = selectedLog;
}

function renderCards(cards) {
  const root = document.getElementById('cards');
  root.innerHTML = '';
  for (const card of cards) {
    const el = document.createElement('div');
    el.className = 'card ' + (card.state || 'muted');
    const label = document.createElement('div');
    label.className = 'card-label';
    label.textContent = card.label;
    const value = document.createElement('div');
    value.className = 'card-value';
    const dot = document.createElement('span');
    dot.className = 'dot';
    const valueText = document.createElement('span');
    valueText.textContent = card.value;
    value.appendChild(dot);
    value.appendChild(valueText);
    const detail = document.createElement('div');
    detail.className = 'card-detail';
    detail.textContent = card.detail || '';
    el.appendChild(label);
    el.appendChild(value);
    el.appendChild(detail);
    root.appendChild(el);
  }
}

function renderSnapshot(data) {
  renderCards(data.cards || []);
  renderLogFiles(data.log_files || []);
  const track = data.track || {};
  const title = text(track.title);
  const artist = text(track.artist);
  const album = text(track.album);
  const status = text(track.status);
  document.getElementById('trackTitle').textContent = title || 'No current track';
  const parts = [];
  if (artist) parts.push(artist);
  if (album) parts.push(album);
  if (status) parts.push(status.charAt(0).toUpperCase() + status.slice(1));
  document.getElementById('trackMeta').textContent = parts.join(' · ') || 'Waiting for Amazon Music';
  document.getElementById('paths').textContent = data.updated_at_text + '\\n' + data.log_path;
}

async function refreshSnapshot() {
  try {
    const data = await pywebview.api.get_snapshot();
    renderSnapshot(data);
  } catch (e) {
    renderCards([{label:'Diagnostics', value:'Error', detail:String(e), state:'bad'}]);
  }
}

async function refreshLog() {
  if (logPaused) return;
  try {
    const result = await pywebview.api.get_log(selectedLog, logOffset);
    const log = document.getElementById('log');
    if (firstLogLoad) {
      log.textContent = result.content || '';
      firstLogLoad = false;
    } else if (result.content) {
      log.textContent += result.content;
    }
    if (log.textContent.length > 120000) {
      log.textContent = log.textContent.slice(-90000);
    }
    logOffset = result.offset || 0;
    document.getElementById('logStatus').textContent = result.size ? Math.round(result.size / 1024) + ' KB' : 'Empty';
    log.scrollTop = log.scrollHeight;
  } catch (e) {
    document.getElementById('logStatus').textContent = 'Unavailable';
  }
}

function changeLogFile() {
  selectedLog = document.getElementById('logSelect').value || 'console.log';
  logOffset = 0;
  firstLogLoad = true;
  document.getElementById('log').textContent = '';
  refreshLog();
}

function togglePause() {
  logPaused = !logPaused;
  document.getElementById('pauseBtn').textContent = logPaused ? 'Resume Log' : 'Pause Log';
}

function refreshNow() {
  refreshSnapshot();
  refreshLog();
}

async function exportReport() {
  const status = document.getElementById('logStatus');
  status.textContent = 'Exporting report';
  try {
    const result = await pywebview.api.export_diagnostics_report();
    if (result && result.ok) {
      status.textContent = 'Report exported';
    } else {
      status.textContent = (result && result.error) || 'Export cancelled';
    }
  } catch (e) {
    status.textContent = 'Export failed';
  }
}

async function openTests() {
  const result = await pywebview.api.get_test_warning();
  if (result && result.dismissed) {
    showTests();
    return;
  }
  document.getElementById('testsWarning').classList.add('visible');
}

function closeTestsWarning() {
  document.getElementById('testsWarning').classList.remove('visible');
}

async function acceptTestsWarning() {
  if (document.getElementById('dontShowTestsWarning').checked) {
    await pywebview.api.dismiss_test_warning();
  }
  closeTestsWarning();
  showTests();
}

function showTests() {
  document.getElementById('testsCard').classList.add('visible');
  if (!document.getElementById('testsResults').children.length) {
    runTests();
  }
}

function hideTests() {
  document.getElementById('testsCard').classList.remove('visible');
}

function setDevActionStatus(text) {
  document.getElementById('devActionStatus').textContent = text;
}

async function resetIntroFlag() {
  await pywebview.api.set_config_flag('intro_seen', false);
  await pywebview.api.set_config_flag('setup_wizard_seen', false);
  setDevActionStatus('Setup wizard will show next time Settings opens.');
}

async function resetTestsWarning() {
  await pywebview.api.set_config_flag('diagnostics_tests_warning_dismissed', false);
  setDevActionStatus('Tests warning will show next time.');
}

async function clearPrivateSession() {
  await pywebview.api.set_config_flag('privacy_private_session', false);
  setDevActionStatus('Private session flag cleared.');
  refreshSnapshot();
}

async function runTests() {
  const root = document.getElementById('testsResults');
  root.textContent = 'Running...';
  const results = await pywebview.api.run_tests();
  root.innerHTML = '';
  for (const result of results || []) {
    const row = document.createElement('div');
    row.className = 'test-result test-' + (result.status || 'fail');
    const dot = document.createElement('span');
    dot.className = 'dot';
    const body = document.createElement('div');
    const name = document.createElement('div');
    name.className = 'test-name';
    name.textContent = result.name || 'Unknown test';
    const detail = document.createElement('div');
    detail.className = 'test-detail';
    detail.textContent = result.detail || '';
    body.appendChild(name);
    body.appendChild(detail);
    row.appendChild(dot);
    row.appendChild(body);
    root.appendChild(row);
  }
}

window.addEventListener('pywebviewready', () => {
  refreshNow();
  setInterval(refreshSnapshot, 1500);
  setInterval(refreshLog, 900);
});
</script>
</body>
</html>"""


class _Api:
    def __init__(self, window_ref):
        self._window_ref = window_ref

    def get_snapshot(self):
        config = load_config()
        state = redact_data(_read_state(), config)
        access = _notification_access()
        track = state.get("track") or {}
        return {
            "cards": _build_cards(state, config, access),
            "track": track,
            "updated_at_text": _age_text(state.get("updated_at")),
            "log_path": LOG_PATH,
            "log_files": _log_files(),
            "config_path": CONFIG_PATH,
            "state_path": DIAGNOSTICS_PATH,
            "app_version": APP_VERSION,
        }

    def get_log(self, label="console.log", offset=0):
        try:
            path = _log_path_for(label)
            if not os.path.exists(path):
                return {"content": "", "offset": 0, "size": 0}
            size = os.path.getsize(path)
            offset = int(offset or 0)
            if offset < 0 or offset > size:
                offset = max(0, size - 60000)
            if offset == 0 and size > 60000:
                offset = max(0, size - 60000)
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                f.seek(offset)
                content = f.read()
                new_offset = f.tell()
            return {"content": redact_text(content, load_config()), "offset": new_offset, "size": size}
        except Exception as e:
            return {"content": redact_text(f"[Diagnostics] Could not read log: {e}", load_config()), "offset": 0, "size": 0}

    def open_report_issue(self):
        webbrowser.open(ISSUES_URL)

    def export_diagnostics_report(self):
        filename = f"AmazonMusicRPC_Diagnostics_{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip"
        try:
            from windows_file_dialog import save_file_dialog
            path = save_file_dialog("Export Amazon Music RPC diagnostics", filename, "zip", "ZIP files (*.zip)|*.zip|All files (*.*)|*.*", CONFIG_DIR)
            if not path:
                return {"ok": False, "error": "Export cancelled."}
            _write_diagnostics_report(path)
            return {"ok": True, "path": path}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_test_warning(self):
        return {"dismissed": bool(load_config().get("diagnostics_tests_warning_dismissed"))}

    def dismiss_test_warning(self):
        config = load_config_for_update()
        config["diagnostics_tests_warning_dismissed"] = True
        save_config(config)
        return {"ok": True}

    def set_config_flag(self, key, value):
        allowed = {
            "intro_seen",
            "setup_wizard_seen",
            "diagnostics_tests_warning_dismissed",
            "privacy_private_session",
        }
        if key not in allowed:
            return {"ok": False, "error": "Unsupported flag"}
        config = load_config_for_update()
        config[key] = bool(value)
        save_config(config)
        return {"ok": True}

    def run_tests(self):
        from self_tests import run_self_tests
        return run_self_tests(CONFIG_DIR, DIAGNOSTICS_PATH)

    def close_window(self):
        window = self._window_ref()
        if window:
            window.destroy()


class DiagnosticsWindow:
    def __init__(self):
        self._window = None

    def show(self):
        config = load_config()
        width = _bounded_int(config.get("diagnostics_window_width"), 940, 700)
        height = _bounded_int(config.get("diagnostics_window_height"), 700, 520)
        html = HTML_TEMPLATE.replace("{icon_b64}", _icon_b64()).replace("{version}", APP_VERSION)

        window_holder = [None]
        api = _Api(lambda: window_holder[0])
        window_holder[0] = webview.create_window(
            "Amazon Music RPC Diagnostics",
            html=html,
            js_api=api,
            width=width,
            height=height,
            resizable=True,
            min_size=(700, 520),
            background_color="#202020",
            text_select=True,
        )
        window_holder[0].events.resized += _save_window_size
        self._window = window_holder[0]
        webview.start()


if __name__ == "__main__":
    DiagnosticsWindow().show()
