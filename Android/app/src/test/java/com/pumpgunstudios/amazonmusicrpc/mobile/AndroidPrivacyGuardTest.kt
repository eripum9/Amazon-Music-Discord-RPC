package com.pumpgunstudios.amazonmusicrpc.mobile

import java.io.File
import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class AndroidPrivacyGuardTest {
    @Test
    fun mediaSessionReaderDoesNotFallbackToUnfilteredSessionsWhenFiltersExist() {
        val source = sourceText("src/main/java/com/pumpgunstudios/amazonmusicrpc/mobile/MediaSessionReader.kt")
        assertTrue("if (filters.isEmpty())" in source)
        assertTrue("filters.any { filter -> controller.packageName.equals(filter, true) }" in source)
        assertFalse("} ?: sessions.firstOrNull { controller ->\n            controller.metadata" in source)
    }

    @Test
    fun externalLookupsAndForegroundNotificationArePrivacyControlled() {
        val service = sourceText("src/main/java/com/pumpgunstudios/amazonmusicrpc/mobile/RpcForegroundService.kt")
        val settings = sourceText("src/main/java/com/pumpgunstudios/amazonmusicrpc/mobile/SettingsStore.kt")
        val secure = sourceText("src/main/java/com/pumpgunstudios/amazonmusicrpc/mobile/SecureStringStore.kt")
        assertTrue("currentSettings.externalLookupsEnabled" in service)
        assertTrue("metadataLookup.enrich(it)" in service)
        assertTrue(".setContentText(getString(R.string.rpc_notification_text))" in service)
        assertTrue(".setVisibility(NotificationCompat.VISIBILITY_PRIVATE)" in service)
        assertTrue("val externalLookupsEnabled: Boolean = false" in settings)
        assertTrue("\"external_lookups_enabled\"" in settings)
        assertTrue("SecureStringStore.protect(settings.token.trim())" in settings)
        assertTrue("SecureStringStore.unprotect(prefs.getString(\"token\", \"\") ?: \"\")" in settings)
        assertTrue("AndroidKeyStore" in secure)
    }

    private fun sourceText(path: String): String {
        val candidates = listOf(File(path), File("app/$path"))
        return candidates.first { it.exists() }.readText()
    }
}
