package com.pumpgunstudios.amazonmusicrpc.mobile

import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import okhttp3.OkHttpClient
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONArray
import org.json.JSONObject
import java.net.URI
import java.util.concurrent.ConcurrentHashMap
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
    private val externalAssetCache = ConcurrentHashMap<String, String>()

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
        val connected = withTimeoutOrNull(5000) {
            ready.await()
            true
        } ?: false
        if (!connected) {
            throw IllegalStateException("Discord Gateway timed out")
        }
        socket?.send(presencePayload(track, settings).toString())
    }

    fun clearPresenceBlocking(settings: AppSettings = AppSettings()): Boolean {
        var sent = false
        runBlocking(Dispatchers.IO) {
            withTimeoutOrNull(5000) {
                sendPresence(null, settings)
                delay(250)
                sent = true
            }
        }
        return sent
    }

    fun close() {
        heartbeatJob?.cancel()
        heartbeatJob = null
        socket?.close(1000, "Stopped")
        socket = null
        if (!ready.isCompleted) ready.cancel()
        onStatus("Stopped")
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

    private suspend fun presencePayload(track: TrackInfo?, settings: AppSettings): JSONObject {
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

    private suspend fun activity(track: TrackInfo, settings: AppSettings): JSONObject? {
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
            .put("assets", JSONObject().put("large_text", DiscordPresenceFormat.assetText(album, track.title)))
            .put("instance", true)
        val artworkUri = track.artworkUri?.takeIf { track.hasDiscordArtwork }
        if (artworkUri != null) {
            activity.getJSONObject("assets")
                .put("large_image", resolveDiscordActivityImage(artworkUri, settings))
                .put("large_url", artworkUri)
        }
        if (paused && settings.showPaused) {
            activity.getJSONObject("assets")
                .put("small_image", PAUSE_ICON_URL)
                .put("small_text", "Paused")
        }
        if ((playing || (paused && settings.showPaused)) && track.hasTimeBar) {
            DiscordPresenceFormat.timestamps(track)?.let { (start, end) ->
                activity.put("timestamps", JSONObject().put("start", start).put("end", end))
            }
        }
        return activity
    }

    private suspend fun resolveDiscordActivityImage(imageUrl: String, settings: AppSettings): String {
        discordMediaProxyAsset(imageUrl)?.let { return it }
        val cacheKey = "${settings.applicationId}|$imageUrl"
        externalAssetCache[cacheKey]?.let { return it }
        val resolved = proxyExternalAsset(imageUrl, settings) ?: return imageUrl
        externalAssetCache[cacheKey] = resolved
        return resolved
    }

    private suspend fun proxyExternalAsset(imageUrl: String, settings: AppSettings): String? {
        if (settings.applicationId.isBlank()) return null
        val json = JSONObject().put("urls", JSONArray().put(imageUrl)).toString()
        val request = Request.Builder()
            .url("https://discord.com/api/v10/applications/${settings.applicationId}/external-assets")
            .header("Authorization", token)
            .header("User-Agent", "AmazonMusicRPC-Android-Beta")
            .post(json.toRequestBody("application/json; charset=utf-8".toMediaType()))
            .build()
        return withContext(Dispatchers.IO) {
            try {
                http.newCall(request).execute().use { response ->
                    if (!response.isSuccessful) return@withContext null
                    val data = JSONArray(response.body?.string().orEmpty())
                    val assetPath = data.optJSONObject(0)?.optString("external_asset_path").orEmpty()
                    assetPath.takeIf { it.isNotBlank() }?.let { "mp:$it" }
                }
            } catch (_: Exception) {
                null
            }
        }
    }

    private fun discordMediaProxyAsset(imageUrl: String): String? {
        return try {
            val uri = URI(imageUrl)
            val host = uri.host.orEmpty().lowercase()
            if (host != "media.discordapp.net" && host != "cdn.discordapp.com" && !host.startsWith("images-ext-")) {
                return null
            }
            val path = uri.rawPath?.trimStart('/')?.takeIf { it.isNotBlank() } ?: return null
            val query = uri.rawQuery?.takeIf { it.isNotBlank() }?.let { "?$it" }.orEmpty()
            "mp:$path$query"
        } catch (_: Exception) {
            null
        }
    }

    companion object {
        private const val PAUSE_ICON_URL = "https://raw.githubusercontent.com/eripum9/Amazon-Music-Discord-RPC/master/Images/pause_icon.png"
    }
}
