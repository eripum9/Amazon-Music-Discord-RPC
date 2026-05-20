# MIT License - Copyright (c) 2026 eripum9

"""
Read Amazon Music track info from Windows notification center.
Amazon Music sends a toast notification (ToastImageAndText04 template)
with [title, artist, album] every time a new song starts playing.
"""

import asyncio
import re
from winsdk.windows.ui.notifications.management import (
    UserNotificationListener,
    UserNotificationListenerAccessStatus,
)
from winsdk.windows.ui.notifications import NotificationKinds, KnownNotificationBindings

_EXPLICIT_RE = re.compile(r'\s*\[Explicit\]\s*$', re.IGNORECASE)
_AMAZON_TEMPLATE = "ToastImageAndText04"

_last_seen_id = 0


def _strip_explicit(text):
    return _EXPLICIT_RE.sub("", text).strip()


async def _get_latest_amazon_notification():
    """Return the latest Amazon Music notification as (id, title, artist, album) or None."""
    global _last_seen_id

    listener = UserNotificationListener.current
    access = listener.get_access_status()
    if access != UserNotificationListenerAccessStatus.ALLOWED:
        access = await listener.request_access_async()
        if access != UserNotificationListenerAccessStatus.ALLOWED:
            return None

    notifs = await listener.get_notifications_async(NotificationKinds.TOAST)
    count = notifs.size
    if count == 0:
        return None

    for i in range(count - 1, -1, -1):
        n = notifs.get_at(i)
        try:
            binding = n.notification.visual.get_binding(
                KnownNotificationBindings.toast_generic
            )
            if not binding:
                continue

            hints = binding.hints
            if not hints.has_key("hint-originalTemplate"):
                continue
            template = hints.lookup("hint-originalTemplate")
            if template != _AMAZON_TEMPLATE:
                continue

            texts = binding.get_text_elements()
            if texts.size != 3:
                continue

            title = _strip_explicit(texts.get_at(0).text or "")
            artist = texts.get_at(1).text or ""
            album = _strip_explicit(texts.get_at(2).text or "")

            return {
                "id": n.id,
                "title": title,
                "artist": artist,
                "album": album,
            }
        except Exception:
            continue

    return None


async def get_notification_track():
    """Get the latest Amazon Music track from notifications.
    Returns dict with id, title, artist, album or None."""
    return await _get_latest_amazon_notification()


def get_notification_track_sync():
    """Synchronous wrapper."""
    return asyncio.run(get_notification_track())


def is_new_notification(notif_data):
    """Check if this notification is newer than the last one we saw."""
    global _last_seen_id
    if notif_data is None:
        return False
    if notif_data["id"] != _last_seen_id:
        _last_seen_id = notif_data["id"]
        return True
    return False


if __name__ == "__main__":
    track = get_notification_track_sync()
    if track:
        print(f"ID:     {track['id']}")
        print(f"Title:  {track['title']}")
        print(f"Artist: {track['artist']}")
        print(f"Album:  {track['album']}")
        new = is_new_notification(track)
        print(f"New:    {new}")
        track2 = get_notification_track_sync()
        new2 = is_new_notification(track2)
        print(f"New (2nd call): {new2}")
    else:
        print("No Amazon Music notification found.")
        print("Make sure notifications are enabled in Amazon Music settings.")
