package com.pumpgunstudios.amazonmusicrpc.mobile

import android.content.Context
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

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
    val lookup: String,
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

    fun diagnostics(): List<String> {
        return prefs.getString("diagnostics", "")?.lineSequence()
            ?.map { it.trim() }
            ?.filter { it.isNotEmpty() }
            ?.toList()
            .orEmpty()
    }

    fun appendDiagnostic(value: String) {
        val timestamp = SimpleDateFormat("HH:mm:ss", Locale.US).format(Date())
        val entry = "$timestamp ${sanitizeDiagnostic(value)}"
        val next = (diagnostics() + entry).takeLast(MAX_DIAGNOSTICS)
        prefs.edit().putString("diagnostics", next.joinToString("\n")).apply()
    }

    fun clearDiagnostics() {
        prefs.edit().remove("diagnostics").apply()
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
            lookup = prefs.getString("track_lookup", "No active track") ?: "No active track",
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
                .putString("track_lookup", "No active track")
                .apply()
            return
        }
        editor
            .putString("track_title", track.title)
            .putString("track_artist", track.artist.orEmpty())
            .putString("track_album", track.album.orEmpty())
            .putString("track_artwork", artworkText(track))
            .putString("track_timebar", timeBarText(track))
            .putString("track_lookup", lookupText(track))
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

    private fun lookupText(track: TrackInfo): String {
        val source = track.lookupSource ?: return "No lookup result"
        val lookupAlbum = track.lookupAlbum?.takeIf { it.isNotBlank() }
        val metadataAlbum = track.album?.takeIf { it.isNotBlank() }
        return when {
            lookupAlbum == null -> source
            metadataAlbum == null -> "$source album: $lookupAlbum"
            metadataAlbum.trim().equals(lookupAlbum.trim(), ignoreCase = true) -> "$source album match: $lookupAlbum"
            else -> "$source album differs: $lookupAlbum"
        }
    }

    private fun formatMs(value: Long?): String {
        val totalSeconds = ((value ?: 0L) / 1000L).coerceAtLeast(0L)
        val minutes = totalSeconds / 60L
        val seconds = totalSeconds % 60L
        return "$minutes:${seconds.toString().padStart(2, '0')}"
    }

    private fun sanitizeDiagnostic(value: String): String {
        return value
            .replace(Regex("mfa\\.[A-Za-z0-9_-]+"), "mfa.[redacted]")
            .replace(Regex("[A-Za-z0-9_-]{24}\\.[A-Za-z0-9_-]{6}\\.[A-Za-z0-9_-]{20,}"), "[redacted-token]")
            .take(240)
    }

    companion object {
        private const val LEGACY_PACKAGE_FILTERS = "com.amazon.mp3,com.amazon.music"
        private const val MAX_DIAGNOSTICS = 40
        const val DEFAULT_PACKAGE_FILTERS = "com.amazon.mp3,com.amazon.music,com.pumpgunstudios.amazonmusicrpc.fakeamazon"
    }
}
