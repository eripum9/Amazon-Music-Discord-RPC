import sys
import types
from pathlib import Path

WINDOWS_DIR = Path(__file__).resolve().parents[1]
if str(WINDOWS_DIR) not in sys.path:
    sys.path.insert(0, str(WINDOWS_DIR))


def _install_winsdk_stub():
    winsdk = types.ModuleType("winsdk")
    windows = types.ModuleType("winsdk.windows")
    media = types.ModuleType("winsdk.windows.media")
    control = types.ModuleType("winsdk.windows.media.control")
    ui = types.ModuleType("winsdk.windows.ui")
    notifications = types.ModuleType("winsdk.windows.ui.notifications")
    management = types.ModuleType("winsdk.windows.ui.notifications.management")

    class PlaybackStatus:
        PLAYING = object()
        PAUSED = object()
        STOPPED = object()
        CLOSED = object()
        OPENED = object()
        CHANGING = object()

    class SessionManager:
        @staticmethod
        async def request_async():
            return types.SimpleNamespace(get_sessions=lambda: [])

    class UserNotificationListenerAccessStatus:
        ALLOWED = object()

    class _NotificationListener:
        def get_access_status(self):
            return None

        async def request_access_async(self):
            return None

        async def get_notifications_async(self, kind):
            return types.SimpleNamespace(size=0)

    class UserNotificationListener:
        current = _NotificationListener()

    class NotificationKinds:
        TOAST = object()

    class KnownNotificationBindings:
        toast_generic = object()

    control.GlobalSystemMediaTransportControlsSessionManager = SessionManager
    control.GlobalSystemMediaTransportControlsSessionPlaybackStatus = PlaybackStatus
    notifications.NotificationKinds = NotificationKinds
    notifications.KnownNotificationBindings = KnownNotificationBindings
    management.UserNotificationListener = UserNotificationListener
    management.UserNotificationListenerAccessStatus = UserNotificationListenerAccessStatus

    sys.modules.setdefault("winsdk", winsdk)
    sys.modules.setdefault("winsdk.windows", windows)
    sys.modules.setdefault("winsdk.windows.media", media)
    sys.modules.setdefault("winsdk.windows.media.control", control)
    sys.modules.setdefault("winsdk.windows.ui", ui)
    sys.modules.setdefault("winsdk.windows.ui.notifications", notifications)
    sys.modules.setdefault("winsdk.windows.ui.notifications.management", management)


try:
    import winsdk.windows.media.control
except Exception:
    _install_winsdk_stub()
