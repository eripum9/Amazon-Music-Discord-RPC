package com.pumpgunstudios.amazonmusicrpc.mobile

import android.content.Context

data class AppSettings(
    val token: String = "",
    val applicationId: String = "1479925587697995857",
    val packageFilters: String = SettingsStore.DEFAULT_PACKAGE_FILTERS,
    val showPaused: Boolean = true,
)

data class TrackDiagnostics(
    val title: String,
    val artist: String,
    val album: String,
    val artwork: String,
    val timeBar: String,
)

class SettingsStore(context: Context) {
    private val prefs = context.getSharedPreferences("amazon_music_rpc", Context.MODE_PRIVATE)

    fun load(): AppSettings {
        val storedFilters = prefs.getString("package_filters", DEFAULT_PACKAGE_FILTERS) ?: DEFAULT_PACKAGE_FILTERS
        return AppSettings(
            token = prefs.getString("token", "") ?: "",
            applicationId = prefs.getString("application_id", "1479925587697995857") ?: "1479925587697995857",
            packageFilters = if (storedFilters == LEGACY_PACKAGE_FILTERS) DEFAULT_PACKAGE_FILTERS else storedFilters,
            showPaused = prefs.getBoolean("show_paused", true),
        )
    }

    fun save(settings: AppSettings) {
        prefs.edit()
            .putString("token", settings.token.trim())
            .putString("application_id", settings.applicationId.trim())
            .putString("package_filters", settings.packageFilters.trim())
            .putBoolean("show_paused", settings.showPaused)
            .apply()
    }

    fun status(): String {
        return prefs.getString("status", "Stopped") ?: "Stopped"
    }

    fun setStatus(value: String) {
        prefs.edit().putString("status", value).apply()
    }

    fun serviceRunning(): Boolean {
        return prefs.getBoolean("service_running", false)
    }

    fun setServiceRunning(value: Boolean) {
        prefs.edit().putBoolean("service_running", value).apply()
    }

    fun trackDiagnostics(): TrackDiagnostics {
        return TrackDiagnostics(
            title = prefs.getString("track_title", "") ?: "",
            artist = prefs.getString("track_artist", "") ?: "",
            album = prefs.getString("track_album", "") ?: "",
            artwork = prefs.getString("track_artwork", "No active track") ?: "No active track",
            timeBar = prefs.getString("track_timebar", "No active track") ?: "No active track",
        )
    }

    fun setTrackDiagnostics(track: TrackInfo?) {
        val editor = prefs.edit()
        if (track == null) {
            editor
                .putString("track_title", "")
                .putString("track_artist", "")
                .putString("track_album", "")
                .putString("track_artwork", "No active track")
                .putString("track_timebar", "No active track")
                .apply()
            return
        }
        editor
            .putString("track_title", track.title)
            .putString("track_artist", track.artist.orEmpty())
            .putString("track_album", track.album.orEmpty())
            .putString("track_artwork", artworkText(track))
            .putString("track_timebar", timeBarText(track))
            .apply()
    }

    private fun artworkText(track: TrackInfo): String {
        return when {
            track.hasDiscordArtwork -> "Discord-ready: ${track.artworkSource ?: "URL"}"
            track.hasArtwork -> "Local only: ${track.artworkSource}"
            else -> "Not exposed"
        }
    }

    private fun timeBarText(track: TrackInfo): String {
        if (!track.hasTimeBar) {
            return when {
                track.positionMs == null && track.durationMs == null -> "Missing position and duration"
                track.positionMs == null -> "Missing position"
                else -> "Missing duration"
            }
        }
        val positionSource = track.positionSource ?: "unknown position"
        val durationSource = track.durationSource ?: "unknown duration"
        return "Ready: ${formatMs(track.positionMs)} / ${formatMs(track.durationMs)} ($positionSource, $durationSource)"
    }

    private fun formatMs(value: Long?): String {
        val totalSeconds = ((value ?: 0L) / 1000L).coerceAtLeast(0L)
        val minutes = totalSeconds / 60L
        val seconds = totalSeconds % 60L
        return "$minutes:${seconds.toString().padStart(2, '0')}"
    }

    companion object {
        private const val LEGACY_PACKAGE_FILTERS = "com.amazon.mp3,com.amazon.music"
        const val DEFAULT_PACKAGE_FILTERS = "com.amazon.mp3,com.amazon.music,com.pumpgunstudios.amazonmusicrpc.fakeamazon"
    }
}
