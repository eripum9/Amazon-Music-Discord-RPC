# MIT License - Copyright (c) 2026 eripum9

import json
import hmac
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from amazify_compat import AMAZIFY_RPC_BRIDGE_PORT, amazify_bridge_token
from amazon_domains import AMAZON_WEBAPP_HOSTS, exact_https_origin
from config import APP_VERSION


ALLOWED_COMMANDS = {
    "settings",
    "diagnostics",
    "launch_amazon",
    "private",
    "game_mode",
    "wrong_song",
    "toggle_rpc",
    "updates",
}
TOKEN_HEADER = "X-Amazon-Music-RPC-Token"
MAX_REQUEST_BYTES = 16 * 1024


class AmazifyRpcBridge:
    def __init__(self, state_provider, command_handler, port=AMAZIFY_RPC_BRIDGE_PORT, token=None):
        self.state_provider = state_provider
        self.command_handler = command_handler
        self.port = int(port)
        self.httpd = None
        self.thread = None
        self.started_at = time.time()
        self.token = str(token or amazify_bridge_token())

    def start(self):
        if self.httpd:
            return True
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                return

            def do_OPTIONS(self):
                if not self.allowed_origin:
                    self._send_json({"ok": False, "error": "Origin not allowed"}, status=403)
                    return
                self._send_json({"ok": True})

            def do_GET(self):
                if not self.authorized:
                    self._send_json({"ok": False, "error": "Unauthorized"}, status=401)
                    return
                if self.path_only == "/health":
                    self._send_json({"ok": True, "app": "AmazonMusicRPC", "version": APP_VERSION, "port": bridge.port})
                    return
                if self.path_only == "/state":
                    try:
                        data = bridge.state_provider()
                    except Exception as e:
                        self._send_json({"ok": False, "error": str(e)}, status=500)
                        return
                    self._send_json({"ok": True, "app": "AmazonMusicRPC", "version": APP_VERSION, "port": bridge.port, **data})
                    return
                self._send_json({"ok": False, "error": "Not found"}, status=404)

            def do_POST(self):
                if not self.authorized:
                    self._send_json({"ok": False, "error": "Unauthorized"}, status=401)
                    return
                if self.path_only != "/command":
                    self._send_json({"ok": False, "error": "Not found"}, status=404)
                    return
                try:
                    payload = self._read_payload()
                except ValueError as e:
                    self._send_json({"ok": False, "error": str(e)}, status=400)
                    return
                command = str(payload.get("command") or "").strip().lower()
                if command not in ALLOWED_COMMANDS:
                    self._send_json({"ok": False, "error": "Command not allowed"}, status=403)
                    return
                try:
                    bridge.command_handler(command)
                except Exception as e:
                    self._send_json({"ok": False, "error": str(e)}, status=500)
                    return
                self._send_json({"ok": True, "command": command})

            @property
            def path_only(self):
                return self.path.split("?", 1)[0]

            @property
            def allowed_origin(self):
                origin = str(self.headers.get("Origin") or "")
                return exact_https_origin(origin, AMAZON_WEBAPP_HOSTS)

            @property
            def authorized(self):
                supplied = str(self.headers.get(TOKEN_HEADER) or "")
                return bool(supplied and hmac.compare_digest(supplied, bridge.token))

            def _read_payload(self):
                try:
                    length = int(self.headers.get("Content-Length") or "0")
                except ValueError as error:
                    raise ValueError("Invalid Content-Length") from error
                if length < 0 or length > MAX_REQUEST_BYTES:
                    raise ValueError("Request body is too large")
                raw = self.rfile.read(length) if length else b"{}"
                try:
                    data = json.loads(raw.decode("utf-8") or "{}")
                except json.JSONDecodeError as e:
                    raise ValueError("Invalid JSON") from e
                if not isinstance(data, dict):
                    raise ValueError("Payload must be an object")
                return data

            def _send_json(self, data, status=200):
                body = json.dumps(data).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                if self.allowed_origin:
                    self.send_header("Access-Control-Allow-Origin", self.allowed_origin)
                    self.send_header("Vary", "Origin")
                    self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                    self.send_header("Access-Control-Allow-Headers", f"Content-Type, {TOKEN_HEADER}")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

        try:
            self.httpd = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        except OSError:
            return False
        self.thread = threading.Thread(target=self.httpd.serve_forever, name="amazify-rpc-bridge", daemon=False)
        self.thread.start()
        return True

    def stop(self):
        if not self.httpd:
            return
        try:
            self.httpd.shutdown()
            self.httpd.server_close()
        except Exception:
            pass
        self.httpd = None
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(timeout=5)
        self.thread = None


def start_amazify_rpc_bridge(state_provider, command_handler):
    bridge = AmazifyRpcBridge(state_provider, command_handler)
    return bridge if bridge.start() else None
