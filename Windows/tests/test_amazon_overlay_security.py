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
