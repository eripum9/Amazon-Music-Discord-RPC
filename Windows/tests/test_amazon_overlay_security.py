# MIT License - Copyright (c) 2026 eripum9

import inspect

import amazon_status_overlay


class FakeClient:
    def __init__(self):
        self.calls = []

    def request(self, method, params=None):
        self.calls.append((method, params or {}))
        if method == "Page.getFrameTree":
            return {"result": {"frameTree": {"frame": {"id": "main-frame"}}}}
        if method == "Page.createIsolatedWorld":
            return {"result": {"executionContextId": 73}}
        return {"result": {"result": {"value": True}}}


def test_overlay_evaluates_only_in_isolated_world(tmp_path):
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
    overlay._evaluate(client, "1 + 1")
    create = next(params for method, params in client.calls if method == "Page.createIsolatedWorld")
    evaluate = next(params for method, params in client.calls if method == "Runtime.evaluate")
    assert create == {
        "frameId": "main-frame",
        "worldName": amazon_status_overlay.OVERLAY_WORLD_NAME,
        "grantUniveralAccess": False,
    }
    assert evaluate["contextId"] == 73


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
    assert "Page.createIsolatedWorld" in inspect.getsource(
        amazon_status_overlay.AmazonStatusOverlay._ensure_isolated_context
    )
    assert "api.nextAction" not in script
    assert "consume: function" in script


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
