package com.pumpgunstudios.amazonmusicrpc.mobile

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

class RpcForegroundService : Service() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var loopJob: Job? = null
    private var gateway: DiscordGatewayClient? = null
    private var shutdownHandled = false
    private lateinit var settingsStore: SettingsStore
    private lateinit var mediaSessionReader: MediaSessionReader
    private lateinit var metadataLookup: MetadataLookup

    override fun onCreate() {
        super.onCreate()
        settingsStore = SettingsStore(this)
        mediaSessionReader = MediaSessionReader(this)
        metadataLookup = MetadataLookup()
        createNotificationChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_START -> startRpc()
            ACTION_STOP -> stopRpc()
            ACTION_CLEAR -> clearActivityAndStop()
            else -> stopSelf(startId)
        }
        return START_NOT_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onTaskRemoved(rootIntent: Intent?) {
        settingsStore.appendDiagnostic("Task removed; stopping RPC")
        stopRpc()
        super.onTaskRemoved(rootIntent)
    }

    override fun onDestroy() {
        stopRpc()
        super.onDestroy()
    }

    private fun startRpc() {
        shutdownHandled = false
        startForeground(NOTIFICATION_ID, notification("Waiting for Amazon Music"))
        settingsStore.setServiceRunning(true)
        settingsStore.appendDiagnostic("RPC service started")
        loopJob?.cancel()
        val settings = settingsStore.load()
        gateway?.close()
        gateway = if (settings.token.isBlank()) {
            settingsStore.setStatus("Local preview mode")
            settingsStore.appendDiagnostic("Started in local preview mode")
            updateNotification("Local preview mode")
            null
        } else {
            settingsStore.appendDiagnostic("Connecting to Discord Gateway")
            DiscordGatewayClient(settings.token, scope) { status ->
                settingsStore.setStatus(status)
                updateNotification(status)
            }
        }
        loopJob = scope.launch {
            var lastKey = ""
            var lastSentAt = 0L
            while (isActive) {
                val currentSettings = settingsStore.load()
                val track = try {
                    mediaSessionReader.read(currentSettings.effectivePackageFilters())
                } catch (e: SecurityException) {
                    settingsStore.setStatus("Enable notification access")
                    updateNotification("Enable notification access")
                    null
                } catch (e: Exception) {
                    settingsStore.setStatus("Media read error: ${e.message ?: "unknown"}")
                    null
                }?.let {
                    if (currentSettings.externalLookupsEnabled) metadataLookup.enrich(it) else it
                }
                settingsStore.setTrackDiagnostics(track)
                val key = track?.stableKey ?: "none"
                val now = System.currentTimeMillis()
                if (key != lastKey || now - lastSentAt > 15000) {
                    try {
                        if (key != lastKey) {
                            settingsStore.appendDiagnostic(track.diagnosticText(currentSettings.token.isBlank()))
                            settingsStore.appendDiagnostic(track.artworkDiagnosticText())
                        }
                        gateway?.sendPresence(track, currentSettings)
                        lastKey = key
                        lastSentAt = now
                        val prefix = if (currentSettings.token.isBlank()) "Metadata: " else ""
                        val status = if (track == null) "${prefix}No active media" else "$prefix${track.title} • ${track.artist ?: "Unknown artist"} • ${track.album ?: "Unknown album"}"
                        settingsStore.setStatus(status)
                        updateNotification(status)
                    } catch (e: Exception) {
                        settingsStore.setStatus("RPC error: ${e.message ?: "unknown"}")
                        settingsStore.appendDiagnostic("RPC error: ${e.message ?: "unknown"}")
                    }
                }
                delay(2000)
            }
        }
    }

    private fun stopRpc() {
        if (shutdownHandled) return
        shutdownHandled = true
        loopJob?.cancel()
        loopJob = null
        val settings = settingsStore.load()
        val cleared = clearDiscordActivity(settings)
        gateway?.close()
        gateway = null
        settingsStore.setServiceRunning(false)
        settingsStore.setTrackDiagnostics(null)
        settingsStore.setStatus("Stopped")
        settingsStore.appendDiagnostic(if (cleared) "RPC stopped and Discord activity cleared" else "RPC stopped")
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    private fun clearActivityAndStop() {
        if (shutdownHandled) return
        shutdownHandled = true
        startForeground(NOTIFICATION_ID, notification("Clearing Discord activity"))
        settingsStore.appendDiagnostic("Clear activity requested")
        loopJob?.cancel()
        loopJob = null
        val settings = settingsStore.load()
        scope.launch {
            val cleared = clearDiscordActivity(settings)
            gateway?.close()
            gateway = null
            settingsStore.setServiceRunning(false)
            settingsStore.setTrackDiagnostics(null)
            val status = when {
                settings.token.isBlank() -> "No Discord token saved"
                cleared -> "Discord activity cleared"
                else -> "Discord activity clear failed"
            }
            settingsStore.setStatus(status)
            settingsStore.appendDiagnostic(status)
            updateNotification(status)
            delay(600)
            stopForeground(STOP_FOREGROUND_REMOVE)
            stopSelf()
        }
    }

    private fun clearDiscordActivity(settings: AppSettings): Boolean {
        if (settings.token.isBlank()) return false
        val existingClient = gateway
        val client = existingClient ?: DiscordGatewayClient(settings.token, scope) { status ->
            settingsStore.setStatus(status)
            updateNotification(status)
        }
        return try {
            client.clearPresenceBlocking(settings)
        } catch (e: Exception) {
            settingsStore.appendDiagnostic("Clear activity failed: ${e.message ?: "unknown"}")
            false
        } finally {
            if (existingClient == null) {
                client.close()
            }
        }
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(CHANNEL_ID, getString(R.string.rpc_channel_name), NotificationManager.IMPORTANCE_LOW)
            getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
        }
    }

    private fun updateNotification(text: String) {
        val manager = getSystemService(NotificationManager::class.java)
        manager.notify(NOTIFICATION_ID, notification(text))
    }

    private fun notification(text: String): Notification {
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_launcher)
            .setContentTitle(getString(R.string.rpc_notification_title))
            .setContentText(getString(R.string.rpc_notification_text))
            .setVisibility(NotificationCompat.VISIBILITY_PRIVATE)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .build()
    }

    companion object {
        private const val CHANNEL_ID = "amazon_music_rpc"
        private const val NOTIFICATION_ID = 8309
        const val ACTION_START = "com.pumpgunstudios.amazonmusicrpc.mobile.START"
        const val ACTION_STOP = "com.pumpgunstudios.amazonmusicrpc.mobile.STOP"
        const val ACTION_CLEAR = "com.pumpgunstudios.amazonmusicrpc.mobile.CLEAR"

        fun start(context: Context) {
            val intent = Intent(context, RpcForegroundService::class.java).setAction(ACTION_START)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }

        fun stop(context: Context) {
            try {
                context.startService(Intent(context, RpcForegroundService::class.java).setAction(ACTION_STOP))
            } catch (_: IllegalStateException) {
            }
        }

        fun clearActivity(context: Context) {
            val intent = Intent(context, RpcForegroundService::class.java).setAction(ACTION_CLEAR)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }
    }
}

private fun TrackInfo?.diagnosticText(metadataOnly: Boolean): String {
    if (this == null) return if (metadataOnly) "Local preview: no active media" else "No active media"
    val artistText = artist?.takeIf { it.isNotBlank() } ?: "Unknown artist"
    val albumText = album?.takeIf { it.isNotBlank() } ?: "Unknown album"
    val prefix = if (metadataOnly) "Local preview" else "Presence"
    return "$prefix track: $title - $artistText - $albumText"
}

private fun TrackInfo?.artworkDiagnosticText(): String {
    if (this == null) return "Presence image: none"
    val uri = artworkUri
    if (uri.isNullOrBlank()) return "Presence image: none"
    val host = runCatching { android.net.Uri.parse(uri).host }.getOrNull().orEmpty()
    val source = artworkSource ?: "unknown source"
    return if (hasDiscordArtwork) {
        "Presence image: $source ${host.ifBlank { "URL" }}"
    } else {
        "Presence image local-only: $source"
    }
}
