# MIT License - Copyright (c) 2026 eripum9

import os
import sys
import base64
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
  .update-status {
    font-size: 12px;
    margin-top: 8px;
    padding: 8px 12px;
    border-radius: 6px;
    display: none;
    text-align: center;
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
</style>
</head>
<body>

<div class="header">
  <img src="data:image/png;base64,{icon_b64}" alt="icon" id="appIcon">
  <div class="header-text">
    <h1>Amazon Music RPC</h1>
    <p>Discord Rich Presence for Amazon Music</p>
  </div>
  <span class="version-badge">v{version}</span>
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
  <div class="card-title">Notification Enrichment</div>
  <div class="row">
    <div class="row-labels">
      <span class="row-label">Enable notification enrichment</span>
      <div class="row-desc">Use Windows notifications for more accurate track info</div>
    </div>
    <label class="toggle">
      <input type="checkbox" id="notifEnrichEnabled" aria-label="Enable notification enrichment" onchange="onNotifEnrichToggle()">
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
  <div class="card-title">Settings</div>

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
  <div class="card-title">Song Link</div>
  <div class="row">
    <div class="row-labels">
      <span class="row-label">Show "Listen on Deezer" button</span>
      <div class="row-desc">Adds a clickable link button on your Discord presence</div>
    </div>
    <label class="toggle">
      <input type="checkbox" id="songLinkEnabled" aria-label="Show listen on Deezer button">
      <div class="toggle-track"></div>
      <div class="toggle-knob"></div>
    </label>
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
<div class="update-status" id="updateStatus"></div>

<script>
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
      song_link_enabled: document.getElementById('songLinkEnabled').checked,
      notification_enrichment_enabled: document.getElementById('notifEnrichEnabled').checked,
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

  async function init() {
    const cfg = await pywebview.api.get_config();
    if (cfg.use_custom_client_id) {
      document.getElementById('idMode').value = 'custom';
      document.getElementById('customIdGroup').classList.add('visible');
    }
    document.getElementById('clientId').value = cfg.discord_client_id || '';
    document.getElementById('startOnStartup').checked = !!cfg.start_on_startup;
    document.getElementById('startMinimized').checked = !!cfg.start_minimized;
    document.getElementById('showPaused').checked = cfg.show_paused !== false;
    document.getElementById('songLinkEnabled').checked = !!cfg.song_link_enabled;
    document.getElementById('notifEnrichEnabled').checked = !!cfg.notification_enrichment_enabled;
    if (cfg.notification_enrichment_enabled) {
      document.getElementById('notifEnrichInfo').classList.add('visible');
    }
    document.getElementById('lastfmEnabled').checked = !!cfg.lastfm_enabled;
    if (cfg.lastfm_enabled) {
      document.getElementById('lastfmFields').classList.add('visible');
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
    }
    if (cfg.listenbrainz_enabled && cfg.listenbrainz_token) {
      lbValidate();
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
      if (result.has_update) {
        status.className = 'update-status update-available';
        status.textContent = '\u2191 Update available: v' + result.version;
        status.style.display = 'block';
      } else if (result.error) {
        status.className = 'update-status update-error';
        status.textContent = '\u2717 ' + result.error;
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

  window.addEventListener('pywebviewready', init);
</script>
</body>
</html>"""


class _Api:
    def __init__(self, on_save, window_ref):
        self._on_save = on_save
        self._window_ref = window_ref

    def get_config(self):
        cfg = load_config()
        cfg["start_on_startup"] = is_startup_enabled()
        return cfg

    def open_url(self, url):
        import webbrowser
        webbrowser.open(url)

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
            from updater import check_for_update
            has_update, version, download_url = check_for_update()
            if has_update:
                return {"has_update": True, "version": version}
            return {"has_update": False}
        except Exception as e:
            return {"has_update": False, "error": f"Could not check: {e}"}

    def save_settings(self, data):
        use_custom = data.get("use_custom", False)
        client_id = data.get("client_id", "").strip() if use_custom else DEFAULT_CLIENT_ID

        config = {
            "discord_client_id": client_id,
            "use_custom_client_id": use_custom,
            "start_on_startup": bool(data.get("start_on_startup")),
            "start_minimized": bool(data.get("start_minimized")),
            "show_paused": bool(data.get("show_paused", True)),
            "song_link_enabled": bool(data.get("song_link_enabled")),
            "notification_enrichment_enabled": bool(data.get("notification_enrichment_enabled")),
            "lastfm_enabled": bool(data.get("lastfm_enabled")),
            "listenbrainz_enabled": bool(data.get("listenbrainz_enabled")),
            "listenbrainz_token": data.get("listenbrainz_token", "").strip(),
        }
        existing = load_config()
        config["lastfm_api_key"] = existing.get("lastfm_api_key", "")
        config["lastfm_api_secret"] = existing.get("lastfm_api_secret", "")
        config["lastfm_session_key"] = existing.get("lastfm_session_key", "")
        config["lastfm_username"] = existing.get("lastfm_username", "")
        save_config(config)
        set_startup(config["start_on_startup"])

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
        html = HTML_TEMPLATE.replace("{icon_b64}", _icon_b64()).replace("{version}", APP_VERSION)

        window_holder = [None]
        api = _Api(self.on_save, lambda: window_holder[0])

        window_holder[0] = webview.create_window(
            "Amazon Music RPC",
            html=html,
            js_api=api,
            width=460,
            height=800,
            resizable=False,
            background_color="#202020",
        )
        self._window = window_holder[0]
        webview.start()


if __name__ == "__main__":
    SettingsWindow().show()
