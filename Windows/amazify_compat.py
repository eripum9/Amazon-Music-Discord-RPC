# MIT License - Copyright (c) 2026 eripum9

import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
import urllib.request
import winreg
from pathlib import Path
from urllib.parse import urlparse

from amazon_domains import AMAZON_WEBAPP_HOSTS


AMAZIFY_NAME = "Amazify"
AMAZIFY_EXE = "amazify.exe"
AMAZIFY_PLUGIN_ID = "amazon-music-rpc.bridge"
AMAZIFY_RPC_BRIDGE_PORT = 14797
AMAZIFY_DEVTOOLS_STATE = "devtools_state.json"
AMAZIFY_PLUGIN_STATE = "plugins_state.json"
AMAZIFY_LOG_PORT_RE = re.compile(r"(?:DevTools port|with DevTools port)\D+(\d{2,5})", re.IGNORECASE)
AMAZIFY_BRIDGE_TOKEN = "rpc_bridge.token"


def _appdata_base():
    return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")


def amazify_root():
    return _appdata_base() / AMAZIFY_NAME


def amazify_plugin_root():
    return amazify_root() / "plugins"


def amazify_bridge_token():
    path = amazify_root() / AMAZIFY_BRIDGE_TOKEN
    if path.exists():
        try:
            value = path.read_text(encoding="ascii").strip().lower()
        except OSError:
            value = ""
        if re.fullmatch(r"[a-f0-9]{64}", value):
            return value
    value = secrets.token_hex(32)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(value, encoding="ascii")
    temporary.replace(path)
    return value


def _local_install_path():
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        return None
    path = Path(local) / "Programs" / AMAZIFY_NAME / AMAZIFY_EXE
    return path if path.exists() else None


def _registry_install_path():
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Amazify"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            values = {}
            for name in ("InstallLocation", "DisplayIcon", "UninstallString"):
                try:
                    values[name] = winreg.QueryValueEx(key, name)[0]
                except OSError:
                    pass
    except OSError:
        return None
    candidates = []
    location = str(values.get("InstallLocation") or "").strip().strip('"')
    if location:
        candidates.append(Path(location) / AMAZIFY_EXE)
    for name in ("DisplayIcon", "UninstallString"):
        raw = str(values.get(name) or "").strip()
        if raw:
            cleaned = raw.strip('"')
            if cleaned.lower().endswith(".exe"):
                candidates.append(Path(cleaned))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def detect_amazify_install():
    candidates = [_local_install_path(), _registry_install_path()]
    found = next((path for path in candidates if path and path.exists()), None)
    if found:
        return {"installed": True, "path": str(found), "source": "install"}
    found_on_path = shutil.which(AMAZIFY_EXE)
    if found_on_path:
        return {"installed": True, "path": found_on_path, "source": "path"}
    if amazify_root().exists():
        return {"installed": True, "path": "", "source": "appdata"}
    return {"installed": False, "path": "", "source": ""}


def amazify_is_running():
    try:
        completed = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {AMAZIFY_EXE}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=2,
            creationflags=0x08000000,
        )
    except Exception:
        return False
    output = completed.stdout.lower()
    return AMAZIFY_EXE.lower() in output and "no tasks" not in output


def _devtools_state_ports():
    path = amazify_root() / AMAZIFY_DEVTOOLS_STATE
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    port = data.get("last_port") if isinstance(data, dict) else None
    try:
        value = int(port)
    except (TypeError, ValueError):
        return []
    return [value] if 0 < value < 65536 else []


def _log_ports(limit=10):
    log_dir = amazify_root() / "logs"
    if not log_dir.exists():
        return []
    try:
        files = sorted(log_dir.glob("*.log"), key=lambda item: item.stat().st_mtime, reverse=True)[:limit]
    except OSError:
        return []
    ports = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")[-20000:]
        except OSError:
            continue
        for match in AMAZIFY_LOG_PORT_RE.finditer(text):
            try:
                port = int(match.group(1))
            except ValueError:
                continue
            if 0 < port < 65536 and port not in ports:
                ports.append(port)
    return ports


