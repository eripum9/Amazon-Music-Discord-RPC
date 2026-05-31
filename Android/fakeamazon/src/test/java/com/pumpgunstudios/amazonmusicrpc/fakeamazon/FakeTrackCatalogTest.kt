package com.pumpgunstudios.amazonmusicrpc.fakeamazon

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class FakeTrackCatalogTest {
    @Test
    fun includesExpectedRegressionTracks() {
        val byTitle = fakeTracks.associateBy { it.title }
        assertEquals("Wolf", byTitle.getValue("WOLF").album)
        assertEquals("Wolf", byTitle.getValue("Rusty").album)
        assertEquals("Chromakopia+", byTitle.getValue("Noid").album)
        assertTrue(fakeTracks.all { it.durationMs > 0L })
        assertTrue(fakeTracks.all { it.artist == "Tyler, The Creator" })
    }
}
