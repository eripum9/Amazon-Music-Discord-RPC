# MIT License - Copyright (c) 2026 eripum9

import os
import sys
import base64
import webview
from config import load_config, save_config, is_startup_enabled, set_startup, DEFAULT_CLIENT_ID

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

  .error-msg {
    color: #f04747;
    font-size: 12px;
    margin-top: 4px;
    display: none;
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
</div>

<div class="card">
  <div class="card-title">Discord Client ID</div>
  <div class="row">
    <div class="row-labels"><span class="row-label">Mode</span></div>
    <select id="idMode" onchange="onModeChange()">
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
  <div class="card-title">Settings</div>

  <div class="row">
    <div class="row-labels">
      <span class="row-label">Start on Windows startup</span>
      <div class="row-desc">Launch automatically when you log in</div>
    </div>
    <label class="toggle">
      <input type="checkbox" id="startOnStartup">
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
      <input type="checkbox" id="startMinimized">
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
      <input type="checkbox" id="songLinkEnabled">
      <div class="toggle-track"></div>
      <div class="toggle-knob"></div>
    </label>
  </div>
</div>

<button class="save-btn" onclick="save()">Save Changes</button>

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

  async function save() {
    const mode = document.getElementById('idMode').value;
    const customId = document.getElementById('clientId').value.trim();

    if (mode === 'custom' && !customId) {
      document.getElementById('idError').style.display = 'block';
      return;
    }
    document.getElementById('idError').style.display = 'none';

    const data = {
      use_custom: mode === 'custom',
      client_id: customId,
      start_on_startup: document.getElementById('startOnStartup').checked,
      start_minimized: document.getElementById('startMinimized').checked,
      song_link_enabled: document.getElementById('songLinkEnabled').checked
    };

    await pywebview.api.save_settings(data);
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
    document.getElementById('songLinkEnabled').checked = !!cfg.song_link_enabled;
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

    def save_settings(self, data):
        use_custom = data.get("use_custom", False)
        client_id = data.get("client_id", "").strip() if use_custom else DEFAULT_CLIENT_ID

        config = {
            "discord_client_id": client_id,
            "use_custom_client_id": use_custom,
            "start_on_startup": bool(data.get("start_on_startup")),
            "start_minimized": bool(data.get("start_minimized")),
            "song_link_enabled": bool(data.get("song_link_enabled")),
        }
        save_config(config)
        set_startup(config["start_on_startup"])

        if self._on_save:
            self._on_save(config)

        window = self._window_ref()
        if window:
            window.destroy()


class SettingsWindow:
    def __init__(self, on_save_callback=None):
        self.on_save = on_save_callback
        self._window = None

    def show(self):
        html = HTML_TEMPLATE.replace("{icon_b64}", _icon_b64())

        window_holder = [None]
        api = _Api(self.on_save, lambda: window_holder[0])

        window_holder[0] = webview.create_window(
            "Amazon Music RPC",
            html=html,
            js_api=api,
            width=460,
            height=520,
            resizable=False,
            background_color="#202020",
        )
        self._window = window_holder[0]
        webview.start()


if __name__ == "__main__":
    SettingsWindow().show()
