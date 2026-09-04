# MIT License - Copyright (c) 2026 eripum9

import base64
import json
import threading

from amazon_devtools import _CdpSocket, _page_boot_state, _page_target, get_devtools_port


OVERLAY_VERSION = "2026.09.04.1"
OVERLAY_WORLD_NAME = "AmazonMusicRPC.StatusOverlay"
OVERLAY_READY_STABLE_POLLS = 3


def _clean(value):
    return " ".join(str(value or "").strip().split())


def _state_value(value, fallback="Waiting"):
    value = _clean(value)
    return value[:1].upper() + value[1:] if value else fallback


def _image_data_url(icon_path):
    with open(icon_path, "rb") as handle:
        return "data:image/png;base64," + base64.b64encode(handle.read()).decode("ascii")


def build_overlay_payload(config, diagnostics, running):
    config = config or {}
    diagnostics = diagnostics or {}
    privacy = diagnostics.get("privacy") if isinstance(diagnostics.get("privacy"), dict) else {}
    track = diagnostics.get("track") if isinstance(diagnostics.get("track"), dict) else {}
    devtools = diagnostics.get("amazon_devtools") if isinstance(diagnostics.get("amazon_devtools"), dict) else {}

    private = bool(config.get("privacy_private_session") or privacy.get("private_session"))
    track_status = _clean(track.get("status")).lower()
    discord_status = _clean(diagnostics.get("discord_status")).lower()
    devtools_status = _clean(devtools.get("status")).lower()

    if private:
        status_label = "Private"
        tone = "private"
    elif not running:
        status_label = "Paused"
        tone = "paused"
    elif track_status == "paused":
        status_label = "Paused"
        tone = "paused"
    elif discord_status and discord_status not in {"connected", "running"}:
        status_label = "Offline"
        tone = "offline"
    else:
        status_label = "ON"
        tone = "on"

    if devtools_status == "found":
        source = "DevTools DOM"
    elif devtools_status in {"waiting", "unavailable", "launching", "restarting", "error"}:
        source = "Fallback"
    else:
        source = "SMTC"

    return {
        "ok": True,
        "statusLabel": status_label,
        "tone": tone,
        "privacy": private,
        "diagnostics": [
            {"label": "RPC", "value": "Running" if running else "Stopped", "state": "ok" if running else "muted"},
            {"label": "Discord", "value": _state_value(discord_status, "Waiting"), "state": "ok" if discord_status == "connected" else "bad"},
            {
                "label": "DevTools",
                "value": _state_value(devtools_status, "Waiting"),
                "state": "ok" if devtools_status == "found" else "bad" if devtools_status == "error" else "muted",
            },
            {"label": "Source", "value": source, "state": "ok" if source == "DevTools DOM" else "muted"},
            {"label": "Privacy", "value": "Private" if private else "Standard", "state": "ok" if private else "muted"},
        ],
    }


