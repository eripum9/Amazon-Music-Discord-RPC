import base64
import datetime as dt
import ipaddress
import json
import os
import secrets
import socket
import ssl
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from amazon_devtools import _CdpSocket, _page_target


OVERLAY_VERSION = "2026.05.15.2"


class _OverlayServer(ThreadingHTTPServer):
    allow_reuse_address = True


def _clean(value):
    return " ".join(str(value or "").strip().split())


def _state_value(value, fallback="Waiting"):
    value = _clean(value)
    return value[:1].upper() + value[1:] if value else fallback


def _pick_port():
    for port in range(17680, 17730):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind(("127.0.0.1", port))
                return port
            except OSError:
                pass
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _make_certificate(base_dir):
    cert_path = os.path.join(base_dir, "localhost.pem")
    key_path = os.path.join(base_dir, "localhost-key.pem")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = dt.datetime.now(dt.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=7))
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName("localhost"),
                    x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
                ]
            ),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    with open(cert_path, "wb") as handle:
        handle.write(cert.public_bytes(serialization.Encoding.PEM))
    with open(key_path, "wb") as handle:
        handle.write(
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
    return cert_path, key_path


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

    diagnostics_rows = [
        {
            "label": "RPC",
            "value": "Running" if running else "Stopped",
            "state": "ok" if running else "muted",
        },
        {
            "label": "Discord",
            "value": _state_value(discord_status, "Waiting"),
            "state": "ok" if discord_status == "connected" else "bad",
        },
        {
            "label": "DevTools",
            "value": _state_value(devtools_status, "Waiting"),
            "state": "ok" if devtools_status == "found" else "bad" if devtools_status == "error" else "muted",
        },
        {
            "label": "Source",
            "value": source,
            "state": "ok" if source == "DevTools DOM" else "muted",
        },
        {
            "label": "Privacy",
            "value": "Private" if private else "Standard",
            "state": "ok" if private else "muted",
        },
    ]

    return {
        "ok": True,
        "statusLabel": status_label,
        "tone": tone,
        "privacy": private,
        "diagnostics": diagnostics_rows,
    }


class AmazonStatusOverlay:
    def __init__(self, icon_path, config_provider, diagnostics_provider, running_provider, set_privacy):
        self.icon_path = icon_path
        self.config_provider = config_provider
        self.diagnostics_provider = diagnostics_provider
        self.running_provider = running_provider
        self.set_privacy = set_privacy
        self.token = secrets.token_urlsafe(24)
        self.port = None
        self.bridge_url = ""
        self._server = None
        self._server_thread = None
        self._inject_thread = None
        self._stop_event = threading.Event()
        self._client = None
        self._lock = threading.Lock()
        self._last_error = ""

    def start(self):
        with self._lock:
            if self._inject_thread and self._inject_thread.is_alive():
                return
            self._stop_event.clear()
            self._start_bridge()
            self._inject_thread = threading.Thread(target=self._run, daemon=True)
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
        if self._server:
            try:
                self._server.shutdown()
                self._server.server_close()
            except Exception:
                pass
        self._server = None

    def status(self):
        return {
            "running": bool(self._inject_thread and self._inject_thread.is_alive()),
            "bridge_url": self.bridge_url,
            "port": self.port,
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

    def _start_bridge(self):
        if self._server:
            return
        base_dir = os.path.join(tempfile.gettempdir(), "amrpc_status_overlay")
        os.makedirs(base_dir, exist_ok=True)
        cert_path, key_path = _make_certificate(base_dir)
        self.port = _pick_port()
        self.bridge_url = f"https://localhost:{self.port}"
        service = self

        class Handler(BaseHTTPRequestHandler):
            def cors(self):
                origin = self.headers.get("Origin") or "*"
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
                self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.send_header("Access-Control-Allow-Private-Network", "true")
                self.send_header("Cache-Control", "no-store")

            def send_json(self, status, payload):
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.cors()
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def valid(self, query):
                return query.get("token", [""])[0] == service.token

            def do_OPTIONS(self):
                self.send_response(204)
                self.cors()
                self.end_headers()

            def do_GET(self):
                parsed = urlparse(self.path)
                query = parse_qs(parsed.query)
                if not self.valid(query):
                    self.send_json(403, {"ok": False, "error": "forbidden"})
                    return
                if parsed.path == "/status":
                    self.send_json(200, service.payload())
                    return
                if parsed.path == "/privacy":
                    enabled = query.get("enabled", [""])[0].lower() in {"1", "true", "yes", "on"}
                    self.send_json(200, service.apply_privacy(enabled))
                    return
                self.send_json(404, {"ok": False, "error": "not_found"})

            def log_message(self, _format, *args):
                return

        self._server = _OverlayServer(("127.0.0.1", self.port), Handler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert_path, key_path)
        self._server.socket = context.wrap_socket(self._server.socket, server_side=True)
        self._server_thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._server_thread.start()

    def _run(self):
        last_target = None
        while not self._stop_event.is_set():
            try:
                target = _page_target()
                if not target:
                    self._close_client()
                    time.sleep(2)
                    continue
                target_id = target.get("id") or target.get("webSocketDebuggerUrl")
                if not self._client or target_id != last_target:
                    self._close_client()
                    self._client = _CdpSocket(target["webSocketDebuggerUrl"], timeout=5)
                    last_target = target_id
                    self._client.request("Security.enable")
                    self._client.request("Security.setIgnoreCertificateErrors", {"ignore": True})
                    self._client.request("Page.setBypassCSP", {"enabled": True})
                self._client.request("Security.setIgnoreCertificateErrors", {"ignore": True})
                if not self._ui_present(self._client):
                    self._inject(self._client)
                time.sleep(4)
            except Exception as e:
                self._last_error = str(e)
                self._close_client()
                time.sleep(3)

    def _close_client(self):
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
        self._client = None

    def _ui_present(self, client):
        expression = (
            "Boolean(document.getElementById('amrpc-status-button') "
            "&& window.__amrpcStatusOverlay "
            f"&& window.__amrpcStatusOverlay.version === {json.dumps(OVERLAY_VERSION)} "
            "&& window.__amrpcStatusOverlay.bridgeUrl === "
            f"{json.dumps(self.bridge_url)})"
        )
        response = client.request(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
            },
        )
        return bool(response.get("result", {}).get("result", {}).get("value"))

    def _remove_ui(self, client):
        client.request(
            "Runtime.evaluate",
            {
                "expression": "['amrpc-status-button','amrpc-status-menu','amrpc-status-style'].forEach(function(id){var node=document.getElementById(id);if(node&&node.parentElement)node.parentElement.removeChild(node);});delete window.__amrpcStatusOverlay;",
                "returnByValue": True,
            },
        )

    def _inject(self, client):
        script = self._script()
        response = client.request(
            "Runtime.evaluate",
            {
                "expression": script,
                "returnByValue": True,
                "awaitPromise": True,
            },
        )
        result = response.get("result", {}).get("result", {})
        if result.get("subtype") == "error":
            raise RuntimeError(result.get("description") or "Amazon status overlay injection failed")
        value = result.get("value")
        if isinstance(value, dict) and not value.get("ok", False):
            raise RuntimeError(value.get("reason") or "Amazon status overlay injection failed")

    def _script(self):
        bridge_url = self.bridge_url
        token = self.token
        icon_src = _image_data_url(self.icon_path)
        return f"""
(async function () {{
  var bridgeUrl = {json.dumps(bridge_url)};
  var token = {json.dumps(token)};
  var overlayVersion = {json.dumps(OVERLAY_VERSION)};
  var iconSrc = {json.dumps(icon_src)};
  var wait = function (ms) {{ return new Promise(function (resolve) {{ setTimeout(resolve, ms); }}); }};
  var input = null;
  for (var attempt = 0; attempt < 80; attempt += 1) {{
    input = document.querySelector('input.searchBarInput') || document.querySelector('input[placeholder="Search"]');
    if (input) break;
    await wait(250);
  }}
  if (!input) return {{ ok: false, reason: 'search input not found' }};
  var searchContainer = input.closest('.searchBarContainer') || input.closest('.searchBar') || input.parentElement;
  var parent = searchContainer && searchContainer.parentElement;
  if (!searchContainer || !parent) return {{ ok: false, reason: 'search container not found' }};
  ['amrpc-status-button', 'amrpc-status-menu', 'amrpc-status-style'].forEach(function (id) {{
    var node = document.getElementById(id);
    if (node && node.parentElement) node.parentElement.removeChild(node);
  }});
  var style = document.createElement('style');
  style.id = 'amrpc-status-style';
  style.textContent = `
    #amrpc-status-button {{
      height: 36px;
      min-width: 98px;
      margin-right: 10px;
      padding: 0 12px;
      border: 0;
      border-radius: 18px;
      background: rgba(30, 215, 96, .95);
      color: #08120c;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 7px;
      font: 800 12px/1 "Segoe UI", sans-serif;
      letter-spacing: 0;
      white-space: nowrap;
      cursor: pointer;
      box-shadow: 0 0 0 1px rgba(255,255,255,.16), 0 8px 22px rgba(0,0,0,.28);
      position: relative;
      z-index: 80;
    }}
    #amrpc-status-button[data-tone="private"] {{ background: rgba(88, 101, 242, .96); color: #fff; }}
    #amrpc-status-button[data-tone="paused"] {{ background: rgba(255, 209, 102, .96); color: #17110a; }}
    #amrpc-status-button[data-tone="offline"] {{ background: rgba(255, 77, 77, .96); color: #fff; }}
    #amrpc-status-button img {{
      width: 18px;
      height: 18px;
      border-radius: 4px;
      object-fit: cover;
      flex: 0 0 auto;
    }}
    #amrpc-status-label {{
      display: inline-block;
      min-width: 44px;
      text-align: left;
    }}
    #amrpc-status-menu {{
      position: fixed;
      width: 316px;
      padding: 12px;
      border-radius: 14px;
      background: rgba(22, 24, 28, .9);
      color: #fff;
      border: 1px solid rgba(255,255,255,.1);
      box-shadow: 0 18px 48px rgba(0,0,0,.45);
      backdrop-filter: blur(18px);
      -webkit-backdrop-filter: blur(18px);
      z-index: 1000000;
      font: 13px/1.35 "Segoe UI", sans-serif;
      letter-spacing: 0;
    }}
    #amrpc-status-menu[hidden] {{ display: none; }}
    .amrpc-menu-head {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 2px 2px 11px;
    }}
    .amrpc-menu-title {{
      font-size: 14px;
      font-weight: 750;
    }}
    .amrpc-pill {{
      min-width: 52px;
      padding: 3px 8px;
      border-radius: 999px;
      background: rgba(30, 215, 96, .18);
      color: #66f29a;
      font-size: 11px;
      font-weight: 800;
      text-align: center;
    }}
    .amrpc-privacy-row {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 14px;
      padding: 12px;
      border-radius: 10px;
      background: rgba(255,255,255,.065);
      border: 1px solid rgba(255,255,255,.06);
    }}
    .amrpc-row-label {{
      font-weight: 650;
      color: rgba(255,255,255,.94);
    }}
    .amrpc-row-detail {{
      margin-top: 2px;
      font-size: 11px;
      color: rgba(255,255,255,.58);
    }}
    .amrpc-toggle {{
      position: relative;
      display: inline-block;
      width: 40px;
      height: 22px;
      flex: 0 0 auto;
      cursor: pointer;
      border-radius: 11px;
      background: rgba(255,255,255,.18);
    }}
    .amrpc-toggle[data-busy="1"] {{
      cursor: wait;
      opacity: .72;
    }}
    .amrpc-toggle input {{
      display: none;
    }}
    .amrpc-toggle-track {{
      position: absolute;
      inset: 0;
      display: block;
      background: rgba(255,255,255,.22);
      border: 1px solid rgba(255,255,255,.32);
      border-radius: 11px;
      box-sizing: border-box;
      box-shadow: inset 0 1px 3px rgba(0,0,0,.42);
      transition: background .2s, border-color .2s;
    }}
    .amrpc-toggle-knob {{
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
    }}
    .amrpc-toggle input:checked + .amrpc-toggle-track {{
      background: #5865f2;
      border-color: rgba(255,255,255,.2);
    }}
    .amrpc-toggle input:checked ~ .amrpc-toggle-knob {{
      transform: translateX(18px);
    }}
    .amrpc-diag {{
      margin-top: 12px;
      padding-top: 12px;
      border-top: 1px solid rgba(255,255,255,.08);
    }}
    .amrpc-diag-title {{
      margin-bottom: 8px;
      color: rgba(255,255,255,.62);
      font-size: 11px;
      font-weight: 800;
      text-transform: uppercase;
    }}
    .amrpc-diag-row {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 6px 2px;
      color: rgba(255,255,255,.72);
    }}
    .amrpc-diag-row strong {{
      color: rgba(255,255,255,.95);
      font-weight: 650;
      text-align: right;
    }}
    .amrpc-dot {{
      width: 7px;
      height: 7px;
      border-radius: 50%;
      margin-right: 7px;
      display: inline-block;
      background: #1ed760;
      box-shadow: 0 0 12px rgba(30,215,96,.75);
    }}
    .amrpc-diag-row[data-state="bad"] .amrpc-dot {{
      background: #ff4d4d;
      box-shadow: 0 0 12px rgba(255,77,77,.75);
    }}
    .amrpc-diag-row[data-state="muted"] .amrpc-dot {{
      background: #8b8f98;
      box-shadow: none;
    }}
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
    <div class="amrpc-menu-head">
      <div class="amrpc-menu-title">Amazon Music RPC</div>
      <div class="amrpc-pill" id="amrpc-menu-pill">...</div>
    </div>
    <div class="amrpc-privacy-row">
      <div>
        <div class="amrpc-row-label">Private session</div>
        <div class="amrpc-row-detail">Hide Discord presence while enabled</div>
      </div>
      <label class="amrpc-toggle">
        <input id="amrpc-privacy-toggle" type="checkbox">
        <span class="amrpc-toggle-track"></span>
        <span class="amrpc-toggle-knob"></span>
      </label>
    </div>
    <div class="amrpc-diag">
      <div class="amrpc-diag-title">Mini diagnostics</div>
      <div id="amrpc-diag-list"></div>
    </div>
  `;
  document.body.appendChild(menu);
  parent.style.display = 'flex';
  parent.style.alignItems = 'center';
  parent.insertBefore(button, searchContainer);
  var label = button.querySelector('#amrpc-status-label');
  var pill = menu.querySelector('#amrpc-menu-pill');
  var toggle = menu.querySelector('#amrpc-privacy-toggle');
  var toggleShell = toggle.parentElement;
  var diagList = menu.querySelector('#amrpc-diag-list');
  var timer = null;
  var privacyBusy = false;
  var privacyRequestId = 0;
  var positionMenu = function () {{
    var rect = button.getBoundingClientRect();
    menu.style.top = Math.round(rect.bottom + 8) + 'px';
    menu.style.right = Math.max(12, Math.round(window.innerWidth - rect.right)) + 'px';
  }};
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
  var render = function (data, options) {{
    options = options || {{}};
    label.textContent = data.statusLabel || 'ERR';
    pill.textContent = data.statusLabel || 'ERR';
    button.dataset.tone = data.tone || 'offline';
    if (!options.keepToggle) {{
      toggle.checked = !!data.privacy;
    }}
    diagList.innerHTML = (data.diagnostics || []).map(function (row) {{
      return '<div class="amrpc-diag-row" data-state="' + escapeHtml(row.state || 'ok') + '"><span><i class="amrpc-dot"></i>' + escapeHtml(row.label) + '</span><strong>' + escapeHtml(row.value) + '</strong></div>';
    }}).join('');
  }};
  var bridge = async function (path) {{
    var joiner = path.indexOf('?') >= 0 ? '&' : '?';
    var response = await fetch(bridgeUrl + path + joiner + 'token=' + encodeURIComponent(token) + '&t=' + Date.now(), {{ method: 'GET', mode: 'cors', cache: 'no-store' }});
    return response.json();
  }};
  var refresh = async function (options) {{
    options = options || {{}};
    try {{
      render(await bridge('/status'), {{ keepToggle: privacyBusy || !!options.keepToggle }});
    }} catch (error) {{
      render({{ statusLabel: 'ERR', tone: 'offline', privacy: false, diagnostics: [{{ label: 'Bridge', value: 'Failed', state: 'bad' }}, {{ label: 'Error', value: String(error && error.message || error), state: 'bad' }}] }}, {{ keepToggle: privacyBusy }});
    }}
  }};
  var openMenu = async function () {{
    positionMenu();
    menu.hidden = false;
    await refresh();
  }};
  var closeMenu = function () {{
    menu.hidden = true;
  }};
  button.onclick = async function (event) {{
    event.preventDefault();
    event.stopPropagation();
    if (event.stopImmediatePropagation) event.stopImmediatePropagation();
    if (menu.hidden) await openMenu();
    else closeMenu();
    return false;
  }};
  toggle.addEventListener('click', function (event) {{
    if (privacyBusy) {{
      event.preventDefault();
      event.stopPropagation();
      if (event.stopImmediatePropagation) event.stopImmediatePropagation();
      return false;
    }}
  }}, true);
  toggle.addEventListener('change', async function (event) {{
    event.stopPropagation();
    if (privacyBusy) {{
      return;
    }}
    var enabled = toggle.checked;
    var requestId = privacyRequestId + 1;
    privacyRequestId = requestId;
    setPrivacyBusy(true);
    label.textContent = '...';
    try {{
      var data = await bridge('/privacy?enabled=' + (enabled ? '1' : '0'));
      if (requestId === privacyRequestId) {{
        render(data);
      }}
    }} catch (error) {{
      if (requestId === privacyRequestId) {{
        await refresh({{ keepToggle: false }});
      }}
    }} finally {{
      if (requestId === privacyRequestId) {{
        setPrivacyBusy(false);
      }}
    }}
  }}, true);
  menu.addEventListener('click', function (event) {{
    event.stopPropagation();
  }});
  document.addEventListener('click', function (event) {{
    if (!menu.hidden && !menu.contains(event.target) && !button.contains(event.target)) closeMenu();
  }});
  window.addEventListener('resize', positionMenu);
  timer = setInterval(refresh, 3000);
  window.__amrpcStatusOverlay = {{ version: overlayVersion, bridgeUrl: bridgeUrl, refresh: refresh, open: openMenu, close: closeMenu, stop: function () {{ clearInterval(timer); closeMenu(); }} }};
  await refresh();
  var rect = button.getBoundingClientRect();
  return {{ ok: true, bridgeUrl: bridgeUrl, text: label.textContent, rect: {{ x: Math.round(rect.x), y: Math.round(rect.y), width: Math.round(rect.width), height: Math.round(rect.height) }} }};
}})()
"""