def recent_amazify_devtools_ports():
    ports = []
    for port in [*_devtools_state_ports(), *_log_ports()]:
        if port not in ports:
            ports.append(port)
    return ports


def _read_json_url(url, timeout=0.25):
    request = urllib.request.Request(url, headers={"User-Agent": "AmazonMusicRPC-AmazifyCompat"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def _is_amazon_target(target):
    if not isinstance(target, dict) or target.get("type") != "page":
        return False
    title = str(target.get("title") or "").lower()
    parsed = urlparse(str(target.get("url") or ""))
    host = (parsed.hostname or "").lower()
    try:
        port = parsed.port
    except ValueError:
        return False
    return bool(
        "amazon music" in title
        and parsed.scheme.lower() == "https"
        and host in AMAZON_WEBAPP_HOSTS
        and port in (None, 443)
        and not parsed.username
        and not parsed.password
    )


def valid_amazify_devtools_port(port, timeout=0.25):
    try:
        port = int(port)
    except (TypeError, ValueError):
        return False
    if not 0 < port < 65536:
        return False
    try:
        targets = _read_json_url(f"http://127.0.0.1:{port}/json/list", timeout=timeout)
    except Exception:
        return False
    return isinstance(targets, list) and any(_is_amazon_target(target) for target in targets)


def discover_amazify_devtools_port(max_ports=3, timeout=0.25):
    for port in recent_amazify_devtools_ports()[:max(1, int(max_ports))]:
        if valid_amazify_devtools_port(port, timeout=timeout):
            return port
    return 0


def _plugin_dir():
    return amazify_plugin_root() / AMAZIFY_PLUGIN_ID


def _plugin_manifest(version):
    return {
        "id": AMAZIFY_PLUGIN_ID,
        "name": "Amazon Music RPC Bridge",
        "version": str(version or "0.0.0"),
        "author": "Amazon Music RPC",
        "type": "ui",
        "description": "Adds the Amazon Music RPC status and controls inside Amazify.",
        "entry": "plugin.js",
        "styles": ["style.css"],
        "assets": {"icon": "icon.png"},
        "permissions": ["dom-write", "dom-style"],
        "amazonMusic": {
            "target": "desktop",
            "integration": "amazify",
        },
    }


def _rpc_icon_path():
    if getattr(sys, "frozen", False):
        bundle = Path(getattr(sys, "_MEIPASS", ""))
        path = bundle / "icon.png"
        if path.exists():
            return path
    path = Path(__file__).with_name("icon.png")
    return path if path.exists() else None


def _plugin_js(token=None):
    token = str(token or amazify_bridge_token())
    return f"""
const RPC_PORT = {AMAZIFY_RPC_BRIDGE_PORT};
const RPC_TOKEN = {json.dumps(token)};
const ROOT_ID = "amrpc-amazify-panel";
const iconSrc = source && typeof source.assetUrl === "function"
  ? source.assetUrl("icon")
  : (Amazify.assets && typeof Amazify.assets.url === "function" ? Amazify.assets.url(manifest.id, "icon") : "");
let latestState = null;
let panel = null;
let refreshTimer = null;

const button = Amazify.ui.addHeaderAction(manifest.id, "RPC", () => {{
  togglePanel();
}});

button.classList.add("amrpc-amazify-button");
button.title = "Amazon Music RPC";
button.setAttribute("aria-label", "Amazon Music RPC");
button.innerHTML = `${{iconSrc ? `<img src="${{iconSrc}}" alt="">` : ""}}<span class="amrpc-status-label">...</span>`;
const buttonLabel = button.querySelector(".amrpc-status-label");

window.__amrpcAmazifyBridge = {{
  version: 1,
  receiveState: (data) => {{
    latestState = data && typeof data === "object" ? data : {{ ok: false }};
    render();
    return true;
  }}
}};

function clean(value) {{
  return String(value || "").replace(/\\s+/g, " ").trim();
}}

function esc(value) {{
  return clean(value).replace(/[&<>"']/g, (char) => ({{ "&": "&amp;", "<": "&lt;", ">": "&gt;", "\\"": "&quot;", "'": "&#039;" }}[char]));
}}

async function rpcFetch(path, options) {{
  const supplied = options || {{}};
  const response = await fetch(`http://127.0.0.1:${{RPC_PORT}}${{path}}`, {{
    cache: "no-store",
    ...supplied,
    headers: {{ "X-Amazon-Music-RPC-Token": RPC_TOKEN, ...(supplied.headers || {{}}) }}
  }});
  if (!response.ok) throw new Error(`RPC bridge ${{response.status}}`);
  return await response.json();
}}

async function loadState() {{
  try {{
    latestState = await rpcFetch("/state");
    render();
  }} catch (error) {{
    if (!latestState) {{
      latestState = {{ ok: false, error: clean(error.message || error), waitingForPush: true }};
    }}
    render();
  }}
}}

function snapshot() {{
  return (latestState && latestState.snapshot) || {{}};
}}

function statusText() {{
  const data = snapshot();
  if (!latestState || latestState.waitingForPush) return "Waiting";
  if (latestState.ok === false) return "Offline";
  if (data.presence === "Private") return "Private";
  if (data.source === "Paused") return "Paused";
  if (data.rpc === "On") return "ON";
  return "Offline";
}}

function tone() {{
  const text = statusText();
  if (text === "Private") return "private";
  if (text === "Paused") return "paused";
  if (text === "Waiting") return "waiting";
  if (text === "ON") return "ok";
  return "offline";
}}

function renderButton() {{
  const text = statusText();
  if (buttonLabel) buttonLabel.textContent = text;
  button.dataset.tone = tone();
}}

function ensurePanel() {{
  if (panel) return panel;
  panel = document.createElement("div");
  panel.id = ROOT_ID;
  panel.dataset.amazifyPluginId = manifest.id;
  document.body.appendChild(panel);
  document.addEventListener("click", (event) => {{
    if (!panel || panel.hidden) return;
    if (panel.contains(event.target) || button.contains(event.target)) return;
    hidePanel();
  }}, true);
  document.addEventListener("keydown", (event) => {{
    if (event.key === "Escape") hidePanel();
  }});
  return panel;
}}

function diagnosticRows(data) {{
  const rows = [
    ["RPC", data.rpc || "Off", data.rpc === "On" ? "ok" : "bad"],
    ["Discord", data.discord || "Waiting", data.discord === "Connected" ? "ok" : "warn"],
    ["DevTools", data.devtools_status || "Waiting", data.devtools_status === "Found" ? "ok" : "muted"],
    ["Source", data.source || "Waiting", data.source === "Waiting" ? "warn" : "ok"],
    ["Privacy", data.presence || "Hidden", data.presence === "Private" ? "warn" : "muted"]
  ];
  return rows.map((row) => `<div class="amrpc-diag-row" data-state="${{esc(row[2])}}"><span><i class="amrpc-dot"></i>${{esc(row[0])}}</span><strong>${{esc(row[1])}}</strong></div>`).join("");
}}

function render() {{
  renderButton();
  if (!panel || panel.hidden) return;
  const data = snapshot();
  panel.innerHTML = `
    <div class="amrpc-menu-head">
      <div><div class="amrpc-menu-title">Amazon Music RPC</div><div class="amrpc-menu-origin">Amazify integration</div></div>
      <div class="amrpc-pill">${{esc(statusText())}}</div>
    </div>
    <div class="amrpc-privacy-row">
      <div><div class="amrpc-row-label">Private session</div><div class="amrpc-row-detail">Hide Discord presence while enabled</div></div>
      <label class="amrpc-toggle"><input id="amrpc-amazify-privacy-toggle" type="checkbox" ${{data.private ? "checked" : ""}}><span class="amrpc-toggle-track"></span><span class="amrpc-toggle-knob"></span></label>
    </div>
    <div class="amrpc-diag"><div class="amrpc-diag-title">Mini diagnostics</div>${{diagnosticRows(data)}}</div>
  `;
  const toggle = panel.querySelector("#amrpc-amazify-privacy-toggle");
  if (toggle) {{
    toggle.addEventListener("change", async () => {{
      await sendCommand("private");
      await loadState();
    }});
  }}
}}

async function sendCommand(command) {{
  await rpcFetch("/command", {{
    method: "POST",
    headers: {{ "Content-Type": "application/json" }},
    body: JSON.stringify({{ command }})
  }});
}}

function showPanel() {{
  ensurePanel();
  panel.hidden = false;
  loadState();
}}

function hidePanel() {{
  if (panel) panel.hidden = true;
}}

function togglePanel() {{
  ensurePanel();
  if (panel.hidden === false) {{
    hidePanel();
  }} else {{
    showPanel();
  }}
}}

loadState();
refreshTimer = window.setInterval(loadState, 2500);

return () => {{
  window.clearInterval(refreshTimer);
  if (panel) panel.remove();
}};
""".strip()


def _plugin_css():
    return """
.amrpc-amazify-button {
  height: 36px !important;
  min-width: 98px !important;
  margin-right: 10px !important;
  padding: 0 12px !important;
  border: 0 !important;
  border-radius: 18px !important;
  background: rgba(30, 215, 96, .95) !important;
  color: #08120c !important;
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  gap: 7px !important;
  font: 800 12px/1 "Segoe UI", sans-serif !important;
  letter-spacing: 0 !important;
  white-space: nowrap !important;
  cursor: pointer !important;
  box-shadow: 0 0 0 1px rgba(255,255,255,.16), 0 8px 22px rgba(0,0,0,.28) !important;
}

.amrpc-amazify-button[data-tone="private"] {
  background: rgba(88, 101, 242, .96) !important;
  color: #fff !important;
}

.amrpc-amazify-button[data-tone="paused"] {
  background: rgba(255, 209, 102, .96) !important;
  color: #17110a !important;
}

.amrpc-amazify-button[data-tone="waiting"] {
  background: rgba(139, 143, 152, .96) !important;
  color: #fff !important;
}

.amrpc-amazify-button[data-tone="offline"] {
  background: rgba(255, 77, 77, .96) !important;
  color: #fff !important;
}

.amrpc-amazify-button img {
  width: 18px !important;
  height: 18px !important;
  border-radius: 4px !important;
  object-fit: cover !important;
  flex: 0 0 auto !important;
}

.amrpc-amazify-button .amrpc-status-label {
  display: inline-block !important;
  min-width: 44px !important;
  text-align: left !important;
}

#amrpc-amazify-panel {
  position: fixed;
  top: 76px;
  right: 22px;
  width: 316px;
  z-index: 1000000;
  background: rgba(22, 24, 28, .92);
  border: 1px solid rgba(255,255,255,.1);
  border-radius: 14px;
  box-shadow: 0 18px 48px rgba(0,0,0,.45);
  color: #fff;
  font: 13px/1.35 "Segoe UI", sans-serif;
  letter-spacing: 0;
  padding: 12px;
}

#amrpc-amazify-panel[hidden] {
  display: none !important;
}

#amrpc-amazify-panel .amrpc-menu-head,
#amrpc-amazify-panel .amrpc-diag-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

#amrpc-amazify-panel .amrpc-menu-head {
  padding: 2px 2px 11px;
}

#amrpc-amazify-panel .amrpc-menu-title {
  font-size: 14px;
  font-weight: 750;
}

#amrpc-amazify-panel .amrpc-menu-origin {
  margin-top: 2px;
  color: rgba(255,255,255,.55);
  font-size: 11px;
  font-weight: 650;
}

#amrpc-amazify-panel .amrpc-pill {
  min-width: 52px;
  padding: 3px 8px;
  border-radius: 999px;
  background: rgba(30, 215, 96, .18);
  color: #66f29a;
  font-size: 11px;
  font-weight: 800;
  text-align: center;
}

#amrpc-amazify-panel .amrpc-privacy-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 12px;
  border-radius: 10px;
  background: rgba(255,255,255,.065);
  border: 1px solid rgba(255,255,255,.06);
}

#amrpc-amazify-panel .amrpc-row-label {
  font-weight: 650;
  color: rgba(255,255,255,.94);
}

#amrpc-amazify-panel .amrpc-row-detail {
  margin-top: 2px;
  font-size: 11px;
  color: rgba(255,255,255,.58);
}

#amrpc-amazify-panel .amrpc-toggle {
  position: relative;
  display: inline-block;
  width: 40px;
  height: 22px;
  flex: 0 0 auto;
  cursor: pointer;
  border-radius: 11px;
  background: rgba(255,255,255,.18);
}

#amrpc-amazify-panel .amrpc-toggle input {
  display: none;
}

#amrpc-amazify-panel .amrpc-toggle-track {
  position: absolute;
  inset: 0;
  display: block;
  background: rgba(255,255,255,.22);
  border: 1px solid rgba(255,255,255,.32);
  border-radius: 11px;
  box-sizing: border-box;
  box-shadow: inset 0 1px 3px rgba(0,0,0,.42);
  transition: background .2s, border-color .2s;
}

#amrpc-amazify-panel .amrpc-toggle-knob {
  position: absolute;
  top: 3px;
  left: 3px;
  width: 16px;
  height: 16px;
  background: #fff;
  border-radius: 50%;
  transition: transform .2s;
  pointer-events: none;
  z-index: 1;
  box-shadow: 0 1px 5px rgba(0,0,0,.42);
}

#amrpc-amazify-panel .amrpc-toggle input:checked + .amrpc-toggle-track {
  background: #5865f2;
  border-color: rgba(255,255,255,.2);
}

#amrpc-amazify-panel .amrpc-toggle input:checked ~ .amrpc-toggle-knob {
  transform: translateX(18px);
}

#amrpc-amazify-panel .amrpc-diag {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid rgba(255,255,255,.08);
}

#amrpc-amazify-panel .amrpc-diag-title {
  margin-bottom: 8px;
  color: rgba(255,255,255,.62);
  font-size: 11px;
  font-weight: 800;
  text-transform: uppercase;
}

#amrpc-amazify-panel .amrpc-diag-row {
  padding: 6px 2px;
  color: rgba(255,255,255,.72);
}

#amrpc-amazify-panel .amrpc-diag-row strong {
  color: rgba(255,255,255,.95);
  font-weight: 650;
  text-align: right;
}

#amrpc-amazify-panel .amrpc-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  margin-right: 7px;
  display: inline-block;
  background: #1ed760;
  box-shadow: 0 0 12px rgba(30,215,96,.75);
}

#amrpc-amazify-panel .amrpc-diag-row[data-state="bad"] .amrpc-dot {
  background: #ff4d4d;
  box-shadow: 0 0 12px rgba(255,77,77,.75);
}

#amrpc-amazify-panel .amrpc-diag-row[data-state="muted"] .amrpc-dot {
  background: #8b8f98;
  box-shadow: none;
}

#amrpc-amazify-panel .amrpc-diag-row[data-state="warn"] .amrpc-dot {
  background: #ffd166;
  box-shadow: 0 0 12px rgba(255,209,102,.65);
}
""".strip()


def _write_json_atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def push_rpc_state_to_amazify(port, payload):
    try:
        from amazon_devtools import _CdpSocket, _page_target
        target = _page_target(port=port)
        if not target:
            return False
        client = _CdpSocket(
            target["webSocketDebuggerUrl"],
            expected_port=port,
            expected_target_id=target.get("id", ""),
        )
        try:
            expression = (
                "(()=>{const bridge=window.__amrpcAmazifyBridge;"
                "if(!bridge||typeof bridge.receiveState!=='function')return false;"
                f"return bridge.receiveState({json.dumps(payload)});"
                "})()"
            )
            response = client.request("Runtime.evaluate", {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": False,
                "timeout": 1000,
            })
            return bool(response.get("result", {}).get("result", {}).get("value"))
        finally:
            client.close()
    except Exception:
        return False


def _read_plugin_state():
    path = amazify_root() / AMAZIFY_PLUGIN_STATE
    if not path.exists():
        return {"enabled": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"enabled": {}}
    if not isinstance(data, dict):
        return {"enabled": {}}
    if not isinstance(data.get("enabled"), dict):
        data["enabled"] = {}
    return data


def plugin_installed():
    root = _plugin_dir()
    return (root / "manifest.json").exists() and (root / "plugin.js").exists()


def plugin_enabled():
    state = _read_plugin_state()
    return bool(state.get("enabled", {}).get(AMAZIFY_PLUGIN_ID))


def install_rpc_plugin(version, enable=True):
    install = detect_amazify_install()
    if not install.get("installed"):
        return {"ok": False, "reason": "Amazify is not installed", "installed": False}
    root = _plugin_dir()
    root.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(root / "manifest.json", _plugin_manifest(version))
    (root / "plugin.js").write_text(_plugin_js(), encoding="utf-8")
    (root / "style.css").write_text(_plugin_css(), encoding="utf-8")
    icon_path = _rpc_icon_path()
    if icon_path:
        shutil.copyfile(icon_path, root / "icon.png")
    if enable:
        state = _read_plugin_state()
        state.setdefault("enabled", {})[AMAZIFY_PLUGIN_ID] = True
        _write_json_atomic(amazify_root() / AMAZIFY_PLUGIN_STATE, state)
    return {
        "ok": True,
        "installed": True,
        "plugin_installed": True,
        "plugin_enabled": plugin_enabled(),
        "plugin_dir": str(root),
    }


def remove_rpc_plugin():
    removed = True
    root = _plugin_dir()
    try:
        if root.exists():
            shutil.rmtree(root)
    except OSError:
        removed = False
    state_path = amazify_root() / AMAZIFY_PLUGIN_STATE
    if state_path.exists():
        try:
            state = _read_plugin_state()
            state.setdefault("enabled", {}).pop(AMAZIFY_PLUGIN_ID, None)
            _write_json_atomic(state_path, state)
        except OSError:
            removed = False
    try:
        (amazify_root() / AMAZIFY_BRIDGE_TOKEN).unlink(missing_ok=True)
    except OSError:
        removed = False
    return removed


def amazify_compat_state(version=None):
    install = detect_amazify_install()
    running = amazify_is_running()
    port = discover_amazify_devtools_port(4 if running else 1, 0.25 if running else 0.12)
    return {
        "installed": bool(install.get("installed")),
        "install_path": install.get("path", ""),
        "install_source": install.get("source", ""),
        "running": bool(running or port),
        "devtools_port": port,
        "plugin_id": AMAZIFY_PLUGIN_ID,
        "plugin_installed": plugin_installed(),
        "plugin_enabled": plugin_enabled(),
        "rpc_bridge_port": AMAZIFY_RPC_BRIDGE_PORT,
        "version": str(version or ""),
    }


def ensure_amazify_compat(version):
    state = amazify_compat_state(version)
    if not state.get("installed"):
        return {**state, "ok": False, "reason": "Amazify is not installed"}
    result = install_rpc_plugin(version, enable=True)
    time.sleep(0.02)
    return {**amazify_compat_state(version), "ok": bool(result.get("ok")), "reason": result.get("reason", "")}