class AmazonStatusOverlay:
    def __init__(self, icon_path, config_provider, diagnostics_provider, running_provider, set_privacy):
        self.icon_path = icon_path
        self.config_provider = config_provider
        self.diagnostics_provider = diagnostics_provider
        self.running_provider = running_provider
        self.set_privacy = set_privacy
        self._inject_thread = None
        self._stop_event = threading.Event()
        self._client = None
        self._context_id = None
        self._lock = threading.Lock()
        self._last_error = ""

    def start(self):
        with self._lock:
            if self._inject_thread and self._inject_thread.is_alive():
                return
            self._stop_event.clear()
            self._inject_thread = threading.Thread(target=self._run, name="amazon-status-overlay", daemon=False)
            self._inject_thread.start()

    def stop(self):
        self._stop_event.set()
        try:
            if self._client:
                self._remove_ui(self._client)
                self._client.close()
        except Exception:
            pass
        self._client = None
        if self._inject_thread and self._inject_thread is not threading.current_thread():
            self._inject_thread.join(timeout=5)
        self._inject_thread = None

    def status(self):
        return {
            "running": bool(self._inject_thread and self._inject_thread.is_alive()),
            "bridge_url": "",
            "port": None,
            "last_error": self._last_error,
        }

    def payload(self):
        return build_overlay_payload(
            self.config_provider(),
            self.diagnostics_provider(),
            self.running_provider(),
        )

    def apply_privacy(self, enabled):
        self.set_privacy(bool(enabled))
        return self.payload()

    def _run(self):
        last_target = None
        ready_target = None
        ready_polls = 0
        while not self._stop_event.is_set():
            try:
                target = _page_target()
                if not target:
                    self._close_client()
                    ready_target = None
                    ready_polls = 0
                    self._stop_event.wait(2)
                    continue
                port = get_devtools_port(False)
                readiness = _page_boot_state(port) if port else {"ready": False}
                target_id = target.get("id") or target.get("webSocketDebuggerUrl")
                if not readiness.get("ready"):
                    self._close_client()
                    ready_target = None
                    ready_polls = 0
                    self._stop_event.wait(1)
                    continue
                if target_id != ready_target:
                    ready_target = target_id
                    ready_polls = 1
                else:
                    ready_polls += 1
                if ready_polls < OVERLAY_READY_STABLE_POLLS:
                    self._stop_event.wait(1)
                    continue
                if not self._client or target_id != last_target:
                    self._close_client()
                    self._client = _CdpSocket(
                        target["webSocketDebuggerUrl"],
                        timeout=5,
                        expected_port=port,
                        expected_target_id=target.get("id", ""),
                    )
                    self._context_id = None
                    self._ensure_isolated_context(self._client)
                    last_target = target_id
                if not self._ui_present(self._client):
                    self._inject(self._client)
                self._consume_action(self._client)
                self._push_payload(self._client)
                self._stop_event.wait(1)
            except Exception as e:
                self._last_error = str(e)
                self._close_client()
                ready_target = None
                ready_polls = 0
                self._stop_event.wait(3)

    def _close_client(self):
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
        self._client = None
        self._context_id = None

    def _ensure_isolated_context(self, client):
        if self._context_id:
            return self._context_id
        client.request("Page.enable")
        tree = client.request("Page.getFrameTree")
        frame_id = (
            tree.get("result", {})
            .get("frameTree", {})
            .get("frame", {})
            .get("id")
        )
        if not frame_id:
            raise RuntimeError("Amazon status overlay could not resolve the main frame")
        created = client.request(
            "Page.createIsolatedWorld",
            {
                "frameId": frame_id,
                "worldName": OVERLAY_WORLD_NAME,
                "grantUniveralAccess": False,
            },
        )
        self._context_id = created.get("result", {}).get("executionContextId")
        if not self._context_id:
            raise RuntimeError("Amazon status overlay could not create an isolated world")
        return self._context_id

    def _evaluate(self, client, expression, await_promise=False):
        params = {
            "expression": expression,
            "returnByValue": True,
            "contextId": self._ensure_isolated_context(client),
        }
        if await_promise:
            params["awaitPromise"] = True
        return client.request("Runtime.evaluate", params)

    def _ui_present(self, client):
        expression = (
            "Boolean(document.getElementById('amrpc-status-button') "
            "&& window.__amrpcStatusOverlay "
            f"&& window.__amrpcStatusOverlay.version === {json.dumps(OVERLAY_VERSION)})"
        )
        response = self._evaluate(client, expression)
        return bool(response.get("result", {}).get("result", {}).get("value"))

    def _remove_ui(self, client):
        self._evaluate(
            client,
            "if(window.__amrpcStatusOverlay&&window.__amrpcStatusOverlay.stop)window.__amrpcStatusOverlay.stop();['amrpc-status-button','amrpc-status-menu','amrpc-status-style'].forEach(function(id){var node=document.getElementById(id);if(node&&node.parentElement)node.parentElement.removeChild(node);});delete window.__amrpcStatusOverlay;",
        )

    def _consume_action(self, client):
        response = self._evaluate(
            client,
            "(function(){var api=window.__amrpcStatusOverlay;return api&&api.consume?api.consume():null;})()",
        )
        action = response.get("result", {}).get("result", {}).get("value")
        if isinstance(action, dict) and action.get("type") == "privacy":
            self.apply_privacy(bool(action.get("enabled")))

    def _push_payload(self, client):
        payload = json.dumps(self.payload())
        self._evaluate(
            client,
            f"(function(data){{if(window.__amrpcStatusOverlay&&window.__amrpcStatusOverlay.render)window.__amrpcStatusOverlay.render(data);}})({payload})",
        )

    def _inject(self, client):
        script = self._script()
        response = self._evaluate(client, script, await_promise=True)
        result = response.get("result", {}).get("result", {})
        if result.get("subtype") == "error":
            raise RuntimeError(result.get("description") or "Amazon status overlay injection failed")
        value = result.get("value")
        if isinstance(value, dict) and not value.get("ok", False):
            raise RuntimeError(value.get("reason") or "Amazon status overlay injection failed")

    def _script(self):
        icon_src = _image_data_url(self.icon_path)
        initial_payload = self.payload()
        return f"""
(async function () {{
  var overlayVersion = {json.dumps(OVERLAY_VERSION)};
  var iconSrc = {json.dumps(icon_src)};
  var initialData = {json.dumps(initial_payload)};
  var wait = function (ms) {{ return new Promise(function (resolve) {{ setTimeout(resolve, ms); }}); }};
  var input = null;
  for (var attempt = 0; attempt < 80; attempt += 1) {{
    input = document.querySelector('input.searchBarInput') || document.querySelector('input[placeholder="Search"]');
    if (input) break;
    await wait(250);
  }}
  if (!input) return {{ ok: false, reason: 'search input not found' }};
  var searchContainer = input.closest('.searchBarContainer') || input.closest('.searchBar') || input.parentElement;
  if (!searchContainer) return {{ ok: false, reason: 'search container not found' }};
  ['amrpc-status-button', 'amrpc-status-menu', 'amrpc-status-style'].forEach(function (id) {{
    var node = document.getElementById(id);
    if (node && node.parentElement) node.parentElement.removeChild(node);
  }});
  var style = document.createElement('style');
  style.id = 'amrpc-status-style';
  style.textContent = `
    #amrpc-status-button {{
      height: 36px; min-width: 98px; margin-right: 10px; padding: 0 12px; border: 0; border-radius: 18px;
      background: rgba(30, 215, 96, .95); color: #08120c; display: inline-flex; align-items: center;
      justify-content: center; gap: 7px; font: 800 12px/1 "Segoe UI", sans-serif; letter-spacing: 0;
      white-space: nowrap; cursor: pointer; box-shadow: 0 0 0 1px rgba(255,255,255,.16), 0 8px 22px rgba(0,0,0,.28);
      position: fixed; z-index: 1000000;
    }}
    #amrpc-status-button[data-tone="private"] {{ background: rgba(88, 101, 242, .96); color: #fff; }}
    #amrpc-status-button[data-tone="paused"] {{ background: rgba(255, 209, 102, .96); color: #17110a; }}
    #amrpc-status-button[data-tone="offline"] {{ background: rgba(255, 77, 77, .96); color: #fff; }}
    #amrpc-status-button img {{ width: 18px; height: 18px; border-radius: 4px; object-fit: cover; flex: 0 0 auto; }}
    #amrpc-status-label {{ display: inline-block; min-width: 44px; text-align: left; }}
    #amrpc-status-menu {{
      position: fixed; width: 316px; padding: 12px; border-radius: 14px; background: rgba(22, 24, 28, .92);
      color: #fff; border: 1px solid rgba(255,255,255,.1); box-shadow: 0 18px 48px rgba(0,0,0,.45);
      z-index: 1000000; font: 13px/1.35 "Segoe UI", sans-serif; letter-spacing: 0;
    }}
    #amrpc-status-menu[hidden] {{ display: none; }}
    .amrpc-menu-head {{ display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 2px 2px 11px; }}
    .amrpc-menu-title {{ font-size: 14px; font-weight: 750; }}
    .amrpc-pill {{ min-width: 52px; padding: 3px 8px; border-radius: 999px; background: rgba(30, 215, 96, .18); color: #66f29a; font-size: 11px; font-weight: 800; text-align: center; }}
    .amrpc-privacy-row {{ display: flex; align-items: center; justify-content: space-between; gap: 14px; padding: 12px; border-radius: 10px; background: rgba(255,255,255,.065); border: 1px solid rgba(255,255,255,.06); }}
    .amrpc-row-label {{ font-weight: 650; color: rgba(255,255,255,.94); }}
    .amrpc-row-detail {{ margin-top: 2px; font-size: 11px; color: rgba(255,255,255,.58); }}
    .amrpc-toggle {{ position: relative; display: inline-block; width: 40px; height: 22px; flex: 0 0 auto; cursor: pointer; border-radius: 11px; background: rgba(255,255,255,.18); }}
    .amrpc-toggle[data-busy="1"] {{ cursor: wait; opacity: .72; }}
    .amrpc-toggle input {{ display: none; }}
    .amrpc-toggle-track {{ position: absolute; inset: 0; display: block; background: rgba(255,255,255,.22); border: 1px solid rgba(255,255,255,.32); border-radius: 11px; box-sizing: border-box; box-shadow: inset 0 1px 3px rgba(0,0,0,.42); transition: background .2s, border-color .2s; }}
    .amrpc-toggle-knob {{ position: absolute; top: 3px; left: 3px; width: 16px; height: 16px; background: #fff; border-radius: 50%; transition: transform .2s; pointer-events: none; z-index: 1; box-shadow: 0 1px 5px rgba(0,0,0,.42); }}
    .amrpc-toggle input:checked + .amrpc-toggle-track {{ background: #5865f2; border-color: rgba(255,255,255,.2); }}
    .amrpc-toggle input:checked ~ .amrpc-toggle-knob {{ transform: translateX(18px); }}
    .amrpc-diag {{ margin-top: 12px; padding-top: 12px; border-top: 1px solid rgba(255,255,255,.08); }}
    .amrpc-diag-title {{ margin-bottom: 8px; color: rgba(255,255,255,.62); font-size: 11px; font-weight: 800; text-transform: uppercase; }}
    .amrpc-diag-row {{ display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 6px 2px; color: rgba(255,255,255,.72); }}
    .amrpc-diag-row strong {{ color: rgba(255,255,255,.95); font-weight: 650; text-align: right; }}
    .amrpc-dot {{ width: 7px; height: 7px; border-radius: 50%; margin-right: 7px; display: inline-block; background: #1ed760; box-shadow: 0 0 12px rgba(30,215,96,.75); }}
    .amrpc-diag-row[data-state="bad"] .amrpc-dot {{ background: #ff4d4d; box-shadow: 0 0 12px rgba(255,77,77,.75); }}
    .amrpc-diag-row[data-state="muted"] .amrpc-dot {{ background: #8b8f98; box-shadow: none; }}
  `;
  document.head.appendChild(style);
  var button = document.createElement('button');
  button.id = 'amrpc-status-button';
  button.type = 'button';
  button.title = 'Amazon Music RPC';
  button.innerHTML = '<img src="' + iconSrc + '" alt=""><span id="amrpc-status-label">...</span>';
  var menu = document.createElement('div');
  menu.id = 'amrpc-status-menu';
  menu.hidden = true;
  menu.innerHTML = `
    <div class="amrpc-menu-head"><div class="amrpc-menu-title">Amazon Music RPC</div><div class="amrpc-pill" id="amrpc-menu-pill">...</div></div>
    <div class="amrpc-privacy-row">
      <div><div class="amrpc-row-label">Private session</div><div class="amrpc-row-detail">Hide Discord presence while enabled</div></div>
      <label class="amrpc-toggle"><input id="amrpc-privacy-toggle" type="checkbox"><span class="amrpc-toggle-track"></span><span class="amrpc-toggle-knob"></span></label>
    </div>
    <div class="amrpc-diag"><div class="amrpc-diag-title">Mini diagnostics</div><div id="amrpc-diag-list"></div></div>
  `;
  document.body.appendChild(button);
  document.body.appendChild(menu);
  var label = button.querySelector('#amrpc-status-label');
  var pill = menu.querySelector('#amrpc-menu-pill');
  var toggle = menu.querySelector('#amrpc-privacy-toggle');
  var toggleShell = toggle.parentElement;
  var diagList = menu.querySelector('#amrpc-diag-list');
  var privacyBusy = false;
  var nextAction = null;
  var escapeHtml = function (value) {{
    return String(value || '').replace(/[&<>"']/g, function (ch) {{
      return {{ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }}[ch];
    }});
  }};
  var setPrivacyBusy = function (busy) {{
    privacyBusy = !!busy;
    toggle.disabled = privacyBusy;
    toggleShell.dataset.busy = privacyBusy ? '1' : '0';
  }};
  var positionButton = function () {{
    var searchRect = searchContainer.getBoundingClientRect();
    var width = button.offsetWidth || 98;
    var top = searchRect.top + Math.max(0, (searchRect.height - 36) / 2);
    button.style.top = Math.max(8, Math.round(top)) + 'px';
    button.style.left = Math.max(12, Math.round(searchRect.left - width - 10)) + 'px';
  }};
  var positionMenu = function () {{
    positionButton();
    var rect = button.getBoundingClientRect();
    menu.style.top = Math.round(rect.bottom + 8) + 'px';
    menu.style.right = Math.max(12, Math.round(window.innerWidth - rect.right)) + 'px';
  }};
  var render = function (data) {{
    data = data || {{}};
    label.textContent = data.statusLabel || 'ERR';
    pill.textContent = data.statusLabel || 'ERR';
    button.dataset.tone = data.tone || 'offline';
    toggle.checked = !!data.privacy;
    setPrivacyBusy(false);
    diagList.innerHTML = (data.diagnostics || []).map(function (row) {{
      return '<div class="amrpc-diag-row" data-state="' + escapeHtml(row.state || 'ok') + '"><span><i class="amrpc-dot"></i>' + escapeHtml(row.label) + '</span><strong>' + escapeHtml(row.value) + '</strong></div>';
    }}).join('');
    positionButton();
  }};
  var openMenu = function () {{
    positionMenu();
    menu.hidden = false;
  }};
  var closeMenu = function () {{
    menu.hidden = true;
  }};
  button.addEventListener('click', function (event) {{
    if (!event.isTrusted) return;
    event.preventDefault();
    event.stopPropagation();
    if (event.stopImmediatePropagation) event.stopImmediatePropagation();
    if (menu.hidden) openMenu();
    else closeMenu();
  }}, true);
  toggle.addEventListener('click', function (event) {{
    if (!event.isTrusted) {{
      event.preventDefault();
      event.stopPropagation();
      return false;
    }}
    if (privacyBusy) {{
      event.preventDefault();
      event.stopPropagation();
      if (event.stopImmediatePropagation) event.stopImmediatePropagation();
      return false;
    }}
  }}, true);
  toggle.addEventListener('change', function (event) {{
    event.stopPropagation();
    if (!event.isTrusted || privacyBusy) return;
    setPrivacyBusy(true);
    label.textContent = '...';
    nextAction = {{ type: 'privacy', enabled: !!toggle.checked, at: Date.now() }};
  }}, true);
  menu.addEventListener('click', function (event) {{ event.stopPropagation(); }});
  document.addEventListener('click', function (event) {{
    if (!menu.hidden && !menu.contains(event.target) && !button.contains(event.target)) closeMenu();
  }});
  window.addEventListener('resize', function () {{
    if (menu.hidden) positionButton();
    else positionMenu();
  }});
  window.__amrpcStatusOverlay = {{
    version: overlayVersion,
    render: render,
    open: openMenu,
    close: closeMenu,
    stop: closeMenu,
    consume: function () {{ var action = nextAction; nextAction = null; return action; }}
  }};
  positionButton();
  render(initialData);
  var rect = button.getBoundingClientRect();
  return {{ ok: true, text: label.textContent, rect: {{ x: Math.round(rect.x), y: Math.round(rect.y), width: Math.round(rect.width), height: Math.round(rect.height) }} }};
}})()
"""
