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
    val developerToolsEnabled: Boolean = false,
    val developerWarningDismissed: Boolean = false,
) {
    fun effectivePackageFilters(): String {
        val filters = if (developerToolsEnabled) "$packageFilters,${SettingsStore.TEST_PACKAGE_FILTER}" else packageFilters
        return filters.split(",")
            .map { it.trim() }
            .filter { it.isNotEmpty() }
            .distinctBy { it.lowercase(Locale.US) }
            .joinToString(",")
    }
}

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
        val developerToolsEnabled = prefs.getBoolean("developer_tools_enabled", false)
        return AppSettings(
            token = prefs.getString("token", "") ?: "",
            applicationId = prefs.getString("application_id", "1479925587697995857") ?: "1479925587697995857",
            packageFilters = when (storedFilters) {
                LEGACY_PACKAGE_FILTERS, LEGACY_TEST_PACKAGE_FILTERS -> DEFAULT_PACKAGE_FILTERS
                else -> storedFilters
            },
            showPaused = prefs.getBoolean("show_paused", true),
            developerToolsEnabled = developerToolsEnabled,
            developerWarningDismissed = prefs.getBoolean("developer_warning_dismissed", false),
        )
    }

    fun save(settings: AppSettings) {
        prefs.edit()
            .putString("token", settings.token.trim())
            .putString("application_id", settings.applicationId.trim())
            .putString("package_filters", settings.packageFilters.trim())
            .putBoolean("show_paused", settings.showPaused)
            .putBoolean("developer_tools_enabled", settings.developerToolsEnabled)
            .putBoolean("developer_warning_dismissed", settings.developerWarningDismissed)
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
        val entry = "$timestamp ${DiagnosticsFormat.sanitizeDiagnostic(value)}"
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
        return DiagnosticsFormat.artworkText(track)
    }

    private fun timeBarText(track: TrackInfo): String {
        return DiagnosticsFormat.timeBarText(track)
    }

    private fun lookupText(track: TrackInfo): String {
        return DiagnosticsFormat.lookupText(track)
    }

    companion object {
        private const val LEGACY_PACKAGE_FILTERS = "com.amazon.mp3,com.amazon.music"
        private const val LEGACY_TEST_PACKAGE_FILTERS = "com.amazon.mp3,com.amazon.music,com.pumpgunstudios.amazonmusicrpc.fakeamazon"
        private const val MAX_DIAGNOSTICS = 40
        const val DEFAULT_PACKAGE_FILTERS = "com.amazon.mp3,com.amazon.music"
        const val TEST_PACKAGE_FILTER = "com.pumpgunstudios.amazonmusicrpc.fakeamazon"
    }
}
