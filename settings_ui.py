# MIT License - Copyright (c) 2026 eripum9

import os
import sys
import base64
import json
import subprocess
import webview
from config import load_config, save_config, is_startup_enabled, set_startup, DEFAULT_CLIENT_ID, APP_VERSION

if getattr(sys, 'frozen', False):
    _BUNDLE_DIR = sys._MEIPASS
else:
    _BUNDLE_DIR = os.path.dirname(os.path.abspath(__file__))

ICON_PATH = os.path.join(_BUNDLE_DIR, "icon.png")


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
    config = load_config()
    config["settings_window_width"] = _bounded_int(width, 460, 420)
    config["settings_window_height"] = _bounded_int(height, 800, 560)
    save_config(config)


def _split_aliases(value):
    if isinstance(value, list):
        items = value
    else:
        items = str(value or "").replace("\n", ",").split(",")
    return [str(item).strip() for item in items if str(item).strip()]


def _clean_custom_albums(items):
    if not isinstance(items, list):
        return []
    cleaned = []
    for item in items:
        if not isinstance(item, dict):
            continue
        album = str(item.get("album", "")).strip()
        art_url = str(item.get("art_url", "")).strip()
        aliases = _split_aliases(item.get("aliases", []))
        if album and art_url:
            cleaned.append({"album": album, "aliases": aliases, "art_url": art_url})
    return cleaned


