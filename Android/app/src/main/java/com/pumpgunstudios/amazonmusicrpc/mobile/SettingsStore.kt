package com.pumpgunstudios.amazonmusicrpc.mobile

import android.content.Context

data class AppSettings(
    val token: String = "",
    val applicationId: String = "1479925587697995857",
    val packageFilters: String = SettingsStore.DEFAULT_PACKAGE_FILTERS,
    val showPaused: Boolean = true,
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

    companion object {
        private const val LEGACY_PACKAGE_FILTERS = "com.amazon.mp3,com.amazon.music"
        const val DEFAULT_PACKAGE_FILTERS = "com.amazon.mp3,com.amazon.music,com.pumpgunstudios.amazonmusicrpc.fakeamazon"
    }
}
