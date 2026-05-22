package com.pumpgunstudios.amazonmusicrpc.mobile

import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeoutOrNull
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.TimeUnit

class DiscordGatewayClient(
    private val token: String,
    private val scope: CoroutineScope,
    private val onStatus: (String) -> Unit,
) {
    private val http = OkHttpClient.Builder().pingInterval(30, TimeUnit.SECONDS).build()
    private var socket: WebSocket? = null
    private var sequence: Int? = null
    private var heartbeatJob: Job? = null
    private var ready = CompletableDeferred<Unit>()

    fun connect() {
        if (socket != null) return
        ready = CompletableDeferred()
        val request = Request.Builder()
            .url("wss://gateway.discord.gg/?v=10&encoding=json")
            .build()
        socket = http.newWebSocket(request, listener())
        onStatus("Connecting to Discord Gateway")
    }

    suspend fun sendPresence(track: TrackInfo?, settings: AppSettings) {
        connect()
        ready.await()
        socket?.send(presencePayload(track, settings).toString())
    }

    fun clearPresenceBlocking() {
        runBlocking(Dispatchers.IO) {
            withTimeoutOrNull(2500) {
                clearPresence()
            }
        }
    }

    fun close() {
        heartbeatJob?.cancel()
        heartbeatJob = null
        socket?.close(1000, "Stopped")
        socket = null
        if (!ready.isCompleted) ready.cancel()
        onStatus("Stopped")
    }

    private suspend fun clearPresence() {
        val currentSocket = socket ?: return
        if (!ready.isCompleted) {
            withTimeoutOrNull(1500) {
                ready.await()
            } ?: return
        }
        currentSocket.send(presencePayload(null, AppSettings()).toString())
        delay(250)
    }

    private fun listener(): WebSocketListener {
        return object : WebSocketListener() {
            override fun onMessage(webSocket: WebSocket, text: String) {
                handleMessage(text)
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                onStatus("Gateway error: ${t.message ?: "unknown"}")
                socket = null
                if (!ready.isCompleted) ready.cancel()
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                socket = null
                heartbeatJob?.cancel()
                heartbeatJob = null
                onStatus("Gateway closed")
            }
        }
    }

    private fun handleMessage(text: String) {
        val payload = JSONObject(text)
        if (!payload.isNull("s")) {
            sequence = payload.optInt("s")
        }
        when (payload.optInt("op")) {
            10 -> {
                val interval = payload.getJSONObject("d").getLong("heartbeat_interval")
                sendIdentify()
                startHeartbeat(interval)
            }
            0 -> {
                if (payload.optString("t") == "READY") {
                    if (!ready.isCompleted) ready.complete(Unit)
                    onStatus("Connected")
                }
            }
            7 -> reconnect()
            9 -> sendIdentify()
        }
    }

    private fun sendIdentify() {
        val properties = JSONObject()
            .put("os", "Android")
            .put("browser", "Amazon Music RPC")
            .put("device", "Android")
        val data = JSONObject()
            .put("token", token)
            .put("capabilities", 65)
            .put("compress", false)
            .put("large_threshold", 100)
            .put("properties", properties)
        socket?.send(JSONObject().put("op", 2).put("d", data).toString())
    }

    private fun startHeartbeat(intervalMs: Long) {
        heartbeatJob?.cancel()
        heartbeatJob = scope.launch(Dispatchers.IO) {
            while (true) {
                socket?.send(JSONObject().put("op", 1).put("d", sequence ?: JSONObject.NULL).toString())
                delay(intervalMs)
            }
        }
    }

    private fun reconnect() {
        socket?.close(4000, "Reconnect requested")
        socket = null
        connect()
    }

    private fun presencePayload(track: TrackInfo?, settings: AppSettings): JSONObject {
        val data = JSONObject()
            .put("afk", false)
            .put("since", JSONObject.NULL)
            .put("status", "online")
        val activity = if (track == null) null else activity(track, settings)
        if (activity == null) {
            data.put("activities", JSONArray())
        } else {
            data.put("activities", JSONArray().put(activity))
        }
        return JSONObject().put("op", 3).put("d", data)
    }

    private fun activity(track: TrackInfo, settings: AppSettings): JSONObject? {
        val artist = track.artist?.takeIf { it.isNotBlank() }
        val album = track.album?.takeIf { it.isNotBlank() }
        val playing = track.playbackState == android.media.session.PlaybackState.STATE_PLAYING
        val paused = track.playbackState == android.media.session.PlaybackState.STATE_PAUSED
        if (!playing && paused && !settings.showPaused) return null
        val state = if (artist != null) "by $artist" else "Unknown Artist"
        val activity = JSONObject()
            .put("name", "Amazon Music")
            .put("type", 2)
            .put("details", track.title.take(128).ifBlank { "Unknown Title" })
            .put("state", state.take(128))
            .put("application_id", settings.applicationId)
            .put("assets", JSONObject().put("large_text", discordAssetText(album, track.title)))
            .put("instance", true)
        val artworkUri = track.artworkUri?.takeIf { track.hasDiscordArtwork }
        if (artworkUri != null) {
            activity.getJSONObject("assets").put("large_image", artworkUri)
        }
        if (paused && settings.showPaused) {
            activity.getJSONObject("assets")
                .put("small_image", PAUSE_ICON_URL)
                .put("small_text", "Paused")
        }
        if ((playing || (paused && settings.showPaused)) && track.hasTimeBar) {
            val position = track.positionMs ?: 0L
            val duration = track.durationMs ?: 0L
            val start = track.updatedAtMs - position
            val end = start + duration
            activity.put("timestamps", JSONObject().put("start", start).put("end", end))
        }
        return activity
    }

    private fun discordAssetText(albumName: String?, title: String?): String {
        val album = albumName.orEmpty().trim()
        if (album.length >= 2) return album.take(128)
        if (album.isNotEmpty()) return "Album: $album".take(128)
        val track = title.orEmpty().trim()
        if (track.length >= 2) return track.take(128)
        if (track.isNotEmpty()) return "Track: $track".take(128)
        return "Unknown Album"
    }

    companion object {
        private const val PAUSE_ICON_URL = "https://raw.githubusercontent.com/eripum9/Amazon-Music-Discord-RPC/master/Images/pause_icon.png"
    }
}
