# MIT License - Copyright (c) 2026 eripum9

import amazon_status_overlay


class FakeClient:
    def __init__(self):
        self.calls = []

    def request(self, method, params=None):
        self.calls.append((method, params or {}))
        if method == "Runtime.evaluate" and not (params or {}).get("returnByValue", True):
            return {"result": {"result": {"objectId": "overlay-api"}}}
        if method == "Runtime.callFunctionOn" and "Boolean(this.ok)" in (params or {}).get("functionDeclaration", ""):
            return {"result": {"result": {"value": {"ok": True, "version": amazon_status_overlay.OVERLAY_VERSION}}}}
        return {"result": {"result": {"value": True}}}


def test_overlay_uses_private_main_world_object_without_isolated_world(tmp_path):
    icon = tmp_path / "icon.png"
    icon.write_bytes(b"icon")
    overlay = amazon_status_overlay.AmazonStatusOverlay(
        str(icon),
        lambda: {},
        lambda: {},
        lambda: True,
        lambda enabled: None,
    )
    client = FakeClient()
    overlay._inject(client)
    evaluate = next(params for method, params in client.calls if method == "Runtime.evaluate")
    assert evaluate["returnByValue"] is False
    assert "contextId" not in evaluate
    assert overlay._api_object_id == "overlay-api"
    assert all(method not in {"Page.enable", "Page.createIsolatedWorld"} for method, _ in client.calls)
    assert any(method == "Runtime.callFunctionOn" for method, _ in client.calls)


def test_overlay_privacy_action_requires_trusted_user_event(tmp_path):
    icon = tmp_path / "icon.png"
    icon.write_bytes(b"icon")
    overlay = amazon_status_overlay.AmazonStatusOverlay(
        str(icon),
        lambda: {},
        lambda: {},
        lambda: True,
        lambda enabled: None,
    )
    script = overlay._script()
    assert "event.isTrusted" in script
    assert "window.__amrpcStatusOverlay" not in script
    assert "api.nextAction" not in script
    assert "consume: function" in script


def test_overlay_mounts_outside_amazon_owned_layout(tmp_path):
    icon = tmp_path / "icon.png"
    icon.write_bytes(b"icon")
    overlay = amazon_status_overlay.AmazonStatusOverlay(
        str(icon),
        lambda: {},
        lambda: {},
        lambda: True,
        lambda enabled: None,
    )
    script = overlay._script()
    assert "document.body.appendChild(button)" in script
    assert "position: fixed" in script
    assert "parent.style" not in script
    assert "parent.insertBefore" not in script


def test_overlay_does_not_attach_during_amazon_splash(monkeypatch, tmp_path):
    icon = tmp_path / "icon.png"
    icon.write_bytes(b"icon")
    overlay = amazon_status_overlay.AmazonStatusOverlay(
        str(icon),
        lambda: {},
        lambda: {},
        lambda: True,
        lambda enabled: None,
    )

    class StopAfterWait:
        def __init__(self):
            self.done = False

        def is_set(self):
            return self.done

        def wait(self, timeout):
            self.done = True

        def set(self):
            self.done = True

    overlay._stop_event = StopAfterWait()
    monkeypatch.setattr(
        amazon_status_overlay,
        "_page_target",
        lambda: {"id": "page", "webSocketDebuggerUrl": "ws://127.0.0.1:52856/devtools/page/page"},
    )
    monkeypatch.setattr(amazon_status_overlay, "get_devtools_port", lambda create=False: 52856)
    monkeypatch.setattr(
        amazon_status_overlay,
        "_page_boot_state",
        lambda port: {"ready": False, "status": "loading", "splash_visible": True},
    )
    monkeypatch.setattr(
        amazon_status_overlay,
        "_CdpSocket",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Overlay attached during splash")),
    )
    overlay._run()
    assert overlay._client is None


def test_overlay_requires_stable_ready_page_before_attach(monkeypatch, tmp_path):
    icon = tmp_path / "icon.png"
    icon.write_bytes(b"icon")
    overlay = amazon_status_overlay.AmazonStatusOverlay(
        str(icon),
        lambda: {},
        lambda: {},
        lambda: True,
        lambda enabled: None,
    )

    class StopAfterWaits:
        def __init__(self, limit):
            self.limit = limit
            self.waits = 0

        def is_set(self):
            return self.waits >= self.limit

        def wait(self, timeout):
            self.waits += 1

        def set(self):
            self.waits = self.limit

    created = []

    def create_client(*args, **kwargs):
        client = FakeClient()
        created.append((overlay._stop_event.waits, client))
        return client

    overlay._stop_event = StopAfterWaits(amazon_status_overlay.OVERLAY_READY_STABLE_POLLS)
    monkeypatch.setattr(
        amazon_status_overlay,
        "_page_target",
        lambda: {"id": "page", "webSocketDebuggerUrl": "ws://127.0.0.1:52856/devtools/page/page"},
    )
    monkeypatch.setattr(amazon_status_overlay, "get_devtools_port", lambda create=False: 52856)
    monkeypatch.setattr(
        amazon_status_overlay,
        "_page_boot_state",
        lambda port: {"ready": True, "status": "ready", "splash_visible": False},
    )
    monkeypatch.setattr(amazon_status_overlay, "_CdpSocket", create_client)
    overlay._run()
    assert len(created) == 1
    assert created[0][0] == amazon_status_overlay.OVERLAY_READY_STABLE_POLLS - 1
    assert overlay._client is created[0][1]
