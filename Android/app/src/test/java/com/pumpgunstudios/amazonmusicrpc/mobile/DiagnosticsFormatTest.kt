package com.pumpgunstudios.amazonmusicrpc.mobile

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class DiagnosticsFormatTest {
    @Test
    fun formatsArtworkTimeBarAndLookupDiagnostics() {
        val track = trackInfo(
            album = "Wolf",
            artworkUri = "https://example.com/art.jpg",
            artworkSource = "Deezer",
            positionMs = 61000L,
            durationMs = 185000L,
            positionSource = "media session",
            durationSource = "Deezer",
            lookupSource = "Deezer",
            lookupAlbum = "Wolf",
        )
        assertEquals("Discord-ready: Deezer", DiagnosticsFormat.artworkText(track))
        assertEquals("Ready: 1:01 / 3:05 (media session, Deezer)", DiagnosticsFormat.timeBarText(track))
        assertEquals("Deezer album match: Wolf", DiagnosticsFormat.lookupText(track))
    }

    @Test
    fun reportsMissingTimeBarParts() {
        assertEquals("Missing position and duration", DiagnosticsFormat.timeBarText(trackInfo(positionMs = null, durationMs = null)))
        assertEquals("Missing position", DiagnosticsFormat.timeBarText(trackInfo(positionMs = null, durationMs = 1000L)))
        assertEquals("Missing duration", DiagnosticsFormat.timeBarText(trackInfo(positionMs = 1000L, durationMs = null)))
    }

    @Test
    fun sanitizesDiscordTokensAndCapsLength() {
        val token = "123456789012345678901234.abcdef.abcdefghijklmnopqrstuvwxyz"
        val value = "mfa.abcdefghijklmnopqrstuvwxyz $token"
        val sanitized = DiagnosticsFormat.sanitizeDiagnostic(value + "x".repeat(300))
        assertTrue("mfa.[redacted]" in sanitized)
        assertTrue("[redacted-token]" in sanitized)
        assertFalse("mfa.abcdefghijklmnopqrstuvwxyz" in sanitized)
        assertFalse(token in sanitized)
        assertTrue(sanitized.length <= 240)
    }
}