def _settings_payload():
    cfg = load_config()
    try:
        cfg["start_on_startup"] = is_startup_enabled()
    except Exception:
        cfg["start_on_startup"] = False
    keys = [
        "discord_client_id",
        "use_custom_client_id",
        "custom_albums",
        "start_on_startup",
        "start_minimized",
        "show_paused",
        "privacy_private_session",
        "privacy_disable_scrobbling",
        "privacy_blocked_keywords",
        "song_link_enabled",
        "song_link_provider",
        "notification_enrichment_enabled",
        "amazon_devtools_enabled",
        "amazon_devtools_auto_launch",
        "lastfm_enabled",
        "lastfm_username",
        "listenbrainz_enabled",
        "listenbrainz_token",
        "intro_seen",
    ]
    payload = {key: cfg.get(key) for key in keys}
    payload["custom_albums"] = _clean_custom_albums(payload.get("custom_albums"))
    try:
        from amazon_devtools import amazon_devtools_launcher_state
        launcher_state = amazon_devtools_launcher_state()
        payload["amazon_devtools_launcher_installed"] = bool(launcher_state.get("installed"))
        payload["amazon_devtools_launcher_path"] = launcher_state.get("path", "")
    except Exception:
        payload["amazon_devtools_launcher_installed"] = False
        payload["amazon_devtools_launcher_path"] = ""
    return payload


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: 'Segoe UI Variable', 'Segoe UI', sans-serif;
    background: #202020;
    color: #e4e4e4;
    padding: 28px 24px 20px;
    user-select: none;
    overflow-y: auto;
  }
  ::-webkit-scrollbar { width: 6px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: #555; border-radius: 3px; }

  .header {
    display: flex;
    align-items: center;
    gap: 14px;
    margin-bottom: 24px;
  }
  .header img {
    width: 48px;
    height: 48px;
    border-radius: 10px;
  }
  .header-text h1 {
    font-size: 20px;
    font-weight: 600;
    color: #fff;
    line-height: 1.2;
  }
  .header-text p {
    font-size: 12px;
    color: #999;
    margin-top: 2px;
  }

  .card {
    background: #2d2d2d;
    border: 1px solid #3d3d3d;
    border-radius: 8px;
    padding: 16px 18px;
    margin-bottom: 14px;
  }
  .card-title {
    font-size: 13px;
    font-weight: 600;
    color: #fff;
    margin-bottom: 14px;
  }

  .row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 6px 0;
  }
  .row-labels {
    flex: 1;
  }
  .row-label {
    font-size: 13px;
    color: #e4e4e4;
  }
  .row-desc {
    font-size: 11px;
    color: #888;
    margin-top: 1px;
  }
  .separator {
    height: 1px;
    background: #3d3d3d;
    margin: 4px 0;
  }

  /* Dropdown / Select */
  select {
    appearance: none;
    -webkit-appearance: none;
    background: #383838;
    color: #e4e4e4;
    border: 1px solid #4a4a4a;
    border-radius: 6px;
    padding: 7px 32px 7px 12px;
    font-size: 13px;
    font-family: inherit;
    cursor: pointer;
    outline: none;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%23999' stroke-width='2'%3E%3Cpolyline points='6 9 12 15 18 9'/%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-position: right 10px center;
    transition: border-color 0.15s;
  }
  select:hover { border-color: #5865f2; }
  select:focus { border-color: #5865f2; box-shadow: 0 0 0 1px #5865f250; }

  /* Text input */
  input[type="text"], input[type="number"] {
    background: #383838;
    color: #e4e4e4;
    border: 1px solid #4a4a4a;
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 13px;
    font-family: inherit;
    outline: none;
    width: 100%;
    transition: border-color 0.15s;
  }
  input:hover { border-color: #5865f2; }
  input:focus { border-color: #5865f2; box-shadow: 0 0 0 1px #5865f250; }
  input[type="number"] { width: 64px; text-align: center; }
  input[type="number"]::-webkit-inner-spin-button { opacity: 1; }
  textarea {
    background: #383838;
    color: #e4e4e4;
    border: 1px solid #4a4a4a;
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 13px;
    font-family: inherit;
    outline: none;
    width: 100%;
    min-height: 58px;
    resize: vertical;
    transition: border-color 0.15s;
  }
  textarea:hover { border-color: #5865f2; }
  textarea:focus { border-color: #5865f2; box-shadow: 0 0 0 1px #5865f250; }

  /* Custom ID field */
  .custom-id-group {
    margin-top: 10px;
    overflow: hidden;
    max-height: 0;
    opacity: 0;
    transition: max-height 0.25s ease, opacity 0.2s ease, margin-top 0.25s ease;
  }
  .custom-id-group.visible {
    max-height: 80px;
    opacity: 1;
  }
  .custom-id-group label {
    font-size: 11px;
    color: #888;
    display: block;
    margin-bottom: 4px;
  }

  .lastfm-fields {
    margin-top: 10px;
    overflow: hidden;
    max-height: 0;
    opacity: 0;
    transition: max-height 0.3s ease, opacity 0.2s ease;
  }
  .lastfm-fields.visible {
    max-height: 300px;
    opacity: 1;
  }
  .lastfm-fields label {
    font-size: 11px;
    color: #888;
    display: block;
    margin-bottom: 4px;
  }
  .lastfm-fields input {
    margin-bottom: 10px;
  }
  .lastfm-hint {
    font-size: 11px;
    color: #888;
    margin-top: 6px;
    line-height: 1.4;
  }
  .lastfm-hint a {
    color: #5865f2;
    text-decoration: none;
  }
  .lastfm-hint a:hover {
    text-decoration: underline;
  }
  .lastfm-status {
    font-size: 12px;
    margin-top: 8px;
    padding: 6px 10px;
    border-radius: 6px;
    background: #383838;
  }
  .lastfm-status.connected { color: #43b581; }
  .lastfm-status.disconnected { color: #f04747; }

  .custom-album-list {
    display: grid;
    gap: 10px;
  }
  .custom-album-item {
    background: #262626;
    border: 1px solid #3d3d3d;
    border-radius: 8px;
    padding: 12px;
  }
  .custom-album-fields {
    display: grid;
    gap: 8px;
  }
  .custom-album-fields label {
    font-size: 11px;
    color: #888;
    display: block;
    margin-bottom: 4px;
  }
  .custom-album-actions {
    display: flex;
    justify-content: flex-end;
    margin-top: 10px;
  }
  .mini-btn {
    padding: 7px 12px;
    background: #383838;
    color: #e4e4e4;
    border: 1px solid #4a4a4a;
    border-radius: 6px;
    font-size: 12px;
    font-weight: 600;
    font-family: inherit;
    cursor: pointer;
  }
  .mini-btn:hover { border-color: #5865f2; background: #404040; }
  .mini-btn.remove { color: #ff9b9b; }
  .empty-state {
    color: #888;
    font-size: 12px;
    padding: 4px 0 10px;
  }
  .auth-btn {
    padding: 7px 14px;
    background: #d51007;
    color: #fff;
    border: none;
    border-radius: 6px;
    font-size: 12px;
    font-weight: 600;
    font-family: inherit;
    cursor: pointer;
    transition: background 0.15s;
    margin-top: 4px;
  }
  .auth-btn:hover { background: #b30d06; }
  .auth-btn:disabled { background: #555; cursor: default; }

  /* Toggle switch */
  .toggle {
    position: relative;
    width: 40px;
    height: 22px;
    flex-shrink: 0;
  }
  .toggle input { display: none; }
  .toggle-track {
    position: absolute;
    top: 0; left: 0; right: 0; bottom: 0;
    background: #555;
    border-radius: 11px;
    cursor: pointer;
    transition: background 0.2s;
  }
  .toggle input:checked + .toggle-track { background: #5865f2; }
  .toggle-knob {
    position: absolute;
    top: 3px;
    left: 3px;
    width: 16px;
    height: 16px;
    background: #fff;
    border-radius: 50%;
    transition: transform 0.2s;
    pointer-events: none;
  }
  .toggle input:checked ~ .toggle-knob { transform: translateX(18px); }

  /* Save button */
  .save-btn {
    width: 100%;
    padding: 11px;
    background: #5865f2;
    color: #fff;
    border: none;
    border-radius: 6px;
    font-size: 14px;
    font-weight: 600;
    font-family: inherit;
    cursor: pointer;
    transition: background 0.15s;
    margin-top: 6px;
  }
  .save-btn:hover { background: #4752c4; }
  .save-btn:active { background: #3c45a5; transform: scale(0.99); }
  .save-btn:disabled { background: #4752c4; cursor: default; }
  .save-btn.saved { background: #43b581; }
  .save-btn.error { background: #f04747; }

  .btn-row {
    display: flex;
    gap: 8px;
    margin-top: 6px;
  }
  .close-btn {
    flex: 0 0 auto;
    padding: 11px 20px;
    background: #383838;
    color: #e4e4e4;
    border: 1px solid #4a4a4a;
    border-radius: 6px;
    font-size: 14px;
    font-weight: 600;
    font-family: inherit;
    cursor: pointer;
    transition: background 0.15s;
  }
  .close-btn:hover { background: #404040; }

  .update-btn {
    width: 100%;
    padding: 10px;
    background: #383838;
    color: #e4e4e4;
    border: 1px solid #4a4a4a;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 600;
    font-family: inherit;
    cursor: pointer;
    transition: background 0.15s, border-color 0.15s;
    margin-top: 8px;
  }
  .update-btn:hover { background: #404040; border-color: #5865f2; }
  .update-btn:disabled { color: #888; cursor: default; }
  .primary-action {
    background: #5865f2;
    border-color: #5865f2;
    color: #fff;
  }
  .primary-action:hover { background: #4752c4; }
  .update-status {
    font-size: 12px;
    margin-top: 8px;
    padding: 8px 12px;
    border-radius: 6px;
    display: none;
    text-align: center;
    white-space: pre-line;
  }
  .update-status.up-to-date {
    display: block;
    background: #2d3d2d;
    color: #43b581;
    border: 1px solid #3d5d3d;
  }
  .update-status.update-available {
    display: block;
    background: #3d3020;
    color: #faa61a;
    border: 1px solid #5d4d2d;
  }
  .update-status.update-error {
    display: block;
    background: #3d2020;
    color: #f04747;
    border: 1px solid #5d2d2d;
  }

  .error-msg {
    color: #f04747;
    font-size: 12px;
    margin-top: 4px;
    display: none;
  }

  .version-badge {
    font-size: 11px;
    color: #888;
    background: #383838;
    border: 1px solid #4a4a4a;
    border-radius: 4px;
    padding: 2px 8px;
    margin-left: auto;
  }
  .intro-overlay {
    position: fixed;
    inset: 0;
    background: rgba(18, 18, 18, 0.88);
    backdrop-filter: blur(18px);
    z-index: 20;
    display: none;
    align-items: center;
    justify-content: center;
    padding: 24px;
  }
  .intro-overlay.visible { display: flex; }
  .intro-card {
    width: min(420px, 100%);
    background: #2d2d2d;
    border: 1px solid #464646;
    border-radius: 10px;
    padding: 28px;
    animation: introRise 0.36s ease-out;
    box-shadow: 0 24px 70px rgba(0, 0, 0, 0.35);
  }
  .intro-mark {
    width: 72px;
    height: 72px;
    border-radius: 18px;
    margin-bottom: 18px;
    display: grid;
    place-items: center;
    background: #383838;
    border: 1px solid #555;
    position: relative;
    overflow: hidden;
  }
  .intro-mark::before {
    content: "";
    position: absolute;
    width: 140%;
    height: 140%;
    background: conic-gradient(from 90deg, transparent, #5865f2, #43b581, transparent);
    animation: introSpin 2.6s linear infinite;
  }
  .intro-mark img {
    width: 48px;
    height: 48px;
    border-radius: 10px;
    position: relative;
    z-index: 1;
  }
  .intro-title {
    font-size: 24px;
    color: #fff;
    font-weight: 650;
    line-height: 1.15;
    margin-bottom: 8px;
  }
  .intro-copy {
    color: #aaa;
    font-size: 13px;
    line-height: 1.5;
    margin-bottom: 18px;
  }
  .intro-list {
    display: grid;
    gap: 8px;
    margin-bottom: 20px;
  }
  .intro-item {
    background: #383838;
    border: 1px solid #4a4a4a;
    border-radius: 8px;
    padding: 10px 12px;
    color: #ddd;
    font-size: 12px;
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
  .modal-actions {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
  }
  .modal-actions button {
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
  .modal-actions button:hover { border-color: #5865f2; background: #404040; }
  .modal-actions button.primary-action {
    background: #5865f2;
    border-color: #5865f2;
    color: #fff;
  }
  .modal-actions button.primary-action:hover { background: #4752c4; }
  @keyframes introRise {
    from { opacity: 0; transform: translateY(18px) scale(0.98); }
    to { opacity: 1; transform: translateY(0) scale(1); }
  }
  @keyframes introSpin {
    to { transform: rotate(360deg); }
  }
</style>
</head>
<body>

<div class="intro-overlay" id="introOverlay">
  <div class="intro-card">
    <div class="intro-mark"><img src="data:image/png;base64,{icon_b64}" alt="icon"></div>
    <div class="intro-title">Amazon Music RPC</div>
    <div class="intro-copy">An RPC for Amazon Music. These are the main settings worth checking before you leave it running in the tray.</div>
    <div class="intro-list">
      <div class="intro-item">Amazon Metadata is the main source for track info, artwork, pause state, and timing.</div>
      <div class="intro-item">Privacy controls hide tracks you do not want to share.</div>
      <div class="intro-item">Song Link controls the button shown on your Discord presence.</div>
      <div class="intro-item">Diagnostics shows status, logs, and development checks.</div>
    </div>
    <button class="save-btn" onclick="finishIntro()">Get Started</button>
  </div>
</div>

<div class="modal-overlay" id="metadataWarning">
  <div class="modal">
    <div class="modal-title">Amazon Metadata</div>
    <div class="modal-copy">Disabling enhanced Amazon metadata is not recommended. It is the most reliable source for track info, artwork, pause state, and timing. If you disable it, Amazon Music RPC will fall back to SMTC and notifications, which can be less accurate.</div>
    <div class="modal-actions">
      <button onclick="closeMetadataWarning()">Keep Enabled</button>
      <button class="primary-action" onclick="acceptMetadataWarning()">Disable Anyway</button>
    </div>
  </div>
</div>

<div class="header">
  <img src="data:image/png;base64,{icon_b64}" alt="icon" id="appIcon">
  <div class="header-text">
    <h1>Amazon Music RPC</h1>
    <p>Discord Rich Presence for Amazon Music</p>
  </div>
  <span class="version-badge">v{version}</span>
</div>

<div class="card">
  <div class="card-title">Amazon Metadata</div>
  <div class="row">
    <div class="row-labels">
      <span class="row-label">Enhanced Amazon metadata</span>
      <div class="row-desc">Use Amazon Music's local playback metadata for better track info</div>
    </div>
    <label class="toggle">
      <input type="checkbox" id="amazonDevtoolsEnabled" aria-label="Enable enhanced Amazon metadata" onchange="onAmazonMetadataToggle()">
      <div class="toggle-track"></div>
      <div class="toggle-knob"></div>
    </label>
  </div>
  <div class="separator"></div>
  <div class="row">
    <div class="row-labels">
      <span class="row-label">Auto-launch Amazon Music</span>
      <div class="row-desc">Start or restart Amazon Music for metadata when RPC starts</div>
    </div>
    <label class="toggle">
      <input type="checkbox" id="amazonDevtoolsAutoLaunch" aria-label="Auto-launch Amazon Music metadata">
      <div class="toggle-track"></div>
      <div class="toggle-knob"></div>
    </label>
  </div>
  <button class="update-btn" type="button" onclick="launchAmazonDevtools()">Launch Amazon Music Now</button>
  <button class="update-btn" id="amazonLauncherBtn" type="button" onclick="toggleAmazonLauncher()">Add Start Menu Launcher</button>
</div>

<div class="card">
  <div class="card-title">Song Link</div>
  <div class="row">
    <div class="row-labels">
      <span class="row-label">Show listen button</span>
      <div class="row-desc">Adds a clickable Amazon Music or Deezer link on your Discord presence</div>
    </div>
    <label class="toggle">
      <input type="checkbox" id="songLinkEnabled" aria-label="Show listen button">
      <div class="toggle-track"></div>
      <div class="toggle-knob"></div>
    </label>
  </div>
  <div class="separator"></div>
  <div class="row">
    <div class="row-labels">
      <span class="row-label">Button source</span>
      <div class="row-desc">Amazon Music is used by default when available</div>
    </div>
    <select id="songLinkProvider" aria-label="Listen button source">
      <option value="amazon">Amazon Music</option>
      <option value="deezer">Deezer</option>
    </select>
  </div>
</div>

<div class="card">
  <div class="card-title">Privacy</div>

  <div class="row">
    <div class="row-labels">
      <span class="row-label">Private session</span>
      <div class="row-desc">Hide Discord presence and skip protected activity</div>
    </div>
    <label class="toggle">
      <input type="checkbox" id="privacyPrivateSession" aria-label="Private session">
      <div class="toggle-track"></div>
      <div class="toggle-knob"></div>
    </label>
  </div>
  <div class="separator"></div>

  <div class="row">
    <div class="row-labels">
      <span class="row-label">Disable scrobbling while private</span>
      <div class="row-desc">Do not send Last.fm or ListenBrainz updates for hidden tracks</div>
    </div>
    <label class="toggle">
      <input type="checkbox" id="privacyDisableScrobbling" aria-label="Disable scrobbling while private">
      <div class="toggle-track"></div>
      <div class="toggle-knob"></div>
    </label>
  </div>
  <div class="separator"></div>

  <div style="padding:6px 0;">
    <div class="row-label">Blocked keywords</div>
    <div class="row-desc" style="margin-bottom:8px;">Comma-separated words that hide matching tracks, artists, or albums</div>
    <textarea id="privacyBlockedKeywords" placeholder="artist name, track title, album keyword"></textarea>
  </div>
</div>

<div class="card">
  <div class="card-title">Custom Album Art</div>
  <div class="row-desc" style="margin-bottom:10px;">Match album names or aliases to a custom cover image URL</div>
  <div class="custom-album-list" id="customAlbumList"></div>
  <button class="update-btn" type="button" onclick="addCustomAlbum()">Add Album Art</button>
</div>

<div class="card">
  <div class="card-title">Startup & Presence</div>

  <div class="row">
    <div class="row-labels">
      <span class="row-label">Start on Windows startup</span>
      <div class="row-desc">Launch automatically when you log in</div>
    </div>
    <label class="toggle">
      <input type="checkbox" id="startOnStartup" aria-label="Start on Windows startup">
      <div class="toggle-track"></div>
      <div class="toggle-knob"></div>
    </label>
  </div>
  <div class="separator"></div>

  <div class="row">
    <div class="row-labels">
      <span class="row-label">Start minimized</span>
      <div class="row-desc">Start hidden in the system tray</div>
    </div>
    <label class="toggle">
      <input type="checkbox" id="startMinimized" aria-label="Start minimized">
      <div class="toggle-track"></div>
      <div class="toggle-knob"></div>
    </label>
  </div>
  <div class="separator"></div>

  <div class="row">
    <div class="row-labels">
      <span class="row-label">Show paused state</span>
      <div class="row-desc">Keep presence visible when music is paused</div>
    </div>
    <label class="toggle">
      <input type="checkbox" id="showPaused" aria-label="Show paused state">
      <div class="toggle-track"></div>
      <div class="toggle-knob"></div>
    </label>
  </div>
</div>

<div class="card">
  <div class="card-title">Fallback Metadata</div>
  <div class="row">
    <div class="row-labels">
      <span class="row-label">Notification fallback</span>
      <div class="row-desc">Use Windows notifications only when Amazon metadata is unavailable</div>
    </div>
    <label class="toggle">
      <input type="checkbox" id="notifEnrichEnabled" aria-label="Enable notification fallback" onchange="onNotifEnrichToggle()">
      <div class="toggle-track"></div>
      <div class="toggle-knob"></div>
    </label>
  </div>
  <div class="lastfm-fields" id="notifEnrichInfo">
    <div style="margin-top:6px; font-size:11px; color:#bbb; line-height:1.5;">
      <strong style="color:#e4e4e4;">Requirements:</strong><br>
      &bull; Notifications must be enabled in Amazon Music settings<br>
      &bull; Amazon Music must be <strong>minimized</strong> for notifications to appear
    </div>
    <div style="margin-top:8px;">
      <a href="#" onclick="pywebview.api.open_url('https://eripum9.github.io/Amazon-Music-Discord-RPC/notification-setup'); return false;"
         style="color:#5865f2; font-size:12px; text-decoration:none; font-weight:600;">
        Learn how to enable it &rarr;
      </a>
    </div>
  </div>
</div>

<div class="card">
  <div class="card-title">Discord Client ID</div>
  <div class="row">
    <div class="row-labels"><span class="row-label">Mode</span></div>
    <select id="idMode" aria-label="Client ID mode" onchange="onModeChange()">
      <option value="default">Default</option>
      <option value="custom">Custom</option>
    </select>
  </div>
  <div class="custom-id-group" id="customIdGroup">
    <label>Application ID</label>
    <input type="text" id="clientId" placeholder="Enter your Discord Application ID">
    <div class="error-msg" id="idError">Please enter a valid Client ID or switch back to Default.</div>
  </div>
</div>

<div class="card">
  <div class="card-title">Last.fm</div>
  <div class="row">
    <div class="row-labels">
      <span class="row-label">Enable Last.fm Scrobbling</span>
      <div class="row-desc">Scrobble tracks and send now playing updates</div>
    </div>
    <label class="toggle">
      <input type="checkbox" id="lastfmEnabled" aria-label="Enable Last.fm scrobbling" onchange="onLastfmToggle()">
      <div class="toggle-track"></div>
      <div class="toggle-knob"></div>
    </label>
  </div>
  <div class="lastfm-fields" id="lastfmFields">
    <div style="margin-top: 4px;">
      <button class="auth-btn" id="authBtn" onclick="lastfmAuth()">Authenticate with Last.fm</button>
      <button class="auth-btn" id="completeAuthBtn" onclick="lastfmCompleteAuth()" style="display:none; margin-left:6px; background:#43b581;">Complete Authentication</button>
    </div>
    <div class="lastfm-status" id="lastfmStatus" style="display:none;"></div>
  </div>
</div>

<div class="card">
  <div class="card-title">ListenBrainz</div>
  <div class="row">
    <div class="row-labels">
      <span class="row-label">Enable ListenBrainz Scrobbling</span>
      <div class="row-desc">Scrobble tracks and send now playing updates</div>
    </div>
    <label class="toggle">
      <input type="checkbox" id="lbEnabled" aria-label="Enable ListenBrainz scrobbling" onchange="onLbToggle()">
      <div class="toggle-track"></div>
      <div class="toggle-knob"></div>
    </label>
  </div>
  <div class="lastfm-fields" id="lbFields">
    <div style="margin-top: 6px;">
      <div style="display:flex; align-items:center; gap:8px; margin-bottom:10px;">
        <button class="auth-btn" style="background:#353070;" onclick="lbGetToken()">1. Get Token</button>
        <span style="font-size:11px; color:#888;">Opens listenbrainz.org to copy your token</span>
      </div>
      <label style="font-size:11px; color:#888; display:block; margin-bottom:4px;">2. Paste your token below</label>
      <div style="display:flex; gap:8px;">
        <input type="text" id="lbToken" placeholder="Paste your ListenBrainz user token" style="flex:1;">
        <button class="auth-btn" id="lbValidateBtn" style="background:#43b581; white-space:nowrap;" onclick="lbValidate()">Validate</button>
      </div>
    </div>
    <div class="lastfm-status" id="lbStatus" style="display:none;"></div>
  </div>
</div>

<div class="btn-row">
  <button class="save-btn" id="saveBtn" onclick="save()">Save Changes</button>
  <button class="close-btn" onclick="pywebview.api.close_window()">Close</button>
</div>

<button class="update-btn" id="updateBtn" onclick="checkForUpdates()">↑ Check for Updates</button>
<button class="update-btn" id="diagBtn" onclick="pywebview.api.open_diagnostics()">Open Diagnostics</button>
<button class="update-btn" onclick="pywebview.api.open_url('https://github.com/eripum9/Amazon-Music-Discord-RPC/issues')">Report Issue</button>
<div class="update-status" id="updateStatus"></div>

<script>
  const BOOTSTRAP_CONFIG = {config_json};
  let customAlbums = [];
  let amazonLauncherInstalled = false;

  function showSettingsStatus(text, kind) {
    const status = document.getElementById('updateStatus');
    status.className = 'update-status ' + (kind || 'update-error');
    status.textContent = text;
    status.style.display = 'block';
  }

  function hideSettingsStatus() {
    const status = document.getElementById('updateStatus');
    if (status.className.indexOf('update-error') !== -1 && status.textContent.indexOf('settings') !== -1) {
      status.style.display = 'none';
      status.className = 'update-status';
      status.textContent = '';
    }
  }

  function onModeChange() {
    const group = document.getElementById('customIdGroup');
    const mode = document.getElementById('idMode').value;
    if (mode === 'custom') {
      group.classList.add('visible');
    } else {
      group.classList.remove('visible');
      document.getElementById('idError').style.display = 'none';
    }
  }

  function escapeHtml(value) {
    return String(value || '').replace(/[&<>"']/g, (ch) => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;'
    }[ch]));
  }

  function splitAliasText(value) {
    return String(value || '').split(/[\\n,]+/).map((item) => item.trim()).filter(Boolean);
  }

  function collectCustomAlbums(keepEmpty) {
    return Array.from(document.querySelectorAll('.custom-album-item')).map((item) => {
      const album = item.querySelector('[data-field="album"]').value.trim();
      const aliases = splitAliasText(item.querySelector('[data-field="aliases"]').value);
      const artUrl = item.querySelector('[data-field="art_url"]').value.trim();
      return { album, aliases, art_url: artUrl };
    }).filter((item) => keepEmpty || (item.album && item.art_url));
  }

  function renderCustomAlbums(items) {
    customAlbums = Array.isArray(items) ? items.map((item) => ({
      album: item.album || '',
      aliases: Array.isArray(item.aliases) ? item.aliases : splitAliasText(item.aliases || ''),
      art_url: item.art_url || ''
    })) : [];
    const list = document.getElementById('customAlbumList');
    if (!customAlbums.length) {
      list.innerHTML = '<div class="empty-state">No custom album art configured.</div>';
      return;
    }
    list.innerHTML = customAlbums.map((item, index) => `
      <div class="custom-album-item">
        <div class="custom-album-fields">
          <div>
            <label>Album</label>
            <input type="text" data-field="album" value="${escapeHtml(item.album)}" placeholder="Album name">
          </div>
          <div>
            <label>Alternative names</label>
            <textarea data-field="aliases" placeholder="One alias per line">${escapeHtml(item.aliases.join('\\n'))}</textarea>
          </div>
          <div>
            <label>Cover image URL</label>
            <input type="text" data-field="art_url" value="${escapeHtml(item.art_url)}" placeholder="https://example.com/cover.jpg">
          </div>
        </div>
        <div class="custom-album-actions">
          <button class="mini-btn remove" type="button" onclick="removeCustomAlbum(${index})">Remove</button>
        </div>
      </div>
    `).join('');
  }

  function addCustomAlbum() {
    customAlbums = collectCustomAlbums(true);
    customAlbums.push({ album: '', aliases: [], art_url: '' });
    renderCustomAlbums(customAlbums);
  }

  function removeCustomAlbum(index) {
    customAlbums = collectCustomAlbums(true);
    customAlbums.splice(index, 1);
    renderCustomAlbums(customAlbums);
  }

  function onLastfmToggle() {
    const fields = document.getElementById('lastfmFields');
    if (document.getElementById('lastfmEnabled').checked) {
      fields.classList.add('visible');
    } else {
      fields.classList.remove('visible');
    }
  }

  function onNotifEnrichToggle() {
    const fields = document.getElementById('notifEnrichInfo');
    if (document.getElementById('notifEnrichEnabled').checked) {
      fields.classList.add('visible');
    } else {
      fields.classList.remove('visible');
    }
  }

  function onAmazonMetadataToggle() {
    const input = document.getElementById('amazonDevtoolsEnabled');
    if (input.checked) {
      return;
    }
    document.getElementById('metadataWarning').classList.add('visible');
  }

  function closeMetadataWarning() {
    document.getElementById('metadataWarning').classList.remove('visible');
    document.getElementById('amazonDevtoolsEnabled').checked = true;
  }

  function acceptMetadataWarning() {
    document.getElementById('metadataWarning').classList.remove('visible');
    document.getElementById('amazonDevtoolsEnabled').checked = false;
  }

  function onLbToggle() {
    const fields = document.getElementById('lbFields');
    if (document.getElementById('lbEnabled').checked) {
      fields.classList.add('visible');
    } else {
      fields.classList.remove('visible');
    }
  }

  function lbGetToken() {
    pywebview.api.open_url('https://listenbrainz.org/settings/');
  }

  async function lbValidate() {
    const token = document.getElementById('lbToken').value.trim();
    if (!token) {
      const s = document.getElementById('lbStatus');
      s.style.display = 'block';
      s.className = 'lastfm-status disconnected';
      s.textContent = '\u2717 Please paste a token first.';
      return;
    }
    const btn = document.getElementById('lbValidateBtn');
    btn.disabled = true;
    btn.textContent = 'Checking...';
    const result = await pywebview.api.validate_lb_token(token);
    btn.disabled = false;
    btn.textContent = 'Validate';
    const s = document.getElementById('lbStatus');
    s.style.display = 'block';
    if (result && result.valid) {
      s.className = 'lastfm-status connected';
      s.textContent = '\u2713 Connected as: ' + result.user_name;
    } else {
      s.className = 'lastfm-status disconnected';
      s.textContent = '\u2717 ' + (result ? result.error : 'Validation failed.');
    }
  }

  async function lastfmAuth() {
    document.getElementById('authBtn').disabled = true;
    document.getElementById('authBtn').textContent = 'Opening browser...';
    const result = await pywebview.api.lastfm_auth();
    document.getElementById('authBtn').disabled = false;
    document.getElementById('authBtn').textContent = 'Authenticate with Last.fm';
    if (result && result.ok) {
      document.getElementById('completeAuthBtn').style.display = 'inline-block';
      const status = document.getElementById('lastfmStatus');
      status.style.display = 'block';
      status.className = 'lastfm-status disconnected';
      status.textContent = 'Approve in your browser, then click Complete Authentication.';
    } else {
      alert(result ? result.error : 'Authentication failed.');
    }
  }

  async function lastfmCompleteAuth() {
    document.getElementById('completeAuthBtn').disabled = true;
    document.getElementById('completeAuthBtn').textContent = 'Verifying...';
    const result = await pywebview.api.lastfm_complete_auth();
    document.getElementById('completeAuthBtn').disabled = false;
    document.getElementById('completeAuthBtn').textContent = 'Complete Authentication';
    if (result && result.ok) {
      document.getElementById('completeAuthBtn').style.display = 'none';
      const status = document.getElementById('lastfmStatus');
      status.style.display = 'block';
      status.className = 'lastfm-status connected';
      status.textContent = '\u2713 Connected as: ' + result.username;
    } else {
      const status = document.getElementById('lastfmStatus');
      status.style.display = 'block';
      status.className = 'lastfm-status disconnected';
      status.textContent = '\u2717 ' + (result ? result.error : 'Failed. Did you approve in the browser?');
    }
  }

  async function save() {
    const mode = document.getElementById('idMode').value;
    const customId = document.getElementById('clientId').value.trim();
    const btn = document.getElementById('saveBtn');

    if (mode === 'custom' && !customId) {
      document.getElementById('idError').style.display = 'block';
      return;
    }
    if (mode === 'custom' && (!/^\\d+$/.test(customId) || customId.length < 15)) {
      document.getElementById('idError').textContent = 'Client ID must be numeric and at least 15 digits.';
      document.getElementById('idError').style.display = 'block';
      document.getElementById('clientId').style.borderColor = '#f04747';
      return;
    }
    document.getElementById('idError').style.display = 'none';
    document.getElementById('clientId').style.borderColor = '';

    btn.disabled = true;
    btn.textContent = 'Saving...';
    btn.className = 'save-btn';

    const data = {
      use_custom: mode === 'custom',
      client_id: customId,
      start_on_startup: document.getElementById('startOnStartup').checked,
      start_minimized: document.getElementById('startMinimized').checked,
      show_paused: document.getElementById('showPaused').checked,
      privacy_private_session: document.getElementById('privacyPrivateSession').checked,
      privacy_disable_scrobbling: document.getElementById('privacyDisableScrobbling').checked,
      privacy_blocked_keywords: document.getElementById('privacyBlockedKeywords').value.trim(),
      custom_albums: collectCustomAlbums(false),
      song_link_enabled: document.getElementById('songLinkEnabled').checked,
      song_link_provider: document.getElementById('songLinkProvider').value,
      notification_enrichment_enabled: document.getElementById('notifEnrichEnabled').checked,
      amazon_devtools_enabled: document.getElementById('amazonDevtoolsEnabled').checked,
      amazon_devtools_auto_launch: document.getElementById('amazonDevtoolsAutoLaunch').checked,
      lastfm_enabled: document.getElementById('lastfmEnabled').checked,
      listenbrainz_enabled: document.getElementById('lbEnabled').checked,
      listenbrainz_token: document.getElementById('lbToken').value.trim()
    };

    try {
      await pywebview.api.save_settings(data);
      btn.textContent = '\u2713 Saved!';
      btn.className = 'save-btn saved';
      setTimeout(() => {
        btn.textContent = 'Save Changes';
        btn.className = 'save-btn';
        btn.disabled = false;
      }, 2000);
    } catch (e) {
      btn.textContent = '\u2717 Save failed';
      btn.className = 'save-btn error';
      setTimeout(() => {
        btn.textContent = 'Save Changes';
        btn.className = 'save-btn';
        btn.disabled = false;
      }, 2000);
    }
  }

  function applyConfig(cfg) {
    cfg = cfg || {};
    if (cfg.use_custom_client_id) {
      document.getElementById('idMode').value = 'custom';
      document.getElementById('customIdGroup').classList.add('visible');
    } else {
      document.getElementById('idMode').value = 'default';
      document.getElementById('customIdGroup').classList.remove('visible');
    }
    document.getElementById('clientId').value = cfg.discord_client_id || '';
    document.getElementById('startOnStartup').checked = !!cfg.start_on_startup;
    document.getElementById('startMinimized').checked = !!cfg.start_minimized;
    document.getElementById('showPaused').checked = cfg.show_paused !== false;
    document.getElementById('privacyPrivateSession').checked = !!cfg.privacy_private_session;
    document.getElementById('privacyDisableScrobbling').checked = cfg.privacy_disable_scrobbling !== false;
    document.getElementById('privacyBlockedKeywords').value = cfg.privacy_blocked_keywords || '';
    renderCustomAlbums(cfg.custom_albums || []);
    document.getElementById('songLinkEnabled').checked = !!cfg.song_link_enabled;
    document.getElementById('songLinkProvider').value = cfg.song_link_provider === 'deezer' ? 'deezer' : 'amazon';
    document.getElementById('notifEnrichEnabled').checked = !!cfg.notification_enrichment_enabled;
    document.getElementById('amazonDevtoolsEnabled').checked = !!cfg.amazon_devtools_enabled;
    document.getElementById('amazonDevtoolsAutoLaunch').checked = cfg.amazon_devtools_auto_launch !== false;
    amazonLauncherInstalled = !!cfg.amazon_devtools_launcher_installed;
    renderAmazonLauncherButton();
    if (cfg.notification_enrichment_enabled) {
      document.getElementById('notifEnrichInfo').classList.add('visible');
    } else {
      document.getElementById('notifEnrichInfo').classList.remove('visible');
    }
    document.getElementById('lastfmEnabled').checked = !!cfg.lastfm_enabled;
    if (cfg.lastfm_enabled) {
      document.getElementById('lastfmFields').classList.add('visible');
    } else {
      document.getElementById('lastfmFields').classList.remove('visible');
    }
    if (cfg.lastfm_username) {
      const status = document.getElementById('lastfmStatus');
      status.style.display = 'block';
      status.className = 'lastfm-status connected';
      status.textContent = '\u2713 Connected as: ' + cfg.lastfm_username;
    }
    document.getElementById('lbEnabled').checked = !!cfg.listenbrainz_enabled;
    document.getElementById('lbToken').value = cfg.listenbrainz_token || '';
    if (cfg.listenbrainz_enabled) {
      document.getElementById('lbFields').classList.add('visible');
    } else {
      document.getElementById('lbFields').classList.remove('visible');
    }
    if (cfg.listenbrainz_enabled && cfg.listenbrainz_token && window.pywebview && window.pywebview.api) {
      lbValidate();
    }
    if (!cfg.intro_seen) {
      document.getElementById('introOverlay').classList.add('visible');
    } else {
      document.getElementById('introOverlay').classList.remove('visible');
    }
  }

  function apiReady() {
    return !!(window.pywebview && window.pywebview.api);
  }

  async function waitForApi(timeoutMs = 7000) {
    const start = Date.now();
    while (!apiReady()) {
      if ((Date.now() - start) > timeoutMs) {
        throw new Error('Timed out waiting for app bridge.');
      }
      await new Promise((resolve) => setTimeout(resolve, 120));
    }
  }

  async function init() {
    applyConfig(BOOTSTRAP_CONFIG);
    try {
      await waitForApi();
      const cfg = await pywebview.api.get_config();
      applyConfig(cfg);
      hideSettingsStatus();
    } catch (e) {
      showSettingsStatus('\u2717 Could not refresh settings from the app bridge. Showing saved config snapshot.', 'update-error');
    }
  }

  async function finishIntro() {
    try {
      await pywebview.api.dismiss_intro();
      document.getElementById('introOverlay').classList.remove('visible');
    } catch (e) {
      showSettingsStatus('\u2717 Could not save intro state yet. Try again after Settings finishes loading.', 'update-error');
    }
  }

  async function checkForUpdates() {
    const btn = document.getElementById('updateBtn');
    const status = document.getElementById('updateStatus');
    btn.disabled = true;
    btn.textContent = 'Checking...';
    status.style.display = 'none';
    status.className = 'update-status';
    try {
      const result = await pywebview.api.check_for_updates();
      if (result.install_started) {
        status.className = 'update-status up-to-date';
        status.textContent = '\u2713 Installer launched.';
        status.style.display = 'block';
      } else if (result.error) {
        status.className = 'update-status update-error';
        status.textContent = '\u2717 ' + result.error;
        status.style.display = 'block';
      } else if (result.has_update) {
        status.className = 'update-status update-available';
        status.textContent = '\u2191 Update available: v' + result.version + (result.changelog ? "\\n\\nWhat's new:\\n" + result.changelog : '');
        status.style.display = 'block';
      } else {
        status.className = 'update-status up-to-date';
        status.textContent = '\u2713 You are up to date!';
        status.style.display = 'block';
      }
    } catch (e) {
      status.className = 'update-status update-error';
      status.textContent = '\u2717 Could not check for updates.';
      status.style.display = 'block';
    }
    btn.disabled = false;
    btn.textContent = '\u2191 Check for Updates';
  }

  function renderAmazonLauncherButton() {
    const btn = document.getElementById('amazonLauncherBtn');
    if (!btn) {
      return;
    }
    btn.textContent = amazonLauncherInstalled ? 'Remove Start Menu Launcher' : 'Add Start Menu Launcher';
  }

  async function launchAmazonDevtools() {
    try {
      const result = await pywebview.api.launch_amazon_devtools();
      if (result && result.ok) {
        showSettingsStatus('\u2713 Amazon Music launched for metadata.', 'up-to-date');
      } else {
        showSettingsStatus('\u2717 ' + ((result && result.error) || 'Could not launch Amazon Music for metadata.'), 'update-error');
      }
    } catch (e) {
      showSettingsStatus('\u2717 Could not launch Amazon Music for metadata.', 'update-error');
    }
  }

  async function toggleAmazonLauncher() {
    const btn = document.getElementById('amazonLauncherBtn');
    btn.disabled = true;
    btn.textContent = amazonLauncherInstalled ? 'Removing...' : 'Adding...';
    try {
      const result = await pywebview.api.set_amazon_devtools_launcher(!amazonLauncherInstalled);
      if (result && result.ok) {
        amazonLauncherInstalled = !!result.installed;
        renderAmazonLauncherButton();
        showSettingsStatus(amazonLauncherInstalled ? '\u2713 Start Menu launcher added.' : '\u2713 Start Menu launcher removed.', 'up-to-date');
      } else {
        showSettingsStatus('\u2717 ' + ((result && result.error) || 'Could not update Start Menu launcher.'), 'update-error');
        renderAmazonLauncherButton();
      }
    } catch (e) {
      showSettingsStatus('\u2717 Could not update Start Menu launcher.', 'update-error');
      renderAmazonLauncherButton();
    }
    btn.disabled = false;
  }

  document.addEventListener('DOMContentLoaded', () => {
    applyConfig(BOOTSTRAP_CONFIG);
    init();
  });
  window.addEventListener('pywebviewready', init);
</script>
</body>
</html>"""


class _Api:
    def __init__(self, on_save, window_ref):
        self._on_save = on_save
        self._window_ref = window_ref

    def get_config(self):
        return _settings_payload()

    def open_url(self, url):
        import webbrowser
        webbrowser.open(url)

    def dismiss_intro(self):
        config = load_config()
        config["intro_seen"] = True
        save_config(config)
        return {"ok": True}

    def validate_lb_token(self, token):
        try:
            import urllib.request
            import json
            req = urllib.request.Request(
                "https://api.listenbrainz.org/1/validate-token",
                headers={"Authorization": f"Token {token}"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            if data.get("valid"):
                return {"valid": True, "user_name": data.get("user_name", "")}
            return {"valid": False, "error": "Invalid token. Please check and try again."}
        except Exception as e:
            return {"valid": False, "error": f"Could not validate: {e}"}

    def lastfm_auth(self):
        try:
            from lastfm import get_auth_url
            config = load_config()
            url, skg = get_auth_url(config["lastfm_api_key"], config["lastfm_api_secret"])
            _Api._skg = skg
            _Api._auth_url = url
            import webbrowser
            webbrowser.open(url)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    _skg = None
    _auth_url = None
    _diagnostics_proc = None

    def lastfm_complete_auth(self):
        try:
            if not _Api._skg or not _Api._auth_url:
                return {"ok": False, "error": "No auth in progress. Click Authenticate first."}
            from lastfm import complete_auth
            session_key, username = complete_auth(_Api._skg, _Api._auth_url)
            _Api._skg = None
            _Api._auth_url = None

            config = load_config()
            config["lastfm_session_key"] = session_key
            config["lastfm_username"] = username
            config["lastfm_enabled"] = True
            save_config(config)

            return {"ok": True, "username": username}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def check_for_updates(self):
        try:
            from updater import check_for_update, prompt_for_update
            has_update, version, download_url, changelog = check_for_update()
            if has_update:
                result = {"has_update": True, "version": version, "changelog": changelog}
                if download_url:
                    installer_path = prompt_for_update(version, download_url, changelog)
                    result["install_started"] = bool(installer_path)
                else:
                    result["error"] = "No installer asset found for this release."
                return result
            return {"has_update": False}
        except Exception as e:
            return {"has_update": False, "error": f"Could not check: {e}"}

    def open_diagnostics(self):
        try:
            if _Api._diagnostics_proc and _Api._diagnostics_proc.poll() is None:
                return {"ok": True}
            if getattr(sys, 'frozen', False):
                cmd = [sys.executable, '--diagnostics']
            else:
                cmd = [sys.executable, os.path.join(_BUNDLE_DIR, "diagnostics_ui.py")]
            _Api._diagnostics_proc = subprocess.Popen(cmd, creationflags=0x08000000)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def launch_amazon_devtools(self):
        try:
            from amazon_devtools import launch_amazon_music_devtools
            return launch_amazon_music_devtools()
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def set_amazon_devtools_launcher(self, install):
        try:
            from amazon_devtools import install_amazon_devtools_launcher, remove_amazon_devtools_launcher
            if install:
                return install_amazon_devtools_launcher()
            return remove_amazon_devtools_launcher()
        except Exception as e:
            return {"ok": False, "error": str(e), "installed": False}

    def save_settings(self, data):
        use_custom = data.get("use_custom", False)
        client_id = data.get("client_id", "").strip() if use_custom else DEFAULT_CLIENT_ID

        existing = load_config()
        config = {
            **existing,
            "discord_client_id": client_id,
            "use_custom_client_id": use_custom,
            "start_on_startup": bool(data.get("start_on_startup")),
            "start_minimized": bool(data.get("start_minimized")),
            "show_paused": bool(data.get("show_paused", True)),
            "privacy_private_session": bool(data.get("privacy_private_session")),
            "privacy_disable_scrobbling": bool(data.get("privacy_disable_scrobbling", True)),
            "privacy_blocked_keywords": data.get("privacy_blocked_keywords", "").strip(),
            "custom_albums": _clean_custom_albums(data.get("custom_albums", [])),
            "song_link_enabled": bool(data.get("song_link_enabled")),
            "song_link_provider": data.get("song_link_provider") if data.get("song_link_provider") in ("amazon", "deezer") else "amazon",
            "notification_enrichment_enabled": bool(data.get("notification_enrichment_enabled")),
            "amazon_devtools_enabled": bool(data.get("amazon_devtools_enabled")),
            "amazon_devtools_auto_launch": bool(data.get("amazon_devtools_auto_launch", True)),
            "lastfm_enabled": bool(data.get("lastfm_enabled")),
            "listenbrainz_enabled": bool(data.get("listenbrainz_enabled")),
            "listenbrainz_token": data.get("listenbrainz_token", "").strip(),
        }
        save_config(config)
        set_startup(config["start_on_startup"], config["start_minimized"])

        if self._on_save:
            self._on_save(config)

    def close_window(self):
        window = self._window_ref()
        if window:
            window.destroy()


class SettingsWindow:
    def __init__(self, on_save_callback=None):
        self.on_save = on_save_callback
        self._window = None

    def show(self):
        config = load_config()
        width = _bounded_int(config.get("settings_window_width"), 460, 420)
        height = _bounded_int(config.get("settings_window_height"), 800, 560)
        config_json = json.dumps(_settings_payload()).replace("</", "<\\/")
        html = (
            HTML_TEMPLATE
            .replace("{icon_b64}", _icon_b64())
            .replace("{version}", APP_VERSION)
            .replace("{config_json}", config_json)
        )

        window_holder = [None]
        api = _Api(self.on_save, lambda: window_holder[0])

        window_holder[0] = webview.create_window(
            "Amazon Music RPC",
            html=html,
            js_api=api,
            width=width,
            height=height,
            resizable=True,
            min_size=(420, 560),
            background_color="#202020",
        )
        window_holder[0].events.resized += _save_window_size
        self._window = window_holder[0]
        webview.start()


if __name__ == "__main__":
    SettingsWindow().show()
