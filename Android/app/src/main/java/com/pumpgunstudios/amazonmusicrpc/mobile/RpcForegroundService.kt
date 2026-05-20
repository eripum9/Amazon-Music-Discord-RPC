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
    private lateinit var settingsStore: SettingsStore
    private lateinit var mediaSessionReader: MediaSessionReader

    override fun onCreate() {
        super.onCreate()
        settingsStore = SettingsStore(this)
        mediaSessionReader = MediaSessionReader(this)
        createNotificationChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_START -> startRpc()
            ACTION_STOP -> stopRpc()
            else -> stopSelf(startId)
        }
        return START_NOT_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        stopRpc()
        super.onDestroy()
    }

    private fun startRpc() {
        startForeground(NOTIFICATION_ID, notification("Waiting for Amazon Music"))
        loopJob?.cancel()
        val settings = settingsStore.load()
        gateway?.close()
        gateway = if (settings.token.isBlank()) {
            settingsStore.setStatus("Metadata test mode")
            updateNotification("Metadata test mode")
            null
        } else {
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
                    mediaSessionReader.read(currentSettings.packageFilters)
                } catch (e: SecurityException) {
                    settingsStore.setStatus("Enable notification access")
                    updateNotification("Enable notification access")
                    null
                } catch (e: Exception) {
                    settingsStore.setStatus("Media read error: ${e.message ?: "unknown"}")
                    null
                }
                val key = track?.stableKey ?: "none"
                val now = System.currentTimeMillis()
                if (key != lastKey || now - lastSentAt > 15000) {
                    try {
                        gateway?.sendPresence(track, currentSettings)
                        lastKey = key
                        lastSentAt = now
                        val prefix = if (currentSettings.token.isBlank()) "Metadata: " else ""
                        val status = if (track == null) "${prefix}No active media" else "$prefix${track.title} • ${track.artist ?: "Unknown artist"}"
                        settingsStore.setStatus(status)
                        updateNotification(status)
                    } catch (e: Exception) {
                        settingsStore.setStatus("RPC error: ${e.message ?: "unknown"}")
                    }
                }
                delay(2000)
            }
        }
    }

    private fun stopRpc() {
        loopJob?.cancel()
        loopJob = null
        gateway?.close()
        gateway = null
        settingsStore.setStatus("Stopped")
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
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
            .setContentText(text)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .build()
    }

    companion object {
        private const val CHANNEL_ID = "amazon_music_rpc"
        private const val NOTIFICATION_ID = 8309
        const val ACTION_START = "com.pumpgunstudios.amazonmusicrpc.mobile.START"
        const val ACTION_STOP = "com.pumpgunstudios.amazonmusicrpc.mobile.STOP"

        fun start(context: Context) {
            val intent = Intent(context, RpcForegroundService::class.java).setAction(ACTION_START)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }

        fun stop(context: Context) {
            context.startService(Intent(context, RpcForegroundService::class.java).setAction(ACTION_STOP))
        }
    }
}
