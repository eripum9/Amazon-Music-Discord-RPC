package com.pumpgunstudios.amazonmusicrpc.mobile

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class MetadataTextTest {
    @Test
    fun cleansTitlesAndArtistsForLookups() {
        assertEquals("Noid", MetadataText.cleanTitle("Noid [Explicit]"))
        assertEquals("Song", MetadataText.cleanTitle("Song (feat. Artist)"))
        assertEquals("Tyler, The Creator", MetadataText.cleanArtist("Tyler, The Creator feat. Someone"))
    }

    @Test
    fun matchesNormalizedTrackAndArtist() {
        assertTrue(MetadataText.matchesResult("WOLF", "Tyler, The Creator", "Wolf", "Tyler The Creator"))
        assertTrue(MetadataText.matchesResult("Noid", "Wrong Artist", "Noid", ""))
        assertFalse(MetadataText.matchesResult("Rusty", "Tyler, The Creator", "Noid", "Tyler, The Creator"))
        assertFalse(MetadataText.matchesResult("Noid", "Other", "Noid", "Tyler, The Creator"))
    }

    @Test
    fun scoresAlbumHintsAndUpscalesItunesArt() {
        assertTrue(MetadataText.albumScore("Wolf", "Wolf", 0) > MetadataText.albumScore("Other", "Wolf", 0))
        assertTrue(MetadataText.albumScore("Chromakopia+", "Chromakopia", 0) > MetadataText.albumScore("", "Chromakopia", 0))
        assertEquals("https://example.com/600x600bb.jpg", MetadataText.upscaleItunesArtwork("https://example.com/100x100bb.jpg"))
    }
}
