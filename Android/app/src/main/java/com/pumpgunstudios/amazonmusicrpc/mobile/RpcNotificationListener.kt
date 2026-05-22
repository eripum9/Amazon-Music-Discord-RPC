package com.pumpgunstudios.amazonmusicrpc.mobile

import android.app.Notification
import android.os.Build
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import java.util.concurrent.ConcurrentHashMap

data class NotificationArtwork(
    val hasArtwork: Boolean,
    val source: String?,
    val positionMs: Long?,
    val durationMs: Long?,
    val updatedAtMs: Long,
)

class RpcNotificationListener : NotificationListenerService() {
    override fun onListenerConnected() {
        activeNotifications?.forEach { updateSnapshot(it) }
    }

    override fun onNotificationPosted(sbn: StatusBarNotification?) {
        if (sbn != null) {
            updateSnapshot(sbn)
        }
    }

    override fun onNotificationRemoved(sbn: StatusBarNotification?) {
        if (sbn != null) {
            snapshots.remove(sbn.packageName)
        }
    }

    private fun updateSnapshot(sbn: StatusBarNotification) {
        val notification = sbn.notification ?: return
        val extras = notification.extras
        val source = when {
            Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && notification.getLargeIcon() != null -> "notification large icon"
            extras?.containsKey("android.largeIcon") == true -> "notification extras large icon"
            extras?.containsKey(Notification.EXTRA_PICTURE) == true -> "notification picture"
            else -> null
        }
        val progress = extras?.getInt(Notification.EXTRA_PROGRESS, -1)?.takeIf { it >= 0 }?.toLong()
        val progressMax = extras?.getInt(Notification.EXTRA_PROGRESS_MAX, -1)?.takeIf { it > 0 }?.toLong()
        snapshots[sbn.packageName] = NotificationArtwork(
            hasArtwork = source != null,
            source = source,
            positionMs = progress,
            durationMs = progressMax,
            updatedAtMs = System.currentTimeMillis(),
        )
    }

    companion object {
        private val snapshots = ConcurrentHashMap<String, NotificationArtwork>()

        fun artworkFor(packageName: String): NotificationArtwork? {
            return snapshots[packageName]
        }
    }
}
