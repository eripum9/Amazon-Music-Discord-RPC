package com.pumpgunstudios.amazonmusicrpc.mobile

import kotlin.test.Test
import kotlin.test.assertEquals

class AppSettingsTest {
    @Test
    fun defaultFiltersStayProductionOnly() {
        assertEquals("com.amazon.mp3,com.amazon.music", AppSettings().effectivePackageFilters())
        assertEquals(false, AppSettings().externalLookupsEnabled)
    }

    @Test
    fun developerToolsAddCompanionFilterOnce() {
        val settings = AppSettings(developerToolsEnabled = true)
        assertEquals(
            "com.amazon.mp3,com.amazon.music,com.pumpgunstudios.amazonmusicrpc.fakeamazon",
            settings.effectivePackageFilters(),
        )
    }

    @Test
    fun effectiveFiltersTrimAndDeduplicate() {
        val settings = AppSettings(
            packageFilters = " com.amazon.mp3,com.amazon.music,com.amazon.mp3 ",
            developerToolsEnabled = true,
        )
        assertEquals(
            "com.amazon.mp3,com.amazon.music,com.pumpgunstudios.amazonmusicrpc.fakeamazon",
            settings.effectivePackageFilters(),
        )
    }
}
